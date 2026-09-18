"""Fault controls exercise actual matched agents without model/network calls."""

import json
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

from cadence.agent.balanced import BalancedAgent
from cadence.agent.pipeline import SupportAgent
from cadence.agent.quality import QualityAgent
from cadence.agent.request_frame import RISK_KINDS
from cadence.agent.verified import VerifiedAgent
from cadence.eval.challenge import CHALLENGE_FAILURES, challenge_setup, validate_setup
from cadence.knowledge.store import KnowledgeStore
from cadence.llm.base import CallMeta, LLMError


class Retriever:
    def __init__(self):
        self.calls = 0

    def search(self, *args, **kwargs):
        self.calls += 1
        return []


class Client:
    model = "offline-fixture"

    def __init__(self):
        self.calls = []
        self._request = SimpleNamespace(budgets=())

    @contextmanager
    def request_budget(self, **kwargs):
        prior = self._request.budgets
        budget = SimpleNamespace(deadline=12345.0, deadline_exceeded=False)
        self._request.budgets = (*prior, budget)
        try:
            yield budget
        finally:
            self._request.budgets = prior

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append(schema.__name__)
        route = dict(intent="playback_or_app_bug", intent_confidence=.99,
                     sentiment="neutral", decision="auto_handle")
        if schema.__name__ == "RequestFrame":
            row = dict(intent="playback_or_app_bug", intent_confidence=.99,
                       issues=["playback_failure"], requested_outcome="Diagnose playback",
                       language_supported=True, intelligible=True,
                       risks=[dict(kind=kind, state="absent") for kind in RISK_KINDS])
        elif schema.__name__ == "ResponseAudit":
            choices = json.loads(prompt)["alternatives"]
            row = dict(human_required=False, risk_reason="No required risk", choice=choices[0]["action_id"],
                       alternatives=[dict(action_id=c["action_id"], reply_sha256=c["reply_sha256"],
                                          addresses_issue=True, supported=True, prerequisites_met=True,
                                          necessary_next_step=True, no_unperformed_action=True,
                                          reason="Useful diagnostic help") for c in choices])
        elif schema.__name__ == "RoutingDecision":
            row = route
        elif schema.__name__ == "BalancedPlan":
            row = route | dict(action="ask_device", fallback="ask_error", request_scope="public_help",
                               rationale="Device is missing")
        elif schema.__name__ == "QualityDraft":
            row = dict(action="ask_device", rationale="Device is missing")
        elif schema.__name__ in {"ReleaseReview", "Audit"}:
            row = dict(addresses_issue=True, supported=True, no_unperformed_action=True,
                       useful_next_step=True, reason="Appropriate question")
            if schema.__name__ == "Audit":
                row.update(choice="primary", human_required=False)
        else:
            row = route | dict(reply_draft="Which device is affected? /AI", citations=[], grounding_notes="Question")
        return schema.model_validate(row), CallMeta(model=self.model, cached=True, latency_ms=0,
                                                   prompt_tokens=10, output_tokens=5, attempts=0)


class Observed:
    """Same observation/delegation shape as the experiment runner."""

    def __init__(self, client):
        self.client, self.calls = client, []

    def __getattr__(self, key):
        return getattr(self.client, key)

    def generate_json(self, *args, **kwargs):
        try:
            result = self.client.generate_json(*args, **kwargs)
        except Exception as error:
            self.calls.append(type(error).__name__)
            raise
        self.calls.append("success")
        return result


def build(agent_type):
    client = Observed(Client())
    kwargs = {"as_of": date(2026, 9, 18)} if agent_type is VerifiedAgent else {}
    return agent_type(client, Retriever(), **kwargs), client


@pytest.mark.parametrize("setup", ["provider_error", {"inject": "unknown"}, {"inject": 1},
                                  {"inject": "provider_error", "gold": True}, ["provider_error"]])
def test_invalid_setup_rejected_before_invocation(setup):
    agent, client = build(SupportAgent)
    with pytest.raises(ValueError), challenge_setup(agent, client, setup):
        pytest.fail("Malformed setup reached invocation")
    assert not client.calls


def test_supported_setup_schema_and_system_validation():
    for token in CHALLENGE_FAILURES:
        assert validate_setup({"inject": token}, ["agent", "quality", "balanced", "verified"]) == {"inject": token}
    assert validate_setup(None) == {}
    with pytest.raises(ValueError):
        validate_setup({}, ["unregistered"])
    with pytest.raises(ValueError):
        validate_setup({}, "agent")


@pytest.mark.parametrize("agent_type", [SupportAgent, QualityAgent, BalancedAgent, VerifiedAgent])
@pytest.mark.parametrize("inject", ["provider_timeout", "provider_error", "context_budget",
                                    "malformed_extraction", "deadline_exhausted"])
def test_common_fault_reaches_all_four_agents_and_restores_dependencies(agent_type, inject):
    agent, client = build(agent_type)
    underlying, retriever = client.client, agent.retriever
    with challenge_setup(agent, client, {"inject": inject}) as execution:
        if agent_type is VerifiedAgent:
            response = agent.handle("My music stops playing")
            assert response.decision == "escalate" and response.trace.execution_error
        else:
            with pytest.raises((TimeoutError, LLMError, ValueError)):
                agent.handle("My music stops playing")
    assert execution["applicable"] and execution["triggered"] and execution["status"] == "applied"
    assert execution["synthetic"] and len(client.calls) == 1
    assert not underlying.calls  # Injected failures are not live model calls.
    assert client.client is underlying and agent.client is client and agent.retriever is retriever


