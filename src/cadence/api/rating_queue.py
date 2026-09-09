"""Deterministic blind rating queue (CONTRACT.md §10 ``/api/rating-queue`` and §13 judge agreement).

The human rates 20 (example, system) pairs per judged system, drawn from the test split with a
stratified sample seeded by ``SEED``. Systems are hidden behind aliases ``A``/``B``/``C`` whose
assignment is shuffled per example (seeded by the example id) so the rater cannot learn a mapping.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable
from typing import Any

from cadence.config import JUDGED_SYSTEMS, SEED

Row = dict[str, Any]

PER_SYSTEM = 20
"""Number of examples rated per judged system."""
ALIASES: tuple[str, ...] = tuple(chr(ord("A") + i) for i in range(len(JUDGED_SYSTEMS)))
"""Blind labels, one per judged system."""


def alias_map(example_id: str) -> dict[str, str]:
    """Return ``{alias: system}`` for one example, shuffled deterministically from ``SEED`` and the id."""
    systems = list(JUDGED_SYSTEMS)
    random.Random(f"{SEED}:{example_id}").shuffle(systems)
    return dict(zip(ALIASES, systems, strict=True))


def alias_for(example_id: str, system: str) -> str:
    """Inverse of :func:`alias_map`: the alias that hides ``system`` for this example."""
    for alias, hidden in alias_map(example_id).items():
        if hidden == system:
            return alias
    raise ValueError(f"{system!r} is not a judged system ({', '.join(JUDGED_SYSTEMS)})")


def resolve_alias(example_id: str, alias: str) -> str:
    """Resolve a blind alias back to the system name; raises ``KeyError`` for an unknown alias."""
    mapping = alias_map(example_id)
    key = alias.strip().upper()
    if key not in mapping:
        raise KeyError(f"unknown system alias {alias!r}; expected one of {', '.join(ALIASES)}")
    return mapping[key]


def _gold_intent(row: Row) -> str:
    gold = row.get("gold") or {}
    return str(gold.get("intent") or "other")


def stratified_sample(
    rows: list[Row], n: int, rng: random.Random, key: Callable[[Row], str] = _gold_intent
) -> list[Row]:
    """Sample ``n`` rows stratified by ``key`` (largest-remainder allocation), shuffled with ``rng``.

    Rows are first sorted by ``id`` so the result depends only on the row contents and the seed.
    """
    ordered = sorted(rows, key=lambda r: r["id"])
    n = min(n, len(ordered))
    if n == 0:
        return []
    groups: dict[str, list[Row]] = {}
    for row in ordered:
        groups.setdefault(key(row), []).append(row)
    labels = sorted(groups)
    quotas = {label: len(groups[label]) * n / len(ordered) for label in labels}
    alloc = {label: math.floor(q) for label, q in quotas.items()}
    leftover = n - sum(alloc.values())
    for label in sorted(labels, key=lambda lb: (-(quotas[lb] - alloc[lb]), lb))[:leftover]:
        alloc[label] += 1
    picked: list[Row] = []
    for label in labels:
        picked.extend(rng.sample(groups[label], alloc[label]))
    rng.shuffle(picked)
    return picked


def plan_pairs(golden_rows: Iterable[Row], per_system: int = PER_SYSTEM) -> list[tuple[str, str]]:
    """Return the full blind-rating plan as ``(example_id, system)`` pairs.

    ``per_system * len(JUDGED_SYSTEMS)`` distinct test examples are sampled (stratified by gold intent)
    and dealt round-robin to the judged systems, so every system gets ``per_system`` examples and no
    example is rated twice.
    """
    test_rows = [row for row in golden_rows if row.get("split") == "test"]
    rng = random.Random(SEED)
    picked = stratified_sample(test_rows, per_system * len(JUDGED_SYSTEMS), rng)
    return [(row["id"], JUDGED_SYSTEMS[i % len(JUDGED_SYSTEMS)]) for i, row in enumerate(picked)]


def rated_pairs(ratings: Iterable[Row]) -> set[tuple[str, str]]:
    """``(id, system)`` pairs already present in ``human_ratings.jsonl``."""
    return {(r["id"], r["system"]) for r in ratings if "id" in r and "system" in r}


def build_queue(
    golden_rows: list[Row],
    predictions: dict[str, dict[str, Row]],
    done: set[tuple[str, str]],
    per_system: int = PER_SYSTEM,
) -> list[Row]:
    """Build the blind queue of still-unrated pairs. Items never carry the system name."""
    by_id = {row["id"]: row for row in golden_rows}
    items: list[Row] = []
    for example_id, system in plan_pairs(golden_rows, per_system):
        if (example_id, system) in done:
            continue
        prediction = predictions.get(system, {}).get(example_id)
        if prediction is None:
            continue
        example = by_id[example_id]
        items.append(
            {
                "id": example_id,
                "system_alias": alias_for(example_id, system),
                "text": example.get("text", ""),
                "reply_draft": prediction.get("reply_draft", ""),
                "evidence": prediction.get("evidence") or [],
                "historical_brand_reply": example.get("historical_brand_reply", ""),
            }
        )
    items.sort(key=lambda item: (item["id"], item["system_alias"]))
    return items
