"""Deterministic blind rating queue (CONTRACT.md §10 ``/api/rating-queue`` and §13 judge agreement).

The human rates every judged system on the same 20 sampled messages, drawn with a
stratified sample seeded by ``SEED``. Systems are hidden behind aliases ``A``/``B``/``C`` whose
assignment is shuffled per example (seeded by the example id) so the rater cannot learn a mapping.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable
from typing import Any

from cadence.config import JUDGED_SYSTEMS, SEED
from cadence.eval.review import RUBRIC_VERSION, reply_hash

Row = dict[str, Any]

PER_SYSTEM = 20
"""Number of examples rated per judged system."""
ALIASES: tuple[str, ...] = tuple(chr(ord("A") + i) for i in range(len(JUDGED_SYSTEMS)))
"""Blind labels, one per judged system."""


def alias_map(example_id: str, systems=JUDGED_SYSTEMS) -> dict[str, str]:
    """Return ``{alias: system}`` for one example, shuffled deterministically from ``SEED`` and the id."""
    systems = list(systems)
    random.Random(f"{SEED}:{example_id}").shuffle(systems)
    return dict(zip(ALIASES[:len(systems)], systems, strict=True))


def alias_for(example_id: str, system: str, systems=JUDGED_SYSTEMS) -> str:
    """Inverse of :func:`alias_map`: the alias that hides ``system`` for this example."""
    for alias, hidden in alias_map(example_id, systems).items():
        if hidden == system:
            return alias
    raise ValueError(f"{system!r} is not a judged system ({', '.join(JUDGED_SYSTEMS)})")


def resolve_alias(example_id: str, alias: str, systems=JUDGED_SYSTEMS) -> str:
    """Resolve a blind alias back to the system name; raises ``KeyError`` for an unknown alias."""
    mapping = alias_map(example_id, systems)
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


def plan_pairs(golden_rows: Iterable[Row], per_system: int = PER_SYSTEM, systems=JUDGED_SYSTEMS) -> list[tuple[str, str]]:
    """Sample the same messages for every system; random aliases hide their identities."""
    test_rows = [row for row in golden_rows if row.get("split") == "test"]
    picked = stratified_sample(test_rows, per_system, random.Random(SEED))
    return [(row["id"], system) for row in picked for system in systems]


def rated_pairs(ratings: Iterable[Row], reviewer_id: str = "legacy", run_id: str | None = None) -> set[tuple[str, str]]:
    """``(id, system)`` pairs already present in ``human_ratings.jsonl``."""
    return {(r["id"], r["system"]) for r in ratings if "id" in r and "system" in r
            and r.get("reviewer_id", "legacy") == reviewer_id
            and (run_id is None or r.get("run_id") == run_id)}


def build_queue(
    golden_rows: list[Row],
    predictions: dict[str, dict[str, Row]],
    done: set[tuple[str, str]],
    per_system: int = PER_SYSTEM,
    *, run_id: str = "legacy", systems=JUDGED_SYSTEMS,
) -> list[Row]:
    """Build the blind queue of still-unrated pairs. Items never carry the system name."""
    by_id = {row["id"]: row for row in golden_rows}
    items: list[Row] = []
    for example_id, system in plan_pairs(golden_rows, per_system, systems):
        if (example_id, system) in done:
            continue
        prediction = predictions.get(system, {}).get(example_id)
        if prediction is None:
            continue
        example = by_id[example_id]
        items.append(
            {
                "id": example_id,
                "system_alias": alias_for(example_id, system, systems),
                "text": example.get("text", ""),
                "reply_draft": prediction.get("reply_draft", ""),
                "reply_hash": reply_hash(prediction.get("reply_draft", "")),
                "run_id": run_id, "rubric_version": RUBRIC_VERSION,
                "evidence": prediction.get("evidence") or [],
                "historical_brand_reply": example.get("historical_brand_reply", ""),
            }
        )
    items.sort(key=lambda item: (item["id"], item["system_alias"]))
    return items
