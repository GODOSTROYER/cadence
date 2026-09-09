"""Resolve the most frequent ``t.co`` links in SpotifyCares replies -> ``data/processed/link_map.json``.

One-time network step (HEAD then GET fallback, redirects followed, 8 s timeout, 8 threads).
Run before ``scripts/01_prepare_data.py`` so brand replies can carry ``resolved_links``.

    python scripts/resolve_links.py [--top 150] [--workers 8] [--timeout 8]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from cadence.config import BRAND, Paths
from cadence.data.links import (
    DEFAULT_TIMEOUT,
    DEFAULT_TOP_N,
    DEFAULT_WORKERS,
    collect_links,
    resolve_links,
    success_rate,
)
from cadence.data.load import load_twcs
from cadence.utils.io import write_json
from cadence.utils.log import get_logger

log = get_logger("scripts.resolve_links")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", type=Path, default=Paths.RAW_TWCS, help="path to twcs.csv")
    parser.add_argument("--brand", default=BRAND, help="brand author_id (default SpotifyCares)")
    parser.add_argument("--out", type=Path, default=Paths.LINK_MAP, help="output json path")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="how many links to resolve")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    t0 = time.perf_counter()
    df = load_twcs(args.csv)
    brand_texts = df.loc[df["author_id"] == args.brand, "text"].tolist()
    counts = collect_links(brand_texts)
    log.info(
        "%d distinct t.co links in %d brand tweets (%d occurrences)",
        len(counts),
        len(brand_texts),
        sum(counts.values()),
    )
    n = min(args.top, len(counts))
    with Progress(
        TextColumn("resolving"), BarColumn(), TextColumn("{task.completed}/{task.total}"), TimeElapsedColumn()
    ) as bar:
        task = bar.add_task("resolve", total=n)
        link_map = resolve_links(
            counts,
            top_n=args.top,
            workers=args.workers,
            timeout=args.timeout,
            progress=lambda _url: bar.advance(task),
        )
    write_json(args.out, link_map)
    rate = success_rate(link_map)
    covered = sum(v["count"] for v in link_map.values() if v["url"])
    log.info(
        "wrote %s: %d/%d links resolved (%.1f%%), covering %d of %d link occurrences; %.1fs total",
        args.out,
        round(rate * len(link_map)),
        len(link_map),
        rate * 100,
        covered,
        sum(counts.values()),
        time.perf_counter() - t0,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
