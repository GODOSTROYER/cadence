from types import SimpleNamespace

import pytest

from cadence.agent.selective import SelectiveAgent
from cadence.baselines.simple import TrainedIntentBaseline
from cadence.llm.base import CallMeta


class Client:
    def __init__(self, escalate=False):
        self.calls = []
        self.escalate = escalate

    def generate_json(self, prompt, schema, **kwargs):
        self.calls.append(prompt)
        obj = {"intent": "playback_or_app_bug", "intent_confidence": 0.99, "secondary_intent": None,
               "sentiment": "neutral", "decision": "escalate" if self.escalate else "auto_handle",
               "reply_draft": "Please restart the app and tell us what happens. /AI", "citations": ["e"],
               "escalation_reason_code": "needs_account_lookup" if self.escalate else None}
        if len(self.calls) == 2:
            obj["intent"] = "feature_request_or_feedback"
        return schema.model_validate(obj), CallMeta(model="fake", cached=True, latency_ms=1, prompt_tokens=10, output_tokens=5, attempts=0)


class Retriever:
    def __init__(self):
        self.calls = 0

    def search(self, *args, **kwargs):
        self.calls += 1
        return [SimpleNamespace(thread_id="e", score=1, thread={"customer_text": "app broken", "first_reply_text": "Restart the app."})]


def test_escalated_route_skips_retrieval_and_drafting_but_keeps_intent():
    client, retriever = Client(True), Retriever()
    result = SelectiveAgent(client, retriever).handle("My music stops playing after every song")
    assert result.intent == "playback_or_app_bug" and result.decision == "escalate"
    assert len(client.calls) == 1 and retriever.calls == 0
    assert result.trace.model_calls == 1


def test_drafting_cannot_change_message_only_routing_and_tokens_are_summed():
    client, retriever = Client(), Retriever()
    result = SelectiveAgent(client, retriever).handle("My music stops playing after every song")
    assert result.intent == "playback_or_app_bug"
    assert result.trace.model_calls == 2 and result.trace.prompt_tokens == 20
    assert retriever.calls == 1
    assert "Restart the app" not in client.calls[0]


def test_trained_baseline_does_not_use_evaluation_labels_or_vocabulary():
    rows = [{"id": str(i), "text": text, "gold": {"intent": label}} for i, (text, label) in enumerate([
        ("music stops playing", "playback_or_app_bug"), ("cannot play songs", "playback_or_app_bug"),
        ("charged twice money", "billing_or_charge"), ("refund payment", "billing_or_charge")])]
    model = TrainedIntentBaseline().fit(rows)
    evaluation = [{"id": "new", "text": "unseenword music", "gold": {"intent": "other"}}]
    predicted = model.predict(evaluation)
    evaluation[0]["gold"]["intent"] = "billing_or_charge"
    assert predicted == model.predict(evaluation)
    assert "unseenword" not in model.classifier.named_steps["tfidf"].vocabulary_
    with pytest.raises(ValueError, match="overlap"):
        model.predict(rows)
