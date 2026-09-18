"""Stratified candidate sampling for the golden set (``data/golden/candidates.jsonl``).

Procedure (see ``docs/SAMPLING_NOTE.md`` for the narrative):

1. Pool = English openers with at least one brand reply, exact-duplicate texts removed.
2. Every pooled message is assigned to the keyword bucket ``kw:<intent_id>`` of the intent with the most
   keyword hits (ties -> earlier intent in ``config/intents.yaml``; no hit -> no keyword bucket).
   Keywords shorter than five characters match on word boundaries, longer ones as substrings.
3. Draws happen in three passes with ``random.Random(SEED)``-seeded shuffles: ``short_or_media``
   (``n_words <= 3`` or a bare ``<url>``), then each keyword bucket (up to ``per_bucket``), then a
   uniform ``random`` bucket sized so that at least ``min_random_share`` of all candidates are random.
4. Within every pass the draw round-robins over calendar months so candidates spread across time, and a
   message is rejected when its text is a near-duplicate (rapidfuzz ratio > ``dedupe_ratio``) of one
   already accepted.
5. The final list is shuffled with ``SEED`` and given ids ``c_001``... so annotators do not see buckets.
"""

from __future__ import annotations

import math
import random
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from rapidfuzz import fuzz

from cadence.config import SEED, intents_config
from cadence.data.clean import URL_TOKEN

RANDOM_BUCKET = "random"
SHORT_BUCKET = "short_or_media"
KW_PREFIX = "kw:"
WORD_BOUNDARY_MAX_LEN = 4
"""Keywords of at most this many characters are matched on word boundaries (``\\bapp\\b``)."""


@dataclass(frozen=True)
class SamplingPlan:
    """Knobs of :func:`sample_candidates`."""

    target: int = 420
    per_bucket: int = 30
    n_short: int = 15
    min_random_share: float = 0.30
    dedupe_ratio: float = 92.0
    seed: int = SEED


@dataclass
class IntentKeywords:
    """Compiled keyword matchers for one intent."""

    intent_id: str
    patterns: list[re.Pattern[str]] = field(default_factory=list)

    def hits(self, text_lower: str) -> int:
        return sum(1 for p in self.patterns if p.search(text_lower))


def compile_keyword(keyword: str) -> re.Pattern[str]:
    """Compile one keyword: word-boundary match when short (and alphanumeric), substring otherwise."""
    kw = keyword.strip().lower()
    escaped = re.escape(kw)
    has_word_chars = bool(re.search(r"\w", kw))
    if len(kw) <= WORD_BOUNDARY_MAX_LEN and has_word_chars:
        return re.compile(r"(?<!\w)" + escaped + r"(?!\w)")
    return re.compile(escaped)


def load_intent_keywords(config: Mapping[str, Any] | None = None) -> list[IntentKeywords]:
    """Read ``config/intents.yaml`` (or the given mapping) into ordered keyword matchers."""
    cfg = config if config is not None else intents_config()
    matchers: list[IntentKeywords] = []
    for intent in cfg.get("intents", []):
        keywords = [str(k) for k in intent.get("keywords", []) if str(k).strip()]
        matchers.append(IntentKeywords(intent["id"], [compile_keyword(k) for k in keywords]))
    if not matchers:
        raise ValueError("intents config defines no intents")
    return matchers


def assign_bucket(text: str, matchers: Sequence[IntentKeywords]) -> str | None:
    """Return ``kw:<intent_id>`` of the intent with most keyword hits, or ``None`` when nothing matches.

    Ties go to the earlier intent, mirroring the ``simple_keyword`` baseline (CONTRACT §15.1).
    """
    lowered = (text or "").lower()
    best_id: str | None = None
    best_hits = 0
    for m in matchers:
        n = m.hits(lowered)
        if n > best_hits:
            best_id, best_hits = m.intent_id, n
    return f"{KW_PREFIX}{best_id}" if best_id else None


def is_short_or_media(text: str, n_words: int) -> bool:
    """Messages that test the ``ambiguous_or_media_only`` policy."""
    stripped = (text or "").strip()
    return n_words <= 3 or bool(stripped) and all(tok == URL_TOKEN for tok in stripped.split())


def candidate_pool(openers: pd.DataFrame, matchers: Sequence[IntentKeywords]) -> pd.DataFrame:
    """English openers with a brand reply, exact-duplicate texts dropped, plus ``kw_bucket``/``month``/``short``."""
    required = {"thread_id", "customer_text", "language", "n_brand_replies", "n_words", "created_at"}
    missing = required - set(openers.columns)
    if missing:
        raise ValueError(f"openers table is missing columns: {sorted(missing)}")
    pool = openers[(openers["language"] == "en") & (openers["n_brand_replies"] >= 1)].copy()
    pool["customer_text"] = pool["customer_text"].astype(str)
    pool = pool.sort_values(
        "opener_tweet_id" if "opener_tweet_id" in pool.columns else "thread_id", kind="stable"
    )
    pool = pool.drop_duplicates(subset="customer_text", keep="first")
    created = pd.to_datetime(pool["created_at"], utc=True, errors="coerce")
    pool["month"] = created.dt.strftime("%Y-%m").fillna("unknown")
    pool["kw_bucket"] = pool["customer_text"].map(lambda t: assign_bucket(t, matchers))
    pool["short"] = [
        is_short_or_media(t, int(n)) for t, n in zip(pool["customer_text"], pool["n_words"], strict=True)
    ]
    return pool.reset_index(drop=True)


