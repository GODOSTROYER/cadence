"""Deterministic escalation rules compiled once from ``config/escalation.yaml`` (CONTRACT.md §5, §15.3).

Rules are evaluated in file order; the first *forcing* rule that fires supplies the reason code and
reason. Soft flags are recorded but never decide anything. Messages shorter than
``min_words_for_auto_handle`` words are flagged ``too_short`` (reason ``ambiguous_or_media_only``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from cadence.config import escalation_config
from cadence.utils.text import word_count

TOO_SHORT_FLAG = "too_short"
TOO_SHORT_REASON_CODE = "ambiguous_or_media_only"


@dataclass
class RuleResult:
    """Outcome of :func:`apply_rules` for one message."""

    flags: list[str] = field(default_factory=list)
    soft_flags: list[str] = field(default_factory=list)
    force_escalate: bool = False
    reason_code: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class _Rule:
    flag: str
    patterns: tuple[re.Pattern[str], ...]
    force_escalate: bool
    reason_code: str | None
    reason: str | None

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


def _compile(entry: dict[str, Any], *, soft: bool) -> _Rule:
    patterns = tuple(re.compile(p, re.IGNORECASE) for p in entry.get("patterns", []))
    if not patterns:
        raise ValueError(f"rule {entry.get('flag')!r} in escalation.yaml has no patterns")
    return _Rule(
        flag=str(entry["flag"]),
        patterns=patterns,
        force_escalate=False if soft else bool(entry.get("force_escalate", False)),
        reason_code=None if soft else entry.get("reason_code"),
        reason=None if soft else entry.get("reason"),
    )


@lru_cache(maxsize=1)
def _compiled() -> tuple[tuple[_Rule, ...], tuple[_Rule, ...], int]:
    """(hard rules, soft rules, min_words) compiled once per process."""
    cfg = escalation_config()
    hard = tuple(_compile(r, soft=False) for r in cfg.get("rules", []))
    soft = tuple(_compile(r, soft=True) for r in cfg.get("soft_flags", []))
    return hard, soft, int(cfg.get("min_words_for_auto_handle", 0))


def min_words_for_auto_handle() -> int:
    """Minimum word count below which a message is treated as ambiguous/media-only."""
    return _compiled()[2]


def apply_rules(text: str) -> RuleResult:
    """Run every deterministic rule on ``text`` (case-insensitive) and return the aggregated result."""
    hard, soft, min_words = _compiled()
    result = RuleResult()
    for rule in hard:
        if rule.matches(text):
            result.flags.append(rule.flag)
            if rule.force_escalate and not result.force_escalate:
                result.force_escalate = True
                result.reason_code = rule.reason_code
                result.reason = rule.reason
    result.soft_flags = [rule.flag for rule in soft if rule.matches(text)]
    n_words = word_count(text)
    if n_words < min_words:
        result.flags.append(TOO_SHORT_FLAG)
        if not result.force_escalate:
            result.force_escalate = True
            result.reason_code = TOO_SHORT_REASON_CODE
            result.reason = (
                f"Message has only {n_words} word(s) (fewer than {min_words}); "
                "too short to determine the issue, a human needs to look."
            )
    return result


__all__ = [
    "RuleResult",
    "apply_rules",
    "min_words_for_auto_handle",
    "TOO_SHORT_FLAG",
    "TOO_SHORT_REASON_CODE",
]
