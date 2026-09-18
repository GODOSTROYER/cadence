"""Trivial baseline (CONTRACT.md §15.1): majority intent, always escalate, canned brand template.

Every prediction is constant per run, so this is the floor every other system must beat.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from cadence.baselines._common import (
    Response,
    build_response,
    escalation_payload,
    gold_intent,
    row_id,
    row_text,
)
from cadence.config import Paths, intent_ids
from cadence.utils.io import read_json
from cadence.utils.log import get_logger

logger = get_logger(__name__)

SYSTEM = "trivial"
MODEL = "majority_intent+top_template"
FALLBACK_INTENT = "other"
ESCALATION_REASON_CODE = "low_confidence"
ESCALATION_REASON = "trivial baseline escalates everything"
FALLBACK_TEMPLATE = "Hey there! Can you DM us your account's email address? We'll take a look backstage /AI"
"""Used when ``data/processed/reply_templates.json`` has not been produced yet."""

_TEMPLATE_KEYS = ("template", "text", "reply", "first_reply_text")


def majority_intent(rows: Sequence[Mapping[str, Any]]) -> str:
    """Most frequent gold intent; ties break toward the earlier intent in ``config/intents.yaml``.

    Rows without gold labels (candidates) are ignored; with no labels at all the answer is ``other``.
    """
    counts = Counter(intent for intent in (gold_intent(r) for r in rows) if intent)
    if not counts:
        return FALLBACK_INTENT
    order = {intent: i for i, intent in enumerate(intent_ids())}
    return min(counts, key=lambda intent: (-counts[intent], order.get(intent, len(order)), intent))


def top_template(path: Path | None = None) -> str:
    """Top canonical brand reply from ``reply_templates.json``, or the built-in fallback when absent."""
    path = Path(path) if path is not None else Paths.REPLY_TEMPLATES
    if not path.exists():
        logger.info("reply templates missing at %s; using the built-in fallback template", path)
        return FALLBACK_TEMPLATE
    template = _first_template(read_json(path))
    if not template:
        logger.warning("could not read a template from %s; using the built-in fallback", path)
        return FALLBACK_TEMPLATE
    return template


def _first_template(payload: Any) -> str | None:
    """Accept ``[str]``, ``[{"template"|"text"|"reply": ...}]`` or ``{"templates": [...]}``."""
    if isinstance(payload, Mapping):
        payload = payload.get("templates")
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if isinstance(first, str):
        return first.strip() or None
    if isinstance(first, Mapping):
        for key in _TEMPLATE_KEYS:
            value = first.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def run_trivial(rows: Sequence[Mapping[str, Any]]) -> list[Response]:
    """One trivial response per golden row, aligned with ``rows``."""
    started = time.perf_counter()
    intent = majority_intent(rows)
    template = top_template()
    latency_ms = int((time.perf_counter() - started) * 1000)
    escalation = escalation_payload(ESCALATION_REASON_CODE, ESCALATION_REASON)
    return [
        build_response(
            id=row_id(row),
            system=SYSTEM,
            input_text=row_text(row),
            intent=intent,
            decision="escalate",
            escalation=escalation,
            reply_draft=template,
            grounding_notes="Most common historical brand template; not tailored to this message.",
            model=MODEL,
            latency_ms=latency_ms,
        )
        for row in rows
    ]
