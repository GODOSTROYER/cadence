"""Recompute historical metrics from hash-verified predictions. Zero model calls.

This is artifact replay, NOT a fresh execution of today's changed agent or a latency benchmark.
"""

from __future__ import annotations

import json
import sqlite3
import time

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.eval.run_eval import run_eval
from cadence.llm.cache import LLMCache
from cadence.utils.io import read_json, write_json


def main(argv=None):
    started = time.perf_counter()
    manifest = read_json(Paths.RESULTS / "recorded_manifest.json")
    for name, digest in manifest["files"].items():
        if sha256(Paths.ROOT / name) != digest:
            raise ValueError(f"Recorded input changed: {name}. Do not overwrite historical evidence.")
    with sqlite3.connect(Paths.LLM_CACHE.as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        calls = conn.execute("SELECT * FROM calls").fetchall()
        for row in calls:
            if (
                LLMCache.key(
                    row["model"], row["system"], row["prompt"], row["schema_json"], row["temperature"]
                )
                != row["key"]
            ):
                raise ValueError("Replay cache key does not match its inputs")
            json.loads(row["response_json"])
    out = Paths.RESULTS / "reproduced"
    out.mkdir(parents=True, exist_ok=True)
    summary = run_eval(
        summary_path=out / "eval_summary.json",
        failures_path=out / "failure_modes.json",
        n_boot=1000,
        make_figures=False,
        quiet=True,
    )
    for key, expected in manifest["headline"].items():
        if isinstance(expected, (float, int)) and abs(summary["headline"][key] - expected) > 1e-10:
            raise ValueError(f"Headline drift: {key}")
    summary["meta"].update(
        {
            "evidence_kind": "historical_artifact_replay",
            "prediction_commit": manifest["prediction_commit"],
            "live_model_calls": 0,
            "cache_receipts_verified": len(calls),
            "reproduction_seconds": round(time.perf_counter() - started, 3),
        }
    )
    write_json(out / "eval_summary.json", summary)
    print(
        json.dumps(
            {
                "kind": "historical_artifact_replay",
                "headline": summary["headline"],
                "threshold_selection": summary["meta"].get("threshold_selection"),
                "seconds": summary["meta"]["reproduction_seconds"],
                "model_calls": 0,
                "cache_receipts_verified": len(calls),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
