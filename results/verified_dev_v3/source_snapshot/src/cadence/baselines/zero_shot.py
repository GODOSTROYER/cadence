"""LLM zero-shot baseline (CONTRACT.md §15.1 ``llm_zero_shot``).

Intent + decision straight from the zero-shot model with the taxonomy and escalation policy in the
prompt, **no retrieval evidence**, batched ten messages per structured call. ``reply_draft`` is empty.

The system is skipped (with a log line) when there is no client to call: no client passed, no API key
and no LLM cache to replay from. Batches that miss the cache in cache-only mode are left out.
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

from cadence.baselines._common import (
    Response,
    build_response,
    escalation_payload,
    row_id,
    row_text,
    trace_payload,
)
from cadence.config import (
    DECISIONS,
    Paths,
    api_key,
    escalation_config,
    intent_ids,
    intents_config,
    reason_codes,
)
from cadence.utils.log import get_logger

logger = get_logger(__name__)

SYSTEM = "llm_zero_shot"
BATCH_SIZE = 10
MESSAGE_LINE = "[{id}] {text}"
"""One customer message per prompt line; the bracketed id is how results are mapped back."""
FALLBACK_INTENT = "other"
FALLBACK_REASON_CODE = "low_confidence"
MISSING_REASON = "Zero-shot model returned no item for this message; escalating by default."

_INTENT_IDS: tuple[str, ...] = tuple(intent_ids())
_REASON_CODES: tuple[str, ...] = tuple(reason_codes())

IntentId = Literal[_INTENT_IDS]  # type: ignore[valid-type]
Decision = Literal[DECISIONS]  # type: ignore[valid-type]
ReasonCode = Literal[_REASON_CODES]  # type: ignore[valid-type]


class ZeroShotItem(BaseModel):
    """One classified message."""

    id: str
    intent: IntentId
    intent_confidence: float = Field(ge=0.0, le=1.0)
    decision: Decision
    escalation_reason_code: ReasonCode | None = None


class ZeroShotBatch(BaseModel):
    """Structured output for one batched call."""

    items: list[ZeroShotItem]


SYSTEM_PROMPT = (
    "You triage public tweets sent to the @SpotifyCares support account. For every message decide the "
    "customer's intent (one id from the taxonomy), your confidence in that intent (0-1), and whether the "
    "brand can auto_handle it with a public self-serve reply or must escalate it to a human agent. When "
    "you escalate, give exactly one primary escalation_reason_code. Do not draft replies. Return one item "
    "per message id, in the same order, and never invent ids."
)


# ---------------------------------------------------------------------------
# Prompt blocks (shared with the agent when available)
# ---------------------------------------------------------------------------
def _shared_block(name: str) -> str | None:
    """``cadence.agent.prompts.<name>()`` when the agent module provides it."""
    try:
        from cadence.agent import prompts
    except ImportError:
        return None
    builder = getattr(prompts, name, None)
    if builder is None:
        return None
    try:
        block = builder()
    except Exception as exc:  # signature drift in the agent module; fall back to our own block
        logger.info("cadence.agent.prompts.%s unusable (%s); using baseline-local block", name, exc)
        return None
    return str(block) if block else None


def taxonomy_block() -> str:
    """Intent taxonomy for the prompt: ids, names, descriptions and examples."""
    shared = _shared_block("taxonomy_block")
    if shared:
        return shared
    lines = ["INTENT TAXONOMY (use the id exactly):"]
    for intent in intents_config()["intents"]:
        description = " ".join(str(intent.get("description", "")).split())
        lines.append(f"- {intent['id']} — {intent.get('name', '')}: {description}")
        for example in intent.get("examples") or []:
            lines.append(f'    e.g. "{example}"')
    return "\n".join(lines)


def policy_block() -> str:
    """Escalation policy for the prompt: what auto_handle/escalate mean and the reason codes."""
    shared = _shared_block("policy_block")
    if shared:
        return shared
    lines = [
        "ESCALATION POLICY:",
        "- auto_handle: the public reply can be posted without human review. It needs no account access, "
        "no money movement, no policy exception and no legal/PR exposure (self-serve steps, help link, "
        "acknowledgement, language redirect).",
        "- escalate: a human agent must take the case. Give exactly one primary escalation_reason_code:",
    ]
    for code in escalation_config().get("reason_codes") or []:
        lines.append(f"  - {code['id']}: {' '.join(str(code.get('description', '')).split())}")
    return "\n".join(lines)


def build_prompt(rows: Sequence[Mapping[str, Any]]) -> str:
    """Taxonomy + policy + the batch of messages (no retrieval evidence)."""
    messages = "\n".join(MESSAGE_LINE.format(id=row_id(r), text=row_text(r) or "<empty>") for r in rows)
    return (
        f"{taxonomy_block()}\n\n{policy_block()}\n\n"
        f"MESSAGES ({len(rows)}), one per line as [id] text:\n{messages}\n\n"
        "Return one item for each id above."
    )


# ---------------------------------------------------------------------------
# Client resolution and cache-miss handling
# ---------------------------------------------------------------------------
def _resolve_client(client: Any | None) -> Any | None:
    """The passed client, else ``cadence.llm.get_client('zero_shot')`` when a call could succeed."""
    if client is not None:
        return client
    mock_requested = os.environ.get("CADENCE_LLM", "").strip().lower() == "mock"
    if not mock_requested and api_key() is None and not Paths.LLM_CACHE.exists():
        logger.warning("skipping %s: no client passed, no API key and no LLM cache to replay", SYSTEM)
        return None
    try:
        from cadence.llm import get_client

        return get_client("zero_shot")
    except Exception as exc:  # llm layer missing or refusing to build a client
        logger.warning("skipping %s: could not create a zero-shot client (%s)", SYSTEM, exc)
        return None


def _is_cache_miss(exc: Exception) -> bool:
    """True for ``cadence.llm``'s ``CacheMissError`` (matched by class, or by name before the module exists)."""
    for module_name in ("cadence.llm", "cadence.llm.base", "cadence.llm.cache"):
        try:
            module = __import__(module_name, fromlist=["CacheMissError"])
        except ImportError:
            continue
        cls = getattr(module, "CacheMissError", None)
        if cls is not None and isinstance(exc, cls):
            return True
    return type(exc).__name__ == "CacheMissError"