def _month_round_robin(frame: pd.DataFrame, rng: random.Random) -> list[int]:
    """Row positions of ``frame`` ordered so consecutive picks rotate through months (shuffled within month)."""
    by_month: dict[str, list[int]] = {}
    for pos, month in enumerate(frame["month"].tolist()):
        by_month.setdefault(month, []).append(pos)
    months = sorted(by_month)
    for m in months:
        rng.shuffle(by_month[m])
    rng.shuffle(months)
    order: list[int] = []
    depth = 0
    while len(order) < len(frame):
        for m in months:
            bucket = by_month[m]
            if depth < len(bucket):
                order.append(bucket[depth])
        depth += 1
    return order


class _Dedupe:
    """Greedy near-duplicate filter over accepted candidate texts."""

    def __init__(self, ratio: float) -> None:
        self.ratio = ratio
        self.accepted: list[str] = []

    def accept(self, text: str) -> bool:
        if any(fuzz.ratio(text, seen) > self.ratio for seen in self.accepted):
            return False
        self.accepted.append(text)
        return True


def _draw(
    frame: pd.DataFrame,
    quota: int,
    bucket: str,
    rng: random.Random,
    dedupe: _Dedupe,
    taken: set[str],
) -> list[tuple[str, str]]:
    """Draw up to ``quota`` (thread_id, bucket) pairs from ``frame`` honouring dedupe and prior picks."""
    picks: list[tuple[str, str]] = []
    if quota <= 0 or frame.empty:
        return picks
    thread_ids = frame["thread_id"].tolist()
    texts = frame["customer_text"].tolist()
    for pos in _month_round_robin(frame, rng):
        if len(picks) >= quota:
            break
        tid = thread_ids[pos]
        if tid in taken or not dedupe.accept(texts[pos]):
            continue
        taken.add(tid)
        picks.append((tid, bucket))
    return picks


def sample_candidates(
    openers: pd.DataFrame,
    matchers: Sequence[IntentKeywords],
    plan: SamplingPlan | None = None,
) -> pd.DataFrame:
    """Return the sampled pool rows with a ``sampling_bucket`` column, in final (shuffled) order."""
    plan = plan or SamplingPlan()
    pool = candidate_pool(openers, matchers)
    rng = random.Random(plan.seed)
    dedupe = _Dedupe(plan.dedupe_ratio)
    taken: set[str] = set()
    picks: list[tuple[str, str]] = []

    picks += _draw(pool[pool["short"]], plan.n_short, SHORT_BUCKET, rng, dedupe, taken)
    for m in matchers:
        bucket = f"{KW_PREFIX}{m.intent_id}"
        picks += _draw(pool[pool["kw_bucket"] == bucket], plan.per_bucket, bucket, rng, dedupe, taken)

    n_drawn = len(picks)
    min_random = math.ceil(plan.min_random_share * n_drawn / (1.0 - plan.min_random_share))
    n_random = max(plan.target - n_drawn, min_random)
    picks += _draw(pool, n_random, RANDOM_BUCKET, rng, dedupe, taken)

    random.Random(plan.seed).shuffle(picks)
    bucket_of = dict(picks)
    order = [tid for tid, _ in picks]
    sampled = pool.set_index("thread_id").loc[order].reset_index()
    sampled["sampling_bucket"] = sampled["thread_id"].map(bucket_of)
    return sampled


def to_candidate_rows(
    sampled: pd.DataFrame, threads_by_id: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Build ``candidates.jsonl`` rows (ids ``c_001``...) from sampled openers and their threads."""
    rows: list[dict[str, Any]] = []
    for i, rec in enumerate(sampled.to_dict("records"), start=1):
        thread = threads_by_id.get(rec["thread_id"])
        if thread is None:
            raise KeyError(f"thread {rec['thread_id']} missing from threads file")
        created = rec["created_at"]
        rows.append(
            {
                "id": f"c_{i:03d}",
                "thread_id": rec["thread_id"],
                "text": rec["customer_text"],
                "text_raw": rec["customer_text_raw"],
                "created_at": created.strftime("%Y-%m-%dT%H:%M:%SZ")
                if hasattr(created, "strftime")
                else created,
                "historical_brand_reply": thread["first_reply_text"],
                "historical_thread": thread["turns"],
                "sampling_bucket": rec["sampling_bucket"],
                "n_words": int(rec["n_words"]),
                "has_link": bool(rec["has_link"]),
                "n_brand_replies": int(rec["n_brand_replies"]),
            }
        )
    return rows


def bucket_histogram(buckets: Iterable[str]) -> list[tuple[str, int]]:
    """``(bucket, count)`` pairs sorted by count desc then name."""
    counts = Counter(buckets)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


__all__ = [
    "IntentKeywords",
    "KW_PREFIX",
    "RANDOM_BUCKET",
    "SHORT_BUCKET",
    "SamplingPlan",
    "assign_bucket",
    "bucket_histogram",
    "candidate_pool",
    "compile_keyword",
    "is_short_or_media",
    "load_intent_keywords",
    "sample_candidates",
    "to_candidate_rows",
]
