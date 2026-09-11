"""The ``SupportAgent`` pipeline: rules → BM25 retrieval → Gemini structured call → policy post-processing.

See CONTRACT.md §5 (decision policy), §6 (output schema) and §15.3 (interface).
"""

from __future__ import annotations

import re
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


_USELESS_LINK = re.compile(
    r"^https?://(?:(?:www\.|open\.|play\.)?spotify\.com/?|(?:x|twitter)\.com/messages/.*|t\.co/.*)$", re.IGNORECASE
)
"""Links that carry no resolution: a bare Spotify home page, the DM-compose card, or an unresolved t.co."""
_PLACEHOLDER_OR_BARE_LINK = re.compile(
    r"(?:\s*\b(?:at|via|here|below)\s*:?|\s*:)?"
    r"\s*(?:<url>|https?://(?:(?:www\.|open\.|play\.)?spotify\.com/?|(?:x|twitter)\.com/messages/\S*|t\.co/\S*))(?=[\s.,;:!?)]|$)",
    re.IGNORECASE,
)
"""Placeholder tokens and useless links that must never appear in a public reply."""
_EMOJI = r"[\U0001F300-\U0001FAFF☀-➿⭐❤\U0001F900-\U0001F9FF]"
_END = r"(?=\s*(?:" + _EMOJI + r"\s*)*(?:/AI\s*)?$)"
"""End of the reply body: optional emoji, optional signature, end of string (lookahead, nothing consumed)."""
_TAIL = r"\s*(?::\s*[?.!]*(?!\s*https?://)|" + _END + r")"
"""What makes a link introducer dangling: a colon with no URL after it (consumed with junk punctuation), or the end."""
_DANGLING_LINK_CLAUSE = re.compile(
    r"(?:,?\s*\b(?:but|and|so)\s+)?(?:\b(?:can|could) you\s+(?:try\s+)?|\bplease\s+|\bjust\s+|\bthere(?:'s|’s| is)\s+)?"
    r"\b(?:"
    # "we have some more info about the app on Roku here:", "full steps here:", "more details at:"
    r"(?:we(?:'ve|’ve| have)?\s+(?:got\s+)?)?(?:some\s+|more\s+|full\s+|the\s+|all the\s+)*"
    r"(?:info(?:rmation)?|details?|steps|tips|guide|help article|article)(?:'s|’s)?(?:\s+(?:about|on|for)\s+(?:\w+\s+){0,5}\w+)?(?:\s+(?:is|are))?"
    r"\s*(?:here|at|below|via|on)?"
    # "you can find/read/check it (out) here:", "check for job opportunities here:", "take a look at:"
    r"|(?:you can\s+)?(?:find|read|check|see|get|grab|take a look|have a look)(?:\s+(?:it|them|more|out|for|the|all)(?:\s+\w+){0,4})?\s*(?:here|at|below|via|on)"
    # "try heading to this link:", "go to the page:"
    r"|(?:head(?:ing)?|go(?:ing)?)\s+(?:over\s+)?to\s+(?:this|the)\s+(?:link|page|article)"
    # "this link:", "the article:"
    r"|(?:this|the)\s+(?:link|page|article)"
    r")" + _TAIL
    # bare "here:"/"below:" with a colon and nothing useful after it, or a bare trailing "at"/"via"
    + r"|\b(?:here|below)\s*:\s*(?:[?.!]+(?!\s*https?://)|" + _END + r")"
    + r"|\b(?:at|via)\s*:?\s*[?.!]*" + _END,
    re.IGNORECASE,
)
_TRAILING_COLON = re.compile(r"\s*:\s*[?.!]*" + _END)
"""A colon left at the very end of the body ("...you'd like to see:") after its link was removed."""
"""A link-introducing clause left dangling ("More info here:", "at:") after its link was scrubbed."""


def is_useful_link(url: str) -> bool:
    """True when ``url`` points at an actual article/page rather than a home page, DM card or t.co stub."""
    return bool(url) and not _USELESS_LINK.match(url.strip())


