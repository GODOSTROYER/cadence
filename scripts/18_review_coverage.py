"""Measure useful automatic coverage from explicit, content-bound development reply reviews.

Requires one review of every prediction by one named reviewer. AI and human reports stay separate.
The review schema matches scripts/14_review_study.py; aliases here are system IDs.
"""
import argparse
import csv
from pathlib import Path

from cadence.eval.provenance import sha256
from cadence.eval.review import RUBRIC_VERSION, reply_hash, validate_reviews
from cadence.utils.io import read_json, read_jsonl, write_json


def coverage(predictions, ratings):
    by_key = {(r["id"], r["system"]): r for r in predictions}
    if len(by_key) != len(predictions):
        raise ValueError("Duplicate prediction")
    reviewed = {(r["id"], r["system"]): r for r in ratings}
    if len(reviewed) != len(ratings) or set(reviewed) != set(by_key):
        raise ValueError("One review per prediction is required; partial coverage would bias the denominator")
    if len({(r["reviewer_id"], r["reviewer_type"]) for r in ratings}) != 1:
        raise ValueError("Produce a separate report for each reviewer")
    report = {}
    for system in sorted({s for _, s in by_key}):
        rows = [p for p in predictions if p["system"] == system]
        automatic = [p for p in rows if p["decision"] == "auto_handle"]
        useful = [reviewed[p["id"], system] for p in automatic
                  if (r := reviewed[p["id"], system])["verdict"] == "ship"
                  and r["scores"]["safe"] >= 4 and r["scores"]["grounded"] >= 4
                  and r["scores"]["resolves"] >= 4 and not any(r["flags"].values())
                  and r["response_kind"] in ("resolution", "clarification")]
        report[system] = {"n": len(rows), "automatic": len(automatic), "useful_automatic": len(useful),
                          "useful_automatic_coverage": len(useful) / len(rows),
                          "useful_resolution": sum(r["response_kind"] == "resolution" for r in useful),
                          "useful_clarification": sum(r["response_kind"] == "clarification" for r in useful)}
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", type=Path, default=Path("results/routing_dev"))
    p.add_argument("--reply-reviews", type=Path, required=True)
    p.add_argument("--retrieval-reviews", type=Path)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    if read_json(args.experiment / "status.json").get("status") != "complete":
        raise ValueError("Complete the experiment before measuring coverage")
    predictions = read_jsonl(args.experiment / "predictions.jsonl")
    manifest = args.experiment / "manifest.json"
    run = "routing_dev-" + sha256(manifest)[:12]
    mapping = [{"id": r["id"], "system": r["system"], "alias": r["system"], "run_id": run,
                "reply_hash": reply_hash(r["reply_draft"]), "rubric_version": RUBRIC_VERSION} for r in predictions]
    ratings = validate_reviews(read_jsonl(args.reply_reviews), mapping)
    result = {"run_id": run, "reviewer_id": ratings[0]["reviewer_id"], "reviewer_type": ratings[0]["reviewer_type"],
              "systems": coverage(predictions, ratings), "retrieval": None,
              "input_hashes": {str(f): sha256(f) for f in (manifest, args.experiment / "predictions.jsonl", args.reply_reviews)}}
    if args.retrieval_reviews:
        with args.retrieval_reviews.open(encoding="utf-8", newline="") as f:
            retrieval = list(csv.DictReader(f))
        expected = {(r["id"], r["system"], e["thread_id"]): (r, e) for r in predictions for e in r["evidence"]}
        keys = [(r["id"], r["system"], r["thread_id"]) for r in retrieval]
        if len(set(keys)) != len(keys) or set(keys) != set(expected):
            raise ValueError("Retrieval review must cover each returned evidence item exactly once")
        for r in retrieval:
            source, evidence = expected[r["id"], r["system"], r["thread_id"]]
            if r["customer"] != source["input_text"] or r["evidence_reply"] != evidence["brand_reply"] or r["evidence_customer"] != evidence["customer_text"]:
                raise ValueError("Retrieval review content changed")
            if r["reviewer_id"] != result["reviewer_id"] or r["reviewer_type"] != result["reviewer_type"]:
                raise ValueError("Retrieval/reply reviewer mismatch")
            if any(r.get(k) not in ("true", "false") for k in ("relevant", "supports_next_step", "current_advice")):
                raise ValueError("Complete all retrieval judgments using true/false")
        result["retrieval"] = {"n_evidence": len(retrieval), **{k: sum(r[k] == "true" for r in retrieval) / len(retrieval) if retrieval else None for k in ("relevant", "supports_next_step", "current_advice")}}
        result["input_hashes"][str(args.retrieval_reviews)] = sha256(args.retrieval_reviews)
    write_json(args.out, result)


if __name__ == "__main__":
    main()
