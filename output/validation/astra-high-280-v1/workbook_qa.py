"""Read-only, independent OOXML QA of the human label validation workbook.

Inputs are limited to review_data.json and Cadence-Label-Validation.xlsx.
Only workbook_qa.json is written; the input files are never changed.
Run after the author announces that both inputs are final.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


NS = {
    "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}
EXPECTED_COUNTS = {"confirmation": 200, "challenge": 80}
SOURCE_FIELDS = (
    "id", "text", "scenario_setup", "intent", "secondary_intent",
    "should_escalate", "escalation_reason_code", "sentiment", "notes",
    "confidence", "needs_human_attention", "validation_question", "annotator",
    "model", "reasoning_effort", "labeled_at",
)
ALIASES = {
    "id": {"id", "case_id", "record_id", "message_id", "row_id"},
    "text": {"text", "source_text", "original_text", "message_text", "customer_text", "message"},
    "scenario_setup": {"scenario_setup", "scenario", "setup"},
    "intent": {"intent", "primary_intent"},
    "secondary_intent": {"secondary_intent"},
    "should_escalate": {"should_escalate", "escalate", "escalation"},
    "escalation_reason_code": {"escalation_reason_code", "escalation_reason", "reason_code"},
    "sentiment": {"sentiment"},
    "notes": {"notes", "rationale", "label_notes", "label_rationale", "reasoning"},
    "confidence": {"confidence", "label_confidence"},
    "needs_human_attention": {"needs_human_attention", "needs_attention", "human_attention"},
    "validation_question": {"validation_question", "review_question", "question_for_reviewer"},
    "annotator": {"annotator", "annotator_name", "annotation_source"},
    "model": {"model", "model_name"},
    "reasoning_effort": {"reasoning_effort", "effort"},
    "labeled_at": {"labeled_at", "labelled_at", "label_timestamp", "labeled_timestamp", "annotation_timestamp"},
}
PREFIXES = ("original_", "source_", "proposed_", "ai_", "astra_", "model_", "label_", "annotation_")
HUMAN_TOKENS = {"human", "reviewer", "validator", "validation", "review", "final", "corrected", "override", "adjudicated"}
STATUS_ALIASES = {"status", "validation_status", "review_status", "human_status", "human_validation_status", "human_review_status"}
REVIEWER_ALIASES = {"reviewer", "reviewer_name", "human_reviewer", "human_reviewer_name", "validator", "validator_name", "validated_by", "reviewed_by", "human_validator"}
REVIEWED_AT_ALIASES = {"reviewed_at", "validated_at", "review_date", "validation_date", "review_timestamp", "validation_timestamp", "human_reviewed_at", "human_validation_timestamp", "reviewed_on"}
REVIEW_NOTES_ALIASES = {"review_notes", "reviewer_notes", "validation_notes", "human_notes", "human_validation_notes", "human_review_notes", "review_comment", "review_comments", "reviewer_comments"}
CORRECTION_TOKENS = {"corrected", "final", "override", "adjudicated", "validated", "human"}
INTENTS = [
    "non_english", "account_hacked_or_security", "billing_or_charge", "login_or_password",
    "download_or_offline", "metadata_or_artist_issue", "playlist_or_library",
    "content_or_availability", "playback_or_app_bug", "subscription_or_plan",
    "feature_request_or_feedback", "other",
]
CANONICAL_CHOICES = {
    "status": ["Pending", "Approved", "Corrected", "Needs discussion"],
    "intent": INTENTS,
    "secondary_intent": INTENTS + [""],
    "should_escalate": ["true", "false"],
    "escalation_reason_code": [
        "billing_dispute", "account_security", "needs_account_lookup",
        "high_frustration_or_churn", "legal_or_safety", "ambiguous_or_media_only",
        "low_confidence", "out_of_scope", "",
    ],
    "sentiment": ["positive", "neutral", "frustrated", "angry"],
}


def normalized(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def col_num(value):
    number = 0
    for ch in value.upper():
        number = number * 26 + ord(ch) - 64
    return number


def col_name(number):
    result = ""
    while number:
        number, rem = divmod(number - 1, 26)
        result = chr(65 + rem) + result
    return result


def cell_position(address):
    match = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", address.upper())
    if not match:
        raise ValueError(f"Unsupported cell address: {address!r}")
    return int(match[2]), col_num(match[1])


def range_bounds(address):
    parts = address.split(":")
    start = cell_position(parts[0])
    end = cell_position(parts[-1])
    return start[0], start[1], end[0], end[1]


def contains(address, row, column):
    top, left, bottom, right = range_bounds(address)
    return top <= row <= bottom and left <= column <= right


def decode_excel_text(value):
    value = re.sub(r"_x([0-9a-fA-F]{4})_", lambda m: chr(int(m[1], 16)), value)
    return value.encode("utf-16", "surrogatepass").decode("utf-16", "surrogatepass")


def text_content(element):
    if element is None:
        return ""
    return decode_excel_text("".join(node.text or "" for node in element.iter(f"{{{NS['s']}}}t")))


def rel_path(owner, target):
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(owner), target))


def relationship_file(owner):
    return posixpath.join(posixpath.dirname(owner), "_rels", posixpath.basename(owner) + ".rels")


def source_match(header):
    name = normalized(header).removesuffix("_utc")
    # Resolve human workflow fields separately, while permitting the two source
    # fields that explicitly mention validation / human attention.
    for field, options in ALIASES.items():
        if name in options:
            return field
    if set(name.split("_")) & {"human", "reviewer", "validator", "corrected", "final", "override", "adjudicated"}:
        if not name.endswith("needs_human_attention"):
            return None
    variants = {name}
    for _ in range(3):
        for variant in list(variants):
            for prefix in PREFIXES:
                if variant.startswith(prefix):
                    variants.add(variant[len(prefix):])
    for field, options in ALIASES.items():
        if variants & options:
            return field
    return None


def human_match(header):
    name = normalized(header).removesuffix("_utc")
    if name in STATUS_ALIASES:
        return "status"
    if name in REVIEWER_ALIASES:
        return "reviewer"
    if name in REVIEWED_AT_ALIASES:
        return "reviewed_at"
    if name in REVIEW_NOTES_ALIASES:
        return "review_notes"
    tokens = set(name.split("_"))
    if "status" in tokens and tokens & HUMAN_TOKENS:
        return "status"
    if tokens & {"reviewer", "validator"} and "name" in tokens:
        return "reviewer"
    if tokens & HUMAN_TOKENS and tokens & {"timestamp", "time", "date", "at"}:
        return "reviewed_at"
    if tokens & HUMAN_TOKENS and tokens & {"notes", "note", "comments", "comment", "rationale"}:
        return "review_notes"
    if tokens & CORRECTION_TOKENS:
        return "correction"
    return None


def json_semantic_equal(expected, actual):
    if expected is None or isinstance(expected, bool) or isinstance(actual, bool):
        return type(expected) is type(actual) and expected == actual
    if isinstance(expected, dict):
        return isinstance(actual, dict) and expected.keys() == actual.keys() and all(json_semantic_equal(value, actual[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(json_semantic_equal(a, b) for a, b in zip(expected, actual))
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and expected == actual
    return type(expected) is type(actual) and expected == actual


def values_equal(expected, actual, field=None):
    if field == "scenario_setup" and isinstance(expected, dict):
        if actual in (None, ""):
            return expected == {}
        if not isinstance(actual, str):
            return False
        try:
            return json_semantic_equal(expected, json.loads(actual))
        except json.JSONDecodeError:
            return False
    if expected is None:
        return actual in (None, "")
    if isinstance(expected, bool):
        if isinstance(actual, bool):
            return expected == actual
        return isinstance(actual, str) and actual == str(expected).lower()
    if isinstance(expected, (int, float)):
        return not isinstance(actual, bool) and isinstance(actual, (int, float)) and expected == actual
    return isinstance(actual, str) and expected == actual


class Workbook:
    def __init__(self, path):
        self.package = zipfile.ZipFile(path, "r")
        names = self.package.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP member names in workbook")
        self.shared = []
        if "xl/sharedStrings.xml" in names:
            self.shared = [text_content(si) for si in self.xml("xl/sharedStrings.xml").findall("s:si", NS)]
        self.root = self.xml("xl/workbook.xml")
        props = self.root.find("s:workbookPr", NS)
        self.date1904 = props is not None and props.get("date1904") in {"1", "true"}
        self.formats = {}
        self.cell_formats = []
        self.unlocked_styles = set()
        if "xl/styles.xml" in names:
            styles = self.xml("xl/styles.xml")
            self.formats = {int(node.get("numFmtId")): node.get("formatCode") for node in styles.findall("s:numFmts/s:numFmt", NS)}
            self.cell_formats = [int(node.get("numFmtId", "0")) for node in styles.findall("s:cellXfs/s:xf", NS)]
            for index, node in enumerate(styles.findall("s:cellXfs/s:xf", NS)):
                protection = node.find("s:protection", NS)
                if protection is not None and protection.get("locked") in {"0", "false"} and node.get("applyProtection") not in {"0", "false"}:
                    self.unlocked_styles.add(index)
        self.defined_names = {node.get("name"): node.text for node in self.root.findall("s:definedNames/s:definedName", NS)}
        links = self.relationships("xl/workbook.xml")
        self.sheets = []
        for item in self.root.findall("s:sheets/s:sheet", NS):
            link = links[item.get(f"{{{NS['r']}}}id")]
            sheet_path = rel_path("xl/workbook.xml", link["Target"])
            root = self.xml(sheet_path)
            cells = {}
            for node in root.findall("s:sheetData/s:row/s:c", NS):
                address = node.get("r")
                kind = node.get("t")
                raw = node.findtext("s:v", default=None, namespaces=NS)
                if kind == "s":
                    value = self.shared[int(raw)]
                elif kind == "inlineStr":
                    value = text_content(node.find("s:is", NS))
                elif kind in {"str", "e", "d"}:
                    value = decode_excel_text(raw or "")
                elif kind == "b":
                    value = raw == "1"
                elif raw is None:
                    value = None
                else:
                    number = float(raw)
                    value = int(number) if number.is_integer() else number
                style_index = int(node.get("s", "0"))
                format_id = self.cell_formats[style_index] if style_index < len(self.cell_formats) else 0
                cells[address] = {"value": value, "type": kind, "formula": node.find("s:f", NS) is not None, "number_format_id": format_id, "number_format": self.formats.get(format_id), "unlocked": style_index in self.unlocked_styles}
            rels = self.relationships(sheet_path)
            tables = []
            for part in root.findall("s:tableParts/s:tablePart", NS):
                link = rels[part.get(f"{{{NS['r']}}}id")]
                table = self.xml(rel_path(sheet_path, link["Target"]))
                auto_filter = table.find("s:autoFilter", NS)
                tables.append({
                    "name": table.get("name"), "ref": table.get("ref"),
                    "filter_ref": auto_filter.get("ref") if auto_filter is not None else None,
                    "headers": [c.get("name") for c in table.findall("s:tableColumns/s:tableColumn", NS)],
                })
            validations = []
            for rule in root.findall("s:dataValidations/s:dataValidation", NS):
                validations.append({**rule.attrib, "formula1": rule.findtext("s:formula1", default="", namespaces=NS)})
            pane = root.find("s:sheetViews/s:sheetView/s:pane", NS)
            auto_filter = root.find("s:autoFilter", NS)
            self.sheets.append({
                "name": item.get("name"), "state": item.get("state", "visible"),
                "root": root, "path": sheet_path, "cells": cells, "tables": tables,
                "validations": validations, "pane": dict(pane.attrib) if pane is not None else {},
                "filter_ref": auto_filter.get("ref") if auto_filter is not None else None,
            })

    def xml(self, path):
        return ET.fromstring(self.package.read(path))

    def relationships(self, owner):
        path = relationship_file(owner)
        if path not in self.package.namelist():
            return {}
        return {node.get("Id"): dict(node.attrib) for node in self.xml(path).findall("p:Relationship", NS)}

    def validation_values(self, formula, context_sheet):
        formula = formula.removeprefix("=")
        if formula.startswith('"') and formula.endswith('"'):
            return formula[1:-1].split(",")
        formula = self.defined_names.get(formula, formula)
        if re.fullmatch(r"[A-Za-z$0-9:]+", formula or ""):
            formula = "'" + context_sheet.replace("'", "''") + "'!" + formula
        match = re.fullmatch(r"(?:'((?:[^']|'')+)'|([^!]+))!([A-Za-z$0-9:]+)", formula or "")
        if not match:
            return None
        sheet_name = (match[1] or match[2]).replace("''", "'")
        sheet = next((s for s in self.sheets if s["name"] == sheet_name), None)
        if sheet is None:
            return None
        top, left, bottom, right = range_bounds(match[3])
        return [sheet["cells"].get(f"{col_name(c)}{r}", {}).get("value") for r in range(top, bottom + 1) for c in range(left, right + 1)]


def check_workbook(data_path, workbook_path):
    result = {
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_file": str(data_path), "workbook_file": str(workbook_path),
        "read_only": True, "checks": [], "sheets": [], "failures": [],
        "limitations": ["Saved OOXML inspection does not prove rendering or interactive behavior in Microsoft Excel."],
    }

    def check(name, passed, details=None):
        item = {"check": name, "passed": bool(passed)}
        if details is not None:
            item["details"] = details
        result["checks"].append(item)
        if not passed:
            result["failures"].append(item)

    data_bytes = data_path.read_bytes()
    workbook_bytes = workbook_path.read_bytes()
    result["source_sha256"] = hashlib.sha256(data_bytes).hexdigest()
    result["workbook_sha256"] = hashlib.sha256(workbook_bytes).hexdigest()
    payload = json.loads(data_bytes.decode("utf-8-sig"))
    check("source_cohorts", set(EXPECTED_COUNTS) <= set(payload), {"required": list(EXPECTED_COUNTS), "present": sorted(payload)})
    result["ignored_root_metadata_keys"] = sorted(set(payload) - set(EXPECTED_COUNTS))
    source = {cohort: payload.get(cohort, []) for cohort in EXPECTED_COUNTS}
    ids = []
    for cohort, count in EXPECTED_COUNTS.items():
        rows = source.get(cohort, [])
        check(f"source_{cohort}_count", len(rows) == count, {"expected": count, "actual": len(rows)})
        missing = [{"index": i, "fields": sorted(set(SOURCE_FIELDS) - set(row))} for i, row in enumerate(rows) if set(SOURCE_FIELDS) - set(row)]
        check(f"source_{cohort}_fields", not missing, missing)
        ids.extend(row.get("id") for row in rows)
    check("source_ids_unique", len(ids) == len(set(ids)), {"total": len(ids), "unique": len(set(ids))})
    workbook = Workbook(workbook_path)
    matched_cohorts = set()
    all_formulas = []
    all_error_cells = []
    text_special_count = 0

    for sheet in workbook.sheets:
        name = sheet["name"]
        cells = sheet["cells"]
        all_formulas.extend({"sheet": name, "cell": addr} for addr, cell in cells.items() if cell["formula"])
        all_error_cells.extend({"sheet": name, "cell": addr, "error": cell["value"]} for addr, cell in cells.items() if cell["type"] == "e")
        rows_by_number = collections.defaultdict(dict)
        for address, cell in cells.items():
            r, c = cell_position(address)
            rows_by_number[r][c] = cell["value"]
        candidates = []
        for row_no, row in rows_by_number.items():
            mapping = {}
            for column, value in row.items():
                key = source_match(value) if isinstance(value, str) else None
                if key:
                    mapping.setdefault(key, []).append(column)
            if "id" in mapping and "text" in mapping:
                candidates.append((len(mapping), row_no, mapping))
        if not candidates:
            result["sheets"].append({"sheet": name, "role": "supporting", "state": sheet["state"], "tables": sheet["tables"]})
            continue
        _, header_row, source_map = max(candidates)
        headers = rows_by_number[header_row]
        id_col, text_col = source_map["id"][0], source_map["text"][0]
        data_tables = [table for table in sheet["tables"] if range_bounds(table["ref"])[0] == header_row and contains(table["ref"], header_row, id_col) and contains(table["ref"], header_row, text_col)]
        check(f"{name}:one_review_table", len(data_tables) == 1, [table["name"] for table in data_tables])
        table_end = range_bounds(data_tables[0]["ref"])[2] if len(data_tables) == 1 else max(rows_by_number)
        record_rows = [r for r in sorted(rows_by_number) if header_row < r <= table_end and rows_by_number[r].get(id_col) not in (None, "")]
        source_ids_outside_table = [f"{col_name(id_col)}{r}" for r, row in rows_by_number.items() if r not in record_rows and row.get(id_col) in set(ids)]
        check(f"{name}:source_ids_inside_review_table", not source_ids_outside_table, source_ids_outside_table)
        record_ids = [rows_by_number[r].get(source_map["id"][0]) for r in record_rows]
        overlaps = {cohort: len(set(record_ids) & {row["id"] for row in entries}) for cohort, entries in source.items()}
        cohort = max(overlaps, key=overlaps.get)
        check(f"{name}:recognizable_cohort", overlaps[cohort] > 0, overlaps)
        check(f"{name}:cohort_once", cohort not in matched_cohorts, cohort)
        matched_cohorts.add(cohort)
        expected = {row["id"]: row for row in source[cohort]}
        check(f"{name}:all_source_headers", set(source_map) == set(SOURCE_FIELDS), {"missing": sorted(set(SOURCE_FIELDS) - set(source_map)), "ambiguous": {k: v for k, v in source_map.items() if len(v) != 1}})
        check(f"{name}:unique_source_headers", all(len(v) == 1 for v in source_map.values()))
        check(f"{name}:record_count", len(record_rows) == EXPECTED_COUNTS[cohort], {"expected": EXPECTED_COUNTS[cohort], "actual": len(record_rows)})
        check(f"{name}:ids_unique", len(record_ids) == len(set(record_ids)))
        check(f"{name}:ids_exact", set(record_ids) == set(expected), {"missing": sorted(set(expected) - set(record_ids)), "extra": sorted(set(record_ids) - set(expected))})
        human = collections.defaultdict(list)
        source_columns = {c for columns in source_map.values() for c in columns}
        unknown = {}
        for column, value in headers.items():
            if column in source_columns or value in (None, ""):
                continue
            key = human_match(value)
            if key:
                human[key].append(column)
            else:
                unknown[col_name(column)] = value
        summary_fields = collections.defaultdict(list)
        for row_no, row in rows_by_number.items():
            if row_no >= header_row:
                continue
            for column, value in row.items():
                kind = human_match(value) if isinstance(value, str) else None
                if kind in {"reviewer", "reviewed_at"}:
                    summary_fields[kind].append({"label_cell": f"{col_name(column)}{row_no}", "input_cell": f"{col_name(column + 1)}{row_no}", "blank": row.get(column + 1) in (None, "")})
        check(f"{name}:human_workflow_fields", {"status", "review_notes"} <= set(human) and {"reviewer", "reviewed_at"} <= (set(human) | set(summary_fields)), {"row_fields": {key: [headers[c] for c in columns] for key, columns in human.items()}, "sheet_fields": dict(summary_fields)})
        check(f"{name}:human_summary_fields_blank", all(cell["blank"] for group in summary_fields.values() for cell in group), dict(summary_fields))
        check(f"{name}:headers_classified", not unknown, unknown)
        mismatches, human_nonblank, not_pending, unsafe, nonliteral_timestamps, bad_boolean_display = [], [], [], [], [], []
        comparisons = collections.Counter()
        for row_no, record_id in zip(record_rows, record_ids):
            actual = rows_by_number[row_no]
            if record_id not in expected:
                continue
            for field in SOURCE_FIELDS:
                if field not in source_map or len(source_map[field]) != 1:
                    continue
                column = source_map[field][0]
                address = f"{col_name(column)}{row_no}"
                exp = expected[record_id][field]
                got = actual.get(column)
                comparisons[field] += 1
                if not values_equal(exp, got, field):
                    # Preserve privacy and keep reports compact: locations and
                    # hashes identify mismatches without duplicating source text.
                    mismatches.append({"id": record_id, "field": field, "cell": address, "expected_type": type(exp).__name__, "actual_type": type(got).__name__, "expected_sha256": hashlib.sha256(str(exp).encode()).hexdigest(), "actual_sha256": hashlib.sha256(str(got).encode()).hexdigest()})
                if field in {"should_escalate", "needs_human_attention"} and got not in ("true", "false"):
                    bad_boolean_display.append({"id": record_id, "field": field, "cell": address})
                if field == "labeled_at" and (cells[address].get("type") not in {"s", "str", "inlineStr"} or cells[address].get("formula")):
                    nonliteral_timestamps.append({"id": record_id, "cell": address})
                if isinstance(exp, str) and exp.startswith(("=", "+", "-", "@")):
                    text_special_count += 1
                    cell = cells.get(address, {})
                    if cell.get("formula") or cell.get("type") not in {"s", "inlineStr", "str"} or got != exp:
                        unsafe.append({"id": record_id, "field": field, "cell": address})
            for field, columns in human.items():
                for column in columns:
                    got = actual.get(column)
                    address = f"{col_name(column)}{row_no}"
                    if field == "status":
                        if got != "Pending":
                            not_pending.append({"id": record_id, "cell": address})
                    elif got not in (None, ""):
                        human_nonblank.append({"id": record_id, "field": field, "cell": address})
        check(f"{name}:source_values_exact", not mismatches, {"comparisons_by_field": dict(comparisons), "mismatches": mismatches})
        check(f"{name}:booleans_canonical_display", not bad_boolean_display, bad_boolean_display)
        check(f"{name}:timestamps_literal_text", not nonliteral_timestamps, nonliteral_timestamps)
        check(f"{name}:human_fields_blank", not human_nonblank, human_nonblank)
        check(f"{name}:statuses_pending", not not_pending, not_pending)
        check(f"{name}:special_prefixes_literal", not unsafe, unsafe)
        pane = sheet["pane"]
        freeze_cols = int(float(pane.get("xSplit", 0)))
        freeze_rows = int(float(pane.get("ySplit", 0)))
        id_col, text_col = source_map["id"][0], source_map["text"][0]
        check(f"{name}:freeze_id_text_headers", pane.get("state") in {"frozen", "frozenSplit"} and freeze_cols == max(id_col, text_col) and freeze_rows == header_row, pane)
        first_col, last_col = min(headers), max(headers)
        last_row = max(record_rows) if record_rows else header_row
        filter_ranges = [sheet["filter_ref"]] if sheet["filter_ref"] else []
        filter_ranges += [t["filter_ref"] for t in sheet["tables"] if t["filter_ref"]]
        expected_bounds = (header_row, first_col, last_row, last_col)
        full_filter = any(range_bounds(ref) == expected_bounds for ref in filter_ranges)
        full_table = any(range_bounds(table["ref"]) == expected_bounds for table in sheet["tables"])
        check(f"{name}:filter_all_columns_rows", full_filter, filter_ranges)
        check(f"{name}:table_all_columns_rows", full_table, sheet["tables"])
        check(f"{name}:table_headers_match", any(range_bounds(table["ref"]) == expected_bounds and table["headers"] == [headers.get(c) for c in range(first_col, last_col + 1)] for table in sheet["tables"]))
        validation_report, validation_failures, invalid_initial_choices = [], [], []
        for rule in sheet["validations"]:
            options = workbook.validation_values(rule["formula1"], name) if rule.get("type") == "list" else None
            options = ["" if value is None else value for value in options] if options is not None else None
            validation_report.append({**rule, "resolved_options": options})
        # This design edits the initial labels in place. Require dropdowns on
        # status and the five editable label columns; provenance stays read-only.
        categorical = list(human.get("status", []))
        for field in ("intent", "secondary_intent", "should_escalate", "escalation_reason_code", "sentiment"):
            categorical.extend(source_map.get(field, []))
        for column in human.get("correction", []):
            tokens = set(normalized(headers[column]).split("_"))
            if tokens & {"intent", "sentiment", "escalate", "escalation", "confidence", "attention", "decision", "agreement"}:
                categorical.append(column)
        for column in categorical:
            field = "status" if column in human.get("status", []) else next((field for field, columns in source_map.items() if column in columns), None)
            for row_no in record_rows:
                rules = [r for r in validation_report if r.get("type") == "list" and any(contains(ref, row_no, column) for ref in r.get("sqref", "").split())]
                acceptable = [r for r in rules if r["resolved_options"] == CANONICAL_CHOICES.get(field)]
                if not acceptable:
                    validation_failures.append({"cell": f"{col_name(column)}{row_no}", "header": headers[column]})
                actual_value = rows_by_number[row_no].get(column)
                actual_value = "" if actual_value is None else actual_value
                if actual_value not in CANONICAL_CHOICES.get(field, []):
                    invalid_initial_choices.append({"cell": f"{col_name(column)}{row_no}", "header": headers[column]})
        check(f"{name}:list_validation_coverage", not validation_failures and bool(categorical), {"categorical_columns": [headers[c] for c in categorical], "failures": validation_failures, "rules": validation_report})
        check(f"{name}:initial_choices_valid", not invalid_initial_choices, invalid_initial_choices)
        editable_columns = set(categorical) | {c for columns in human.values() for c in columns}
        editable_cells = {f"{col_name(column)}{row_no}" for row_no in record_rows for column in editable_columns}
        editable_cells |= {cell["input_cell"] for group in summary_fields.values() for cell in group}
        protection = sheet["root"].find("s:sheetProtection", NS)
        protected = protection is not None and protection.get("sheet") in {"1", "true"}
        locked_inputs = sorted(address for address in editable_cells if protected and not cells.get(address, {}).get("unlocked", False))
        check(f"{name}:review_inputs_editable", not locked_inputs, {"sheet_protected": protected, "review_input_count": len(editable_cells), "locked_review_inputs": locked_inputs})
        result["sheets"].append({"sheet": name, "role": cohort, "state": sheet["state"], "header_row": header_row, "record_count": len(record_rows), "source_columns": {field: [col_name(c) for c in cols] for field, cols in source_map.items()}, "human_columns": {field: [col_name(c) for c in cols] for field, cols in human.items()}, "tables": sheet["tables"], "pane": pane, "list_validation_count": sum(r.get("type") == "list" for r in sheet["validations"])})
    check("both_cohorts_present", matched_cohorts == set(EXPECTED_COUNTS), sorted(matched_cohorts))
    check("no_unexpected_worksheet_formulas", not all_formulas, all_formulas)
    check("no_excel_error_cells", not all_error_cells, all_error_cells)
    result["special_prefix_source_values_checked"] = text_special_count
    check("inputs_unchanged", hashlib.sha256(data_path.read_bytes()).hexdigest() == result["source_sha256"] and hashlib.sha256(workbook_path.read_bytes()).hexdigest() == result["workbook_sha256"])
    result["passed"] = not result["failures"]
    result["summary"] = {"total_checks": len(result["checks"]), "passed_checks": sum(c["passed"] for c in result["checks"]), "failed_checks": len(result["failures"])}
    workbook.package.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    folder = args.directory.resolve()
    data_path = folder / "review_data.json"
    workbook_path = folder / "Cadence-Label-Validation.xlsx"
    report_path = folder / "workbook_qa.json"
    try:
        report = check_workbook(data_path, workbook_path)
    except Exception as exc:
        report = {"passed": False, "read_only": True, "fatal_error": f"{type(exc).__name__}: {exc}", "source_file": str(data_path), "workbook_file": str(workbook_path)}
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "summary": report.get("summary"), "fatal_error": report.get("fatal_error"), "failed_checks": [c["check"] for c in report.get("failures", [])], "report": str(report_path)}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
