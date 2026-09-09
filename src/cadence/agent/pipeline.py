"""The ``SupportAgent`` pipeline: rules → BM25 retrieval → Gemini structured call → policy post-processing.

See CONTRACT.md §5 (decision policy), §6 (output schema) and §15.3 (interface).
"""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING, Any

from cadence.config import escalation_config, intents_config, model_name
from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws

from .models import (
    REPLY_MAX_CHARS,
    REPLY_SIGNATURE,
    AgentResponse,
    Escalation,
    EvidenceItem,
    LLMDecision,
    Trace,
    fit_reply,
)
from .prompts import build_system_prompt, build_user_prompt
from .rules import RuleResult, apply_rules

if TYPE_CHECKING:  # pragma: no cover - typing only; the concrete classes live in sibling modules
    from cadence.llm.base import LLMClient
    from cadence.retrieval.index import Retriever

log = get_logger(__name__)

LINK_TRIGGERS: tuple[str, ...] = ("help article", "this guide")
"""Phrases in the reply that make the pipeline append the first cited resolved link."""
FALLBACK_LLM_REASON_CODE = "needs_account_lookup"


def _ms(start: float, end: float) -> int:
    return int(round((end - start) * 1000))


def _thread_field(thread: dict[str, Any], key: str, default: Any = "") -> Any:
    value = thread.get(key)
    return default if value is None else value


def evidence_from_hit(hit: Any) -> EvidenceItem:
    """Convert a retriever ``Hit`` (thread_id, score, thread dict — §15.2) into an :class:`EvidenceItem`."""
    thread: dict[str, Any] = getattr(hit, "thread", None) or {}
    replies = _thread_field(thread, "brand_replies", [])
    first_reply = replies[0] if replies else {}
    brand_reply = _thread_field(thread, "first_reply_text", "") or _thread_field(first_reply, "text", "")
    links = [str(u) for u in (_thread_field(first_reply, "resolved_links", []) or []) if u]
    return EvidenceItem(
        thread_id=str(getattr(hit, "thread_id", None) or _thread_field(thread, "thread_id", "")),
        score=float(getattr(hit, "score", 0.0) or 0.0),
        customer_text=str(_thread_field(thread, "customer_text", "")),
        brand_reply=str(brand_reply),
        resolved_links=links,
    )


def filter_citations(citations: Iterable[str], evidence: Sequence[EvidenceItem]) -> list[str]:
    """Keep citations that name an evidence thread, de-duplicated, in the model's order."""
    known = {ev.thread_id for ev in evidence}
    kept: list[str] = []
    for cid in citations:
        if cid in known and cid not in kept:
            kept.append(cid)
    return kept


def _first_cited_link(citations: Sequence[str], evidence: Sequence[EvidenceItem]) -> str | None:
    by_id = {ev.thread_id: ev for ev in evidence}
    for cid in citations:
        ev = by_id.get(cid)
        if ev is not None and ev.resolved_links:
            return ev.resolved_links[0]
    return None


def append_link(reply: str, link: str, limit: int = REPLY_MAX_CHARS) -> str:
    """Append ``link`` before the signature when the result still fits within ``limit`` chars."""
    stripped = reply.rstrip()
    sig = REPLY_SIGNATURE.strip()
    if stripped.endswith(sig):
        body = stripped[: -len(sig)].rstrip()
        candidate = f"{body} {link}{REPLY_SIGNATURE}"
    else:
        candidate = f"{stripped} {link}"
    return candidate if len(candidate) <= limit else reply


def finalize_reply(reply: str, citations: Sequence[str], evidence: Sequence[EvidenceItem]) -> str:
    """Trim the draft to 280 chars (sentence boundary, signature kept) and attach the cited help link if referenced."""
    text = fit_reply(normalize_ws(reply))
    if any(trigger in text.lower() for trigger in LINK_TRIGGERS):
        link = _first_cited_link(citations, evidence)
        if link and link not in text:
            text = append_link(text, link)
    return text


