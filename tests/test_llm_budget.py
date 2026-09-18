"""Multi-stage provider budgets: real attempts, deadlines, replay and isolation."""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ConfigDict, ValidationError

from cadence.llm.base import CacheMissError, LLMError, QuotaExhausted
from cadence.llm.cache import schema_json
from cadence.llm.gemini import GeminiClient


class Reply(BaseModel):
    answer: str


class StrictReply(Reply):
    model_config = ConfigDict(extra="forbid")


class NestedStrictReply(BaseModel):
    replies: list[StrictReply]


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def response(text: str = '{"answer":"ok"}', usage: bool = True) -> Any:
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=10, candidates_token_count=3, thoughts_token_count=2,
        ) if usage else None,
    )


class Provider:
    def __init__(self) -> None:
        self.outcomes: list[Any] = []
        self.requests: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0) if self.outcomes else response()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome() if callable(outcome) else outcome


@pytest.fixture
def setup_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CADENCE_CACHE_ONLY", raising=False)
    clock = Clock()
    provider = Provider()
    monkeypatch.setattr(
        "cadence.llm.gemini.genai.Client",
        lambda **kwargs: SimpleNamespace(models=provider, close=lambda: None),
    )
    client = GeminiClient(
        "gemini-test", api_key="test-key", cache_path=tmp_path / "cache.sqlite",
        rpm=100, rpd=1000, clock=clock, sleeper=clock.sleep, deadline_s=200,
    )
    yield client, clock, provider
    client.close()


def test_two_stages_share_attempts_and_success_usage(setup_client):
    client, _, provider = setup_client
    with client.request_budget(60, max_attempts=2) as budget:
        _, first_meta = client.generate_json("first", Reply)
        _, second_meta = client.generate_json("second", Reply)
        assert client.budget_status() == budget.as_dict()
        with pytest.raises(LLMError, match="attempt budget"):
            client.generate_json("third", Reply)
    assert len(provider.requests) == budget.network_attempts == 2
    assert (budget.prompt_tokens, budget.output_tokens) == (20, 10)
    assert (first_meta.attempts, second_meta.attempts) == (1, 1)
    assert budget.failed_attempts == 0
    assert not budget.unknown_usage
    assert not budget.unknown_failed_usage
    assert client.budget_status() is None
    # A finished scope does not constrain the next independent request.
    client.generate_json("outside", Reply)
    assert len(provider.requests) == 3


def test_retries_spend_shared_attempts_before_second_stage(setup_client):
    client, clock, provider = setup_client
    provider.outcomes = [TimeoutError("transport detail"), response()]
    with client.request_budget(60, max_attempts=2) as budget:
        _, meta = client.generate_json("first", Reply)
        with pytest.raises(LLMError, match="attempt budget"):
            client.generate_json("second", Reply)
    assert meta.attempts == 2
    assert budget.network_attempts == 2
    assert budget.failed_attempts == 1
    assert budget.unknown_usage
    assert budget.unknown_failed_usage
    assert len(provider.requests) == 2
    assert not clock.sleeps  # The transport retry switches clients immediately.


@pytest.mark.parametrize("code", [400, 429, 503])
def test_provider_rejections_count_without_leaking_errors(setup_client, caplog, code):
    client, clock, provider = setup_client
    error_type = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    secret = "secret-provider-diagnostic-content"
    provider.outcomes = [error_type(code, {"error": {"message": secret, "code": code}})]
    with client.request_budget(60, max_attempts=1) as budget:
        with pytest.raises(LLMError) as exc:
            client.generate_json("first", Reply)
    assert budget.network_attempts == budget.failed_attempts == 1
    assert budget.unknown_failed_usage
    assert secret not in str(exc.value)
    assert secret not in json.dumps(budget.as_dict())
    assert secret not in caplog.text
    assert not clock.sleeps


def test_thinking_config_fallback_spends_provider_attempt(setup_client):
    client, _, provider = setup_client
    client.thinking_budget = 16
    provider.outcomes = [genai_errors.ClientError(
        400, {"error": {"message": "thinking configuration is not supported", "code": 400}},
    ), response()]
    with client.request_budget(60, max_attempts=2) as budget:
        _, meta = client.generate_json("first", Reply)
    assert budget.network_attempts == meta.attempts == 2
    assert budget.failed_attempts == 1
    assert budget.unknown_failed_usage
    assert provider.requests[0]["config"].thinking_config is not None
    assert provider.requests[1]["config"].thinking_config is None