def _meta(meta: Any, name: str, default: Any = None) -> Any:
    if isinstance(meta, Mapping):
        return meta.get(name, default)
    return getattr(meta, name, default)


def _batches(rows: Sequence[Mapping[str, Any]], size: int) -> Iterator[Sequence[Mapping[str, Any]]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


# ---------------------------------------------------------------------------
# Response assembly
# ---------------------------------------------------------------------------
def _default_reason_code(intent: str) -> str:
    """Reason code when the model escalates without naming one: the intent's default, else low_confidence."""
    for entry in intents_config()["intents"]:
        if entry["id"] == intent and entry.get("default_reason_code"):
            return str(entry["default_reason_code"])
    return FALLBACK_REASON_CODE


def _response_for(row: Mapping[str, Any], item: ZeroShotItem | None, meta: Any, batch_index: int) -> Response:
    latency_ms = int(_meta(meta, "latency_ms", 0) or 0)
    common = {
        "id": row_id(row),
        "system": SYSTEM,
        "input_text": row_text(row),
        "model": str(_meta(meta, "model", "unknown")),
        "latency_ms": latency_ms,
        "cached": bool(_meta(meta, "cached", False)),
    }
    tokens = {"prompt_tokens": _meta(meta, "prompt_tokens"), "output_tokens": _meta(meta, "output_tokens")}
    if item is None:
        return build_response(
            intent=FALLBACK_INTENT,
            intent_confidence=0.0,
            decision="escalate",
            escalation=escalation_payload(FALLBACK_REASON_CODE, MISSING_REASON),
            grounding_notes=f"Zero-shot batch {batch_index} returned no item for this id.",
            trace=trace_payload(llm_ms=latency_ms, **tokens),
            **common,
        )
    escalation = None
    if item.decision == "escalate":
        code = item.escalation_reason_code or _default_reason_code(item.intent)
        escalation = escalation_payload(code, f"Zero-shot model escalated with reason code {code}.")
    return build_response(
        intent=item.intent,
        intent_confidence=float(item.intent_confidence),
        decision=item.decision,
        escalation=escalation,
        grounding_notes=f"Zero-shot classification (batch {batch_index}); no reply drafted, no evidence retrieved.",
        trace=trace_payload(
            llm_ms=latency_ms,
            llm_decision=item.decision,
            llm_reason_code=item.escalation_reason_code,
            **tokens,
        ),
        **common,
    )


def run_zero_shot(
    rows: Sequence[Mapping[str, Any]], client: Any | None = None, *, batch_size: int = BATCH_SIZE
) -> list[Response] | None:
    """Zero-shot rows in golden order; ``None`` when the system is skipped for lack of a client.

    Batches raising ``CacheMissError`` (cache-only mode) are logged and left out of the result, so the
    list can be shorter than ``rows`` — consumers should align by ``id``.
    """
    resolved = _resolve_client(client)
    if resolved is None:
        return None
    responses: list[Response] = []
    missed = 0
    for batch_index, batch in enumerate(_batches(rows, batch_size)):
        try:
            parsed, meta = resolved.generate_json(build_prompt(batch), ZeroShotBatch, system=SYSTEM_PROMPT)
        except Exception as exc:
            if not _is_cache_miss(exc):
                raise
            missed += len(batch)
            logger.warning(
                "%s batch %d: cache miss in cache-only mode; %d rows left out",
                SYSTEM,
                batch_index,
                len(batch),
            )
            continue
        by_id = {item.id: item for item in ZeroShotBatch.model_validate(parsed, from_attributes=True).items}
        responses.extend(_response_for(row, by_id.get(row_id(row)), meta, batch_index) for row in batch)
    if missed:
        logger.warning("%s: %d of %d rows have no prediction (cache misses)", SYSTEM, missed, len(rows))
    return responses
