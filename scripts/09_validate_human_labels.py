"""Validate human-entered labels against the locked sample; never invent missing answers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from cadence.config import SENTIMENTS, Paths, intent_ids, reason_codes
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, read_jsonl, write_jsonl


def validate(directory: Path) -> list[dict]:
    lock = read_json(directory / "HOLDOUT.lock.json")
    for name, digest in lock["files"].items():
        if sha256(directory / name) != digest:
            raise ValueError(f"Locked file changed: {name}")
    examples = read_jsonl(directory / "examples.jsonl")
    with (directory / "human_labels.csv").open(encoding="utf-8-sig", newline="") as f:
        labels = list(csv.DictReader(f))
    if len(labels) != len(examples) or {r["id"] for r in labels} != {r["id"] for r in examples}:
        raise ValueError("Missing, duplicate or extra label IDs")
    by_id = {r["id"]: r for r in labels}
    output = []
    for example in examples:
        r = by_id[example["id"]]
        if r["text"] != example["text"]:
            raise ValueError(f"Text changed: {example['id']}")
        if r["label_source"] != "human" or not r["annotator"].strip():
            raise ValueError(f"{example['id']}: named human annotator and label_source=human required")
        if r["intent"] not in intent_ids() or r["secondary_intent"] not in ["", *intent_ids()]:
            raise ValueError(f"{example['id']}: invalid intent")
        if r["sentiment"] not in SENTIMENTS or r["should_escalate"].lower() not in {"true", "false"}:
            raise ValueError(f"{example['id']}: sentiment and true/false escalation required")
        escalate = r["should_escalate"].lower() == "true"
        if (escalate and r["escalation_reason_code"] not in reason_codes()) or (
            not escalate and r["escalation_reason_code"]
        ):
            raise ValueError(f"{example['id']}: reason must agree with decision")
        if not r["notes"].strip():
            raise ValueError(f"{example['id']}: a brief labeling rationale is required")
        output.append(
            {
                **example,
                "gold": {
                    "intent": r["intent"],
                    "secondary_intent": r["secondary_intent"] or None,
                    "should_escalate": escalate,
                    "escalation_reason_code": r["escalation_reason_code"] or None,
                    "sentiment": r["sentiment"],
                    "notes": r["notes"],
                },
                "label_source": "human",
                "annotator": r["annotator"],
                "labels_sha256": sha256(directory / "human_labels.csv"),
            }
        )
    return output


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, default=Paths.DATA / "holdout")
    args = p.parse_args(argv)
    rows = validate(args.directory)
    write_jsonl(args.directory / "golden_set.jsonl", rows)
    print(
        f"Validated {len(rows)} human-labelled examples. Authorship is self-attested, not independently verified."
    )


if __name__ == "__main__":
    main()
