"""Create an immutable, unlabelled human holdout before running any predictions.

Usage: python scripts/08_lock_holdout.py [--out data/holdout] [--n 200]
Never overwrites a lock. Text-only CSV intentionally hides historical replies and AI labels.
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from rapidfuzz import fuzz, process

from cadence.config import Paths
from cadence.eval.provenance import revision, sha256
from cadence.utils.io import read_jsonl, write_json, write_jsonl


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Paths.DATA / "holdout")
    p.add_argument("--n", type=int, default=200)
    args = p.parse_args(argv)
    if args.out.exists():
        raise SystemExit("Refusing to replace an existing holdout directory.")
    sources = [Paths.CANDIDATES, Paths.GOLDEN, Paths.ROOT / "docs/taxonomy_calibration.jsonl"]
    seen = [r for path in sources for r in read_jsonl(path)]
    excluded_ids = {r["thread_id"] for r in seen}
    texts = [r["text"].casefold() for r in seen]
    threads = read_jsonl(Paths.THREADS)
    # Exclude overlapping conversation components as well as opener IDs.
    excluded_tweets = {
        str(turn["tweet_id"])
        for t in threads
        if t["thread_id"] in excluded_ids
        for turn in t.get("turns", [])
    }
    pool = []
    for t in sorted(threads, key=lambda t: t["thread_id"]):
        if t["thread_id"] in excluded_ids or t.get("language") != "en" or not t.get("brand_replies"):
            continue
        if any(str(turn["tweet_id"]) in excluded_tweets for turn in t.get("turns", [])):
            continue
        if process.extractOne(t["customer_text"].casefold(), texts, scorer=fuzz.ratio, score_cutoff=85):
            continue
        pool.append(t)
    random.Random(2026).shuffle(pool)
    chosen, selected_texts, selected_tweets = [], [], set()
    for t in pool:
        text = t["customer_text"]
        turns = {str(turn["tweet_id"]) for turn in t.get("turns", [])}
        if turns & selected_tweets or process.extractOne(
            text.casefold(), selected_texts, scorer=fuzz.ratio, score_cutoff=85
        ):
            continue
        chosen.append(
            {
                "id": f"h_{len(chosen) + 1:03d}",
                "thread_id": t["thread_id"],
                "text": text,
                "created_at": t.get("created_at"),
                "split": "test",
            }
        )
        selected_texts.append(text.casefold())
        selected_tweets.update(turns)
        if len(chosen) == args.n:
            break
    if len(chosen) != args.n:
        raise SystemExit("Not enough eligible independent examples")
    args.out.mkdir(parents=True)
    write_jsonl(args.out / "examples.jsonl", chosen)
    (args.out / "ids.txt").write_text("".join(r["thread_id"] + "\n" for r in chosen), encoding="utf-8")
    with (args.out / "human_labels.csv").open("w", newline="", encoding="utf-8") as f:
        fields = [
            "id",
            "text",
            "intent",
            "secondary_intent",
            "should_escalate",
            "escalation_reason_code",
            "sentiment",
            "notes",
            "annotator",
            "label_source",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({"id": r["id"], "text": r["text"]} for r in chosen)
    write_json(
        args.out / "HOLDOUT.lock.json",
        {
            "version": 1,
            "seed": 2026,
            "n": len(chosen),
            "eligible_pool": len(pool),
            "status": "unlabelled; no predictions permitted until human labels validated",
            "sampling": "seeded random order; reject >=85 fuzzy duplicates and overlapping tweet components",
            "population": "English threads with brand replies, excluding prior candidate/golden/taxonomy exposure",
            "limitations": "Deduplication changes inclusion probabilities; represents distinct complaints, not tweet traffic.",
            "provenance": revision(Paths.ROOT),
            "files": {name: sha256(args.out / name) for name in ("examples.jsonl", "ids.txt")},
            "sources": {
                str(path.relative_to(Paths.ROOT)).replace("\\", "/"): sha256(path)
                for path in [*sources, Paths.THREADS]
            },
        },
    )
    print(
        f"Locked {len(chosen)} examples from {len(pool)} eligible threads in {args.out}; labels remain blank."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
