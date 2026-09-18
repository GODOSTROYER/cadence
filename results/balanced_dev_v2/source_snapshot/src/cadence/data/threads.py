"""Assemble SpotifyCares conversation threads (CONTRACT.md §3) from the brand reply subgraph."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import pandas as pd

from cadence.config import BRAND
from cadence.data.clean import CleanResult, asks_dm, clean_text, detect_language
from cadence.data.links import best_url
from cadence.data.load import parse_created_at, to_iso_utc
from cadence.utils.log import get_logger
from cadence.utils.text import word_count

log = get_logger(__name__)

MAX_DEPTH = 30
"""Maximum reply depth walked below an opener (guards against pathological chains)."""


@dataclass(frozen=True)
class _Tweet:
    """One row of the subgraph with parsed fields, keyed by ``tweet_id`` in :func:`_index_tweets`."""

    tweet_id: int
    author_id: str
    is_brand: bool
    created: pd.Timestamp | None
    created_iso: str | None
    text_raw: str
    clean: CleanResult
    parent_id: int | None
    child_ids: tuple[int, ...]


def _parse_child_ids(value: Any) -> tuple[int, ...]:
    if value is None or pd.isna(value):
        return ()
    ids: list[int] = []
    for part in str(value).split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return tuple(ids)


def _index_tweets(sub_df: pd.DataFrame, brand: str) -> dict[int, _Tweet]:
    """Clean every tweet once and index it by id."""
    created = parse_created_at(sub_df["created_at"])
    tweets: dict[int, _Tweet] = {}
    rows = zip(
        sub_df["tweet_id"].tolist(),
        sub_df["author_id"].fillna("").tolist(),
        created.tolist(),
        sub_df["text"].fillna("").tolist(),
        sub_df["response_tweet_id"].tolist(),
        sub_df["in_response_to_tweet_id"].tolist(),
        strict=True,
    )
    for tweet_id, author, ts, text, children, parent in rows:
        is_brand = author == brand
        parent_id = None if pd.isna(parent) else int(parent)
        tweets[int(tweet_id)] = _Tweet(
            tweet_id=int(tweet_id),
            author_id=str(author),
            is_brand=is_brand,
            created=None if pd.isna(ts) else ts,
            created_iso=to_iso_utc(ts),
            text_raw=str(text),
            clean=clean_text(text, "brand" if is_brand else "customer"),
            parent_id=parent_id,
            child_ids=_parse_child_ids(children),
        )
    return tweets


def _walk_thread(opener: _Tweet, tweets: dict[int, _Tweet]) -> list[_Tweet]:
    """Breadth-first walk of ``response_tweet_id`` edges from ``opener``.

    Only the opener's author and the brand take part in the thread; replies from third parties are
    not followed. Cycle-safe via a visited set, capped at :data:`MAX_DEPTH` levels.
    """
    visited = {opener.tweet_id}
    collected = [opener]
    queue: deque[tuple[_Tweet, int]] = deque([(opener, 0)])
    while queue:
        node, depth = queue.popleft()
        if depth >= MAX_DEPTH:
            continue
        for child_id in node.child_ids:
            child = tweets.get(child_id)
            if child is None or child_id in visited:
                continue
            if not (child.is_brand or child.author_id == opener.author_id):
                continue
            visited.add(child_id)
            collected.append(child)
            queue.append((child, depth + 1))
    return collected


def _sort_key(tweet: _Tweet) -> tuple[int, float, int]:
    """Chronological order with tweet_id as a stable tie-break; missing timestamps sort last."""
    if tweet.created is None:
        return (1, 0.0, tweet.tweet_id)
    return (0, tweet.created.timestamp(), tweet.tweet_id)


def _brand_reply_record(tweet: _Tweet, link_map: dict[str, dict[str, Any]] | None) -> dict[str, Any]:
    resolved: list[str] = []
    if link_map:
        for link in tweet.clean.links:
            entry = link_map.get(link)
            url = best_url(entry) if entry else None
            if url:
                resolved.append(url)
    return {
        "tweet_id": tweet.tweet_id,
        "created_at": tweet.created_iso,
        "text_raw": tweet.text_raw,
        "text": tweet.clean.text,
        "agent_sig": tweet.clean.agent_sig,
        "links": list(tweet.clean.links),
        "resolved_links": resolved,
        "asks_dm": asks_dm(tweet.clean.text),
    }


def _turn_record(tweet: _Tweet) -> dict[str, Any]:
    turn: dict[str, Any] = {
        "role": "brand" if tweet.is_brand else "customer",
        "tweet_id": tweet.tweet_id,
        "created_at": tweet.created_iso,
        "text": tweet.clean.text,
    }
    if tweet.is_brand:
        turn["agent_sig"] = tweet.clean.agent_sig
    return turn


def _thread_record(
    opener: _Tweet, members: list[_Tweet], link_map: dict[str, dict[str, Any]] | None
) -> dict[str, Any]:
    ordered = sorted(members, key=_sort_key)
    brand_replies = [_brand_reply_record(t, link_map) for t in ordered if t.is_brand]
    turns = [_turn_record(t) for t in ordered]
    return {
        "thread_id": f"t_{opener.tweet_id}",
        "opener_tweet_id": opener.tweet_id,
        "created_at": opener.created_iso,
        "customer_author_id": opener.author_id,
        "customer_text_raw": opener.text_raw,
        "customer_text": opener.clean.text,
        "has_link": opener.clean.has_link,
        "n_words": word_count(opener.clean.text),
        "language": detect_language(opener.clean.text),
        "brand_replies": brand_replies,
        "turns": turns,
        "n_brand_replies": len(brand_replies),
        "n_turns": len(turns),
        "first_reply_text": brand_replies[0]["text"],
        "first_reply_asks_dm": brand_replies[0]["asks_dm"],
    }


def build_threads(
    sub_df: pd.DataFrame,
    brand: str = BRAND,
    link_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build one thread per opener from a brand subgraph (see :func:`cadence.data.load.brand_subgraph`).

    An opener is an inbound tweet whose parent is missing (NaN or absent from the data) and whose
    reply chain contains at least one brand tweet. ``link_map`` (``t.co -> {"url": ...}``) fills
    ``resolved_links`` on brand replies; unknown links yield an empty list. Output is sorted by
    ``opener_tweet_id``.
    """
    t0 = time.perf_counter()
    tweets = _index_tweets(sub_df, brand)
    inbound_ids = sub_df.loc[sub_df["inbound"].astype(bool), "tweet_id"].tolist()
    threads: list[dict[str, Any]] = []
    for tweet_id in inbound_ids:
        opener = tweets[int(tweet_id)]
        if opener.is_brand or (opener.parent_id is not None and opener.parent_id in tweets):
            continue
        members = _walk_thread(opener, tweets)
        if not any(t.is_brand for t in members):
            continue
        threads.append(_thread_record(opener, members, link_map))
    threads.sort(key=lambda t: t["opener_tweet_id"])
    log.info(
        "built %s threads from %s tweets (%.1fs)",
        f"{len(threads):,}",
        f"{len(tweets):,}",
        time.perf_counter() - t0,
    )
    return threads


__all__ = ["MAX_DEPTH", "build_threads"]
