"""Controlled development experiment: current routing, message-first routing, trained TF-IDF.

Default is cache-only. --live-free-tier permits configured Gemini calls. Never promotes a variant.
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz, process

from cadence.agent.pipeline import SupportAgent
from cadence.agent.selective import SelectiveAgent
from cadence.baselines.simple import TrainedIntentBaseline
from cadence.config import Paths, intent_ids, model_name
from cadence.eval.metrics import escalation_metrics, intent_metrics
from cadence.eval.paired import compare
from cadence.eval.provenance import revision, sha256
from cadence.llm.gemini import GeminiClient
from cadence.retrieval.index import Retriever
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def validate_splits(train, evaluation):
    if not evaluation or any(r.get("split") != "dev" or not r.get("gold") for r in evaluation):
        raise ValueError("Explicit labeled development rows are required")
    if len({r["id"] for r in evaluation}) != len(evaluation):
        raise ValueError("Duplicate development IDs")
    if any(r["gold"].get("intent") not in intent_ids() or type(r["gold"].get("should_escalate")) is not bool for r in evaluation):
        raise ValueError("Invalid intent or escalation label")
    train_ids, train_threads = {r["id"] for r in train}, {r["thread_id"] for r in train}
    if train_ids & {r["id"] for r in evaluation} or train_threads & {r["thread_id"] for r in evaluation}:
        raise ValueError("Training/development overlap")
    texts = [r["text"] for r in train]
    if any(process.extractOne(r["text"], texts, scorer=fuzz.ratio, score_cutoff=85) for r in evaluation):
        raise ValueError("Near duplicate across training/development")


def reliability(rows, truth):
    bins = []
    for lower in (0, .2, .4, .6, .8):
        members = [r for r in rows if r.get("intent_confidence") is not None and
                   lower <= r["intent_confidence"] <= round(lower+.2, 1) and (lower == 0 or r["intent_confidence"] > lower)]
        bins.append({"range": [lower, round(lower+.2, 1)], "n": len(members),
                     "mean_confidence": float(np.mean([r["intent_confidence"] for r in members])) if members else None,
                     "accuracy": float(np.mean([r["intent"] == truth[r["id"]]["gold"]["intent"] for r in members])) if members else None})
    return bins


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, default=Paths.DATA / "routing_dev/labels.jsonl")
    p.add_argument("--train", type=Path, default=Paths.GOLDEN)
    p.add_argument("--out", type=Path, default=Paths.RESULTS / "routing_dev")
    p.add_argument("--live-free-tier", action="store_true")
    p.add_argument("--baseline-only", action="store_true", help="Run the learned baseline offline; leave Gemini variants pending")
    args = p.parse_args()
    train, golden = read_jsonl(args.train), read_jsonl(args.labels)
    validate_splits(train, golden)
    # This experiment cannot silently reuse the inspected frozen benchmark.
    held = {r["thread_id"] for r in read_jsonl(Paths.DATA / "holdout/examples.jsonl")}
    if held & {r["thread_id"] for r in golden}:
        raise ValueError("Consumed benchmark is not new development data")
    watched = sorted([*Paths.ROOT.glob("src/cadence/**/*.py"), *Paths.CONFIG.glob("*.yaml"),
                      *Paths.CONFIG.glob("*.json"), Path(__file__), args.labels, args.train])
    frozen = {"inputs": {str(f.relative_to(Paths.ROOT)).replace("\\", "/"): sha256(f) for f in watched},
              "threshold": .9, "model": model_name("agent"), "n": len(golden),
              "label_sources": sorted({r.get("label_source", "unspecified") for r in golden}),
              "training_n": len(train), "training_source": "historical inspected labels designated training",
              "selection_rule": "No promotion without fresh confirmation and reviewed useful coverage; retain current live path",
              "systems": ["agent", "selective", "trained_tfidf_lr"]}
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "manifest.json"
    if path.exists() and read_json(path)["frozen"] != frozen:
        raise ValueError("Experiment code/data changed; use a new output directory")
    if not path.exists():
        write_json(path, {"frozen": frozen, "revision": revision(Paths.ROOT), "purpose": "development, not final generalization"})
    os.environ["CADENCE_CACHE_ONLY"] = "0" if args.live_free_tier else "1"
    threads = read_jsonl(Paths.THREADS)
    texts = [t["customer_text"] for t in threads]
    excluded = {r["thread_id"] for r in golden}
    for r in golden:
        excluded.update(threads[i]["thread_id"] for _, _, i in process.extract(r["text"], texts, scorer=fuzz.ratio, score_cutoff=85, limit=None))
    retriever = Retriever.build([t for t in threads if t["thread_id"] not in excluded])
    predictions_path = args.out / "predictions.jsonl"
    rows = read_jsonl(predictions_path)
    done = {(r["id"], r["system"]) for r in rows}
    expected = {(g["id"], s) for g in golden for s in frozen["systems"]}
    if len(done) != len(rows) or not done <= expected:
        raise ValueError("Unexpected or duplicate saved prediction")
    baseline = TrainedIntentBaseline().fit(train)
    baseline_rows = baseline.run(golden, retriever, exclude_thread_ids=excluded)
    for r in baseline_rows:
        if (r.id, r.system) not in done:
            row = r.model_dump()
            rows.append(row)
            write_jsonl(predictions_path, [row], append=True)
    if args.baseline_only:
        baseline_by_id = {r.id: r for r in baseline_rows}
        write_json(args.out / "baseline_summary.json", {
            "status": "baseline_only", "n": len(golden), "label_sources": frozen["label_sources"],
            "intent": intent_metrics([g["gold"]["intent"] for g in golden], [baseline_by_id[g["id"]].intent for g in golden], intent_ids()),
            "escalation": escalation_metrics([g["gold"]["should_escalate"] for g in golden], [baseline_by_id[g["id"]].decision == "escalate" for g in golden]),
            "model_calls": 0, "remaining": "Current and selective Gemini variants have not run",
        })
        print("Offline learned baseline complete; Gemini variants pending.")
        return
    client = GeminiClient(model_name("agent"), cache_path=args.out / "calls.sqlite", deadline_s=55)
    agents = {"agent": SupportAgent(client, retriever, threshold=.9),
              "selective": SelectiveAgent(client, retriever, threshold=.9, system_name="selective")}
    try:
        for g in golden:
            for system, agent in agents.items():
                if (g["id"], system) in done:
                    continue
                try:
                    row = agent.handle(g["text"], id=g["id"], exclude_thread_ids=excluded).model_dump()
                except Exception as exc:
                    write_jsonl(args.out / "errors.jsonl", [{"id": g["id"], "system": system, "error_type": type(exc).__name__}], append=True)
                    write_json(args.out / "status.json", {"status": "partial", "completed": len(rows), "expected": len(expected)})
                    raise
                rows.append(row)
                write_jsonl(predictions_path, [row], append=True)
                print(f"saved {g['id']} {system} calls={row['trace']['model_calls']}", flush=True)
    finally:
        client.close()
    grouped = {s: [r for r in rows if r["system"] == s] for s in frozen["systems"]}
    truth = {g["id"]: g for g in golden}
    report = {"status": "complete", "kind": "exploratory development with explicit label provenance", "n": len(golden),
              "label_sources": frozen["label_sources"], "promotion": "not promoted; human usefulness and fresh confirmation required",
              "comparisons": {s: compare(golden, rs, grouped["agent"]) for s, rs in grouped.items() if s != "agent"},
              "runtime": {s: {"n": len(rs), "p50_ms": float(np.median([r['latency_ms'] for r in rs])),
                               "p95_ms": float(np.percentile([r['latency_ms'] for r in rs], 95)),
                               "model_calls": sum(r['trace'].get('model_calls', 0) for r in rs) if s != "trained_tfidf_lr" else 0,
                               "prompt_tokens": sum(r['trace'].get('prompt_tokens', 0) for r in rs),
                               "output_tokens": sum(r['trace'].get('output_tokens', 0) for r in rs),
                               "cached": sum(r['cached'] for r in rs)} for s, rs in grouped.items()},
              "reliability_bins": {s: reliability(rs, truth) for s, rs in grouped.items() if s != "trained_tfidf_lr"},
              "useful_automatic_coverage": None, "usefulness_status": "Requires completed reply and retrieval reviews",
              "excluded_retrieval_threads": len(excluded)}
    write_json(args.out / "summary.json", report)
    write_json(args.out / "status.json", {"status": "complete", "completed": len(rows), "expected": len(expected)})
    review_file = args.out / "retrieval_review.csv"
    if not review_file.exists():
        with review_file.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "system", "thread_id", "customer", "evidence_customer", "evidence_reply", "relevant", "supports_next_step", "current_advice", "reviewer_id", "reviewer_type", "rationale"])
            writer.writeheader()
            for r in rows:
                for e in r["evidence"]:
                    writer.writerow({"id": r["id"], "system": r["system"], "thread_id": e["thread_id"], "customer": r["input_text"], "evidence_customer": e["customer_text"], "evidence_reply": e["brand_reply"]})
    print("Complete exploratory experiment; live routing unchanged.")


if __name__ == "__main__":
    main()