@pytest.mark.parametrize("agent_type", [QualityAgent, BalancedAgent, VerifiedAgent])
def test_audit_failure_targets_audit_not_extraction_or_drafting(agent_type):
    agent, client = build(agent_type)
    underlying = client.client
    with challenge_setup(agent, client, {"inject": "malformed_audit"}) as execution:
        if agent_type is VerifiedAgent:
            response = agent.handle("My music stops playing")
            assert response.trace.blocked_stage == "response_audit"
        else:
            with pytest.raises(ValueError):
                agent.handle("My music stops playing")
    assert execution["stage"] == "response_audit" and execution["status"] == "applied"
    assert len(underlying.calls) == (2 if agent_type is QualityAgent else 1)
    assert client.calls[-1] == "ValidationError"


def test_nonexistent_reference_audit_is_explicitly_not_applicable():
    agent, client = build(SupportAgent)
    underlying = client.client
    with challenge_setup(agent, client, {"inject": "malformed_audit"}) as execution:
        agent.handle("My music stops playing")
    assert execution["status"] == "not_applicable" and not execution["applicable"]
    assert not execution["triggered"] and underlying.calls == ["LLMDecision"]


def test_policy_early_return_does_not_claim_untested_audit_coverage():
    agent, client = build(VerifiedAgent)
    with challenge_setup(agent, client, {"inject": "malformed_audit"}) as execution:
        response = agent.handle("I will sue Spotify")
    assert response.decision == "escalate"
    assert execution["applicable"] and not execution["triggered"]
    assert execution["status"] == "not_reached"


@pytest.mark.parametrize("agent_type", [SupportAgent, QualityAgent, BalancedAgent, VerifiedAgent])
def test_retrieval_fault_uses_real_dependency_and_preserves_original(agent_type):
    agent, client = build(agent_type)
    original = agent.retriever
    with challenge_setup(agent, client, {"inject": "retrieval_error"}) as execution:
        if agent_type is VerifiedAgent:
            response = agent.handle("My music stops playing")
            assert response.trace.blocked_stage == "retrieval"
        else:
            with pytest.raises(OSError):
                agent.handle("My music stops playing")
    assert execution["triggered"] and execution["stage"] == "retrieval"
    assert agent.retriever is original and original.calls == 0


@pytest.mark.parametrize("inject", ["expired_knowledge", "missing_knowledge"])
def test_knowledge_controls_change_actual_authority_without_changing_original(inject):
    agent, client = build(VerifiedAgent)
    original = agent.knowledge
    before = original.fingerprint()
    official = [c.id for c in original.claims.values() if original.sources[c.source_id].role == "current_official"]
    assert official and any(original.get(key, agent.as_of) for key in official)
    with challenge_setup(agent, client, {"inject": inject}) as execution:
        assert isinstance(agent.knowledge, KnowledgeStore) and agent.knowledge is not original
        assert all(agent.knowledge.get(key, agent.as_of) is None for key in official)
        assert execution["knowledge_sha256"] != before
        expected = "expired_source" if inject == "expired_knowledge" else "unknown_claim"
        assert agent.knowledge.unavailable_reason(official[0], agent.as_of) == expected
    assert execution["triggered"] and execution["status"] == "applied"
    assert agent.knowledge is original and original.fingerprint() == before


@pytest.mark.parametrize("agent_type", [SupportAgent, QualityAgent, BalancedAgent])
@pytest.mark.parametrize("inject", ["expired_knowledge", "missing_knowledge"])
def test_historical_static_sources_never_count_as_tested_registry_fault(agent_type, inject):
    agent, client = build(agent_type)
    with challenge_setup(agent, client, {"inject": inject}) as execution:
        agent.handle("My music stops playing")
    assert not execution["applicable"] and not execution["triggered"]
    assert execution["status"] == "not_applicable"


def test_deadline_exhaustion_marks_existing_request_budget_without_sleep_or_model_call():
    agent, client = build(SupportAgent)
    with client.request_budget(seconds=30) as budget:
        with challenge_setup(agent, client, {"inject": "deadline_exhausted"}), pytest.raises(TimeoutError):
            agent.handle("My music stops playing")
        assert budget.deadline == 0 and budget.deadline_exceeded


def test_restoration_even_if_invocation_body_raises_before_dependency_use():
    agent, client = build(SupportAgent)
    original = client.client
    with pytest.raises(RuntimeError), challenge_setup(agent, client, {"inject": "provider_error"}) as execution:
        raise RuntimeError("Other invocation failure")
    assert client.client is original
    assert execution["status"] == "not_reached" and not execution["triggered"]


def test_empty_setup_preserves_normal_invocation():
    agent, client = build(QualityAgent)
    original = client.client
    with challenge_setup(agent, client, {}) as execution:
        agent.handle("My music stops playing")
    assert execution["status"] == "not_requested" and not execution["synthetic"]
    assert client.client is original and len(original.calls) == 3
