"""Score every system's reply draft with the comparative LLM judge (CONTRACT.md §13, §15.5).

Usage (from repo root):
    python scripts/05_judge.py [--split test|dev|all] [--limit N] [--fresh] [--systems agent,simple,trivial]

Reads ``data/golden/golden_set.jsonl`` and ``results/predictions.jsonl``, appends JudgeScore rows to
``results/judge_scores.jsonl`` as each example is judged, and resumes by skipping ids that already have
a row for every requested system. ``--fresh`` discards the existing scores first. Needs a Gemini key
unless the calls are already in ``cache/llm_cache.sqlite`` (or ``CADENCE_LLM=mock``).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from cadence.config import JUDGED_SYSTEMS, Paths  # noqa: E402
from cadence.eval.judge import judged_ids, run_judge  # noqa: E402
from cadence.utils.io import read_jsonl, write_jsonl  # noqa: E402
from cadence.utils.log import get_logger  # noqa: E402

log = get_logger("scripts.05_judge")


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--split", choices=("test", "dev", "all"), default="test", help="golden split to judge"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="judge at most N examples (after resume filtering)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="discard existing judge_scores.jsonl and start over"
    )
    parser.add_argument(
        "--systems", default=",".join(JUDGED_SYSTEMS), help="comma-separated systems to compare"
    )
    parser.add_argument("--golden", type=Path, default=None, help="override golden_set.jsonl path")
    parser.add_argument("--predictions", type=Path, default=None, help="override predictions.jsonl path")
    parser.add_argument("--out", type=Path, default=None, help="override judge_scores.jsonl path")
    parser.add_argument(
        "--workers", type=int, default=None,
        help="concurrent judge calls (default: one per configured API key, 1 in cache-only/mock mode)",
    )
    args = parser.parse_args(argv)
    if args.workers is None:
        from cadence.config import api_keys, cache_only

        args.workers = 1 if (cache_only() or os.environ.get("CADENCE_LLM") == "mock") else max(1, len(api_keys()))
    args.workers = max(1, int(args.workers))
    return args


def _group_predictions(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("system")), []).append(row)
    return grouped


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    args = _parse(argv)
    golden_path = args.golden or Paths.GOLDEN
    predictions_path = args.predictions or Paths.PREDICTIONS
    out_path = args.out or Paths.JUDGE_SCORES
    systems = tuple(s.strip() for s in args.systems.split(",") if s.strip())

    if not golden_path.exists():
        log.error("golden set not found at %s", golden_path)
        return 1
    if not predictions_path.exists():
        log.error("predictions not found at %s; run scripts/04_run_agent.py first", predictions_path)
        return 1

    golden = sorted(read_jsonl(golden_path), key=lambda g: str(g.get("id")))
    if args.split != "all":
        golden = [g for g in golden if g.get("split") == args.split]
    predictions = _group_predictions(read_jsonl(predictions_path))
    missing = [s for s in systems if s not in predictions]
    if missing:
        log.warning("no predictions for systems %s; they will be absent from the comparison", missing)

    if args.fresh and out_path.exists():
        out_path.unlink()
        log.info("--fresh: removed %s", out_path)
    existing = read_jsonl(out_path) if out_path.exists() else []
    skip = judged_ids(existing, systems)
    pending = [g for g in golden if str(g.get("id")) not in skip]
    if args.limit is not None:
        pending = pending[: args.limit]
    log.info(
        "split=%s golden=%d already judged=%d to judge=%d",
        args.split,
        len(golden),
        len(golden) - len(pending),
        len(pending),
    )
    if not pending:
        return 0

    def sink(rows: list[dict]) -> None:
        write_jsonl(out_path, rows, append=True)

    rows = run_judge(pending, predictions, None, systems, sink=sink, workers=args.workers)
    log.info("wrote %d judge rows to %s (total now %d)", len(rows), out_path, len(existing) + len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
