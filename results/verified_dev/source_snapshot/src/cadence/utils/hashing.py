"""Stable hashing helpers (cache keys, deterministic ids)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_key(*parts: Any) -> str:
    """sha256 over a canonical JSON encoding of `parts` — order-sensitive, whitespace-insensitive."""
    payload = json.dumps(list(parts), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(payload)