def scrub_reply(text: str) -> str:
    """Remove ``<url>`` placeholders (copied from evidence) and bare home-page / DM / t.co links from a draft."""
    cleaned = _PLACEHOLDER_OR_BARE_LINK.sub("", text)
    cleaned = _DANGLING_LINK_CLAUSE.sub(" ", cleaned)
    cleaned = _TRAILING_COLON.sub(" ", cleaned)
    cleaned = re.sub(r"[,;]?\s*\b(?:but|and|so)\s*(?=(?:[.!?]\s*)?(?:%s\s*)*(?:/AI\s*)?$)" % _EMOJI, "", cleaned)  # ", but" left hanging
    cleaned = re.sub(r"\s*,\s*(?=[.!?]|(?:%s\s*)*(?:/AI\s*)?$)" % _EMOJI, "", cleaned)  # trailing comma
    cleaned = re.sub(r"\(\s*\)", "", cleaned)  # empty parentheses left behind
    cleaned = re.sub(r"\s+([.,;!?])", r"\1", cleaned)  # no colon: keep " :)" emoticons intact
    return normalize_ws(cleaned)


def evidence_from_hit(hit: Any) -> EvidenceItem:
    """Convert a retriever ``Hit`` (thread_id, score, thread dict — §15.2) into an :class:`EvidenceItem`.

    Only useful resolved links (real article paths) are kept; bare home-page and DM-card links are dropped so
    the model never sees, cites or copies them.
    """
    thread: dict[str, Any] = getattr(hit, "thread", None) or {}
    replies = _thread_field(thread, "brand_replies", [])
    first_reply = replies[0] if replies else {}
    brand_reply = _thread_field(thread, "first_reply_text", "") or _thread_field(first_reply, "text", "")
    links = [str(u) for u in (_thread_field(first_reply, "resolved_links", []) or []) if u and is_useful_link(str(u))]
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
    """Scrub placeholders/bare links, trim to 280 chars (sentence boundary, signature kept), attach the cited help link if referenced."""
    text = fit_reply(scrub_reply(reply))
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

    def _decide(self, rules: RuleResult, decision: Any) -> tuple[str, Escalation | None, bool]:
        """CONTRACT §5: rules force → LLM escalate → enforced policy default → low confidence → auto_handle.

        Returns (decision, escalation, enforced_default).
        """
        if rules.force_escalate and rules.reason_code:
            return "escalate", Escalation(
                reason_code=rules.reason_code, reason=rules.reason or "Forced by rules."
            ), False
        if decision.decision == "escalate":
            return "escalate", self._llm_escalation(decision), False
        enforced = self._enforced_default(decision.intent)
        if enforced is not None:
            return "escalate", enforced, True
        if decision.intent_confidence < self.threshold:
            return "escalate", Escalation(
                reason_code="low_confidence",
                reason=f"intent confidence {decision.intent_confidence:.2f} below threshold {self.threshold:.2f}",
            ), False
        return "auto_handle", None, False

    def _enforced_default(self, intent: str) -> Escalation | None:
        """Intents flagged ``enforce_default_decision`` in intents.yaml always escalate, whatever the model said.

        Security and money cases go to a human by policy (CONTRACT §5); the model's opinion cannot override that.
        """
        cfg = self._intent_defaults.get(intent, {})
        if cfg.get("default_decision") == "escalate" and cfg.get("enforce_default_decision"):
            code = cfg.get("default_reason_code") or FALLBACK_LLM_REASON_CODE
            return Escalation(
                reason_code=code,
                reason=f"{cfg.get('name', intent)} cases always go to a human (policy default enforced).",
            )
        return None

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

        final_decision, escalation, enforced_default = self._decide(rules, decision)
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
            enforced_default=enforced_default,
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
    "scrub_reply",
    "is_useful_link",
    "LINK_TRIGGERS",
]
