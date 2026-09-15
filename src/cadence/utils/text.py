"""Tiny text helpers shared across modules (cleaning rules proper live in cadence.data.clean)."""

from __future__ import annotations

import re

_WS = re.compile(r"\s+")
_WORD = re.compile(r"[A-Za-z0-9']+")


def normalize_ws(text: str) -> str:
    """Collapse all whitespace runs to a single space and strip."""
    return _WS.sub(" ", text or "").strip()


def word_count(text: str) -> int:
    """Count alphanumeric words (emoji and punctuation excluded)."""
    meaningful = re.sub(r"https?://\S+|<url>|@\w+", " ", text or "", flags=re.I)
    return len(_WORD.findall(meaningful))


def truncate(text: str, n: int = 120, suffix: str = "…") -> str:
    """Truncate to at most `n` characters, appending `suffix` when cut."""
    text = text or ""
    if len(text) <= n:
        return text
    return text[: max(0, n - len(suffix))].rstrip() + suffix
