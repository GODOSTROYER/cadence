"""Release invariants independent of model compliance and historical benchmarks."""

import json
from contextlib import contextmanager
from datetime import date

import pytest

from cadence.agent.actions import ActionCandidate
from cadence.agent.models import EvidenceItem
from cadence.agent.policy_v2 import POLICY
from cadence.agent.request_frame import RISK_KINDS, RequestFrame, RiskFinding
from cadence.agent.verified import ResponseAudit, VerifiedAgent
from cadence.knowledge.store import KnowledgeStore
from cadence.llm.base import CallMeta, LLMError


def frame(**updates):
    values = dict(
        intent="playback_or_app_bug", intent_confidence=0.8, issues=["playback_failure"],
        requested_outcome="Understand playback failure", language_supported=True, intelligible=True,
        risks=[RiskFinding(kind=kind, state="absent") for kind in RISK_KINDS],
    )
    return RequestFrame(**(values | updates))


def card(identity="ask_device", reply="Which device is affected? Please leave out private account details. /AI"):
    return ActionCandidate(
        id=identity, reply=reply, citations=["policy:clarification"],
        evidence=[EvidenceItem(thread_id="policy:clarification", brand_reply="Ask genuinely missing details.")],
        response_kind="clarification", eligibility_reasons=["Device is missing"], required_claims=[],
    )


def fallback(*args, **kwargs):
    return ActionCandidate(
        id="handoff", reply="A human should review this request. Please keep passwords and payment details private. /AI",
        citations=["policy:handoff"], evidence=[EvidenceItem(thread_id="policy:handoff")],
        response_kind="handoff", eligibility_reasons=[], required_claims=[],
    )


class Retriever:
    def search(self, *args, **kwargs):
        return []


class Client:
    model = "fake"

    def __init__(self, request=None, *, error=None, mutate=None):
        self.request = request or frame()
        self.error, self.mutate, self.calls = error, mutate, []

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append((prompt, schema, kwargs))
        if self.error:
            raise self.error
        meta = CallMeta(model="fake", cached=True, latency_ms=4, prompt_tokens=10, output_tokens=5, attempts=0)
        if schema is RequestFrame:
            return self.request, meta
        assert schema is ResponseAudit
        payload = json.loads(prompt)
        result = dict(
            human_required=False, risk_reason="No material risk", choice=payload["alternatives"][0]["action_id"],
            alternatives=[dict(
                action_id=c["action_id"], reply_sha256=c["reply_sha256"], addresses_issue=True,
                supported=True, prerequisites_met=True, necessary_next_step=True,
                no_unperformed_action=True, reason="Useful missing detail",
            ) for c in payload["alternatives"]],
        )
        if self.mutate:
            self.mutate(result)
        return schema.model_validate(result), meta


def test_default_candidate_uses_postpilot_authority_without_changing_legacy_default():
    agent = VerifiedAgent(Client(), Retriever(), as_of=date(2026, 9, 18))
    legacy = KnowledgeStore.load()

    assert agent.knowledge.registry.version == "spotify-current-v3-2026-09-18"
    assert legacy.registry.version == "spotify-current-v2-2026-09-18"
    assert agent.knowledge.get_applicable(
        "family_separate_accounts", agent.as_of,
        plan="premium_family", region="US", issues=["connect_unwanted_takeover"],
    ) is not None
    assert legacy.get("family_separate_accounts", agent.as_of) is None


def test_injected_legacy_authority_is_retained_for_frozen_studies():
    legacy = KnowledgeStore.load()
    agent = VerifiedAgent(Client(), Retriever(), knowledge=legacy, as_of=date(2026, 9, 18))

    assert agent.knowledge is legacy
    assert agent.knowledge.registry.version == "spotify-current-v2-2026-09-18"
    assert agent.knowledge.get("family_separate_accounts", agent.as_of) is None


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setattr("cadence.agent.verified.shortlist", lambda *a, **k: [card()])
    monkeypatch.setattr("cadence.agent.verified.handoff", fallback)

    def build(client=None, **kwargs):
        return VerifiedAgent(client or Client(), Retriever(), knowledge=object(), **kwargs)
    return build


