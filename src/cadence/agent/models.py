"""Pydantic models for the agent: the public ``AgentResponse`` (CONTRACT.md §6) and the
Gemini structured-output schema ``LLMDecision``.

``LLMDecision`` is built dynamically with :func:`pydantic.create_model` so the allowed intent ids
and escalation reason codes from ``config/*.yaml`` appear as enums in the JSON schema the model
sees. No ``dict[str, Any]`` fields are used anywhere (unsupported by Gemini schema conversion).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from cadence.config import DECISIONS, SENTIMENTS, intent_ids, reason_codes
from cadence.utils.text import normalize_ws

REPLY_MAX_CHARS: int = 280
"""Hard cap on a public reply draft (tweet length, CONTRACT.md §6)."""
REPLY_SIGNATURE: str = " /AI"
"""Brand-style sign-off the agent uses instead of a human's initials."""

Decision = Literal["auto_handle", "escalate"]
Sentiment = Literal["positive", "neutral", "frustrated", "angry"]

_SENTENCE_END = re.compile(r"[.!?…](?=\s)")


def _split_signature(text: str) -> tuple[str, str]:
    """Return ``(body, signature)`` where signature is ``" /AI"`` when the text ends with it, else ``""``."""
    stripped = text.rstrip()
    if stripped.endswith(REPLY_SIGNATURE.strip()):
        return stripped[: -len(REPLY_SIGNATURE.strip())].rstrip(), REPLY_SIGNATURE
    return stripped, ""


