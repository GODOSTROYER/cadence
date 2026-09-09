"""Compute the evaluation summary, failure modes and figures (CONTRACT.md §8, §9, §13).

Usage (from repo root):
    python scripts/06_evaluate.py [--n-boot 1000] [--min-recall 0.9] [--no-figures] [--quiet]

Reads the golden set, ``results/predictions.jsonl``, ``results/judge_scores.jsonl`` and
``data/golden/human_ratings.jsonl`` (the last two are optional) and writes
``results/eval_summary.json``, ``results/failure_modes.json`` and ``results/figures/*.png``.
No LLM calls are made.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from cadence.config import Paths  # noqa: E402
from cadence.eval.run_eval import run_eval  # noqa: E402
from cadence.utils.log import get_logger  # noqa: E402

log = get_logger("scripts.06_evaluate")


def _parse(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--n-boot", type=int, default=1000, help="bootstrap resamples for the 95%% CIs")
    parser.add_argument(
        "--min-recall", type=float, default=0.9, help="dev escalation recall the threshold must reach"
    )
    parser.add_argument("--no-figures", action="store_true", help="skip writing results/figures/*.png")
    parser.add_argument("--quiet", action="store_true", help="do not print the console summary")
    parser.add_argument("--golden", type=Path, default=None, help="override golden_set.jsonl path")
    parser.add_argument("--predictions", type=Path, default=None, help="override predictions.jsonl path")
    parser.add_argument("--judge", type=Path, default=None, help="override judge_scores.jsonl path")
    parser.add_argument("--human", type=Path, default=None, help="override human_ratings.jsonl path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns a process exit code."""
    args = _parse(argv)
    try:
        summary = run_eval(
            golden_path=args.golden,
            predictions_path=args.predictions,
            judge_path=args.judge,
            human_path=args.human,
            n_boot=args.n_boot,
            min_recall=args.min_recall,
            make_figures=not args.no_figures,
            quiet=args.quiet,
        )
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    log.info("wrote %s and %s", Paths.EVAL_SUMMARY, Paths.FAILURE_MODES)
    log.info("systems evaluated: %s", ", ".join(summary["meta"]["systems"]) or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