def test_releases_exact_reviewed_question_despite_uncertain_intent(pipeline):
    client = Client()
    result = pipeline(client).handle("My music stops playing", id="x")
    assert result.decision == "auto_handle"
    assert result.reply_draft == json.loads(client.calls[1][0])["alternatives"][0]["reply"]
    assert result.intent_confidence == 0.8
    assert result.trace.model_calls == 2 and result.trace.prompt_tokens == 20
    assert result.trace.request_frame["issues"] == ["playback_failure"]
    assert "alternatives" not in client.calls[0][0]


def test_mandatory_risk_stops_before_answer_selection(pipeline):
    client = Client(request=frame(intent_confidence=1.0))
    result = pipeline(client).handle("Why are you discriminating against these artists?")
    assert result.decision == "escalate"
    assert result.trace.blocked_stage == "policy"
    assert len(client.calls) == 1


def test_auditor_new_risk_cannot_be_overridden_by_useful_reply(pipeline):
    client = Client(mutate=lambda r: r.update(human_required=True, risk_reason="The customer requests a human."))
    result = pipeline(client).handle("Music stopped")
    assert result.decision == "escalate" and result.trace.blocked_stage == "audit_risk"
    assert result.trace.audit_risk_reason == "The customer requests a human."
    supplied_policy = json.loads(client.calls[1][0])["locked_policy"]
    assert supplied_policy["boundaries"] == POLICY["boundaries"]
    assert supplied_policy["mandatory_risks"] == POLICY["risks"]
    assert supplied_policy["sha256"] == result.trace.policy_sha256


@pytest.mark.parametrize("mutation", [
    lambda r: r["alternatives"][0].update(reply_sha256="changed"),
    lambda r: r.update(choice="unauthorized"),
    lambda r: r["alternatives"].append(r["alternatives"][0].copy()),
])
def test_changed_unknown_or_duplicate_audit_is_not_released(pipeline, mutation):
    result = pipeline(Client(mutate=mutation)).handle("Music stopped")
    assert result.decision == "escalate" and result.trace.execution_error == "ValueError"


def test_fallback_must_also_have_passed_its_exact_review(pipeline, monkeypatch):
    second = card("ask_error", "What exact error appears? Please leave out private account details. /AI")
    monkeypatch.setattr("cadence.agent.verified.shortlist", lambda *a, **k: [card(), second])
    client = Client(mutate=lambda r: r["alternatives"][0].update(addresses_issue=False))
    result = pipeline(client).handle("Music stopped")
    assert result.decision == "auto_handle" and result.reply_draft == second.reply
    assert result.trace.action_id == "ask_error"


def test_no_approved_alternative_produces_handoff(pipeline):
    result = pipeline(Client(mutate=lambda r: r["alternatives"][0].update(supported=False))).handle("Music stopped")
    assert result.decision == "escalate"


def test_fabricated_extraction_cannot_select_specialist_handoff(pipeline):
    invalid = frame(issues=["student_verification"], facts=[dict(slot="plan", value="student", quote="not in input")])
    result = pipeline(Client(request=invalid)).handle("Music stopped")
    assert result.decision == "escalate" and result.intent == "other"
    assert result.trace.execution_error == "ValueError" and not result.trace.request_frame


def test_provider_failure_is_counted_and_does_not_leak_exception(pipeline):
    result = pipeline(Client(error=LLMError("secret-key and private customer details"))).handle("Music stopped")
    assert result.decision == "escalate" and result.trace.execution_error == "LLMError"
    assert "secret-key" not in result.model_dump_json()
    assert result.trace.model_calls == 1 and result.cached is False


def test_deadline_prevents_late_automatic_release(pipeline):
    tick = iter([0, 0, 40, 40])
    result = pipeline(clock=lambda: next(tick), deadline_s=30).handle("Music stopped")
    assert result.decision == "escalate" and result.trace.deadline_exceeded
    assert result.trace.execution_error == "TimeoutError"


