"""Merge golden examples with per-system predictions and judge scores (shape of ``GET /api/golden``)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

Row = dict[str, Any]


def index_by_system(rows: Iterable[Row]) -> dict[str, dict[str, Row]]:
    """Group rows carrying ``system`` and ``id`` keys into ``{system: {id: row}}``.

    Rows without both keys are ignored; a later duplicate (same system, same id) wins so a re-run
    appended to a JSONL file supersedes the earlier row.
    """
    out: dict[str, dict[str, Row]] = {}
    for row in rows:
        system, example_id = row.get("system"), row.get("id")
        if not isinstance(system, str) or not isinstance(example_id, str):
            continue
        out.setdefault(system, {})[example_id] = row
    return out


def merge_example(example: Row, predictions: dict[str, dict[str, Row]], judge: dict[str, dict[str, Row]]) -> Row:
    """Return a copy of one golden example with ``predictions`` and ``judge`` maps keyed by system."""
    example_id = example["id"]
    merged = dict(example)
    merged["predictions"] = {s: rows[example_id] for s, rows in sorted(predictions.items()) if example_id in rows}
    merged["judge"] = {s: rows[example_id] for s, rows in sorted(judge.items()) if example_id in rows}
    return merged


def merge_golden(golden_rows: Iterable[Row], prediction_rows: Iterable[Row], judge_rows: Iterable[Row]) -> list[Row]:
    """Merge golden examples with predictions and judge scores.

    Each returned element is ``GoldenExample & {predictions: {system: AgentResponse}, judge: {system: JudgeScore}}``
    (CONTRACT.md §10). Systems with no row for an example are simply absent from its maps.
    """
    predictions = index_by_system(prediction_rows)
    judge = index_by_system(judge_rows)
    return [merge_example(example, predictions, judge) for example in golden_rows]
