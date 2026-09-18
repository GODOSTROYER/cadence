"""Typed loading of the Kaggle TWCS csv and extraction of a brand's reply subgraph."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from cadence.config import BRAND, Paths
from cadence.utils.log import get_logger

log = get_logger(__name__)

TWCS_DTYPES: dict[str, str] = {
    "tweet_id": "int64",
    "author_id": "string",
    "inbound": "bool",
    "created_at": "string",
    "text": "string",
    "response_tweet_id": "string",
    "in_response_to_tweet_id": "float64",
}
"""Column dtypes measured in CONTRACT.md §2 (``in_response_to_tweet_id`` is float because of NaN roots)."""

CREATED_AT_FORMAT = "%a %b %d %H:%M:%S %z %Y"
"""Twitter's legacy timestamp layout, e.g. ``Tue Oct 31 22:10:47 +0000 2017``."""


def load_twcs(path: Path = Paths.RAW_TWCS) -> pd.DataFrame:
    """Read the full TWCS csv with explicit dtypes (about 9 s / 2.8M rows)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"TWCS csv not found at {path}; download it from Kaggle (customer-support-on-twitter)"
        )
    t0 = time.perf_counter()
    df = pd.read_csv(path, dtype=TWCS_DTYPES, encoding="utf-8", keep_default_na=True)
    missing = set(TWCS_DTYPES) - set(df.columns)
    if missing:
        raise ValueError(f"TWCS csv is missing expected columns: {sorted(missing)}")
    log.info("loaded %s rows from %s in %.1fs", f"{len(df):,}", path.name, time.perf_counter() - t0)
    return df


def split_response_ids(series: pd.Series) -> pd.Series:
    """Explode a comma-joined ``response_tweet_id`` column into an int64 Series of child ids."""
    exploded = series.dropna().str.split(",").explode().str.strip()
    exploded = exploded[exploded != ""]
    return pd.to_numeric(exploded, errors="coerce").dropna().astype("int64")


def brand_subgraph(df: pd.DataFrame, brand: str = BRAND) -> pd.DataFrame:
    """Return every tweet reachable in the reply graph from any tweet authored by ``brand``.

    Iterates set-wise over the parent (``in_response_to_tweet_id``) and child (``response_tweet_id``)
    edges until the reachable set stops growing; no per-row Python loop touches the 2.8M rows.
    """
    t0 = time.perf_counter()
    is_brand = df["author_id"] == brand
    n_brand = int(is_brand.sum())
    if n_brand == 0:
        raise ValueError(f"no tweets authored by {brand!r} in the dataframe")

    tweet_ids = df["tweet_id"]
    parent_ids = df["in_response_to_tweet_id"]
    children = split_response_ids(df["response_tweet_id"])  # index -> row position, value -> child id

    reached: set[int] = set(tweet_ids[is_brand].tolist())
    frontier = set(reached)
    rounds = 0
    while frontier:
        rounds += 1
        in_frontier = tweet_ids.isin(frontier)
        parents = parent_ids[in_frontier].dropna().astype("int64")
        child_ids = children[children.index.isin(df.index[in_frontier])]
        replies_to_frontier = tweet_ids[parent_ids.isin(frontier)]
        candidates = set(parents.tolist()) | set(child_ids.tolist()) | set(replies_to_frontier.tolist())
        frontier = candidates - reached
        reached |= frontier

    sub = df[tweet_ids.isin(reached)].sort_values("tweet_id", kind="stable").reset_index(drop=True)
    log.info(
        "brand subgraph for %s: %s brand tweets -> %s tweets in %d rounds (%.1fs)",
        brand,
        f"{n_brand:,}",
        f"{len(sub):,}",
        rounds,
        time.perf_counter() - t0,
    )
    return sub


def parse_created_at(series: pd.Series) -> pd.Series:
    """Parse TWCS timestamps to tz-aware UTC datetimes (unparseable values become NaT)."""
    return pd.to_datetime(series, format=CREATED_AT_FORMAT, errors="coerce", utc=True)


def to_iso_utc(ts: pd.Timestamp | None) -> str | None:
    """Format a UTC timestamp as ``2017-10-31T22:10:47Z``; ``None``/NaT yield ``None``."""
    if ts is None or pd.isna(ts):
        return None
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "CREATED_AT_FORMAT",
    "TWCS_DTYPES",
    "brand_subgraph",
    "load_twcs",
    "parse_created_at",
    "split_response_ids",
    "to_iso_utc",
]
