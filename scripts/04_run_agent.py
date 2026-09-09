"""Run the Cadence agent (and the baseline systems) over the golden set → ``results/predictions.jsonl``.

Usage (from the repo root)::

    python scripts/04_run_agent.py [--limit N] [--systems agent,trivial,...] [--fresh] [--mock]

The run is resumable: rows already present in ``results/predictions.jsonl`` for a given system are
skipped unless ``--fresh`` is passed (which drops that system's rows first). Golden rows come from
``data/golden/golden_set.jsonl``; when it is missing the script falls back to ``candidates.jsonl``.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import track
from rich.table import Table

from cadence.config import SYSTEMS, Paths
from cadence.utils.io import read_jsonl, write_jsonl
from cadence.utils.log import get_logger

log = get_logger("scripts.04_run_agent")
console = Console()

BASELINE_SYSTEMS: tuple[str, ...] = tuple(s for s in SYSTEMS if s != "agent")


@dataclass
class SystemStats:
    """Per-system counters shown in the final summary table."""

    n: int = 0
    skipped: int = 0
    decisions: Counter[str] = field(default_factory=Counter)
    cached: int = 0
    seconds: float = 0.0

    def add(self, row: dict[str, Any]) -> None:
        self.n += 1
        self.decisions[str(row.get("decision"))] += 1
        self.cached += int(bool(row.get("cached")))


# ----------------------------------------------------------------------------- inputs
def load_golden(limit: int | None) -> list[dict[str, Any]]:
    """Golden rows (or candidates with a warning), each guaranteed to carry ``id``, ``text`` and ``thread_id``."""
    path = Paths.GOLDEN
    if not path.exists():
        if not Paths.CANDIDATES.exists():
            raise FileNotFoundError(
                f"neither {Paths.GOLDEN} nor {Paths.CANDIDATES} exists; run scripts 01-03 first"
            )
        log.warning("golden_set.jsonl missing — falling back to %s (unlabelled candidates)", Paths.CANDIDATES)
        path = Paths.CANDIDATES
    rows = read_jsonl(path)
    for i, row in enumerate(rows):
        row.setdefault("id", f"g_{i + 1:03d}")
        row.setdefault("text", row.get("customer_text", ""))
        row.setdefault("thread_id", "")
    if limit is not None:
        rows = rows[:limit]
    log.info("loaded %d rows from %s", len(rows), path)
    return rows


def existing_ids(path: Path, systems: Iterable[str], fresh: bool) -> dict[str, set[str]]:
    """Ids already predicted per system. With ``fresh`` the selected systems' rows are removed from the file."""
    rows = read_jsonl(path)
    selected = set(systems)
    if fresh and rows:
        kept = [r for r in rows if r.get("system") not in selected]
        write_jsonl(path, kept)
        log.info("--fresh: dropped %d rows for %s", len(rows) - len(kept), ",".join(sorted(selected)))
        rows = kept
    done: dict[str, set[str]] = {s: set() for s in selected}
    for r in rows:
        if r.get("system") in done:
            done[r["system"]].add(str(r.get("id")))
    return done


# ----------------------------------------------------------------------------- clients
def make_client(role: str, mock: bool) -> Any:
    """``MockClient`` when ``mock`` else the configured client for ``role`` (lazy imports)."""
    if mock:
        from cadence.llm.mock import MockClient

        return MockClient()
    from cadence.llm import get_client

    return get_client(role)


def load_retriever() -> Any:
    from cadence.retrieval.index import Retriever

    retriever = Retriever.load()
    log.info("retriever loaded with %d threads", len(retriever))
    return retriever


# ----------------------------------------------------------------------------- runners
def run_agent(rows: Sequence[dict[str, Any]], retriever: Any, mock: bool, done: set[str]) -> SystemStats:
    """Run ``SupportAgent`` over ``rows`` not yet predicted, appending one row per example."""
    from cadence.agent.pipeline import SupportAgent

    agent = SupportAgent(make_client("agent", mock), retriever)
    stats = SystemStats()
    started = time.perf_counter()
    for row in track(rows, description="agent", console=console):
        if row["id"] in done:
            stats.skipped += 1
            continue
        response = agent.handle(row["text"], id=row["id"], exclude_thread_ids={row["thread_id"]} - {""})
        payload = response.model_dump()
        write_jsonl(Paths.PREDICTIONS, [payload], append=True)
        stats.add(payload)
    stats.seconds = time.perf_counter() - started
    return stats


def run_baseline_systems(
    rows: Sequence[dict[str, Any]],
    retriever: Any,
    systems: tuple[str, ...],
    mock: bool,
    done: dict[str, set[str]],
) -> dict[str, SystemStats]:
    """Append the baseline systems' rows (skipping ids already present). Missing module → log and skip."""
    try:
        from cadence.baselines import run_baselines
    except ImportError as exc:
        log.warning("cadence.baselines not available (%s); skipping %s", exc, ",".join(systems))
        return {}
    started = time.perf_counter()
    zero_shot_client = make_client("zero_shot", mock) if "llm_zero_shot" in systems else None
    outputs = run_baselines(list(rows), retriever, zero_shot_client=zero_shot_client, systems=systems)
    result: dict[str, SystemStats] = {}
    for system, responses in outputs.items():
        stats = SystemStats()
        for response in responses:
            payload = response.model_dump() if hasattr(response, "model_dump") else dict(response)
            payload["system"] = system
            if str(payload.get("id")) in done.get(system, set()):
                stats.skipped += 1
                continue
            write_jsonl(Paths.PREDICTIONS, [payload], append=True)
            stats.add(payload)
        stats.seconds = time.perf_counter() - started
        result[system] = stats
    return result


# ----------------------------------------------------------------------------- reporting
def summary_table(stats: dict[str, SystemStats]) -> Table:
    table = Table(title="04_run_agent — predictions written", show_lines=False)
    for col in ("system", "n written", "skipped", "decision split", "cache hit rate", "wall time"):
        table.add_column(col)
    for system in sorted(stats):
        s = stats[system]
        split = ", ".join(f"{k}={v}" for k, v in sorted(s.decisions.items())) or "-"
        hit_rate = f"{s.cached / s.n:.0%}" if s.n else "-"
        table.add_row(system, str(s.n), str(s.skipped), split, hit_rate, f"{s.seconds:.1f}s")
    return table


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--limit", type=int, default=None, help="only the first N golden rows")
    parser.add_argument(
        "--systems", default=",".join(SYSTEMS), help=f"comma-separated subset of {','.join(SYSTEMS)}"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="drop existing rows for the selected systems first"
    )
    parser.add_argument(
        "--mock", action="store_true", help="use cadence.llm.mock.MockClient (no API key needed)"
    )
    args = parser.parse_args(argv)
    systems = tuple(s.strip() for s in args.systems.split(",") if s.strip())
    unknown = sorted(set(systems) - set(SYSTEMS))
    if unknown:
        parser.error(f"unknown systems {unknown}; choose from {','.join(SYSTEMS)}")
    args.systems = systems
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    Paths.ensure_dirs()
    rows = load_golden(args.limit)
    done = existing_ids(Paths.PREDICTIONS, args.systems, args.fresh)
    retriever = load_retriever()
    stats: dict[str, SystemStats] = {}
    if "agent" in args.systems:
        stats["agent"] = run_agent(rows, retriever, args.mock, done["agent"])
    baselines = tuple(s for s in args.systems if s in BASELINE_SYSTEMS)
    if baselines:
        stats.update(run_baseline_systems(rows, retriever, baselines, args.mock, done))
    console.print(summary_table(stats))
    console.print(f"predictions → {Paths.PREDICTIONS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
