"""``run_baselines`` — the §15.4 entry point that runs every baseline system over the golden set."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cadence.baselines._common import Response
from cadence.baselines.nn_reply import SupportsSearch
from cadence.baselines.simple import SYSTEM_KEYWORD, SYSTEM_SIMPLE, run_simple, run_simple_keyword
from cadence.baselines.trivial import SYSTEM as SYSTEM_TRIVIAL
from cadence.baselines.trivial import run_trivial
from cadence.baselines.zero_shot import SYSTEM as SYSTEM_ZERO_SHOT
from cadence.baselines.zero_shot import run_zero_shot
from cadence.utils.log import get_logger

logger = get_logger(__name__)

BASELINE_SYSTEMS: tuple[str, ...] = (SYSTEM_TRIVIAL, SYSTEM_SIMPLE, SYSTEM_KEYWORD, SYSTEM_ZERO_SHOT)
"""Every baseline system this module can produce, in the default run order."""


def run_baselines(
    golden_rows: Sequence[Mapping[str, Any]],
    retriever: SupportsSearch,
    *,
    zero_shot_client: Any | None = None,
    systems: tuple[str, ...] = BASELINE_SYSTEMS,
) -> dict[str, list[Response]]:
    """Run the requested baseline systems; each list is aligned with ``golden_rows`` and carries its ids.

    ``llm_zero_shot`` is omitted from the result when it has to be skipped (no client, key or cache), and
    may be shorter than ``golden_rows`` when cache-only batches miss (see ``run_zero_shot``).
    """
    unknown = [s for s in systems if s not in BASELINE_SYSTEMS]
    if unknown:
        raise ValueError(f"unknown baseline system(s) {unknown}; choose from {list(BASELINE_SYSTEMS)}")
    rows = list(golden_rows)
    results: dict[str, list[Response]] = {}
    simple_rows = run_simple(rows, retriever) if {SYSTEM_SIMPLE, SYSTEM_KEYWORD} & set(systems) else None
    for system in dict.fromkeys(systems):
        if system == SYSTEM_TRIVIAL:
            results[system] = run_trivial(rows)
        elif system == SYSTEM_SIMPLE and simple_rows is not None:
            results[system] = simple_rows
        elif system == SYSTEM_KEYWORD and simple_rows is not None:
            results[system] = run_simple_keyword(rows, simple_rows)
        elif system == SYSTEM_ZERO_SHOT:
            zero_shot_rows = run_zero_shot(rows, zero_shot_client)
            if zero_shot_rows:
                results[system] = zero_shot_rows
            elif zero_shot_rows is not None:
                logger.warning("%s produced no predictions (all cache misses); omitted from results", system)
    logger.info("baselines done: %s", {k: len(v) for k, v in results.items()})
    return results
