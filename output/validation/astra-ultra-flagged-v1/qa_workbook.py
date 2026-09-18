"""Read-only verification of the flagged-case AI-review XLSX export.

Uses only the bundled Python standard library. It does not open Excel, calculate
formulas, alter the workbook, classify cases, or inspect candidate outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
STRING_TYPES = {"s", "inlineStr", "str"}
LABEL_FIELDS = (
    "intent", "secondary_intent", "should_escalate",
    "escalation_reason_code", "sentiment",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def column_number(name: str) -> int:
    result = 0
    for letter in name:
        result = result * 26 + ord(letter) - 64
    return result


def address_parts(address: str) -> tuple[int, int]:
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", address)
    if not match:
        raise ValueError(f"Invalid cell address: {address}")
    return column_number(match[1]), int(match[2])


def contains_address(reference: str, address: str) -> bool:
    col, row = address_parts(address)
    for area in reference.split():
        corners = area.split(":")
        first = address_parts(corners[0])
        last = address_parts(corners[-1])
        if first[0] <= col <= last[0] and first[1] <= row <= last[1]:
            return True
    return False


def xml_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return "".join(node.text or "" for node in element.findall(".//m:t", NS))


@dataclass(frozen=True)
class Cell:
    address: str
    data_type: str | None
    value: str | bool | int | float | None
    formula: str | None


class XlsxReader:
    """Decode actual saved cells and controls without any spreadsheet engine."""

    def __init__(self, path: Path):
        self.path = path
        self.sheets: dict[str, dict] = {}
        self.external_relationships: list[dict] = []
        with zipfile.ZipFile(path) as archive:
            self.parts = set(archive.namelist())
            corrupt_part = archive.testzip()
            if corrupt_part:
                raise ValueError(f"ZIP CRC failure: {corrupt_part}")
            shared = []
            if "xl/sharedStrings.xml" in self.parts:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [xml_text(item) for item in root.findall("m:si", NS)]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = self._relationships(archive, "xl/workbook.xml")
            for sheet in workbook.findall("m:sheets/m:sheet", NS):
                part = relationships[sheet.attrib[f"{{{NS['r']}}}id"]]
                root = ET.fromstring(archive.read(part))
                cells = {}
                for node in root.findall("m:sheetData/m:row/m:c", NS):
                    data_type = node.get("t")
                    value_node = node.find("m:v", NS)
                    raw = value_node.text if value_node is not None else None
                    if data_type == "s":
                        value = shared[int(raw)] if raw is not None else ""
                    elif data_type == "inlineStr":
                        value = xml_text(node.find("m:is", NS))
                    elif data_type == "b":
                        value = raw == "1" if raw is not None else None
                    elif data_type in {"str", "e", "d"}:
                        value = raw
                    elif raw is None:
                        value = None
                    else:
                        value = float(raw) if any(c in raw for c in ".eE") else int(raw)
                    formula_node = node.find("m:f", NS)
                    formula = None if formula_node is None else (formula_node.text or "")
                    cells[node.attrib["r"]] = Cell(node.attrib["r"], data_type, value, formula)
                sheet_relationships = self._relationships(archive, part)
                tables = []
                for table_part in root.findall("m:tableParts/m:tablePart", NS):
                    target = sheet_relationships[table_part.attrib[f"{{{NS['r']}}}id"]]
                    tables.append(ET.fromstring(archive.read(target)))
                self.sheets[sheet.attrib["name"]] = {
                    "part": part,
                    "root": root,
                    "cells": cells,
                    "tables": tables,
                    "state": sheet.get("state", "visible"),
                }
            for part in sorted(self.parts):
                if part.endswith(".rels"):
                    root = ET.fromstring(archive.read(part))
                    for rel in root.findall("p:Relationship", NS):
                        if rel.get("TargetMode") == "External":
                            self.external_relationships.append({"part": part, **rel.attrib})

    @staticmethod
    def _relationships(archive: zipfile.ZipFile, part: str) -> dict[str, str]:
        directory, filename = posixpath.split(part)
        rel_part = posixpath.join(directory, "_rels", filename + ".rels")
        if rel_part not in archive.namelist():
            return {}
        root = ET.fromstring(archive.read(rel_part))
        result = {}
        for node in root.findall("p:Relationship", NS):
            target = node.attrib["Target"]
            result[node.attrib["Id"]] = (
                target.lstrip("/") if target.startswith("/")
                else posixpath.normpath(posixpath.join(directory, target))
            )
        return result

    def cell(self, sheet: str, address: str) -> Cell:
        return self.sheets[sheet]["cells"].get(address, Cell(address, None, None, None))


class Audit:
    def __init__(self, workbook: XlsxReader):
        self.workbook = workbook
        self.errors: list[str] = []
        self.checks = Counter()

    def check(self, condition: bool, category: str, message: str) -> None:
        self.checks[category] += 1
        if not condition:
            self.errors.append(message)

    def equal(self, sheet: str, address: str, expected, category: str) -> None:
        cell = self.workbook.cell(sheet, address)
        actual = cell.value
        if expected in (None, "") and not isinstance(expected, bool):
            matches = actual in (None, "")
        else:
            matches = actual == expected and type(actual) is type(expected)
        self.check(matches, category, f"{sheet}!{address}: {category} mismatch")
        self.check(cell.formula is None, "literal_cells", f"{sheet}!{address}: unexpected formula")
        if isinstance(expected, str) and expected:
            self.check(cell.data_type in STRING_TYPES, "literal_string_types", f"{sheet}!{address}: text not stored as literal string")

    def check_no_cell_formulas_or_errors(self) -> None:
        for name, sheet in self.workbook.sheets.items():
            for address, cell in sheet["cells"].items():
                self.check(cell.formula is None, "formula_scan", f"{name}!{address}: worksheet formula present")
                self.check(cell.data_type != "e", "error_scan", f"{name}!{address}: worksheet error cell present")


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def load_inputs(base: Path) -> tuple[dict, dict[str, dict]]:
    manifest = json.loads((base / "MANIFEST.json").read_text(encoding="utf-8-sig"))
    inputs = {}
    for batch in manifest["batches"]:
        path = base / batch["input"]
        if sha256(path) != batch["sha256"]:
            raise ValueError(f"Input checksum differs from manifest: {batch['input']}")
        records = read_jsonl(path)
        if [record["id"] for record in records] != batch["ids"]:
            raise ValueError(f"Input IDs/order differ from manifest: {batch['input']}")
        for record in records:
            if record["id"] in inputs:
                raise ValueError(f"Duplicate input ID: {record['id']}")
            inputs[record["id"]] = record
    if len(inputs) != 55:
        raise ValueError("Expected exactly 55 flagged source records")
    return manifest, inputs


HEADERS = [
    "Case ID", "Source text", "Scenario setup", "AI disposition",
    "Changed label fields", "Human review status", "Prior intent", "Ultra intent",
    "Prior secondary intent", "Ultra secondary intent", "Prior should escalate",
    "Ultra should escalate", "Prior escalation reason", "Ultra escalation reason",
    "Prior sentiment", "Ultra sentiment", "Ultra rationale", "Question resolution",
    "Remaining question", "Requires human decision", "Ultra confidence",
    "Flagged question", "Human reviewer", "Human reviewed at", "Human notes",
    "Prior rationale", "Prior confidence", "Acceptance review findings",
    "Review source", "Model", "Reasoning effort", "AI reviewer",
    "AI reviewed at (UTC)", "Human verified",
]
SCHEMAS = [("Confirmation", "confirmation", 35), ("Challenge", "challenge", 20)]
STATUSES = ["Pending", "Approved", "Corrected", "Needs discussion"]
SOURCE_FIELDS = (
    "id", "partition", "text", "scenario_setup", "prior_ai_proposal",
    "prior_rationale", "prior_confidence", "flagged_question",
    "acceptance_review_findings",
)


def pretty_json(value) -> str:
    """Match the documented cell presentation, retaining object key order."""
    if value is None or value == {} or value == []:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def expected_row(record: dict) -> list:
    prior = record["prior_ai_proposal"]
    review = record["ultra_review"]
    labels = review["labels"]
    return [
        record["id"], record["text"], pretty_json(record["scenario_setup"]),
        review["disposition"], ", ".join(review["changed_fields"]),
        record["human_review_status"], prior["intent"], labels["intent"],
        prior["secondary_intent"], labels["secondary_intent"],
        prior["should_escalate"], labels["should_escalate"],
        prior["escalation_reason_code"], labels["escalation_reason_code"],
        prior["sentiment"], labels["sentiment"], review["rationale"],
        review["question_resolution"], review["remaining_question"],
        review["requires_human_decision"], review["confidence"],
        record["flagged_question"], record["human_reviewer"],
        record["human_reviewed_at"], record["human_notes"],
        record["prior_rationale"], record["prior_confidence"],
        json.dumps(record["acceptance_review_findings"], ensure_ascii=False, separators=(",", ":")) if record["acceptance_review_findings"] else "",
        review["review_source"], review["model"], review["reasoning_effort"],
        review["reviewer"], review["reviewed_at"], review["human_verified"],
    ]


def exact_data_equal(left, right) -> bool:
    """JSON equality with distinct booleans/numbers and exact string content."""
    return json.dumps(left, sort_keys=True, ensure_ascii=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=False
    )


def verify_controls(audit: Audit, name: str, count: int) -> dict:
    sheet = audit.workbook.sheets[name]
    root = sheet["root"]
    first, last = 9, 8 + count
    table_range = f"A8:AH{last}"
    tables = sheet["tables"]
    audit.check(len(tables) == 1, "tables", f"{name}: expected one table")
    if len(tables) == 1:
        table = tables[0]
        audit.check(table.get("name") == f"{name}UltraReview", "tables", f"{name}: unexpected table name")
        audit.check(table.get("ref") == table_range, "tables", f"{name}: table range mismatch")
        audit.check(table.get("headerRowCount", "1") == "1", "tables", f"{name}: missing table header")
        columns = table.findall("m:tableColumns/m:tableColumn", NS)
        audit.check([column.get("name") for column in columns] == HEADERS, "tables", f"{name}: table headers differ")
        auto_filter = table.find("m:autoFilter", NS)
        audit.check(auto_filter is not None, "filters", f"{name}: table auto-filter missing")
        if auto_filter is not None:
            audit.check(auto_filter.get("ref") == table_range, "filters", f"{name}: auto-filter range mismatch")
            for filter_column in auto_filter.findall("m:filterColumn", NS):
                audit.check(filter_column.get("hiddenButton", "0") not in {"1", "true"}, "filters", f"{name}: hidden filter button")
                audit.check(filter_column.get("showButton", "1") not in {"0", "false"}, "filters", f"{name}: filter button disabled")

    panes = root.findall("m:sheetViews/m:sheetView/m:pane", NS)
    audit.check(len(panes) == 1, "freeze_panes", f"{name}: expected one frozen pane")
    if len(panes) == 1:
        pane = panes[0]
        audit.check(pane.get("state") in {"frozen", "frozenSplit"}, "freeze_panes", f"{name}: pane is not frozen")
        audit.check(float(pane.get("xSplit", "0")) == 1, "freeze_panes", f"{name}: first column is not frozen")
        audit.check(float(pane.get("ySplit", "0")) == 8, "freeze_panes", f"{name}: eight header rows are not frozen")
        audit.check(pane.get("topLeftCell") == "B9", "freeze_panes", f"{name}: freeze anchor is not B9")

    validations = root.findall("m:dataValidations/m:dataValidation", NS)
    audit.check(len(validations) == 1, "validations", f"{name}: expected one status validation")
    if len(validations) == 1:
        validation = validations[0]
        audit.check(validation.get("type") == "list", "validations", f"{name}: status validation is not a list")
        audit.check(validation.get("sqref") == f"F{first}:F{last}", "validations", f"{name}: status validation range mismatch")
        formula = validation.find("m:formula1", NS)
        expected = '"' + ",".join(STATUSES) + '"'
        audit.check(formula is not None and formula.text == expected, "validations", f"{name}: status validation choices mismatch")
        for row in range(first, last + 1):
            audit.check(contains_address(validation.get("sqref", ""), f"F{row}"), "validation_coverage", f"{name}!F{row}: status validation missing")

    audit.check(sheet["state"] == "visible", "visibility", f"{name}: worksheet hidden")
    for row in root.findall("m:sheetData/m:row", NS):
        audit.check(row.get("hidden", "0") not in {"1", "true"}, "visibility", f"{name}: hidden row {row.get('r')}")
    for column in root.findall("m:cols/m:col", NS):
        audit.check(column.get("hidden", "0") not in {"1", "true"}, "visibility", f"{name}: hidden column range")
    audit.check(root.find("m:sheetProtection", NS) is None, "human_editability", f"{name}: worksheet protection may block human fields")
    return {
        "records": count,
        "data_range": f"A9:AH{last}",
        "table": table_range,
        "freeze_anchor": "B9",
        "status_validation": f"F9:F{last}",
    }


def verify_packet(audit: Audit, data: dict, inputs: dict[str, dict]) -> dict:
    expected_names = [schema[0] for schema in SCHEMAS]
    audit.check(list(audit.workbook.sheets) == expected_names, "sheet_structure", "Workbook sheet names/order differ")
    audit.check(not audit.workbook.external_relationships, "package_integrity", "Unexpected external relationships")
    audit.check(not any("vbaProject" in part for part in audit.workbook.parts), "package_integrity", "Unexpected VBA project")
    audit.check(not any(part.startswith("xl/externalLinks/") for part in audit.workbook.parts), "package_integrity", "Unexpected external workbook links")
    metadata = data["metadata"]
    for key, expected in {
        "review_source": "ai", "model": "gpt-6-astra", "reasoning_effort": "ultra",
        "human_validation_complete": False, "candidate_inference_run": False,
    }.items():
        audit.check(exact_data_equal(metadata.get(key), expected), "provenance", f"Packet metadata {key} mismatch")

    all_ids = []
    summaries = {}
    for name, partition, count in SCHEMAS:
        records = data[partition]
        audit.check(len(records) == count, "record_coverage", f"{partition}: expected {count} records")
        all_ids.extend(record["id"] for record in records)
        if name not in audit.workbook.sheets:
            continue
        summaries[name] = verify_controls(audit, name, count)
        for column, header in enumerate(HEADERS, 1):
            audit.equal(name, f"{column_name(column)}8", header, "headers")
        audit.equal(name, "A2", f"Cadence Astra Ultra review — {name}", "sheet_titles")
        audit.equal(name, "A3", "AI review only. GPT-6 Astra (gpt-6-astra), reasoning effort: ultra. Human validation remains Pending.", "provenance_banner")
        audit.equal(name, "A4", "Prior and Ultra proposals are recorded separately. Amber cells record human review; put any label corrections in Human notes.", "human_instructions")
        audit.equal(name, "A5", "Complete human review only after checking labels, recording the reviewer and review time, and explaining corrections or unresolved questions.", "human_instructions")
        input_name = "confirmation_01.jsonl + confirmation_02.jsonl" if partition == "confirmation" else "challenge_01.jsonl"
        audit.equal(name, "A6", f"Source: review_data.json ({partition}) and inputs/{input_name}. {count} flagged cases.", "source_citation")

        actual_ids = []
        for address, cell in audit.workbook.sheets[name]["cells"].items():
            column, row = address_parts(address)
            if column == 1 and row >= 9 and cell.value not in (None, ""):
                actual_ids.append((row, cell.value))
            if row >= 9 and (row > 8 + count or column > 34):
                audit.check(cell.value in (None, "") and cell.formula is None, "record_coverage", f"{name}!{address}: data outside intended record range")
        audit.check([value for _, value in sorted(actual_ids)] == [record["id"] for record in records], "record_coverage", f"{name}: saved IDs/order differ")

        for row, record in enumerate(records, 9):
            case_id = record["id"]
            source = inputs.get(case_id)
            audit.check(source is not None, "source_binding_presence", f"{case_id}: no manifest input")
            if source is not None:
                for field in SOURCE_FIELDS:
                    audit.check(exact_data_equal(record[field], source[field]), "source_binding", f"{case_id}: source field {field} differs")
            audit.check(record["partition"] == partition, "record_coverage", f"{case_id}: wrong partition")
            audit.check(record["human_review_status"] == "Pending", "human_initial_state", f"{case_id}: human status not Pending")
            for field in ("human_reviewer", "human_reviewed_at", "human_notes"):
                audit.check(record[field] == "", "human_initial_state", f"{case_id}: {field} not blank")
            review = record["ultra_review"]
            for key, expected in {
                "id": case_id, "review_source": "ai", "model": "gpt-6-astra",
                "reasoning_effort": "ultra", "human_verified": False,
            }.items():
                audit.check(exact_data_equal(review[key], expected), "provenance", f"{case_id}: review {key} mismatch")
            audit.check(isinstance(review["reviewer"], str) and review["reviewer"].startswith("/root/"), "provenance", f"{case_id}: actual AI reviewer missing")
            try:
                stamp = datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00"))
                stamp_valid = stamp.tzinfo is not None and stamp.utcoffset().total_seconds() == 0
            except (TypeError, ValueError):
                stamp_valid = False
            audit.check(stamp_valid, "provenance", f"{case_id}: review time is not UTC ISO text")
            values = expected_row(record)
            audit.check(len(values) == len(HEADERS), "record_coverage", f"{case_id}: expected cell mapping length differs")
            for column, value in enumerate(values, 1):
                audit.equal(name, f"{column_name(column)}{row}", value, "record_cell_equality")
            for column in ("K", "L", "T", "AH"):
                cell = audit.workbook.cell(name, f"{column}{row}")
                audit.check(cell.data_type == "b" and type(cell.value) is bool, "native_booleans", f"{name}!{column}{row}: expected native boolean")
            audit.equal(name, f"F{row}", "Pending", "human_initial_state")
            for column in ("W", "X", "Y"):
                audit.equal(name, f"{column}{row}", "", "human_initial_state")
            audit.equal(name, f"AH{row}", False, "human_initial_state")

    audit.check(len(all_ids) == 55 and len(set(all_ids)) == 55, "record_coverage", "Expected 55 unique review IDs")
    audit.check(set(all_ids) == set(inputs), "record_coverage", "Review IDs differ from manifest input IDs")
    audit.check_no_cell_formulas_or_errors()
    return summaries


def main() -> int:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workbook", type=Path, default=base / "Cadence-Astra-Ultra-Review.xlsx")
    args = parser.parse_args()
    data_path = base / "review_data.json"
    manifest, inputs = load_inputs(base)
    data = json.loads(data_path.read_text(encoding="utf-8-sig"))
    workbook = XlsxReader(args.workbook)
    audit = Audit(workbook)
    summaries = verify_packet(audit, data, inputs)
    formula_count = sum(cell.formula is not None for sheet in workbook.sheets.values() for cell in sheet["cells"].values())
    error_count = sum(cell.data_type == "e" for sheet in workbook.sheets.values() for cell in sheet["cells"].values())
    report = {
        "status": "passed" if not audit.errors else "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "method": "Read-only Python standard-library ZIP/XML inspection",
        "scope": "Saved-file content and control serialization; no label judgments",
        "workbook": args.workbook.name,
        "workbook_sha256": sha256(args.workbook),
        "review_data_sha256": sha256(data_path),
        "manifest_sha256": sha256(base / "MANIFEST.json"),
        "records_checked": len(inputs),
        "record_cells_compared": audit.checks["record_cell_equality"],
        "source_fields_compared": audit.checks["source_binding"],
        "sheets": summaries,
        "checks": dict(sorted(audit.checks.items())),
        "worksheet_formula_count": formula_count,
        "worksheet_error_count": error_count,
        "input_hashes_verified": {batch["input"]: batch["sha256"] for batch in manifest["batches"]},
        "native_excel_tested": False,
        "errors": audit.errors,
    }
    output = base / "workbook_qa.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "records": len(inputs), "cells": report["record_cells_compared"], "errors": audit.errors, "report": str(output)}, ensure_ascii=False))
    return 0 if not audit.errors else 1


if __name__ == "__main__":
    sys.exit(main())