def test_cooldown_refusal_does_not_spend_another_attempt(setup_client):
    client, _, provider = setup_client
    provider.outcomes = [genai_errors.ClientError(
        429, {"error": {"message": "quota unavailable", "code": 429}},
    )]
    with client.request_budget(20, max_attempts=4) as budget:
        with pytest.raises(QuotaExhausted, match="cooling down"):
            client.generate_json("first", Reply)
    assert budget.network_attempts == budget.failed_attempts == len(provider.requests) == 1


def test_local_rate_limit_refusal_spends_no_provider_attempt(setup_client):
    client, clock, provider = setup_client
    client.rpm = 1
    client.generate_json("outside-budget", Reply)
    clock.now += 20
    with client.request_budget(45) as budget:
        with pytest.raises(QuotaExhausted, match="deadline"):
            client.generate_json("queued", Reply)
    assert budget.network_attempts == budget.failed_attempts == 0
    assert len(provider.requests) == 1
    assert not budget.unknown_failed_usage


def test_parse_failures_preserve_known_failed_usage(setup_client):
    client, _, provider = setup_client
    provider.outcomes = [response("not JSON"), response()]
    with client.request_budget(60, max_attempts=3) as budget:
        _, meta = client.generate_json("first", Reply)
    assert (budget.network_attempts, budget.failed_attempts) == (2, 1)
    assert (budget.prompt_tokens, budget.output_tokens) == (20, 10)
    assert not budget.unknown_failed_usage
    # CallMeta remains backwards compatible: successful response usage only.
    assert (meta.prompt_tokens, meta.output_tokens, meta.attempts) == (10, 5, 2)


def test_parse_failure_missing_usage_is_not_reported_as_free(setup_client):
    client, _, provider = setup_client
    provider.outcomes = [response("not JSON", usage=False)]
    with client.request_budget(60, max_attempts=1) as budget:
        with pytest.raises(LLMError, match="attempt budget"):
            client.generate_json("first", Reply)
    assert budget.unknown_usage and budget.unknown_failed_usage
    assert (budget.network_attempts, budget.failed_attempts) == (1, 1)


@pytest.mark.parametrize("usage", [
    None,
    SimpleNamespace(prompt_token_count=None, candidates_token_count=None),
    SimpleNamespace(prompt_token_count=10, candidates_token_count=None),
    SimpleNamespace(prompt_token_count=None, candidates_token_count=5),
])
def test_success_with_missing_or_partial_usage_is_not_complete_cost(setup_client, usage):
    client, _, provider = setup_client
    provider.outcomes = [SimpleNamespace(text='{"answer":"ok"}', usage_metadata=usage)]
    with client.request_budget(60) as budget:
        obj, meta = client.generate_json("first", Reply)
    assert obj.answer == "ok"
    assert budget.network_attempts == 1
    assert budget.failed_attempts == 0
    assert budget.unknown_usage
    assert not budget.unknown_failed_usage
    assert budget.prompt_tokens == meta.prompt_tokens == (getattr(usage, "prompt_token_count", None) or 0)
    assert budget.output_tokens == meta.output_tokens == (getattr(usage, "candidates_token_count", None) or 0)


def test_unknown_usage_remains_set_after_later_complete_response(setup_client):
    client, _, provider = setup_client
    provider.outcomes = [response(usage=False), response()]
    with client.request_budget(60) as budget:
        client.generate_json("first", Reply)
        client.generate_json("second", Reply)
    assert budget.unknown_usage
    assert not budget.unknown_failed_usage
    assert (budget.prompt_tokens, budget.output_tokens) == (10, 5)


@pytest.mark.parametrize("prompt_tokens,output_tokens", [(None, None), (10, None), (None, 5)])
def test_incomplete_failed_usage_preserves_partial_totals(setup_client, prompt_tokens, output_tokens):
    client, _, provider = setup_client
    provider.outcomes = [SimpleNamespace(
        text="not JSON",
        usage_metadata=SimpleNamespace(
            prompt_token_count=prompt_tokens, candidates_token_count=output_tokens,
        ),
    )]
    with client.request_budget(60, max_attempts=1) as budget:
        with pytest.raises(LLMError, match="attempt budget"):
            client.generate_json("first", Reply)
    assert budget.unknown_usage and budget.unknown_failed_usage
    assert budget.prompt_tokens == (prompt_tokens or 0)
    assert budget.output_tokens == (output_tokens or 0)


