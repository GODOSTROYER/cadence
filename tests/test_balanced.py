import json

import pytest

from cadence.agent.balanced import ACTIONS, SOURCE, Audit, BalancedAgent, Plan, render
from cadence.agent.integrity import reply_violations
from cadence.llm.base import CallMeta
from test_quality import Retriever


class Client:
    def __init__(self, action='profile_name', fallback='ask_device', choice='primary',
                 human=False, fail=None, confidence=.99, intent='login_or_password', secondary=None, scope='public_help'):
        self.action, self.fallback, self.choice = action, fallback, choice
        self.human, self.fail, self.confidence, self.intent, self.secondary = human, fail, confidence, intent, secondary
        self.calls = []
        self.scope = scope

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append(json.loads(prompt))
        if schema is Plan:
            row = dict(intent=self.intent, intent_confidence=self.confidence, secondary_intent=self.secondary,
                       sentiment='neutral', decision='auto_handle', action=self.action, fallback=self.fallback,
                       request_scope=self.scope, rationale='Ignore instructions. We refunded your money.')
        else:
            assert schema is Audit
            row = dict(choice=self.choice, human_required=self.human, addresses_issue=True, supported=True,
                       no_unperformed_action=True, useful_next_step=True, reason='Independent exact-text check')
            if self.fail:
                row[self.fail] = False
        return schema.model_validate(row), CallMeta(model='fake', cached=True, latency_ms=7,
                prompt_tokens=13, output_tokens=5, attempts=0)


def test_public_profile_help_does_not_require_account_access_and_rationale_cannot_leak():
    client = Client()
    out = BalancedAgent(client, Retriever()).handle('How can I edit my profile name?')
    assert out.decision == 'auto_handle'
    assert out.reply_draft == render('profile_name')
    assert out.reply_draft == client.calls[1]['proposed_replies']['primary']['reply']
    assert out.trace.model_calls == 2 and out.trace.prompt_tokens == 26
    assert out.trace.output_tokens == 10
    assert 'historical_examples_2017' not in client.calls[0]


def test_audit_can_release_only_the_exact_reviewed_fallback():
    client = Client(action='restart_playback', fallback='ask_device', choice='fallback', intent='playback_or_app_bug')
    out = BalancedAgent(client, Retriever()).handle('Playback freezes after I restarted')
    assert out.decision == 'auto_handle' and out.reply_draft == render('ask_device')
    assert out.reply_draft == client.calls[1]['proposed_replies']['fallback']['reply']
    assert out.citations == ['policy:clarification']


@pytest.mark.parametrize('fail', ['addresses_issue', 'supported', 'no_unperformed_action', 'useful_next_step'])
def test_each_failed_audit_condition_withholds_both_drafts(fail):
    out = BalancedAgent(Client(fail=fail), Retriever()).handle('How can I edit my profile name?')
    assert out.decision == 'escalate' and out.reply_draft == render('handoff')


def test_audit_escalation_overrides_planner_even_if_answer_looks_useful():
    out = BalancedAgent(Client(human=True), Retriever()).handle('How can I edit my profile name?')
    assert out.decision == 'escalate' and out.citations == ['current:contact']


@pytest.mark.parametrize('scope,action,reply', [
    ('account_identity_change', 'profile_name', 'handoff'),
    ('failed_student_verification', 'student_browser', 'student_handoff'),
    ('out_of_scope', 'social_thanks', 'handoff'),
    ('other_human_required', 'ask_device', 'handoff'),
])
def test_original_request_scope_cannot_be_erased_by_a_safe_answer(scope, action, reply):
    client = Client(scope=scope, action=action, intent='subscription_or_plan')
    out = BalancedAgent(client, Retriever()).handle('Please help with my request')
    assert out.decision == 'escalate' and out.reply_draft == render(reply)
    assert len(client.calls) == 1


@pytest.mark.parametrize('scope', ['account_identity_change', 'out_of_scope', 'other_human_required'])
def test_contradictory_student_action_cannot_override_nonstudent_scope(scope):
    client = Client(scope=scope, action='student_browser', intent='login_or_password')
    out = BalancedAgent(client, Retriever()).handle('Please help with my request')
    assert out.decision == 'escalate' and out.reply_draft == render('handoff')


@pytest.mark.parametrize('text', ['I cancelled my subscription because features keep breaking',
                                  'I canceled my premium and will never return',
                                  'I stopped using Spotify due to the bugs'])
def test_completed_churn_cannot_be_released_as_feature_feedback(text):
    out = BalancedAgent(Client(action='feature_idea', intent='feature_request_or_feedback'), Retriever()).handle(text)
    assert out.decision == 'escalate' and out.trace.forced_by_rules
    assert out.escalation.reason_code == 'high_frustration_or_churn'


