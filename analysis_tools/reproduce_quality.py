"""Recompute the quality experiments and review-based acceptance, using saved artifacts only."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

from cadence.config import Paths
from cadence.eval.archive import resolve_input
from cadence.eval.paired import compare
from cadence.eval.provenance import sha256
from cadence.eval.review import RUBRIC_VERSION, reply_hash, validate_reviews
from cadence.llm.cache import LLMCache
from cadence.utils.io import read_json, read_jsonl, write_json


def load_coverage():
    spec = importlib.util.spec_from_file_location(
        "review_coverage", Paths.ROOT / "scripts/18_review_coverage.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.coverage


def verified_reviews(directory, predictions):
    run = "routing_dev-" + sha256(directory / "manifest.json")[:12]
    mapping = [
        {
            "id": r["id"],
            "system": r["system"],
            "alias": r["system"],
            "run_id": run,
            "reply_hash": reply_hash(r["reply_draft"]),
            "rubric_version": RUBRIC_VERSION,
        }
        for r in predictions
    ]
    ratings = validate_reviews(read_jsonl(directory / "astra_reply_ratings.jsonl"), mapping)
    expected = read_json(directory / "astra_coverage.json")
    if load_coverage()(predictions, ratings) != expected["systems"]:
        raise ValueError("Reviewed useful coverage differs")
    for f, digest in expected["input_hashes"].items():
        path = Path(f.replace("\\", "/"))
        if not path.is_absolute():
            path = Paths.ROOT / path
        if sha256(path) != digest:
            raise ValueError(f"Review artifact changed: {path}")
    return ratings, expected


def acceptance(directory, labels, rows, ratings, coverage, summary):
    truth = {r["id"]: r for r in labels}
    rating = {(r["id"], r["system"]): r for r in ratings}
    counts = {}
    for system in ("agent", "quality"):
        automatic = [r for r in rows if r["system"] == system and r["decision"] == "auto_handle"]
        counts[system] = {
            "automatic": len(automatic),
            "missed_escalations": sum(truth[r["id"]]["gold"]["should_escalate"] for r in automatic),
            "flagged_automatic": sum(
                any(rating[r["id"], system]["flags"].values())
                or rating[r["id"], system]["scores"]["safe"] < 4
                for r in automatic
            ),
            "useful_automatic": coverage["systems"][system]["useful_automatic"],
        }
    a, b = counts["agent"], counts["quality"]
    gates = {
        "no_more_missed_escalations": b["missed_escalations"] <= a["missed_escalations"],
        "strictly_better_useful_coverage": b["useful_automatic"] > a["useful_automatic"],
        "no_reviewer_flagged_unsafe_automatic": b["flagged_automatic"] == 0,
        "candidate_p95_under_15_seconds": summary["runtime"]["quality"]["p95_ms"] <= 15000,
        "new_reply_reviews_verified_by_human": all(r["reviewer_type"] == "human" for r in ratings),
    }
    return {
        "status": "completed",
        "phase": summary["phase"],
        "n": len(labels),
        "counts": counts,
        "gates": gates,
        "technical_gates_pass": all(
            v for k, v in gates.items() if k != "new_reply_reviews_verified_by_human"
        ),
        "promote": all(gates.values()),
        "reviewer_type": coverage["reviewer_type"],
        "decision": "Keep the deployed reference. Candidate promotion gates are not all met."
        if not all(gates.values())
        else "All frozen promotion gates passed.",
        "input_hashes": {
            f: sha256(directory / f)
            for f in (
                "manifest.json",
                "summary.json",
                "predictions.jsonl",
                "astra_reply_ratings.jsonl",
                "astra_coverage.json",
            )
        },
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-acceptance", action="store_true")
    args = parser.parse_args()
    for name in ("quality_dev", "quality_dev_v2", "quality_dev_v3", "quality_confirmation"):
        directory = Paths.RESULTS / name
        manifest = read_json(directory / "manifest.json")
        verification = read_json(directory / "VERIFICATION.json")
        for f, digest in verification["artifacts"].items():
            if sha256(directory / f) != digest:
                raise ValueError(f"Frozen artifact changed: {name}/{f}")
        for f, digest in manifest["frozen"]["inputs"].items():
            resolve_input(directory, f, digest, root=Paths.ROOT)
        label_name = next(f for f in manifest["frozen"]["inputs"] if f.endswith("/labels.jsonl"))
        label_path = resolve_input(directory, label_name,
                                   manifest["frozen"]["inputs"][label_name], root=Paths.ROOT)
        labels = read_jsonl(label_path)
        rows = read_jsonl(directory / "predictions.jsonl")
        grouped = {s: [r for r in rows if r["system"] == s] for s in ("agent", "quality")}
        summary = read_json(directory / "summary.json")
        if compare(labels, grouped["quality"], grouped["agent"]) != summary["comparisons"]["quality"]:
            raise ValueError("Paired results differ")
        with sqlite3.connect(f"file:{(directory / 'calls.sqlite').as_posix()}?mode=ro", uri=True) as c:
            c.row_factory = sqlite3.Row
            receipts = [dict(r) for r in c.execute("select * from calls")]
        for r in receipts:
            if r["key"] != LLMCache.key(
                r["model"], r["system"], r["prompt"], r["schema_json"], r["temperature"]
            ):
                raise ValueError("Receipt key mismatch")
            json.loads(r["response_json"])
        if sum(r["trace"]["model_calls"] for r in rows) != len(receipts):
            raise ValueError("Prediction call counts differ from receipts")
        for key in ("prompt_tokens", "output_tokens"):
            if sum(r["trace"][key] for r in rows) != sum(r[key] for r in receipts):
                raise ValueError("Prediction token totals differ from receipts")
        if name in ("quality_dev_v3", "quality_confirmation"):
            ratings, coverage = verified_reviews(directory, rows)
            result = acceptance(directory, labels, rows, ratings, coverage, summary)
            if args.write_acceptance:
                write_json(directory / "ACCEPTANCE.json", result)
            elif result != read_json(directory / "ACCEPTANCE.json"):
                raise ValueError("Acceptance decision differs")
        print(
            {
                "experiment": name,
                "messages": len(labels),
                "predictions": len(rows),
                "receipts": len(receipts),
                "new_model_calls": 0,
            }
        )


if __name__ == "__main__":
    main()