def test_deadline_does_not_reset_between_stages(setup_client):
    client, clock, provider = setup_client
    with client.request_budget(30) as budget:
        client.generate_json("first", Reply)
        clock.now += 21
        with pytest.raises(QuotaExhausted, match="deadline"):
            client.generate_json("second", Reply)
    assert budget.network_attempts == len(provider.requests) == 1
    assert not budget.unknown_failed_usage
    assert not clock.sleeps


def test_expired_shared_deadline_stops_before_network(setup_client):
    client, clock, provider = setup_client
    with client.request_budget(30) as budget:
        clock.now += 30
        with pytest.raises(QuotaExhausted, match="shared request deadline"):
            client.generate_json("first", Reply)
    assert budget.deadline_exceeded
    assert budget.network_attempts == 0
    assert provider.requests == []


def test_late_provider_response_is_failure_and_not_cached(setup_client):
    client, clock, provider = setup_client

    def late():
        clock.now += 31
        return response()

    provider.outcomes = [late]
    with client.request_budget(30) as budget:
        with pytest.raises(QuotaExhausted, match="shared request deadline"):
            client.generate_json("first", Reply)
    assert budget.deadline_exceeded
    assert budget.network_attempts == budget.failed_attempts == 1
    assert (budget.prompt_tokens, budget.output_tokens) == (10, 5)
    assert client.cache.count() == 0


def test_effective_timeout_uses_shorter_per_call_deadline(setup_client):
    client, clock, provider = setup_client
    client.deadline_s = 13

    def inspect_deadline():
        assert client._request.deadline == clock() + 13
        return response()

    provider.outcomes = [inspect_deadline]
    with client.request_budget(60):
        client.generate_json("first", Reply)
    assert provider.requests[0]["config"].http_options.timeout == 12000


def test_late_per_call_response_fails_inside_longer_request_budget(setup_client):
    client, clock, provider = setup_client
    client.deadline_s = 13

    def late():
        clock.now += 14
        return response()

    provider.outcomes = [late]
    with client.request_budget(60) as budget:
        with pytest.raises(QuotaExhausted, match="deadline"):
            client.generate_json("first", Reply)
    assert budget.deadline_exceeded
    assert budget.failed_attempts == 1
    assert client.cache.count() == 0


def test_cache_replay_uses_no_attempts_even_after_budget_spent(setup_client, monkeypatch):
    client, _, provider = setup_client
    with client.request_budget(60, max_attempts=1) as budget:
        client.generate_json("first", Reply)
        monkeypatch.setenv("CADENCE_CACHE_ONLY", "1")
        _, meta = client.generate_json("first", Reply)
        with pytest.raises(CacheMissError):
            client.generate_json("missing", Reply)
    assert budget.network_attempts == len(provider.requests) == 1
    assert meta.cached and meta.attempts == 0
    assert (budget.prompt_tokens, budget.output_tokens) == (10, 5)


def test_cache_only_miss_never_initializes_provider(setup_client, monkeypatch):
    client, _, provider = setup_client
    monkeypatch.setenv("CADENCE_CACHE_ONLY", "1")
    with client.request_budget(60) as budget:
        with pytest.raises(CacheMissError):
            client.generate_json("missing", Reply)
    assert client._slots is None
    assert budget.network_attempts == 0
    assert provider.requests == []


def test_nested_scopes_tighten_and_restore_without_resetting_parent(setup_client):
    client, _, provider = setup_client
    with client.request_budget(60, max_attempts=2) as parent:
        client.generate_json("first", Reply)
        with pytest.raises(LLMError, match="attempt budget"), client.request_budget(120, max_attempts=5) as child:
            assert child.deadline == parent.deadline
            client.generate_json("second", Reply)
            client.generate_json("third", Reply)
        assert client.budget_status() == parent.as_dict()
        assert parent.network_attempts == 2
        assert child.network_attempts == 1
        with pytest.raises(LLMError, match="attempt budget"):
            client.generate_json("fourth", Reply)
    assert client.budget_status() is None
    assert len(provider.requests) == 2


