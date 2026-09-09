"""Processed threads -> BM25 retrieval index (CONTRACT.md §1, §15.2).

Builds ``cache/bm25_index.pkl`` from ``data/processed/spotify_threads.jsonl.gz`` and prints the
numbers the report needs: file size, build time, load time, mean query latency over 100 queries,
and five sample queries with their top-3 hits (customer_text -> first_reply_text preview).

    python scripts/02_build_index.py [--threads PATH] [--out PATH] [--n-queries 100] [--compare-doc-text]

``--compare-doc-text`` additionally builds the alternative document-text variant (customer_text
alone vs customer_text + first_reply_text) and prints both variants' top-3 for the 20 hand-check
queries behind the decision recorded in ``cadence.retrieval.index``.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Any

from cadence.config import SEED, Paths
from cadence.retrieval.index import Hit, Retriever
from cadence.utils.io import read_jsonl
from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws, truncate

log = get_logger("scripts.02_build_index")

HAND_CHECK_QUERIES: tuple[str, ...] = (
    "my app keeps crashing every time i open it since the update",
    "downloaded songs disappeared from offline mode",
    "charged twice this month for premium",
    "student discount not working, says im not eligible",
    "cant log in with facebook anymore",
    "someone else is playing music on my account",
    "songs greyed out in my playlist",
    "please add this artist to spotify, not available in my country",
    "my wrapped 2017 isnt showing up",
    "spotify connect wont find my speaker",
    "web player not playing anything in chrome",
    "how do i cancel my subscription",
    "family plan wont let me invite my sister",
    "the shuffle button is broken it plays the same songs",
    "forgot my password and dont have access to that email",
    "podcasts not loading on android",
    "why did my playlist get deleted",
    "hulu bundle not showing up on my account",
    "app skips songs every few seconds",
    "i want a refund i didnt mean to buy premium",
)
"""The 20 hand-checked queries used for the document-text decision; the first five are the samples."""
N_SAMPLE_QUERIES = 5


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--threads", type=Path, default=Paths.THREADS, help="processed threads jsonl(.gz)")
    parser.add_argument("--out", type=Path, default=Paths.BM25_INDEX, help="where to write the pickle")
    parser.add_argument("--n-queries", type=int, default=100, help="queries for the latency measurement")
    parser.add_argument(
        "--compare-doc-text",
        action="store_true",
        help="also build the other document-text variant and compare",
    )
    return parser.parse_args(argv)


def _timed(fn: Any) -> tuple[Any, float]:
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def measure_latency(retriever: Retriever, threads: list[dict[str, Any]], n_queries: int) -> float:
    """Mean wall-clock milliseconds per ``search`` over ``n_queries`` real customer texts (own thread excluded)."""
    rng = random.Random(SEED)
    sample = rng.sample(threads, min(n_queries, len(threads)))
    retriever.search(sample[0]["customer_text"], k=6)  # warm-up (imports, first sparse gather)
    t0 = time.perf_counter()
    for thread in sample:
        retriever.search(thread["customer_text"], k=6, exclude_thread_ids={thread["thread_id"]})
    return (time.perf_counter() - t0) * 1000.0 / len(sample)


def format_hit(hit: Hit) -> str:
    customer = truncate(normalize_ws(hit.thread.get("customer_text", "")), 90)
    reply = truncate(normalize_ws(hit.thread.get("first_reply_text", "")), 90)
    return f"{hit.score:6.2f} {hit.thread_id:<11} {customer} -> {reply}"


def print_samples(retriever: Retriever, queries: tuple[str, ...], k: int = 3) -> None:
    for query in queries:
        print(f"\nQ: {query}")
        for hit in retriever.search(query, k=k):
            print("   " + format_hit(hit))


def compare_doc_text(threads: list[dict[str, Any]], primary: Retriever) -> None:
    """Print top-3 hits of both document-text variants for every hand-check query."""
    other, seconds = _timed(lambda: Retriever.build(threads, include_reply=not primary.include_reply))
    print(f"\n== document-text comparison (alternative variant built in {seconds:.2f}s) ==")
    for query in HAND_CHECK_QUERIES:
        print(f"\nQ: {query}")
        for retriever in (primary, other):
            label = "customer+reply" if retriever.include_reply else "customer only "
            for i, hit in enumerate(retriever.search(query, k=3)):
                prefix = f"  [{label}]" if i == 0 else " " * (len(label) + 4)
                print(f"{prefix} {format_hit(hit)}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    Paths.ensure_dirs()
    if not args.threads.exists():
        log.error("threads file not found: %s (run scripts/01_prepare_data.py first)", args.threads)
        return 1

    threads, read_s = _timed(lambda: read_jsonl(args.threads))
    log.info("read %d threads from %s in %.2fs", len(threads), args.threads, read_s)

    retriever, build_s = _timed(lambda: Retriever.build(threads))
    retriever.save(args.out)
    size_mb = args.out.stat().st_size / 1e6
    loaded, load_s = _timed(lambda: Retriever.load(args.out))
    latency_ms = measure_latency(loaded, threads, args.n_queries)

    print("\n== BM25 index ==")
    print(f"threads indexed        : {len(loaded):,}")
    print(f"vocabulary             : {loaded.vocab_size:,} terms")
    doc_text = "customer_text + first_reply_text" if loaded.include_reply else "customer_text"
    print(f"document text          : {doc_text}")
    print(f"index file             : {args.out} ({size_mb:.1f} MB)")
    print(f"build time             : {build_s:.2f} s")
    print(f"load time              : {load_s:.2f} s")
    print(
        f"mean query latency     : {latency_ms:.2f} ms over {min(args.n_queries, len(threads))} queries (k=6)"
    )

    print("\n== sample queries (top-3) ==")
    print_samples(loaded, HAND_CHECK_QUERIES[:N_SAMPLE_QUERIES])
    if args.compare_doc_text:
        compare_doc_text(threads, loaded)
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # tweets contain emoji; never rely on the console code page
    raise SystemExit(main())