class SupportAgent:
    """Rules + retrieval + LLM agent producing an :class:`AgentResponse` per customer message."""

    def __init__(
        self,
        client: LLMClient,
        retriever: Retriever,
        k: int = 6,
        threshold: float | None = None,
        *,
        system_name: str = "agent",
    ) -> None:
        cfg = escalation_config()
        self.client = client
        self.retriever = retriever
        self.k = k
        self.threshold = float(cfg["confidence_threshold"] if threshold is None else threshold)
        self.system_name = system_name
        self.system_prompt = build_system_prompt()
        self._intent_defaults: dict[str, dict[str, Any]] = {i["id"]: i for i in intents_config()["intents"]}

    # ------------------------------------------------------------------ retrieval
    def _retrieve(self, text: str, exclude_thread_ids: set[str] | None) -> list[EvidenceItem]:
        hits = self.retriever.search(text, k=self.k, exclude_thread_ids=exclude_thread_ids)
        return [evidence_from_hit(h) for h in hits]

    # ------------------------------------------------------------------ decision policy
    def _llm_escalation(self, decision: Any) -> Escalation:
        intent_cfg = self._intent_defaults.get(decision.intent, {})
        code = (
            decision.escalation_reason_code
            or intent_cfg.get("default_reason_code")
            or FALLBACK_LLM_REASON_CODE
        )
        reason = normalize_ws(decision.escalation_reason or "") or (
            f"Model recommended a human review this {decision.intent} case."
        )
        return Escalation(reason_code=code, reason=reason)

    def _decide(self, rules: RuleResult, decision: Any) -> tuple[str, Escalation | None]:
        """CONTRACT §5: rules force → LLM escalate → low confidence → auto_handle."""
        if rules.force_escalate and rules.reason_code:
            return "escalate", Escalation(
                reason_code=rules.reason_code, reason=rules.reason or "Forced by rules."
            )
        if decision.decision == "escalate":
            return "escalate", self._llm_escalation(decision)
        if decision.intent_confidence < self.threshold:
            return "escalate", Escalation(
                reason_code="low_confidence",
                reason=f"intent confidence {decision.intent_confidence:.2f} below threshold {self.threshold:.2f}",
            )
        return "auto_handle", None

    def _policy_conflict(self, intent: str, final_decision: str) -> bool:
        default = self._intent_defaults.get(intent, {}).get("default_decision")
        return final_decision == "auto_handle" and default == "escalate"

    # ------------------------------------------------------------------ main entry point
    def handle(
        self, text: str, *, id: str | None = None, exclude_thread_ids: set[str] | None = None
    ) -> AgentResponse:
        """Classify ``text``, decide auto_handle/escalate and draft a grounded public reply."""
        t0 = time.perf_counter()
        rules = apply_rules(text)
        t_r0 = time.perf_counter()
        evidence = self._retrieve(text, exclude_thread_ids)
        t_r1 = time.perf_counter()

        user_prompt = build_user_prompt(text, evidence, rules)
        decision, meta = self.client.generate_json(user_prompt, LLMDecision, system=self.system_prompt)

        final_decision, escalation = self._decide(rules, decision)
        citations = filter_citations(decision.citations, evidence)
        for ev in evidence:
            ev.cited = ev.thread_id in citations
        reply = finalize_reply(decision.reply_draft, citations, evidence)

        trace = Trace(
            retrieval_ms=_ms(t_r0, t_r1),
            llm_ms=int(getattr(meta, "latency_ms", 0) or 0),
            prompt_tokens=int(getattr(meta, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(meta, "output_tokens", 0) or 0),
            llm_decision=decision.decision,
            llm_reason_code=decision.escalation_reason_code,
            forced_by_rules=bool(rules.force_escalate),
            policy_conflict=self._policy_conflict(decision.intent, final_decision),
        )
        if trace.policy_conflict:
            log.debug("policy conflict: auto_handle for intent %s whose default is escalate", decision.intent)

        return AgentResponse(
            id=id or "",
            system=self.system_name,
            input_text=text,
            intent=decision.intent,
            intent_confidence=float(decision.intent_confidence),
            secondary_intent=decision.secondary_intent,
            sentiment=decision.sentiment,
            reply_draft=reply,
            citations=citations,
            grounding_notes=normalize_ws(decision.grounding_notes or ""),
            decision=final_decision,
            escalation=escalation,
            rule_flags=[*rules.flags, *rules.soft_flags],
            evidence=evidence,
            model=str(getattr(meta, "model", "") or model_name("agent")),
            latency_ms=_ms(t0, time.perf_counter()),
            cached=bool(getattr(meta, "cached", False)),
            trace=trace,
        )


__all__ = [
    "SupportAgent",
    "evidence_from_hit",
    "filter_citations",
    "finalize_reply",
    "append_link",
    "LINK_TRIGGERS",
]
