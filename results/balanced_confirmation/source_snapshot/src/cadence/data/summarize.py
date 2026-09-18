"""Derived artefacts from the thread list: openers table, canonical reply templates and stats.json."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from cadence.data.clean import URL_TOKEN, USER_TOKEN, asks_dm
from cadence.data.links import homepage_rate, success_rate
from cadence.utils.text import normalize_ws, word_count

OPENER_COLUMNS: tuple[str, ...] = (
    "thread_id",
    "opener_tweet_id",
    "created_at",
    "customer_author_id",
    "customer_text",
    "customer_text_raw",
    "has_link",
    "n_words",
    "language",
    "n_brand_replies",
    "n_turns",
    "first_reply_text",
    "first_reply_asks_dm",
    "first_reply_has_link",
    "first_reply_agent_sig",
)
"""Column order of ``spotify_openers.parquet`` (CONTRACT.md §1)."""

TEMPLATE_PREFIX_CHARS = 70
DEFAULT_TOP_TEMPLATES = 40
QUANTILES: tuple[float, ...] = (0.1, 0.25, 0.5, 0.75, 0.9)

_TOKENS_RE = re.compile(re.escape(URL_TOKEN) + "|" + re.escape(USER_TOKEN) + r"|@\w+|https?://\S+")
_SIG_RE = re.compile(r"\s*/[a-z]{1,3}\s*$")


def openers_table(threads: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Flatten threads to one row per opener with the columns of :data:`OPENER_COLUMNS`."""
    rows: list[dict[str, Any]] = []
    for t in threads:
        first = t["brand_replies"][0]
        rows.append(
            {
                "thread_id": t["thread_id"],
                "opener_tweet_id": int(t["opener_tweet_id"]),
                "created_at": t["created_at"],
                "customer_author_id": t["customer_author_id"],
                "customer_text": t["customer_text"],
                "customer_text_raw": t["customer_text_raw"],
                "has_link": bool(t["has_link"]),
                "n_words": int(t["n_words"]),
                "language": t["language"],
                "n_brand_replies": int(t["n_brand_replies"]),
                "n_turns": int(t["n_turns"]),
                "first_reply_text": first["text"],
                "first_reply_asks_dm": bool(first["asks_dm"]),
                "first_reply_has_link": bool(first["links"]),
                "first_reply_agent_sig": first["agent_sig"],
            }
        )
    df = pd.DataFrame(rows, columns=list(OPENER_COLUMNS))
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    for col in ("thread_id", "customer_author_id", "customer_text", "customer_text_raw", "language"):
        df[col] = df[col].astype("string")
    df["first_reply_text"] = df["first_reply_text"].astype("string")
    df["first_reply_agent_sig"] = df["first_reply_agent_sig"].astype("string")
    return df


def normalize_reply(text: str | None) -> str:
    """Lowercase a cleaned brand reply and drop handles, URL tokens and any leftover signature."""
    lowered = (text or "").lower()
    lowered = _TOKENS_RE.sub(" ", lowered)
    lowered = _SIG_RE.sub("", lowered)
    return normalize_ws(lowered)


def reply_templates(
    first_replies: Iterable[tuple[str, str]],
    top_n: int = DEFAULT_TOP_TEMPLATES,
    prefix_chars: int = TEMPLATE_PREFIX_CHARS,
) -> list[dict[str, Any]]:
    """Group first brand replies by their first ``prefix_chars`` normalised characters.

    ``first_replies`` yields ``(cleaned_text, raw_text)`` pairs. Each returned template carries the
    most common full normalised text in its group, one raw example, the group count, its share of all
    replies and whether the template asks for a DM. Sorted by count descending (ties by template).
    """
    groups: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, dict[str, str]] = defaultdict(dict)
    total = 0
    for cleaned, raw in first_replies:
        norm = normalize_reply(cleaned)
        if not norm:
            continue
        total += 1
        key = norm[:prefix_chars]
        groups[key][norm] += 1
        examples[key].setdefault(norm, raw)
    ranked = sorted(groups.items(), key=lambda kv: (-sum(kv[1].values()), kv[0]))[:top_n]
    out: list[dict[str, Any]] = []
    for key, counter in ranked:
        template = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        count = sum(counter.values())
        out.append(
            {
                "template": template,
                "example_raw": examples[key][template],
                "count": count,
                "share": round(count / total, 6) if total else 0.0,
                "asks_dm": asks_dm(template),
            }
        )
    return out


def _quantiles(values: pd.Series) -> dict[str, float]:
    if values.empty:
        return {f"p{int(q * 100)}": 0.0 for q in QUANTILES}
    return {f"p{int(q * 100)}": float(values.quantile(q)) for q in QUANTILES}


def compute_stats(
    openers: pd.DataFrame,
    *,
    n_rows_total: int,
    n_brand_tweets: int,
    n_subgraph_tweets: int,
    link_map: Mapping[str, Mapping[str, Any]],
    timings: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Assemble ``stats.json`` (counts and shares quoted in the report)."""
    created = openers["created_at"].dropna()
    reply_words = openers["first_reply_text"].fillna("").map(word_count)
    months = created.dt.strftime("%Y-%m").value_counts().sort_index()
    return {
        "n_rows_total": int(n_rows_total),
        "n_brand_tweets": int(n_brand_tweets),
        "n_subgraph_tweets": int(n_subgraph_tweets),
        "n_threads": int(len(openers)),
        "n_openers_english": int((openers["language"] == "en").sum()),
        "date_min": created.min().strftime("%Y-%m-%d") if not created.empty else None,
        "date_max": created.max().strftime("%Y-%m-%d") if not created.empty else None,
        "share_openers_with_link": round(float(openers["has_link"].mean()), 4) if len(openers) else 0.0,
        "share_first_reply_asks_dm": round(float(openers["first_reply_asks_dm"].mean()), 4)
        if len(openers)
        else 0.0,
        "share_multi_turn": round(float((openers["n_brand_replies"] > 1).mean()), 4) if len(openers) else 0.0,
        "link_resolution_success_rate": round(success_rate(link_map), 4),
        "share_links_landing_on_homepage": round(homepage_rate(link_map), 4),
        "n_links_resolved": int(sum(1 for v in link_map.values() if v.get("url"))),
        "n_links_attempted": int(len(link_map)),
        "reply_length_quantiles": _quantiles(reply_words.astype(float)),
        "opener_length_quantiles": _quantiles(openers["n_words"].astype(float)),
        "openers_per_month": {str(k): int(v) for k, v in months.items()},
        "timings_s": {k: round(float(v), 2) for k, v in (timings or {}).items()},
    }


__all__ = [
    "DEFAULT_TOP_TEMPLATES",
    "OPENER_COLUMNS",
    "QUANTILES",
    "TEMPLATE_PREFIX_CHARS",
    "compute_stats",
    "normalize_reply",
    "openers_table",
    "reply_templates",
]
