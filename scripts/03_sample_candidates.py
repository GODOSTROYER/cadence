"""Stratified golden-set candidate sampling -> ``data/golden/candidates.jsonl``.

Reads ``config/intents.yaml`` at runtime (keyword buckets), ``spotify_openers.parquet`` and
``spotify_threads.jsonl.gz`` (historical threads). Deterministic with ``SEED``; prints the bucket
histogram. Re-run after improving the intent keywords.

    python scripts/03_sample_candidates.py [--target 420] [--per-bucket 30] [--n-short 15]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.table import Table

from cadence.config import SEED, Paths
from cadence.data.sample import (
    SamplingPlan,
    bucket_histogram,
    load_intent_keywords,
    sample_candidates,
    to_candidate_rows,
)
from cadence.utils.io import iter_jsonl, write_jsonl
from cadence.utils.log import get_logger

log = get_logger("scripts.03_sample_candidates")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    defaults = SamplingPlan()
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--openers", type=Path, default=Paths.OPENERS, help="spotify_openers.parquet")
    parser.add_argument("--threads", type=Path, default=Paths.THREADS, help="spotify_threads.jsonl.gz")
    parser.add_argument("--out", type=Path, default=Paths.CANDIDATES, help="candidates.jsonl")
    parser.add_argument(
        "--target", type=int, default=defaults.target, help="approximate number of candidates"
    )
    parser.add_argument(
        "--per-bucket", type=int, default=defaults.per_bucket, help="max draws per keyword bucket"
    )
    parser.add_argument("--n-short", type=int, default=defaults.n_short, help="short_or_media draws")
    parser.add_argument("--min-random-share", type=float, default=defaults.min_random_share)
    parser.add_argument(
        "--dedupe-ratio", type=float, default=defaults.dedupe_ratio, help="rapidfuzz ratio threshold"
    )
    parser.add_argument("--seed", type=int, default=SEED)
    return parser.parse_args(argv)


def _print_histogram(rows: list[dict], console: Console) -> None:
    table = Table(title=f"candidate buckets (n={len(rows)})")
    table.add_column("bucket")
    table.add_column("count", justify="right")
    table.add_column("share", justify="right")
    for bucket, count in bucket_histogram(r["sampling_bucket"] for r in rows):
        table.add_row(bucket, str(count), f"{count / len(rows):.1%}")
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    t0 = time.perf_counter()
    for path in (args.openers, args.threads):
        if not path.exists():
            raise FileNotFoundError(f"{path} not found; run scripts/01_prepare_data.py first")
    plan = SamplingPlan(
        target=args.target,
        per_bucket=args.per_bucket,
        n_short=args.n_short,
        min_random_share=args.min_random_share,
        dedupe_ratio=args.dedupe_ratio,
        seed=args.seed,
    )
    matchers = load_intent_keywords()
    openers = pd.read_parquet(args.openers)
    sampled = sample_candidates(openers, matchers, plan)
    threads_by_id = {t["thread_id"]: t for t in iter_jsonl(args.threads)}
    rows = to_candidate_rows(sampled, threads_by_id)
    write_jsonl(args.out, rows)

    console = Console()
    _print_histogram(rows, console)
    n_random = sum(1 for r in rows if r["sampling_bucket"] == "random")
    months = sorted({r["created_at"][:7] for r in rows})
    log.info(
        "wrote %d candidates to %s (random share %.1f%%, %d months: %s..%s) in %.1fs",
        len(rows),
        args.out,
        100 * n_random / len(rows),
        len(months),
        months[0],
        months[-1],
        time.perf_counter() - t0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
