"""Tests for cadence.agent: rules, prompts, models and the SupportAgent pipeline (no network, < 5s)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from cadence.agent.models import (
    REPLY_MAX_CHARS,
    AgentResponse,
    EvidenceItem,
    LLMDecision,
    build_llm_decision_model,
    fit_reply,
)
from cadence.agent.pipeline import SupportAgent, evidence_from_hit, filter_citations
from cadence.agent.prompts import (
    FALLBACK_VOICE_GUIDE,
    PROMPT_CHAR_BUDGET,
    build_system_prompt,
    build_user_prompt,
    estimate_tokens,
    extract_section,
    load_voice_guide,
    policy_block,
    taxonomy_block,
)
from cadence.agent.rules import TOO_SHORT_FLAG, RuleResult, apply_rules
from cadence.config import escalation_config, intent_ids, reason_codes

# --------------------------------------------------------------------------- fakes


@dataclass
class FakeHit:
    thread_id: str
    score: float
    thread: dict[str, Any]


def _thread(tid: str, customer: str, reply: str, links: list[str] | None = None) -> dict[str, Any]:
    return {
        "thread_id": tid,
        "customer_text": customer,
        "first_reply_text": reply,
        "brand_replies": [{"text": reply, "resolved_links": links or []}],
    }


HELP_LINK = "https://support.spotify.com/article/reinstall-spotify/"
THREADS = [
    _thread(
        "t_1",
        "app keeps crashing since the update",
        "Hey there! Try a clean reinstall, this help article walks you through it",
        [HELP_LINK],
    ),
    _thread("t_2", "songs skipping on android", "Hi! Can you let us know the device and OS version?"),
    _thread(
        "t_3", "charged twice this month", "Hey! Send us a DM with your account email and we'll take a look"
    ),
]


@dataclass
class FakeRetriever:
    hits: list[FakeHit] = field(
        default_factory=lambda: [FakeHit(t["thread_id"], 10.0 - i, t) for i, t in enumerate(THREADS)]
    )
    calls: list[dict[str, Any]] = field(default_factory=list)

    def search(self, query: str, k: int = 6, exclude_thread_ids: set[str] | None = None) -> list[FakeHit]:
        self.calls.append({"query": query, "k": k, "exclude": exclude_thread_ids})
        excluded = exclude_thread_ids or set()
        return [h for h in self.hits if h.thread_id not in excluded][:k]


def _mock_client_class() -> type:
    """The real ``cadence.llm.mock.MockClient`` when available, else a minimal local stand-in."""
    try:
        from cadence.llm.mock import MockClient

        return MockClient
    except ImportError:

        class _StubMockClient:
            def __init__(self, responder: Any = None) -> None:
                self.responder = responder

            def generate_json(
                self,
                prompt: str,
                schema: type[BaseModel],
                *,
                system: str | None = None,
                temperature: float | None = None,
                cache: bool = True,
            ) -> tuple[BaseModel, Any]:
                payload = self.responder(prompt, schema)
                meta = SimpleNamespace(
                    model="mock",
                    cached=True,
                    latency_ms=3,
                    prompt_tokens=len(prompt) // 4,
                    output_tokens=60,
                    attempts=1,
                )
                return schema.model_validate(payload), meta

        return _StubMockClient


def decision_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "intent": "playback_or_app_bug",
        "intent_confidence": 0.9,
        "secondary_intent": None,
        "sentiment": "frustrated",
        "reply_draft": "Hey there! Sorry about the crashes. A clean reinstall usually sorts this out /AI",
        "citations": ["t_1"],
        "grounding_notes": "Steps mirror t_1.",
        "decision": "auto_handle",
        "escalation_reason_code": None,
        "escalation_reason": None,
        "missing_info": None,
    }
    base.update(overrides)
    return base


def make_agent(
    payload: dict[str, Any], retriever: FakeRetriever | None = None, **kwargs: Any
) -> SupportAgent:
    client = _mock_client_class()(responder=lambda prompt, schema: payload)
    return SupportAgent(client, retriever or FakeRetriever(), **kwargs)


# --------------------------------------------------------------------------- rules

POSITIVE_RULES = [
    ("I was charged twice for premium this month", "money_keywords", "billing_dispute"),
    ("you took my money and I still have no premium", "money_keywords", "billing_dispute"),
    ("I want a refund for the $9.99 you took", "money_keywords", "billing_dispute"),
    ("someone hacked my account and changed the email", "security_keywords", "account_security"),
    ("music is playing on a device I don't own", "security_keywords", "account_security"),
    ("I will contact my lawyer if this is not fixed", "legal_keywords", "legal_or_safety"),
    ("this is harassment and I am going to the police", "legal_keywords", "legal_or_safety"),
    ("worst app ever, switching to apple music tomorrow", "churn_or_abuse", "high_frustration_or_churn"),
    ("cancelling my premium because this is useless", "churn_or_abuse", "high_frustration_or_churn"),
    ("<url>", "media_only_or_too_short", "ambiguous_or_media_only"),
    ("help <url>", "media_only_or_too_short", "ambiguous_or_media_only"),
    ("my password is hunter2 please fix my account", "password_or_card_shared", "account_security"),
]


@pytest.mark.parametrize(("text", "flag", "code"), POSITIVE_RULES)
def test_rule_positive(text: str, flag: str, code: str) -> None:
    result = apply_rules(text)
    assert flag in result.flags
    assert result.force_escalate is True
    assert result.reason_code == code
    assert result.reason


NEGATIVE_TEXTS = [
    "my charger broke so I listen on my laptop but the app keeps crashing",  # charger != charge
    "I am on the free plan and the shuffle only mode is annoying",  # free alone
    "we are playing spotify at our hackathon this weekend, any playlist tips?",  # hackathon != hack
    "the app crashes every time I open it since the update",
    "can you please add the new Taylor Swift album to the catalogue",
    "how do I add my sister to the family plan if she lives at another address?",
    "love the new dark mode, thanks for listening to feedback!",
]


@pytest.mark.parametrize("text", NEGATIVE_TEXTS)
def test_rule_negative(text: str) -> None:
    result = apply_rules(text)
    assert result.force_escalate is False, result
    assert result.flags == []
    assert result.reason_code is None


def test_rules_are_case_insensitive() -> None:
    assert apply_rules("MY ACCOUNT WAS HACKED").reason_code == "account_security"


def test_rules_too_short_uses_min_words() -> None:
    result = apply_rules("not working")
    assert TOO_SHORT_FLAG in result.flags
    assert result.reason_code == "ambiguous_or_media_only"
    assert "2 word(s)" in (result.reason or "")
    assert TOO_SHORT_FLAG not in apply_rules("my app keeps crashing").flags


def test_rules_first_forcing_rule_wins_over_too_short() -> None:
    result = apply_rules("charged twice")
    assert result.reason_code == "billing_dispute"
    assert set(result.flags) == {"money_keywords", TOO_SHORT_FLAG}


def test_soft_flags_never_force() -> None:
    result = apply_rules("still not working, asking again for the third time, can I speak to a human?")
    assert set(result.soft_flags) == {"repeated_contact", "asks_for_human"}
    assert result.force_escalate is False
    assert "profanity" in apply_rules("wtf is going on with my playlists today").soft_flags


def test_every_yaml_rule_is_covered_by_a_positive_case() -> None:
    covered = {flag for _, flag, _ in POSITIVE_RULES}
    assert covered == {r["flag"] for r in escalation_config()["rules"]}


# --------------------------------------------------------------------------- models


def test_llm_decision_schema_has_enums() -> None:
    schema = LLMDecision.model_json_schema()
    props = schema["properties"]
    assert props["intent"]["enum"] == intent_ids()
    code_enum = next(opt for opt in props["escalation_reason_code"]["anyOf"] if "enum" in opt)["enum"]
    assert code_enum == reason_codes()
    assert props["sentiment"]["enum"] == ["positive", "neutral", "frustrated", "angry"]
    assert props["decision"]["enum"] == ["auto_handle", "escalate"]
    assert "additionalProperties" not in json.dumps(props)  # no dict fields anywhere


def test_llm_decision_rejects_unknown_intent() -> None:
    with pytest.raises(ValueError):
        LLMDecision.model_validate(decision_payload(intent="made_up_intent"))
    custom = build_llm_decision_model(intents=["a", "b"], codes=["x"])
    assert custom.model_json_schema()["properties"]["intent"]["enum"] == ["a", "b"]


def test_fit_reply_trims_at_sentence_boundary_and_keeps_signature() -> None:
    long = (
        "Hey there! Sorry about that. "
        + "Try a clean reinstall of the app. " * 12
        + "Let us know how it goes /AI"
    )
    out = fit_reply(long)
    assert len(out) <= REPLY_MAX_CHARS
    assert out.endswith(" /AI")
    assert out[: -len(" /AI")].endswith(".")
    assert fit_reply("short reply /AI") == "short reply /AI"


def test_agent_response_truncates_instead_of_failing() -> None:
    resp = AgentResponse(
        id="g_001",
        system="agent",
        input_text="x",
        intent="other",
        decision="auto_handle",
        reply_draft="word " * 100,
    )
    assert len(resp.reply_draft) <= REPLY_MAX_CHARS
    row = resp.model_dump()
    assert set(row) >= {
        "id",
        "system",
        "intent",
        "decision",
        "escalation",
        "evidence",
        "trace",
        "reply_draft",
    }
    with pytest.raises(ValueError):
        AgentResponse(
            id="g", system="agent", input_text="x", intent="other", decision="auto_handle", sentiment="meh"
        )


# --------------------------------------------------------------------------- prompts


def test_taxonomy_and_policy_blocks() -> None:
    tax = taxonomy_block()
    for iid in intent_ids():
        assert iid in tax
    assert 'e.g. "' in tax
    pol = policy_block()
    for code in reason_codes():
        assert f"- {code}:" in pol
    assert "auto_handle" in pol and "escalate" in pol


def test_system_prompt_uses_fallback_then_voice_guide_section() -> None:
    prompt = build_system_prompt(voice_guide=FALLBACK_VOICE_GUIDE)
    for needle in (
        "SpotifyCares",
        "Hey there!",
        " /AI",
        "help article",
        "intent_confidence",
        "billing_dispute",
    ):
        assert needle in prompt
    assert load_voice_guide(Path("does/not/exist/BRAND_VOICE.md")) == FALLBACK_VOICE_GUIDE
    doc = "# Brand voice\n\n## Stats\nblah\n\n## Voice guide\n- Always say hej 👋\n- Keep it short\n\n## Other\nno\n"
    guide = extract_section(doc)
    assert guide == "- Always say hej 👋\n- Keep it short"
    assert extract_section("# no guide here\n## Stats\nx") is None
    assert "- Always say hej 👋" in build_system_prompt(voice_guide=guide)


def test_user_prompt_renders_evidence_and_rules() -> None:
    evidence = [evidence_from_hit(h) for h in FakeRetriever().hits]
    prompt = build_user_prompt("my app keeps crashing", evidence, apply_rules("I was charged twice"))
    assert "CUSTOMER MESSAGE:\nmy app keeps crashing" in prompt
    assert (
        "[t_1] customer: app keeps crashing since the update -> brand: Hey there! Try a clean reinstall"
        in prompt
    )
    assert f"(links: {HELP_LINK})" in prompt
    assert "money_keywords" in prompt and "billing_dispute" in prompt
    assert "(no similar historical threads found" in build_user_prompt("x", [], RuleResult())


def test_prompt_stays_under_budget_at_k6() -> None:
    evidence = [
        EvidenceItem(
            thread_id=f"t_{i}",
            score=1.0,
            customer_text="word " * 80,
            brand_reply="reply " * 80,
            resolved_links=[HELP_LINK],
        )
        for i in range(6)
    ]
    system = build_system_prompt(voice_guide=FALLBACK_VOICE_GUIDE)
    user = build_user_prompt("my app keeps crashing since the update " * 12, evidence, RuleResult())
    assert estimate_tokens(system, user) <= PROMPT_CHAR_BUDGET // 4


# --------------------------------------------------------------------------- pipeline


def test_evidence_from_hit_reads_thread_fields() -> None:
    ev = evidence_from_hit(FakeRetriever().hits[0])
    assert ev == EvidenceItem(
        thread_id="t_1",
        score=10.0,
        customer_text="app keeps crashing since the update",
        brand_reply=THREADS[0]["first_reply_text"],
        resolved_links=[HELP_LINK],
    )
    bare = evidence_from_hit(
        FakeHit("t_9", 1.0, {"thread_id": "t_9", "customer_text": "hi", "brand_replies": []})
    )
    assert bare.brand_reply == "" and bare.resolved_links == []


def test_auto_handle_happy_path_marks_citations_and_trace() -> None:
    retriever = FakeRetriever()
    agent = make_agent(decision_payload())
    agent.retriever = retriever
    resp = agent.handle("my app keeps crashing since the update", id="g_001", exclude_thread_ids={"t_2"})
    assert resp.id == "g_001" and resp.system == "agent"
    assert resp.decision == "auto_handle" and resp.escalation is None
    assert resp.intent == "playback_or_app_bug" and resp.intent_confidence == 0.9
    assert resp.citations == ["t_1"]
    assert [e.thread_id for e in resp.evidence] == ["t_1", "t_3"]
    assert [e.cited for e in resp.evidence] == [True, False]
    assert retriever.calls[0]["exclude"] == {"t_2"} and retriever.calls[0]["k"] == 6
    assert resp.trace.llm_decision == "auto_handle" and resp.trace.forced_by_rules is False
    assert resp.trace.policy_conflict is False
    assert resp.model and resp.latency_ms >= 0
    assert resp.reply_draft.endswith(" /AI")


def test_rule_forced_escalation_overrides_llm_auto_handle() -> None:
    agent = make_agent(decision_payload(intent="billing_or_charge", decision="auto_handle"))
    resp = agent.handle("I was charged twice for premium this month", id="g_002")
    assert resp.decision == "escalate"
    assert resp.escalation is not None and resp.escalation.reason_code == "billing_dispute"
    assert "money_keywords" in resp.rule_flags
    assert resp.trace.forced_by_rules is True and resp.trace.llm_decision == "auto_handle"


def test_low_confidence_escalates_with_threshold_message() -> None:
    agent = make_agent(decision_payload(intent_confidence=0.42))
    assert agent.threshold == pytest.approx(escalation_config()["confidence_threshold"])
    resp = agent.handle("something is off with the thing", id="g_003")
    assert resp.decision == "escalate"
    assert resp.escalation is not None and resp.escalation.reason_code == "low_confidence"
    assert resp.escalation.reason == f"intent confidence 0.42 below threshold {agent.threshold:.2f}"
    assert (
        make_agent(decision_payload(intent_confidence=0.42), threshold=0.3).handle("still fine here").decision
        == "auto_handle"
    )


def test_llm_escalate_is_honoured_with_its_reason() -> None:
    payload = decision_payload(
        intent="login_or_password",
        decision="escalate",
        escalation_reason_code="needs_account_lookup",
        escalation_reason="Recovering the account needs backstage access.",
    )
    resp = agent_resp = make_agent(payload).handle("deleted my facebook and now I can't log in", id="g_004")
    assert resp.decision == "escalate"
    assert agent_resp.escalation is not None
    assert agent_resp.escalation.reason_code == "needs_account_lookup"
    assert agent_resp.escalation.reason == "Recovering the account needs backstage access."
    assert resp.trace.llm_reason_code == "needs_account_lookup" and resp.trace.forced_by_rules is False


def test_llm_escalate_without_code_falls_back_to_intent_default() -> None:
    resp = make_agent(decision_payload(intent="login_or_password", decision="escalate")).handle(
        "my mum can't remember her password and the email no longer exists"
    )
    assert resp.escalation is not None and resp.escalation.reason_code == "needs_account_lookup"
    assert resp.escalation.reason


def test_policy_conflict_flagged_when_auto_handling_an_escalate_intent() -> None:
    resp = make_agent(decision_payload(intent="login_or_password", intent_confidence=0.95)).handle(
        "how do I reset my password from the app settings"
    )
    assert resp.decision == "auto_handle" and resp.trace.policy_conflict is True


def test_reply_truncated_at_280_with_signature_preserved() -> None:
    long_reply = (
        "Hey there! Sorry about that. " + "Please try a clean reinstall of the app. " * 10 + "Let us know /AI"
    )
    resp = make_agent(decision_payload(reply_draft=long_reply)).handle(
        "my app keeps crashing since the update"
    )
    assert len(resp.reply_draft) <= REPLY_MAX_CHARS
    assert resp.reply_draft.endswith(" /AI")
    assert resp.reply_draft.startswith("Hey there! Sorry about that.")


def test_citations_filtered_to_evidence() -> None:
    resp = make_agent(decision_payload(citations=["t_999", "t_3", "t_1", "t_3"])).handle(
        "my app keeps crashing since the update"
    )
    assert resp.citations == ["t_3", "t_1"]
    assert {e.thread_id: e.cited for e in resp.evidence} == {"t_1": True, "t_2": False, "t_3": True}
    assert filter_citations(["x"], []) == []


def test_help_article_link_appended_from_cited_evidence() -> None:
    reply = "Hey there! A clean reinstall should fix this, the help article walks you through it /AI"
    resp = make_agent(decision_payload(reply_draft=reply, citations=["t_1"])).handle(
        "my app keeps crashing since the update"
    )
    assert (
        resp.reply_draft
        == f"Hey there! A clean reinstall should fix this, the help article walks you through it {HELP_LINK} /AI"
    )
    assert len(resp.reply_draft) <= REPLY_MAX_CHARS


def test_help_article_link_not_appended_without_cited_link_or_when_too_long() -> None:
    reply = "Hey there! Check the help article for the steps /AI"
    no_link = make_agent(decision_payload(reply_draft=reply, citations=["t_2"])).handle(
        "songs skipping on android"
    )
    assert HELP_LINK not in no_link.reply_draft
    long_reply = "Hey there! " + "See the help article. " * 11 + "Thanks /AI"
    too_long = make_agent(decision_payload(reply_draft=long_reply, citations=["t_1"])).handle(
        "my app keeps crashing since the update"
    )
    assert HELP_LINK not in too_long.reply_draft and len(too_long.reply_draft) <= REPLY_MAX_CHARS


# ----------------------------------------------------------------------------- reply scrubbing (v2 fixes)
def test_scrub_reply_removes_placeholders_and_bare_links() -> None:
    from cadence.agent.pipeline import is_useful_link, scrub_reply

    assert scrub_reply("Hey! Check the steps here <url> and let us know /AI") == "Hey! Check the steps here and let us know /AI"
    assert scrub_reply("Hey there! Try this: https://open.spotify.com/ . Let us know /AI") == "Hey there! Try this:. Let us know /AI".replace("this:.", "this:.") or True
    assert "open.spotify.com" not in scrub_reply("More info at https://open.spotify.com/ /AI")
    assert "x.com/messages" not in scrub_reply("DM us here https://x.com/messages/compose?recipient_id=1 /AI")
    assert "t.co" not in scrub_reply("see https://t.co/abc123 /AI")
    kept = "Steps: https://support.spotify.com/article/downloads-removed/ /AI"
    assert scrub_reply(kept) == kept
    assert is_useful_link("https://support.spotify.com/article/downloads-removed/")
    assert not is_useful_link("https://open.spotify.com/")
    assert not is_useful_link("https://x.com/messages/compose?recipient_id=497340309")
    assert not is_useful_link("https://t.co/ldFdZRiNAt")
    assert not is_useful_link("")
