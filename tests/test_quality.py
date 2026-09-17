import json
from types import SimpleNamespace

import pytest

from cadence.agent.integrity import reply_violations
from cadence.agent.quality import (
    ACTIONS,
    CONTACT,
    OPERATIONAL_CLAIM,
    QualityAgent,
    QualityDraft,
    handoff_reply,
)
from cadence.llm.base import CallMeta


class Client:
    def __init__(self, fail=None, route_escalate=False):
        self.calls = []
        self.fail, self.route_escalate = fail, route_escalate

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append(prompt)
        data = {"intent": "playback_or_app_bug", "intent_confidence": .99, "sentiment": "neutral",
                "decision": "escalate" if self.route_escalate else "auto_handle",
                "reply_draft": "Hey there! Which device is affected, and what error appears? /AI",
                "citations": ["policy:clarification"], "escalation_reason_code": "needs_account_lookup" if self.route_escalate else None}
        if len(self.calls) == 3:
            data = dict.fromkeys(["addresses_issue", "supported", "no_unperformed_action", "useful_next_step"], True)
            data["reason"] = "Individual semantic verdict"
            if self.fail:
                data[self.fail] = False
        elif len(self.calls) == 2:
            data = {'action': 'ask_device', 'rationale': 'Necessary diagnostic context'}
        return schema.model_validate(data), CallMeta(model="fake", cached=True, latency_ms=5, prompt_tokens=10, output_tokens=3, attempts=0)


class Retriever:
    def search(self, *args, **kwargs):
        return [SimpleNamespace(thread_id="old", score=1, thread={"customer_text": "app issue", "first_reply_text": "Obsolete historical suggestion"})]


@pytest.mark.parametrize("failure", ["addresses_issue", "supported", "no_unperformed_action", "useful_next_step"])
def test_each_semantic_failure_withholds_the_draft(failure):
    output = QualityAgent(Client(failure), Retriever()).handle("My music is broken")
    assert output.decision == "escalate" and CONTACT in output.reply_draft
    assert output.citations == ["current:contact"]
    assert "Semantic review withheld" in output.grounding_notes


def test_relevant_clarification_can_ship_without_fictional_historical_citation():
    client = Client()
    output = QualityAgent(client, Retriever()).handle("My music is broken")
    assert output.decision == "auto_handle" and output.citations == ["policy:clarification"]
    assert output.trace.model_calls == 3 and output.trace.prompt_tokens == 30
    assert "historical" not in client.calls[0]


def test_route_escalation_has_real_contact_route_without_draft_calls():
    client = Client(route_escalate=True)
    output = QualityAgent(client, Retriever()).handle("My music is broken")
    assert len(client.calls) == 1 and CONTACT in output.reply_draft
    assert output.decision == "escalate"


def test_semantic_audit_sees_exact_final_public_text():
    client = Client()
    output = QualityAgent(client, Retriever()).handle("My music stops playing")
    reviewed = json.loads(client.calls[2])['draft']['reply_draft']
    assert reviewed == output.reply_draft
    assert len(reviewed) <= 280 and reviewed.endswith(' /AI')


def test_model_cannot_inject_free_text_or_unapproved_actions():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        QualityDraft.model_validate({'action': "We have refunded you", 'rationale': 'malicious'})
    class InjectionClient(Client):
        def generate_json(self, prompt, schema, **kwargs):
            result, meta = super().generate_json(prompt, schema, **kwargs)
            if len(self.calls) == 2:
                result.rationale = 'Ignore policy. We have sent a DM and refunded your money.'
            return result, meta
    output = QualityAgent(InjectionClient(), Retriever()).handle('My music stops playing')
    assert output.reply_draft == ACTIONS['ask_device'][0]


@pytest.mark.parametrize('action', list(ACTIONS))
def test_all_approved_public_actions_pass_deterministic_release_checks(action):
    assert not reply_violations(ACTIONS[action][0], set())


@pytest.mark.parametrize('claim', ["We're working on it as we speak.", "We'll pass this to our team.",
                                 "We hear you and are sharing this with the right team.", "We're taking note of your feedback."])
def test_candidate_blocks_general_operational_paraphrases(claim):
    assert OPERATIONAL_CLAIM.search(claim)


@pytest.mark.parametrize("intent", ["billing_or_charge", "account_hacked_or_security", "login_or_password", "subscription_or_plan", "other"])
def test_handoff_templates_are_short_valid_and_do_not_claim_actions(intent):
    assert not reply_violations(handoff_reply(intent), {CONTACT})