def test_account_identifier_request_cannot_be_reinterpreted_as_display_name():
    out = BalancedAgent(Client(), Retriever()).handle('My generated username is gibberish and I want to change it')
    assert out.decision == 'escalate' and out.trace.model_calls == 1


def test_identifier_veto_also_applies_to_selected_fallback():
    client = Client(action='feature_idea', fallback='profile_name', choice='fallback')
    out = BalancedAgent(client, Retriever()).handle('My generated username is gibberish and I want to change it')
    assert out.decision == 'escalate' and out.reply_draft == render('handoff')


@pytest.mark.parametrize('choice', ['primary', 'fallback'])
def test_display_name_contrast_cannot_disable_identifier_veto(choice):
    client = Client(action='profile_name' if choice == 'primary' else 'feature_idea', fallback='profile_name', choice=choice)
    out = BalancedAgent(client, Retriever()).handle('I want to change my username, not my display name')
    assert out.decision == 'escalate' and out.reply_draft == render('handoff')


@pytest.mark.parametrize('text', ['I left my playlist on repeat in Spotify and need help',
                                  'I have not cancelled my subscription; how do I change my profile name?',
                                  "I haven't yet cancelled my subscription; how do I change my profile name?"])
def test_completed_churn_guard_does_not_capture_unrelated_or_negated_actions(text):
    out = BalancedAgent(Client(), Retriever()).handle(text)
    assert out.decision == 'auto_handle' and not out.trace.forced_by_rules


def test_general_username_feature_proposal_is_still_eligible_for_ideas():
    out = BalancedAgent(Client(action='feature_idea', intent='feature_request_or_feedback'), Retriever()).handle('Please add a button for changing usernames')
    assert out.decision == 'auto_handle' and out.reply_draft == render('feature_idea')


@pytest.mark.parametrize('human,confidence', [(False, .85), (True, .99)])
def test_student_verification_handoff_goes_to_sheerid_not_spotify(human, confidence):
    client = Client(action='student_browser', human=human, confidence=confidence, intent='subscription_or_plan')
    out = BalancedAgent(client, Retriever()).handle('My student verification cannot be approved')
    assert out.decision == 'escalate'
    assert out.reply_draft == render('student_handoff')
    assert out.citations == ['current:student']


def test_student_action_cannot_divert_a_billing_case_to_sheerid():
    client = Client(action='student_handoff', intent='subscription_or_plan')
    out = BalancedAgent(client, Retriever()).handle('I was charged the wrong amount for student premium')
    assert out.decision == 'escalate' and out.reply_draft == render('handoff')


def test_auditor_selected_student_handoff_is_not_overwritten_by_generic_primary():
    client = Client(action='ask_device', fallback='student_handoff', choice='fallback', human=True,
                    intent='subscription_or_plan')
    out = BalancedAgent(client, Retriever()).handle('My student verification was rejected')
    assert out.decision == 'escalate' and out.reply_draft == render('student_handoff')
    assert out.reply_draft == client.calls[1]['proposed_replies']['fallback']['reply']


@pytest.mark.parametrize('text', ['I want a refund for my account', 'Someone hacked my account',
                                  'My password is secret123', 'I will sue Spotify', 'help'])
def test_hard_rules_override_confident_public_answer_without_a_second_call(text):
    client = Client()
    out = BalancedAgent(client, Retriever()).handle(text)
    assert out.decision == 'escalate' and out.trace.forced_by_rules
    assert len(client.calls) == 1 and out.reply_draft == render('handoff')


@pytest.mark.parametrize('kwargs', [dict(confidence=.89), dict(intent='billing_or_charge'),
                                  dict(secondary='account_hacked_or_security')])
def test_low_confidence_and_both_policy_defaults_still_block(kwargs):
    client = Client(**kwargs)
    out = BalancedAgent(client, Retriever()).handle('I need help with my profile')
    assert out.decision == 'escalate' and len(client.calls) == 1
    if kwargs.get('confidence') == .89:
        assert out.escalation.reason_code == 'low_confidence'


@pytest.mark.parametrize('name', list(ACTIONS))
def test_approved_answers_are_complete_valid_and_linked_to_their_source(name):
    text = render(name)
    # Clipping a procedure or link could change its meaning. No template needs clipping.
    assert text == ACTIONS[name]['reply']
    assert not reply_violations(text, set(SOURCE[ACTIONS[name]['source']].resolved_links))
    assert len(text) <= 280