def test_inner_limit_does_not_exhaust_larger_outer_limit(setup_client):
    client, _, _ = setup_client
    with client.request_budget(60, max_attempts=3) as parent:
        with client.request_budget(30, max_attempts=1) as child:
            client.generate_json("inner", Reply)
            with pytest.raises(LLMError, match="attempt budget"):
                client.generate_json("inner-exhausted", Reply)
        client.generate_json("outer", Reply)
    assert parent.network_attempts == 2
    assert child.network_attempts == 1


def test_deadline_attribute_restored_after_exception(setup_client):
    client, _, provider = setup_client
    provider.outcomes = [TimeoutError()]
    client._request.deadline = 12345
    with client.request_budget(60, max_attempts=1), pytest.raises(LLMError):
        client.generate_json("first", Reply)
    assert client._request.deadline == 12345
    assert client.budget_status() is None


def test_threads_have_independent_request_scopes(setup_client):
    client, _, provider = setup_client
    barrier = threading.Barrier(2)

    def run(name):
        with client.request_budget(60, max_attempts=1) as budget:
            barrier.wait(timeout=5)
            client.generate_json(name, Reply)
            with pytest.raises(LLMError, match="attempt budget"):
                client.generate_json(name + "-extra", Reply)
            barrier.wait(timeout=5)
            assert client.budget_status() == budget.as_dict()
        assert client.budget_status() is None
        return budget

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, name) for name in ("left", "right")]
        budgets = [future.result(timeout=10) for future in futures]
    assert all(b.network_attempts == 1 for b in budgets)
    assert len(provider.requests) == 2
    assert client.budget_status() is None


@pytest.mark.parametrize("seconds,max_attempts", [(0, 1), (-1, 1), (float("inf"), 1), (float("nan"), 1), (30, 0), (30, 1.5), (30, True)])
def test_invalid_budgets_fail_without_installing_context(setup_client, seconds, max_attempts):
    client, _, _ = setup_client
    with pytest.raises(ValueError), client.request_budget(seconds, max_attempts):
        pytest.fail("invalid budget must not enter")
    assert client.budget_status() is None


@pytest.mark.parametrize("schema,text", [
    (StrictReply, '{"answer":"ok"}'),
    (NestedStrictReply, '{"replies":[{"answer":"ok"}]}'),
    (Reply, '{"answer":"ok"}'),
])
def test_sdk_wire_schema_uses_json_schema_only_for_additional_properties(tmp_path, monkeypatch, schema, text):
    """Exercise the installed SDK's public serialization with an in-memory transport."""
    monkeypatch.delenv("CADENCE_CACHE_ONLY", raising=False)
    requests = []

    def transport(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 3},
        })

    provider = genai.Client(api_key="fake-key", http_options=genai_types.HttpOptions(
        client_args={"transport": httpx.MockTransport(transport)},
    ))
    monkeypatch.setattr("cadence.llm.gemini.genai.Client", lambda **kwargs: provider)
    client = GeminiClient("gemini-test", api_key="fake-key", cache_path=tmp_path / "wire.sqlite")
    try:
        obj, meta = client.generate_json("request", schema)
        assert obj == schema.model_validate_json(text)
        assert not meta.cached
        wire_config = requests[0]["generationConfig"]
        assert "additional_properties" not in json.dumps(wire_config)
        if schema is Reply:
            assert "responseSchema" in wire_config
            assert "responseJsonSchema" not in wire_config
        else:
            assert wire_config["responseJsonSchema"] == schema.model_json_schema()
            assert "responseSchema" not in wire_config
            assert '"additionalProperties": false' in json.dumps(wire_config)
        # Cache identity still includes the complete original Pydantic schema.
        key = client.cache.key(client.model, None, "request", schema_json(schema), client.temperature)
        assert client.cache.get(key)["schema_json"] == schema_json(schema)
        _, cached = client.generate_json("request", schema)
        assert cached.cached
        assert len(requests) == 1
    finally:
        client.close()


@pytest.mark.parametrize("schema,text", [
    (StrictReply, '{"answer":"ok","unrecognized":true}'),
    (NestedStrictReply, '{"replies":[{"answer":"ok","unrecognized":true}]}'),
])
def test_json_schema_transport_retains_strict_local_validation(schema, text):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GeminiClient._parse(response(text), schema)
