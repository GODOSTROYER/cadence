"""Summarize identity-bound supplemental AI or human ratings without rewriting frozen results."""
import argparse
from pathlib import Path

from cadence.eval.provenance import sha256
from cadence.eval.review import reply_hash, review_report
from cadence.utils.io import read_json, read_jsonl, write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", type=Path, default=Path("results/review_study"))
    p.add_argument("--ratings", type=Path, required=True)
    p.add_argument("--judge", type=Path, default=Path("results/holdout_final/judge_orders.jsonl"))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--api-ratings", action="store_true", help="Import local reviewer queue records rather than the 50-message study")
    p.add_argument("--confirmation", type=Path, help="Human verification record for adopted AI-assisted ratings")
    args = p.parse_args()
    for name, digest in read_json(args.judge.parent / "run_status.json")["artifacts"].items():
        if sha256(args.judge.parent / name) != digest:
            raise ValueError(f"Frozen artifact changed: {name}")
    ratings = read_jsonl(args.ratings)
    mapping = read_json(args.study / "mapping.json")
    predictions = {(r["id"], r["system"]): r for r in read_jsonl(args.judge.parent / "predictions.jsonl")}
    packet = {(r["id"], r["alias"]): r for r in read_jsonl(args.study / "blind_packet.jsonl")}
    for row in mapping:
        source = predictions.get((row["id"], row["system"]))
        shown = packet.get((row["id"], row["alias"]))
        if not source or not shown or reply_hash(source["reply_draft"]) != row["reply_hash"] or reply_hash(shown["reply_draft"]) != row["reply_hash"]:
            raise ValueError("Study reply does not match frozen prediction")
    if args.api_ratings:
        from cadence.api.rating_queue import alias_for, plan_pairs
        from cadence.config import Paths
        from cadence.eval.review import RUBRIC_VERSION
        systems = ("agent", "simple_keyword")
        run = "holdout_final-" + read_json(args.judge.parent / "manifest.json")["commit"][:7]
        pairs = plan_pairs(read_jsonl(Paths.DATA / "holdout/ai_reviewed_set.jsonl"), systems=systems)
        mapping = [{"id": i, "system": s, "alias": alias_for(i, s, systems), "run_id": run,
                    "rubric_version": RUBRIC_VERSION, "reply_hash": reply_hash(predictions[i, s]["reply_draft"])} for i, s in pairs]
        ratings = [{**r, "alias": alias_for(r["id"], r["system"], systems)} for r in ratings if r.get("run_id") == run]
    report = review_report(ratings, mapping, read_jsonl(args.judge))
    report["queue"] = "local matched 20-message queue" if args.api_ratings else "50-message supplemental study"
    report["input_hashes"] = {str(f): sha256(f) for f in (args.ratings, args.judge, args.study / "mapping.json", args.study / "blind_packet.jsonl", args.study / "rubric.md")}
    report["scope"] = "Supplemental review of exact frozen replies; original scores unchanged. AI ratings are not human ratings."
    if args.confirmation:
        confirmation = read_json(args.confirmation)
        if confirmation["status"] != "completed" or len(ratings) != confirmation["n_reply_ratings"]:
            raise ValueError("Incomplete human verification")
        for path, digest in confirmation["artifacts"].items():
            if sha256(Path(path)) != digest:
                raise ValueError(f"Verified rating artifact changed: {path}")
        if str(args.ratings).replace("\\", "/") not in confirmation["artifacts"]:
            raise ValueError("Ratings are not bound by the verification record")
        if any(r["reviewer_id"] != confirmation["reviewer"] or r["reviewer_type"] != "human" for r in ratings):
            raise ValueError("Human verification reviewer mismatch")
        report["verification"] = confirmation
        report["input_hashes"][str(args.confirmation)] = sha256(args.confirmation)
        report["scope"] = "Human-verified AI-assisted ratings versus the original Gemini judge. Initially reviewed by GPT-6 Astra at extra-high reasoning, then verified unchanged by Arnav Bule; not an independent blind human rating pass."
    write_json(args.out, report)
    print({k: {f: v[f] for f in ("reviewer_type", "status", "n", "verdicts")} for k, v in report["reviewers"].items()})


if __name__ == "__main__":
    main()
