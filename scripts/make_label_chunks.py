"""Select the candidates to label and split them into annotator chunks.

Reads data/golden/candidates.jsonl (stratified candidates), draws a stratified subset of N (default 250,
proportional per sampling bucket with a floor per bucket), shuffles with SEED, and writes
data/golden/work/chunk_{i}.jsonl (default 5 chunks). Each annotator labels every chunk independently.

Usage: python scripts/make_label_chunks.py [--n 250] [--chunks 5]
"""

from __future__ import annotations

import argparse
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

from cadence import SEED
from cadence.config import Paths
from cadence.utils.io import read_jsonl, write_jsonl
from cadence.utils.log import get_logger

log = get_logger(__name__)
WORK = Paths.GOLDEN_DIR / "work"


def select_candidates(rows: list[dict], n: int, floor: int = 12, seed: int = SEED) -> list[dict]:
    """Stratified downsample: every bucket keeps at least `floor` (or all it has), rest proportional."""
    rng = random.Random(seed)
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_bucket[r.get("sampling_bucket", "random")].append(r)
    for b in by_bucket.values():
        rng.shuffle(b)
    total = len(rows)
    quota = {b: min(len(v), max(floor, math.floor(n * len(v) / total))) for b, v in by_bucket.items()}
    # adjust to hit n exactly: trim the largest buckets or top up the largest remaining pools
    while sum(quota.values()) > n:
        b = max(quota, key=lambda k: quota[k])
        quota[b] -= 1
    while sum(quota.values()) < n:
        pool = [(len(v) - quota[b], b) for b, v in by_bucket.items() if len(v) > quota[b]]
        if not pool:
            break
        _, b = max(pool)
        quota[b] += 1
    picked = [r for b, v in sorted(by_bucket.items()) for r in v[: quota[b]]]
    rng.shuffle(picked)
    return picked


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=250)
    ap.add_argument("--chunks", type=int, default=5)
    args = ap.parse_args(argv)

    rows = read_jsonl(Paths.CANDIDATES)
    if not rows:
        raise SystemExit(f"no candidates at {Paths.CANDIDATES}; run scripts/03_sample_candidates.py first")
    picked = select_candidates(rows, args.n)
    WORK.mkdir(parents=True, exist_ok=True)
    for old in WORK.glob("chunk_*.jsonl"):
        old.unlink()
    size = math.ceil(len(picked) / args.chunks)
    for i in range(args.chunks):
        chunk = picked[i * size : (i + 1) * size]
        slim = [
            {
                "id": r["id"],
                "thread_id": r["thread_id"],
                "text": r["text"],
                "created_at": r.get("created_at"),
                "has_link": r.get("has_link"),
                "n_words": r.get("n_words"),
                "historical_brand_reply": r.get("historical_brand_reply"),
                "historical_thread": r.get("historical_thread", []),
            }
            for r in chunk
        ]
        write_jsonl(WORK / f"chunk_{i + 1}.jsonl", slim)
        log.info("chunk_%d: %d rows", i + 1, len(slim))
    hist = Counter(r.get("sampling_bucket", "random") for r in picked)
    log.info("selected %d of %d candidates; buckets: %s", len(picked), len(rows), dict(sorted(hist.items())))
    write_jsonl(WORK / "selected.jsonl", picked)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