def _cut(body: str, budget: int) -> str:
    """Cut ``body`` to at most ``budget`` chars, preferring a sentence boundary, then a word boundary."""
    if len(body) <= budget:
        return body
    window = body[: budget + 1]
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    ends = [e for e in ends if e <= budget and e >= budget // 3]
    if ends:
        return body[: ends[-1]].rstrip()
    space = window.rfind(" ", 0, budget)
    if space <= 0:
        return body[: max(0, budget - 1)].rstrip() + "…"
    return body[:space].rstrip(" ,;:-") + "…"


def fit_reply(text: str, limit: int = REPLY_MAX_CHARS, signature: str = REPLY_SIGNATURE) -> str:
    """Return ``text`` shortened to ``limit`` chars, cutting at a sentence boundary and keeping the signature.

    The signature is preserved verbatim at the end when the original reply carried it. Whitespace is
    normalised. Never raises; an already-short reply is returned unchanged apart from whitespace.
    """
    clean = normalize_ws(text)
    if len(clean) <= limit:
        return clean
    body, sig = _split_signature(clean)
    budget = limit - len(sig) if sig else limit
    return _cut(body, budget) + sig


class Escalation(BaseModel):
    """Why a case is handed to a human (exactly one primary reason code)."""

    model_config = ConfigDict()

    reason_code: str = Field(description="One of the reason codes in config/escalation.yaml.")
    reason: str = Field(description="One-sentence human-readable justification.")


class EvidenceItem(BaseModel):
    """One retrieved historical thread shown to the model as grounding evidence."""

    model_config = ConfigDict()

    thread_id: str
    score: float = 0.0
    customer_text: str = ""
    brand_reply: str = ""
    resolved_links: list[str] = Field(default_factory=list)
    cited: bool = False


class Trace(BaseModel):
    """Timing, token and decision provenance for one agent call."""

    model_config = ConfigDict()

    retrieval_ms: int = 0
    llm_ms: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    llm_decision: str | None = None
    llm_reason_code: str | None = None
    forced_by_rules: bool = False
    enforced_default: bool = False
    """True when the intent's enforced policy default (security/billing → human) overrode an LLM auto_handle."""
    policy_conflict: bool = False
    """True when the final decision is auto_handle but the intent's default_decision is escalate."""


class AgentResponse(BaseModel):
    """Per-example output of every system (CONTRACT.md §6). ``.model_dump()`` is one predictions.jsonl row."""

    model_config = ConfigDict()

    id: str
    system: str
    input_text: str
    intent: str
    intent_confidence: float | None = None
    secondary_intent: str | None = None
    sentiment: str = "neutral"
    reply_draft: str = ""
    citations: list[str] = Field(default_factory=list)
    grounding_notes: str = ""
    decision: Decision
    escalation: Escalation | None = None
    rule_flags: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    cached: bool = False
    trace: Trace = Field(default_factory=Trace)

    @field_validator("reply_draft", mode="before")
    @classmethod
    def _cap_reply(cls, value: object) -> object:
        """Truncate over-long drafts gracefully instead of rejecting the whole response."""
        if isinstance(value, str) and len(value) > REPLY_MAX_CHARS:
            return fit_reply(value)
        return value

    @field_validator("sentiment", mode="before")
    @classmethod
    def _known_sentiment(cls, value: object) -> object:
        if isinstance(value, str) and value not in SENTIMENTS:
            raise ValueError(f"sentiment must be one of {SENTIMENTS}, got {value!r}")
        return value


def _literal(values: Sequence[str]) -> type:
    """Build a ``Literal[...]`` type from a runtime sequence of strings."""
    if not values:
        raise ValueError("cannot build a Literal from an empty sequence")
    return Literal[tuple(values)]  # type: ignore[return-value]


def build_llm_decision_model(
    intents: Sequence[str] | None = None,
    codes: Sequence[str] | None = None,
) -> type[BaseModel]:
    """Create the ``LLMDecision`` structured-output schema for the given intent ids and reason codes.

    Defaults read ``config/intents.yaml`` and ``config/escalation.yaml``. Every constrained field is a
    ``Literal`` so the JSON schema carries explicit ``enum`` lists.
    """
    intent_t = _literal(list(intents) if intents is not None else intent_ids())
    code_t = _literal(list(codes) if codes is not None else reason_codes())
    return create_model(
        "LLMDecision",
        __config__=ConfigDict(),
        __doc__="The agent's structured decision for one customer message.",
        intent=(intent_t, Field(description="Primary intent id from the taxonomy.")),
        intent_confidence=(
            float,
            Field(ge=0.0, le=1.0, description="Probability (0-1) that `intent` is correct."),
        ),
        secondary_intent=(
            intent_t | None,
            Field(
                default=None, description="Second intent when the message clearly has two issues, else null."
            ),
        ),
        sentiment=(_literal(SENTIMENTS), Field(description="Customer sentiment.")),
        reply_draft=(
            str,
            Field(description="Public reply, <= 280 chars, in the brand voice, ending with ' /AI'."),
        ),
        citations=(
            list[str],
            Field(default_factory=list, description="thread_ids of the EVIDENCE blocks the reply relies on."),
        ),
        grounding_notes=(
            str,
            Field(
                default="",
                description="One sentence: which evidence the steps come from, or why evidence was insufficient.",
            ),
        ),
        decision=(_literal(DECISIONS), Field(description="auto_handle (post without review) or escalate.")),
        escalation_reason_code=(
            code_t | None,
            Field(default=None, description="Primary reason code when decision is escalate, else null."),
        ),
        escalation_reason=(
            str | None,
            Field(default=None, description="One-sentence reason for escalating, else null."),
        ),
        missing_info=(
            str | None,
            Field(
                default=None,
                description="What the customer would need to provide for a full answer, else null.",
            ),
        ),
    )


LLMDecision: type[BaseModel] = build_llm_decision_model()
"""Structured-output schema built from the current config at import time."""

__all__ = [
    "REPLY_MAX_CHARS",
    "REPLY_SIGNATURE",
    "Decision",
    "Sentiment",
    "Escalation",
    "EvidenceItem",
    "Trace",
    "AgentResponse",
    "LLMDecision",
    "build_llm_decision_model",
    "fit_reply",
]