def test_final_integrity_cannot_release_unperformed_action(pipeline, monkeypatch):
    bad = card(reply="We've refunded your payment. /AI")
    monkeypatch.setattr("cadence.agent.verified.shortlist", lambda *a, **k: [bad])
    result = pipeline().handle("Music stopped")
    assert result.decision == "escalate" and result.trace.integrity_blocked
    assert result.reply_draft == fallback().reply


def test_input_limit_rejects_whole_message_instead_of_truncating_risk(pipeline):
    with pytest.raises(ValueError):
        pipeline().handle("music " * 200 + "I will sue Spotify")


def test_candidate_is_not_a_valid_deployment_promotion_by_construction(pipeline):
    result = pipeline(variant="no_history").handle("Music stopped")
    assert result.system == "verified" and result.trace.variant == "no_history"
    assert result.trace.history_ids == []


def test_live_singleton_uses_each_requests_current_source_date(pipeline, monkeypatch):
    today = [date(2026, 9, 18)]
    monkeypatch.setattr("cadence.agent.verified.current_date", lambda: today[0])
    agent = pipeline()
    first = agent.handle("Music stopped")
    today[0] = date(2026, 10, 19)
    second = agent.handle("Music stopped")
    assert first.trace.source_as_of == "2026-09-18"
    assert second.trace.source_as_of == "2026-10-19"


def test_frozen_experiment_explicit_source_date_is_stable(pipeline, monkeypatch):
    monkeypatch.setattr("cadence.agent.verified.current_date", lambda: date(2027, 1, 1))
    result = pipeline(as_of=date(2026, 9, 18)).handle("Music stopped")
    assert result.trace.source_as_of == "2026-09-18"


def test_invalid_handoff_also_passes_final_integrity_or_uses_safe_holding(pipeline, monkeypatch):
    bad = ActionCandidate(
        id="bad_handoff", response_kind="handoff", reply="Contact support at https://invalid.example/help /AI",
        citations=["current:contact"], evidence=[EvidenceItem(
            thread_id="current:contact", resolved_links=["https://invalid.example/help"],
        )],
    )
    monkeypatch.setattr("cadence.agent.verified.handoff", lambda *a, **k: bad)
    result = pipeline().handle("I will sue Spotify")
    assert result.decision == "escalate" and result.trace.integrity_blocked
    assert result.trace.action_id == "verified_holding"
    assert "https://" not in result.reply_draft
    assert "fallback:unsupported_link" in result.trace.integrity_flags


@pytest.mark.parametrize("brand", ["@Spotify", "@SpotifyCares", "@115888"])
def test_brand_handle_removal_cannot_erase_directed_abuse(pipeline, brand):
    result = pipeline(Client(request=frame(issues=["playlist_create"]))).handle(
        f"Fuck {brand}, how do I create a playlist?"
    )
    assert result.decision == "escalate" and result.trace.blocked_stage == "policy"
    assert "Spotify" in result.input_text
    assert "deterministic:directed_abuse" in result.trace.policy_flags


def test_preserved_brand_handle_does_not_make_incidental_profanity_abuse(pipeline):
    result = pipeline().handle("Hey @SpotifyCares, this damn app stops playing")
    assert result.decision == "auto_handle"
    assert "deterministic:directed_abuse" not in result.trace.policy_flags


def test_failed_attempt_usage_is_preserved_in_api_trace(pipeline):
    class BudgetClient(Client):
        @contextmanager
        def request_budget(self, **kwargs):
            class Budget:
                def as_dict(self):
                    return dict(network_attempts=2, prompt_tokens=120, output_tokens=30,
                                unknown_failed_usage=True, deadline_exceeded=False)
            yield Budget()

    result = pipeline(BudgetClient(error=LLMError("provider unavailable"))).handle("Music stopped")
    assert result.trace.attempts == 2
    assert result.trace.prompt_tokens == 120 and result.trace.output_tokens == 30
    assert result.trace.token_usage_incomplete
