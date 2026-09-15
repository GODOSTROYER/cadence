"""Run a human-labelled locked holdout once at a frozen commit; resumable, no threshold tuning.

Validate labels with script 09 and commit code + labels first. Default prohibits model network calls.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cadence.agent.pipeline import SupportAgent
from cadence.baselines._common import build_response
from cadence.baselines.nn_reply import nearest_reply
from cadence.baselines.simple import keyword_intent, rules_decision
from cadence.baselines.trivial import majority_intent, run_trivial
from cadence.config import Paths, model_name
from cadence.eval.blind_judge import judge_pair
from cadence.eval.paired import compare
from cadence.eval.provenance import revision, sha256
from cadence.llm.gemini import GeminiClient
from cadence.retrieval.index import Retriever
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live-free-tier", action="store_true")
    p.add_argument("--directory", type=Path, default=Paths.DATA / "holdout")
    p.add_argument("--out", type=Path, default=Paths.RESULTS / "holdout")
    p.add_argument(
        "--judge", action="store_true", help="Two-order judge on all 200 pairs; up to 400 extra calls"
    )
    p.add_argument(
        "--ai-reviewed",
        action="store_true",
        help="Use explicitly AI-reviewed labels instead of claiming human labels",
    )
    p.add_argument("--workers", type=int, default=2)
    args = p.parse_args(argv)
    spec = importlib.util.spec_from_file_location(
        "human_validator", Paths.ROOT / "scripts/09_validate_human_labels.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    if args.ai_reviewed:
        review_lock = read_json(args.directory / "AI_REVIEW.lock.json")
        label_path = args.directory / "ai_reviewed_set.jsonl"
        if (
            sha256(label_path) != review_lock["labels_sha256"]
            or sha256(args.directory / "HOLDOUT.lock.json") != review_lock["source_lock_sha256"]
        ):
            raise ValueError("AI-reviewed benchmark was changed after locking")
        sample_lock = read_json(args.directory / "HOLDOUT.lock.json")
        for name, digest in sample_lock["files"].items():
            if sha256(args.directory / name) != digest:
                raise ValueError("Locked sample changed")
        golden = read_jsonl(label_path)
        if any(g.get("label_source") != "ai" for g in golden):
            raise ValueError("Incorrect AI label provenance")
    else:
        golden = validator.validate(args.directory)
        label_path = args.directory / "human_labels.csv"
    state = revision(Paths.ROOT)
    manifest_path = args.out / "manifest.json"
    frozen = {
        "commit": state["commit"],
        "labels": sha256(label_path),
        "label_source": "ai" if args.ai_reviewed else "human",
        "lock": sha256(args.directory / "HOLDOUT.lock.json"),
        "threshold": 0.9,
        "files": {
            str(f.relative_to(Paths.ROOT)).replace("\\", "/"): sha256(f)
            for directory in (Paths.ROOT / "src", Paths.ROOT / "scripts", Paths.CONFIG)
            for f in sorted(directory.rglob("*"))
            if f.suffix in {".py", ".yaml", ".json"}
        },
    }
    if manifest_path.exists():
        if read_json(manifest_path) != frozen:
            raise ValueError(
                "Holdout run is frozen at another code/label revision. Do not tune on this holdout."
            )
    else:
        if state["dirty"] or not state["commit"]:
            raise ValueError("Commit the code and human labels before first holdout execution")
        args.out.mkdir(parents=True, exist_ok=True)
        write_json(manifest_path, frozen)
    os.environ["CADENCE_CACHE_ONLY"] = "0" if args.live_free_tier else "1"
    # Every locked opener is excluded from ALL retrieval calls, not just its own query.
    excluded = {g["thread_id"] for g in golden}
    threads = [t for t in read_jsonl(Paths.THREADS) if t["thread_id"] not in excluded]
    retriever = Retriever.build(threads)
    client = GeminiClient(model_name("agent"), cache_path=args.out / "calls.sqlite")
    systems = {
        s: SupportAgent(client, retriever, k=k, threshold=0.9, system_name=s)
        for s, k in (("agent", 6), ("agent_no_evidence", 0))
    }
    path = args.out / "predictions.jsonl"
    predictions = read_jsonl(path)
    done = {(r["id"], r["system"]) for r in predictions}
    # Majority intent fitted on the old DEV partition only; never on holdout labels.
    majority = majority_intent([g for g in read_jsonl(Paths.GOLDEN) if g["split"] == "dev"])

    def predict(item):
        g, system = item
        if system in systems:
            row = systems[system].handle(g["text"], id=g["id"], exclude_thread_ids=excluded).model_dump()
        elif system == "trivial":
            row = run_trivial([{**g, "gold": {"intent": majority}}])[0].model_dump()
        else:
            outcome = rules_decision(g["text"])
            neighbour = nearest_reply(retriever, g["text"], excluded)
            row = build_response(
                id=g["id"],
                system=system,
                input_text=g["text"],
                intent=keyword_intent(g["text"]),
                decision=outcome.decision,
                escalation=outcome.escalation,
                rule_flags=outcome.rule_flags,
                reply_draft=neighbour.reply,
                citations=neighbour.citations,
                evidence=neighbour.evidence,
                model="keyword+nearest_reply",
            ).model_dump()
        return row

    pending = [
        (g, s)
        for g in golden
        for s in ("agent", "agent_no_evidence", "trivial", "simple_keyword")
        if (g["id"], s) not in done
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for row in pool.map(predict, pending):
            write_jsonl(path, [row], append=True)
            predictions.append(row)
            print(f"saved {row['id']} {row['system']} cached={row['cached']}", flush=True)
    grouped = {
        s: [r for r in predictions if r["system"] == s]
        for s in ("agent", "agent_no_evidence", "trivial", "simple_keyword")
    }
    write_json(
        args.out / "comparisons.json",
        {s: compare(golden, grouped["agent"], rs) for s, rs in grouped.items() if s != "agent"},
    )
    if args.judge:
        judge = GeminiClient(model_name("judge"), cache_path=args.out / "calls.sqlite")
        scores_path = args.out / "judge_orders.jsonl"
        scores = read_jsonl(scores_path)

        def grade(g):
            pair = [next(r for r in grouped[s] if r["id"] == g["id"]) for s in ("agent", "simple_keyword")]
            return judge_pair(g, *pair, judge)

        todo = [g for g in golden if sum(r["id"] == g["id"] for r in scores) != 4]
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for new in pool.map(grade, todo):
                write_jsonl(scores_path, new, append=True)
                print(f"judged {new[0]['id']}", flush=True)
    print("Holdout results written. Do not use these errors to tune and re-report the same set.")


if __name__ == "__main__":
    main()
