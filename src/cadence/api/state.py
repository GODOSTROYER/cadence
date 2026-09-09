"""Lazy, resettable singletons behind the API (golden set, predictions, retriever, agent, ...).

Everything reads ``cadence.config.Paths`` at call time so tests can monkeypatch the paths, and a
missing artifact raises ``503`` with the ``make`` target that produces it.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from cadence.api.merge import index_by_system
from cadence.config import Paths, api_key, cache_only, model_name
from cadence.utils.io import iter_jsonl, read_json, read_jsonl
from cadence.utils.log import get_logger

log = get_logger(__name__)

Row = dict[str, Any]

MAKE_TARGETS: dict[str, str] = {
    "golden": "candidates (then label data/golden/golden_set.jsonl)",
    "predictions": "run",
    "judge": "judge",
    "eval": "eval",
    "index": "index",
    "data": "data",
    "ui": "ui",
}
"""Artifact kind -> the ``make`` target that produces it (used in 503 messages)."""


def require_path(path: Path, kind: str) -> Path:
    """Return ``path`` or raise ``503`` naming the ``make`` target that creates it."""
    if not path.exists():
        target = MAKE_TARGETS.get(kind, kind)
        raise HTTPException(status_code=503, detail=f"{path.name} not found; run: make {target}")
    return path


@contextmanager
def cache_only_env(enabled: bool) -> Iterator[None]:
    """Temporarily force ``CADENCE_CACHE_ONLY=1`` so the LLM client never touches the network."""
    if not enabled:
        yield
        return
    previous = os.environ.get("CADENCE_CACHE_ONLY")
    os.environ["CADENCE_CACHE_ONLY"] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CADENCE_CACHE_ONLY", None)
        else:
            os.environ["CADENCE_CACHE_ONLY"] = previous


def load_retriever() -> Any:
    """Load the BM25 retriever from ``Paths.BM25_INDEX`` (503 when the index has not been built)."""
    require_path(Paths.BM25_INDEX, "index")
    from cadence.retrieval.index import Retriever

    return Retriever.load(Paths.BM25_INDEX)


def build_agent(cache_only_mode: bool) -> Any:
    """Construct a ``SupportAgent`` with a Gemini client for the agent role.

    The client is created inside :func:`cache_only_env` so a client that reads the flag at
    construction time is also pinned to replay mode; the handler additionally wraps every call.
    """
    retriever = load_retriever()
    try:
        from cadence.agent.pipeline import SupportAgent
        from cadence.llm import get_client
    except ImportError as exc:  # pragma: no cover - depends on sibling modules being present
        raise HTTPException(status_code=503, detail=f"agent pipeline unavailable: {exc}") from exc
    with cache_only_env(cache_only_mode):
        client = get_client("agent")
    return SupportAgent(client=client, retriever=retriever)


def count_cache_entries(path: Path) -> int:
    """Rows in the ``calls`` table of the LLM replay cache; 0 when the file or table is missing."""
    if not path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(path))
        try:
            return int(conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.warning("could not count LLM cache entries in %s: %s", path, exc)
        return 0


def count_jsonl(path: Path) -> int:
    """Number of non-blank lines in a JSONL file; 0 when missing."""
    return sum(1 for _ in iter_jsonl(path))


class AppState:
    """Process-wide lazily loaded artifacts. ``reset()`` drops everything (used by tests)."""

    def __init__(self) -> None:
        self._memo: dict[str, Any] = {}
        self.agent_lock = threading.Lock()

    def reset(self) -> None:
        self._memo.clear()

    def _cached(self, key: str, loader: Callable[[], Any]) -> Any:
        if key not in self._memo:
            self._memo[key] = loader()
        return self._memo[key]

    # -- golden set -----------------------------------------------------------------------------
    def golden(self) -> list[Row]:
        """All golden examples (503 until ``golden_set.jsonl`` exists)."""
        return self._cached("golden", lambda: read_jsonl(require_path(Paths.GOLDEN, "golden")))

    def golden_by_id(self) -> dict[str, Row]:
        return self._cached("golden_by_id", lambda: {row["id"]: row for row in self.golden()})

    # -- results --------------------------------------------------------------------------------
    def _optional_by_system(self, key: str, path: Path) -> dict[str, dict[str, Row]]:
        if not path.exists():
            return {}
        return self._cached(key, lambda: index_by_system(iter_jsonl(path)))

    def predictions(self) -> dict[str, dict[str, Row]]:
        """``{system: {id: AgentResponse}}``; empty when predictions have not been produced yet."""
        return self._optional_by_system("predictions", Paths.PREDICTIONS)

    def judge_scores(self) -> dict[str, dict[str, Row]]:
        """``{system: {id: JudgeScore}}``; empty when the judge has not run yet."""
        return self._optional_by_system("judge", Paths.JUDGE_SCORES)

    def human_ratings(self) -> list[Row]:
        """Human ratings are re-read on every call because the API appends to the file."""
        return read_jsonl(Paths.HUMAN_RATINGS)

    def eval_summary(self) -> Row:
        return read_json(require_path(Paths.EVAL_SUMMARY, "eval"))

    def failure_modes(self) -> list[Row]:
        return read_json(require_path(Paths.FAILURE_MODES, "eval"))

    # -- retrieval / agent ----------------------------------------------------------------------
    def retriever(self) -> Any:
        return self._cached("retriever", load_retriever)

    def index_size(self) -> int:
        """Number of indexed threads, or 0 when the index is missing or cannot be loaded."""
        if not Paths.BM25_INDEX.exists():
            return 0
        try:
            return len(self.retriever())
        except Exception as exc:  # noqa: BLE001 - health must never fail because of the index
            log.warning("could not load the BM25 index for /api/health: %s", exc)
            return 0

    def agent(self, cache_only_mode: bool) -> Any:
        """One agent per mode so a replay-only client is never reused for live calls."""
        key = "agent_cache_only" if cache_only_mode else "agent_live"
        return self._cached(key, lambda: build_agent(cache_only_mode))

    def thread(self, thread_id: str) -> Row | None:
        """Look up a processed thread via the index when present, else from the threads file."""
        if Paths.BM25_INDEX.exists():
            return self.retriever().get(thread_id)
        threads = self._cached(
            "threads", lambda: {t["thread_id"]: t for t in iter_jsonl(require_path(Paths.THREADS, "data"))}
        )
        return threads.get(thread_id)


def health_payload(state: AppState) -> Row:
    """The ``GET /api/health`` body (CONTRACT.md §10)."""
    return {
        "status": "ok",
        "has_api_key": api_key() is not None,
        "cache_only": cache_only(),
        "agent_model": model_name("agent"),
        "judge_model": model_name("judge"),
        "cache_entries": count_cache_entries(Paths.LLM_CACHE),
        "index_size": state.index_size(),
        "n_golden": count_jsonl(Paths.GOLDEN),
    }


STATE = AppState()
"""The singleton used by the server; tests call ``STATE.reset()`` between cases."""
