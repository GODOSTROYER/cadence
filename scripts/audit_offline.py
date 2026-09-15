"""Recompute audit measurements without network calls. Does not inspect holdout labels."""

from __future__ import annotations

import platform
import sqlite3
import time
from collections import Counter, defaultdict

import numpy as np
from rapidfuzz import fuzz, process

from cadence.config import Paths
from cadence.eval.metrics import apply_threshold
from cadence.eval.paired import compare
from cadence.eval.provenance import revision
from cadence.retrieval.index import Retriever
from cadence.utils.io import read_jsonl, write_json


def main(argv=None):
    out = Paths.RESULTS / "audit"
    out.mkdir(parents=True, exist_ok=True)
    golden = read_jsonl(Paths.GOLDEN)
    test = [g for g in golden if g["split"] == "test"]
    ids = {g["id"] for g in test}
    predictions = read_jsonl(Paths.PREDICTIONS)
    agent = apply_threshold([r for r in predictions if r["system"] == "agent" and r["id"] in ids], 0.9)
    zero = [r for r in predictions if r["system"] == "llm_zero_shot" and r["id"] in ids]
    start = time.perf_counter()
    threads = read_jsonl(Paths.THREADS)
    read_seconds = time.perf_counter() - start
    start = time.perf_counter()
    retriever = Retriever.build(threads)
    build_seconds = time.perf_counter() - start
    durations = []
    duplicates = []
    corpus_texts = [t["customer_text"].casefold() for t in threads]
    for g in golden:
        start = time.perf_counter()
        retriever.search(g["text"], exclude_thread_ids={g["thread_id"]})
        durations.append((time.perf_counter() - start) * 1000)
        matches = process.extract(
            g["text"].casefold(), corpus_texts, scorer=fuzz.ratio, score_cutoff=90, limit=10
        )
        others = [threads[i]["thread_id"] for _, _, i in matches if threads[i]["thread_id"] != g["thread_id"]]
        if others:
            duplicates.append({"id": g["id"], "near_duplicate_threads": others})
    with sqlite3.connect(Paths.LLM_CACHE.as_uri() + "?mode=ro", uri=True) as conn:
        records = conn.execute("SELECT model,latency_ms,prompt_tokens,output_tokens FROM calls").fetchall()
    grouped = defaultdict(list)
    for r in records:
        grouped[r[0]].append(r[1:])
    recorded = {
        model: {
            "n": len(rs),
            "recorded_call_latency_ms": dict(
                zip(("p50", "p95"), np.percentile([r[0] for r in rs], [50, 95]).tolist(), strict=True)
            ),
            "input_tokens": sum(r[1] for r in rs),
            "output_tokens": sum(r[2] for r in rs),
        }
        for model, rs in grouped.items()
    }
    memory = None
    try:
        import psutil

        memory = psutil.Process().memory_info().rss
    except ImportError:
        pass
    report = {
        "revision": revision(Paths.ROOT),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "historical_agent_vs_zero_shot": compare(test, agent, zero),
        "retrieval": {
            "n_queries": len(durations),
            "read_seconds": read_seconds,
            "build_seconds": build_seconds,
            "p50_ms": float(np.median(durations)),
            "p95_ms": float(np.percentile(durations, 95)),
            "rss_bytes_after_build_and_queries": memory,
        },
        "historical_cache": recorded,
        "golden_with_near_duplicate_corpus_text": len(duplicates),
        "duplicates": duplicates,
        "label_provenance": "AI-labelled; human agreement unavailable",
        "live_deployed_latency": None,
        "retrieval_multipliers": dict(Counter(float(x) for x in retriever._multipliers)),
        "limitations": [
            "Cache call latency is historical, not current network or endpoint latency",
            "RSS is process memory, not isolated index memory",
            "Paired zero-shot comparison changes prompt and policy, not a retrieval-only ablation",
        ],
    }
    write_json(out / "offline_measurements.json", report)
    print(f"Wrote {out / 'offline_measurements.json'}")


if __name__ == "__main__":
    main()
