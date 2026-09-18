"""Shared helpers for the baseline systems.

Golden-row accessors plus a single place that turns a plain field dict into the §6 ``AgentResponse``.
``cadence.agent.models`` is imported lazily so the baselines can be built and tested before the agent
module exists; when it is unavailable (or rejects a payload) the plain dict with the same keys is returned.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from functools import lru_cache
from typing import Any

from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws

logger = get_logger(__name__)

MAX_REPLY_CHARS = 280
"""Hard cap on ``reply_draft`` length (CONTRACT.md §6)."""

DEFAULT_SENTIMENT = "neutral"
"""Baselines do not model sentiment; every row carries the neutral label."""

Response = Any
"""``cadence.agent.models.AgentResponse`` when importable, otherwise a dict with the §6 keys."""


# ---------------------------------------------------------------------------
# Golden-row accessors (schema §7; candidates may lack ``gold``)
# ---------------------------------------------------------------------------
def row_id(row: Mapping[str, Any]) -> str:
    """Golden example id, falling back to the thread id for pre-label candidates."""
    value = row.get("id") or row.get("thread_id")
    if not value:
        raise KeyError("golden row has neither 'id' nor 'thread_id'")
    return str(value)


def row_text(row: Mapping[str, Any]) -> str:
    """Cleaned customer text of a golden row (``text``; ``customer_text`` for candidates)."""
    return normalize_ws(str(row.get("text") or row.get("customer_text") or ""))


def row_thread_id(row: Mapping[str, Any]) -> str | None:
    """Source thread id, used to exclude the example's own thread from retrieval."""
    value = row.get("thread_id")
    return str(value) if value else None


def gold_intent(row: Mapping[str, Any]) -> str | None:
    """Gold intent label when the row is labelled, else ``None``."""
    gold = row.get("gold")
    if not isinstance(gold, Mapping):
        return None
    intent = gold.get("intent")
    return str(intent) if intent else None


# ---------------------------------------------------------------------------
# AgentResponse construction
# ---------------------------------------------------------------------------
def escalation_payload(reason_code: str, reason: str) -> dict[str, str]:
    """The ``escalation`` sub-object of §6."""
    return {"reason_code": reason_code, "reason": reason}


def trace_payload(
    *,
    retrieval_ms: int = 0,
    llm_ms: int = 0,
    prompt_tokens: int | None = 0,
    output_tokens: int | None = 0,
    llm_decision: str | None = None,
    llm_reason_code: str | None = None,
    forced_by_rules: bool = False,
) -> dict[str, Any]:
    """The ``trace`` sub-object of §6, restricted to the keys ``cadence.agent.models.Trace`` accepts."""
    return {
        "retrieval_ms": int(retrieval_ms),
        "llm_ms": int(llm_ms),
        "prompt_tokens": int(prompt_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "llm_decision": llm_decision,
        "llm_reason_code": llm_reason_code,
        "forced_by_rules": forced_by_rules,
    }


def build_response(
    *,
    id: str,
    system: str,
    input_text: str,
    intent: str,
    decision: str,
    model: str,
    intent_confidence: float | None = None,
    reply_draft: str = "",
    citations: Iterable[str] = (),
    grounding_notes: str = "",
    escalation: Mapping[str, str] | None = None,
    rule_flags: Iterable[str] = (),
    evidence: Iterable[Mapping[str, Any]] = (),
    latency_ms: int = 0,
    cached: bool = False,
    trace: Mapping[str, Any] | None = None,
) -> Response:
    """Assemble a §6 response row and validate it as ``AgentResponse`` when the model is importable."""
    if decision == "escalate" and escalation is None:
        raise ValueError(f"{system}/{id}: an escalate decision needs an escalation payload")
    payload: dict[str, Any] = {
        "id": id,
        "system": system,
        "input_text": input_text,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "secondary_intent": None,
        "sentiment": DEFAULT_SENTIMENT,
        "reply_draft": reply_draft[:MAX_REPLY_CHARS],
        "citations": list(citations),
        "grounding_notes": grounding_notes,
        "decision": decision,
        "escalation": dict(escalation) if decision == "escalate" and escalation else None,
        "rule_flags": list(rule_flags),
        "evidence": [dict(e) for e in evidence],
        "model": model,
        "latency_ms": int(latency_ms),
        "cached": cached,
        "trace": dict(trace or {}),
    }
    return _to_model(payload)


def copy_response(response: Response, **updates: Any) -> Response:
    """Return a copy of a response (model or dict) with ``updates`` applied."""
    if isinstance(response, Mapping):
        return {**response, **updates}
    return response.model_copy(update=updates)


def response_field(response: Response, name: str) -> Any:
    """Read one field from a response regardless of whether it is a model or a dict."""
    if isinstance(response, Mapping):
        return response[name]
    return getattr(response, name)


@lru_cache(maxsize=1)
def _agent_response_class() -> type | None:
    try:
        from cadence.agent.models import AgentResponse
    except ImportError:
        logger.info("cadence.agent.models not importable; baselines return plain dict rows")
        return None
    return AgentResponse


_VALIDATION_WARNED = False


def _to_model(payload: dict[str, Any]) -> Response:
    """Prefer the pydantic model; fall back to the dict (warning once) if the model rejects the payload."""
    global _VALIDATION_WARNED
    cls = _agent_response_class()
    if cls is None:
        return payload
    try:
        return cls.model_validate(payload)
    except Exception as exc:  # pydantic.ValidationError or a schema drift in the agent module
        if not _VALIDATION_WARNED:
            logger.warning("AgentResponse rejected a baseline row; returning dict rows instead (%s)", exc)
            _VALIDATION_WARNED = True
        return payload
