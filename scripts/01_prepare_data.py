"""Raw TWCS csv -> processed SpotifyCares artefacts (CONTRACT.md §1, §3).

Writes ``data/processed/spotify_threads.jsonl.gz``, ``spotify_openers.parquet``,
``reply_templates.json`` and ``stats.json``. Brand replies carry ``resolved_links`` taken from
``link_map.json``; that map is produced by ``scripts/resolve_links.py`` (network). Pass
``--skip-links`` to reuse an existing map without touching the network.

    python scripts/01_prepare_data.py [--skip-links] [--top-links 150]
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from cadence.config import BRAND, Paths
from cadence.data.links import DEFAULT_TIMEOUT, DEFAULT_TOP_N, DEFAULT_WORKERS, collect_links, resolve_links
from cadence.data.load import brand_subgraph, load_twcs
from cadence.data.summarize import compute_stats, openers_table, reply_templates
from cadence.data.threads import build_threads
from cadence.utils.io import read_json, write_json, write_jsonl
from cadence.utils.log import get_logger

log = get_logger("scripts.01_prepare_data")


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv", type=Path, default=Paths.RAW_TWCS, help="path to twcs.csv")
    parser.add_argument("--brand", default=BRAND, help="brand author_id (default SpotifyCares)")
    parser.add_argument("--out-dir", type=Path, default=Paths.PROCESSED, help="output directory")
    parser.add_argument(
        "--skip-links", action="store_true", help="reuse an existing link_map.json (no network)"
    )
    parser.add_argument(
        "--top-links", type=int, default=DEFAULT_TOP_N, help="links to resolve when not skipping"
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    return parser.parse_args(argv)


class _Timer:
    """Records wall-clock seconds per named stage."""

    def __init__(self) -> None:
        self.timings: dict[str, float] = {}

    def run(self, name: str, fn: Callable[[], Any]) -> Any:
        t0 = time.perf_counter()
        result = fn()
        self.timings[name] = time.perf_counter() - t0
        log.info("stage %-16s %6.1fs", name, self.timings[name])
        return result


def _load_or_resolve_links(
    args: argparse.Namespace, brand_texts: list[str], link_map_path: Path
) -> dict[str, dict[str, Any]]:
    if args.skip_links:
        if link_map_path.exists():
            link_map = read_json(link_map_path)
            log.info("reusing %s (%d links)", link_map_path, len(link_map))
            return link_map
        log.warning("--skip-links given but %s does not exist; resolved_links will be empty", link_map_path)
        return {}
    counts = collect_links(brand_texts)
    n = min(args.top_links, len(counts))
    with Progress(
        TextColumn("resolving links"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
    ) as bar:
        task = bar.add_task("resolve", total=n)
        link_map = resolve_links(
            counts,
            top_n=args.top_links,
            workers=args.workers,
            timeout=args.timeout,
            progress=lambda _u: bar.advance(task),
        )
    write_json(link_map_path, link_map)
    return link_map


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    timer = _Timer()
    t_start = time.perf_counter()

    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"), TimeElapsedColumn(), transient=True
    ) as bar:
        task = bar.add_task("loading twcs.csv")
        df = timer.run("load_csv", partial(load_twcs, args.csv))
        bar.update(task, description="extracting brand subgraph")
        sub = timer.run("subgraph", partial(brand_subgraph, df, args.brand))
        brand_texts = sub.loc[sub["author_id"] == args.brand, "text"].tolist()
        n_rows_total, n_brand_tweets = len(df), len(brand_texts)
        del df  # free ~2 GB before the per-thread work
        bar.update(task, description="links")

    link_map = timer.run(
        "links", lambda: _load_or_resolve_links(args, brand_texts, out_dir / "link_map.json")
    )

    threads = timer.run("build_threads", lambda: build_threads(sub, args.brand, link_map))
    if not threads:
        raise RuntimeError(f"no threads built for {args.brand!r}; check --brand and the csv")

    threads_path = out_dir / "spotify_threads.jsonl.gz"
    timer.run("write_threads", lambda: write_jsonl(threads_path, threads))

    openers = timer.run("openers_table", lambda: openers_table(threads))
    openers_path = out_dir / "spotify_openers.parquet"
    timer.run("write_parquet", lambda: openers.to_parquet(openers_path, index=False, engine="pyarrow"))

    templates = timer.run(
        "templates",
        lambda: reply_templates((t["first_reply_text"], t["brand_replies"][0]["text_raw"]) for t in threads),
    )
    write_json(out_dir / "reply_templates.json", templates)

    timer.timings["total"] = time.perf_counter() - t_start
    stats = compute_stats(
        openers,
        n_rows_total=n_rows_total,
        n_brand_tweets=n_brand_tweets,
        n_subgraph_tweets=len(sub),
        link_map=link_map,
        timings=timer.timings,
    )
    write_json(out_dir / "stats.json", stats)

    log.info(
        "done: %s threads (%s english), %d templates, link success %.1f%%, %.1fs total -> %s",
        f"{stats['n_threads']:,}",
        f"{stats['n_openers_english']:,}",
        len(templates),
        stats["link_resolution_success_rate"] * 100,
        timer.timings["total"],
        out_dir,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
