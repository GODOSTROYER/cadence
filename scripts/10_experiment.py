"""Paired dev experiment. Never uses the locked holdout or overwrites historical results.

Default is cache-only. --live-free-tier explicitly uses the owner's configured free-tier keys.
Same model, prompt, policy, threshold and examples; only evidence count changes (6 versus 0).
"""

from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from cadence.agent.pipeline import SupportAgent
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
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--judge-limit", type=int, default=20)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out", type=Path, default=Paths.RESULTS / "dev_experiment")
    args = p.parse_args(argv)
    os.environ["CADENCE_CACHE_ONLY"] = "0" if args.live_free_tier else "1"
    rows = [g for g in read_jsonl(Paths.GOLDEN) if g["split"] == "dev"][: args.limit]
    if not rows:
        raise ValueError("No dev examples")
    args.out.mkdir(parents=True, exist_ok=True)
    watched = sorted(
        [
            *Paths.ROOT.glob("src/cadence/agent/*.py"),
            *Paths.ROOT.glob("src/cadence/retrieval/*.py"),
            *Paths.CONFIG.glob("*"),
            Paths.GOLDEN,
        ]
    )
    fingerprint = {
        str(f.relative_to(Paths.ROOT)).replace("\\", "/"): sha256(f) for f in watched if f.is_file()
    }
    meta_path = args.out / "manifest.json"
    if meta_path.exists() and read_json(meta_path)["inputs"] != fingerprint:
        raise ValueError("Code/data changed: use a new --out directory; do not mix runs")
    write_json(
        meta_path,
        {
            "inputs": fingerprint,
            "revision": revision(Paths.ROOT),
            "split": "dev",
            "human_validated": False,
            "threshold": 0.9,
            "n": len(rows),
            "mode": "free-tier-network-permitted" if args.live_free_tier else "cache-only",
        },
    )
    retriever = Retriever.build(read_jsonl(Paths.THREADS))
    client = GeminiClient(model_name("agent"), cache_path=args.out / "calls.sqlite", deadline_s=55)
    agents = {
        name: SupportAgent(client, retriever, k=k, threshold=0.9, system_name=name)
        for name, k in (("agent", 6), ("agent_no_evidence", 0))
    }
    predictions_path = args.out / "predictions.jsonl"
    predictions = read_jsonl(predictions_path)
    done = {(r["id"], r["system"]) for r in predictions}
    pending = [(g, s) for g in rows for s in agents if (g["id"], s) not in done]

    def run(item):
        g, s = item
        return agents[s].handle(g["text"], id=g["id"], exclude_thread_ids={g["thread_id"]}).model_dump()

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run, pending):
            write_jsonl(predictions_path, [result], append=True)
            predictions.append(result)
            print(f"saved {result['id']} {result['system']} cached={result['cached']}", flush=True)
    aligned = {
        s: [r for r in predictions if r["system"] == s and r["id"] in {g["id"] for g in rows}] for s in agents
    }
    result = compare(rows, aligned["agent"], aligned["agent_no_evidence"])
    # Separate the model proposal from release guards: no-evidence cannot substantiate citations.
    raw = {s: [{**r, "decision": r["trace"]["llm_decision"]} for r in aligned[s]] for s in agents}
    result["raw_model_proposal"] = compare(rows, raw["agent"], raw["agent_no_evidence"])
    result["runtime"] = {
        s: {
            "n": len(rs),
            "live_n": sum(not r["cached"] for r in rs),
            "observed_latency_ms": dict(
                zip(
                    ("p50", "p95"),
                    np.percentile([r["latency_ms"] for r in rs], [50, 95]).tolist(),
                    strict=True,
                )
            ),
            "prompt_tokens": sum(r["trace"]["prompt_tokens"] for r in rs),
            "output_tokens": sum(r["trace"]["output_tokens"] for r in rs),
            "integrity_blocked": sum(r["trace"]["integrity_blocked"] for r in rs),
        }
        for s, rs in aligned.items()
    }
    write_json(args.out / "comparison.json", result)
    judge = GeminiClient(model_name("judge"), cache_path=args.out / "calls.sqlite", deadline_s=55)
    scores_path = args.out / "judge_orders.jsonl"
    scores = read_jsonl(scores_path)
    judged = {r["id"] for r in scores if sum(x["id"] == r["id"] for x in scores) == 4}
    by_id = {s: {r["id"]: r for r in rs} for s, rs in aligned.items()}
    for g in rows[: args.judge_limit]:
        if g["id"] in judged:
            continue
        scored = judge_pair(g, by_id["agent"][g["id"]], by_id["agent_no_evidence"][g["id"]], judge)
        write_jsonl(scores_path, scored, append=True)
        scores.extend(scored)
    if scores:
        pairs = []
        for gid in sorted({r["id"] for r in scores}):
            deltas = [
                next(
                    r["scores"]["overall"]
                    for r in scores
                    if r["id"] == gid and r["system"] == "agent" and r["order_id"] == o
                )
                - next(
                    r["scores"]["overall"]
                    for r in scores
                    if r["id"] == gid and r["system"] == "agent_no_evidence" and r["order_id"] == o
                )
                for o in (0, 1)
            ]
            pairs.append(deltas)
        means = np.mean(pairs, axis=1)
        rng = np.random.default_rng(2026)
        ci = np.percentile(
            [np.mean(rng.choice(means, len(means))) for _ in range(2000)], [2.5, 97.5]
        ).tolist()
        write_json(
            args.out / "judge_comparison.json",
            {
                "n": len(pairs),
                "human_agreement": None,
                "mean_overall_delta": float(means.mean()),
                "ci95": ci,
                "preference_order_consistency": float(np.mean([np.sign(a) == np.sign(b) for a, b in pairs])),
                "position_means": {
                    str(pos): float(np.mean([r["scores"]["overall"] for r in scores if r["position"] == pos]))
                    for pos in (1, 2)
                },
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
