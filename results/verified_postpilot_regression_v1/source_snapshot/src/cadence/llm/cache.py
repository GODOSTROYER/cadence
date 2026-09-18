"""SQLite replay cache for structured LLM calls plus the persisted daily quota counter.

The cache is what makes the whole evaluation reproducible without an API key: every Gemini
response is stored under a stable key and replayed on later runs (CONTRACT.md §12).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from cadence.utils.hashing import stable_key

_SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS calls (
        key            TEXT PRIMARY KEY,
        model          TEXT NOT NULL,
        created_at     TEXT NOT NULL,
        system         TEXT,
        prompt         TEXT NOT NULL,
        schema_json    TEXT NOT NULL,
        temperature    REAL,
        response_json  TEXT NOT NULL,
        prompt_tokens  INT  NOT NULL DEFAULT 0,
        output_tokens  INT  NOT NULL DEFAULT 0,
        latency_ms     INT  NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quota (
        model TEXT NOT NULL,
        day   TEXT NOT NULL,
        n     INT  NOT NULL DEFAULT 0,
        PRIMARY KEY (model, day)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_calls_model ON calls(model)",
)

_CALL_COLUMNS = (
    "key",
    "model",
    "created_at",
    "system",
    "prompt",
    "schema_json",
    "temperature",
    "response_json",
    "prompt_tokens",
    "output_tokens",
    "latency_ms",
)


def schema_json(schema: type[BaseModel]) -> str:
    """Canonical JSON encoding of a pydantic model's JSON schema (part of the cache key)."""
    return json.dumps(schema.model_json_schema(), sort_keys=True, ensure_ascii=False)


def utc_day(now: datetime | None = None) -> str:
    """Current UTC calendar day as `YYYY-MM-DD` (the quota bucket)."""
    return (now or datetime.now(UTC)).strftime("%Y-%m-%d")


class LLMCache:
    """Thread-safe SQLite store of LLM calls (`calls`) and per-model daily request counts (`quota`).

    The connection uses WAL mode and is shared across threads behind a single lock, which is
    plenty for the modest write rates of a rate-limited free-tier client.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            for statement in _SCHEMA_SQL:
                self._conn.execute(statement)

    # ------------------------------------------------------------------ keys
    @staticmethod
    def key(model: str, system: str | None, prompt: str, schema_json: str, temperature: float | None) -> str:
        """Stable cache key: sha256 over (model, system, prompt, schema_json, temperature)."""
        return stable_key(model, system, prompt, schema_json, temperature)

    # ----------------------------------------------------------------- calls
    def get(self, key: str) -> dict[str, Any] | None:
        """Return the stored call row for `key`, or None on a miss."""
        with self._lock:
            row = self._conn.execute("SELECT * FROM calls WHERE key = ?", (key,)).fetchone()
        return dict(row) if row is not None else None

    def put(
        self,
        key: str,
        *,
        model: str,
        system: str | None,
        prompt: str,
        schema_json: str,
        temperature: float | None,
        response_json: str,
        prompt_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
    ) -> None:
        """Insert or replace one call. `response_json` must be the validated response serialised as JSON."""
        values = (
            key,
            model,
            datetime.now(UTC).isoformat(timespec="seconds"),
            system,
            prompt,
            schema_json,
            temperature,
            response_json,
            int(prompt_tokens),
            int(output_tokens),
            int(latency_ms),
        )
        placeholders = ", ".join("?" for _ in _CALL_COLUMNS)
        sql = f"INSERT OR REPLACE INTO calls ({', '.join(_CALL_COLUMNS)}) VALUES ({placeholders})"
        with self._lock:
            self._conn.execute(sql, values)

    def count(self) -> int:
        """Number of cached calls."""
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0])

    def stats(self) -> dict[str, Any]:
        """Aggregate numbers for the health endpoint and the cost section of the report."""
        with self._lock:
            totals = self._conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(prompt_tokens), 0) AS p, COALESCE(SUM(output_tokens), 0) AS o "
                "FROM calls"
            ).fetchone()
            by_model = self._conn.execute(
                "SELECT model, COUNT(*) AS n FROM calls GROUP BY model ORDER BY model"
            ).fetchall()
        return {
            "entries": int(totals["n"]),
            "by_model": {row["model"]: int(row["n"]) for row in by_model},
            "total_prompt_tokens": int(totals["p"]),
            "total_output_tokens": int(totals["o"]),
        }

    # ----------------------------------------------------------------- quota
    def quota_get(self, model: str, day: str) -> int:
        """Requests already made for `model` on UTC `day` (0 when none)."""
        with self._lock:
            row = self._conn.execute("SELECT n FROM quota WHERE model = ? AND day = ?", (model, day)).fetchone()
        return int(row["n"]) if row is not None else 0

    def quota_incr(self, model: str, day: str) -> int:
        """Atomically increment the daily counter and return the new value."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO quota (model, day, n) VALUES (?, ?, 1) "
                "ON CONFLICT(model, day) DO UPDATE SET n = n + 1",
                (model, day),
            )
            row = self._conn.execute("SELECT n FROM quota WHERE model = ? AND day = ?", (model, day)).fetchone()
        return int(row["n"])

    # -------------------------------------------------------------- lifecycle
    def close(self) -> None:
        """Close the underlying connection (safe to call more than once)."""
        with self._lock:
            self._conn.close()

    def __repr__(self) -> str:
        return f"LLMCache(path={str(self.path)!r})"


__all__ = ["LLMCache", "schema_json", "utc_day"]
