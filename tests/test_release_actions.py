"""Action claims require capabilities; historical numeric limits are not current policy."""
from types import SimpleNamespace

import pytest

from cadence.agent.integrity import SAFE_HOLDING_REPLY, reply_violations
from cadence.agent.pipeline import SupportAgent
from cadence.llm.base import CallMeta


@pytest.mark.parametrize('reply,flag', [
    ("We've just sent a DM your way. /AI", 'unperformed_action'),
    ("I have already restored your account. /AI", 'unperformed_action'),
    ("We successfully updated your details. /AI", 'unperformed_action'),
    ("You can download up to 8,000 tracks. /AI", 'unverified_numeric_limit'),
    ("The maximum is 4 different devices. /AI", 'unverified_numeric_limit'),
    ("Please drop us a direct message about this. /AI", 'requires_private_handoff'),
    ("DM us with your account email. /AI", 'requires_private_handoff'),
])
def test_unsupported_operational_drafts_are_withheld(reply, flag):
    assert flag in reply_violations(reply, set())


def test_handoff_is_allowed_only_after_escalation():
    reply = "Please send us a DM about your account. /AI"
    assert 'requires_private_handoff' in reply_violations(reply, set())
    assert not reply_violations(reply, set(), allow_private_handoff=True)
    assert 'unperformed_action' in reply_violations(
        "We've sent a private message. /AI", set(), allow_private_handoff=True)


def test_public_instructions_and_prohibitions_remain_available():
    assert not reply_violations("Please restart the app and describe what happens. /AI", set())
    assert not reply_violations("Try step 3 and restart the app. /AI", set())
    assert not reply_violations("Don't send us a DM with your password. Describe the issue here. /AI", set())


def test_private_handoff_cannot_retain_auto_handle_despite_valid_citation():
    class Retriever:
        def search(self, *args, **kwargs):
            return [SimpleNamespace(thread_id='t_safe', score=1, thread={
                'customer_text': 'question about the app',
                'first_reply_text': 'Please describe the issue here.'})]

    class Client:
        def generate_json(self, prompt, schema, **kwargs):
            return schema.model_validate({
                'intent': 'other', 'intent_confidence': 1, 'secondary_intent': None,
                'sentiment': 'neutral', 'reply_draft': 'Please send us a DM about your account. /AI',
                'citations': ['t_safe'], 'grounding_notes': 'Historical reply',
                'decision': 'auto_handle', 'escalation_reason_code': None, 'escalation_reason': None,
            }), CallMeta(model='fake', cached=True, latency_ms=0, prompt_tokens=0, output_tokens=0, attempts=0)

    result = SupportAgent(Client(), Retriever()).handle('I have a question about the app')
    assert result.decision == 'escalate'
    assert result.reply_draft == SAFE_HOLDING_REPLY
    assert 'requires_private_handoff' in result.trace.integrity_flags
