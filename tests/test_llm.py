"""Tests for cadence.llm: cache, rate limiter, mock client, Gemini client (offline), factory."""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import pytest
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

import cadence.llm as llm_pkg
from cadence.llm import (
    CacheMissError,
    CallMeta,
    GeminiClient,
    LLMCache,
    LLMError,
    MockClient,
    QuotaExhausted,
    RateLimiter,
    fill_schema,
    get_client,
    schema_json,
)
from cadence.llm import gemini as gemini_mod
from cadence.llm.cache import utc_day
from cadence.llm.gemini import retry_hint_seconds, strip_code_fences

# --------------------------------------------------------------------------- fixtures / helpers


class Sentiment(StrEnum):
    POS = "positive"
    NEG = "negative"


class Evidence(BaseModel):
    thread_id: str
    score: float = Field(ge=0)
    cited: bool


class Verdict(BaseModel):
    intent: Literal["billing_or_charge", "other"]
    sentiment: Sentiment
    confidence: float = Field(ge=0, le=1)
    n_steps: int
    secondary: str | None
    reply: str = Field(max_length=280)
    evidence: list[Evidence]
    must_have: list[str] = Field(min_length=1)
    notes: str = "default-note"
    tags: list[str] = Field(default_factory=lambda: ["seed"])
    example_field: str = Field(examples=["from-example"])


class Ping(BaseModel):
    greeting: str
    mood: Literal["happy", "neutral"]


class FakeClock:
    """Monotonic clock whose sleep() advances time instantly and records requested durations."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class FakeUsage:
    def __init__(self, prompt: int, candidates: int, thoughts: int | None) -> None:
        self.prompt_token_count = prompt
        self.candidates_token_count = candidates
        self.thoughts_token_count = thoughts


class FakeResponse:
    def __init__(self, text: str | None, parsed: Any = None, usage: FakeUsage | None = None) -> None:
        self.text = text
        self.parsed = parsed
        self.usage_metadata = usage


class FakeModels:
    """Stands in for `genai.Client().models`; pops scripted outcomes (exception or response) per call."""

    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.requests: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.requests.append({"model": model, "contents": contents, "config": config})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def list(self) -> list[Any]:
        class M:
            def __init__(self, name: str) -> None:
                self.name = name

        return [M("models/gemini-2.5-flash"), M("models/embedding-001"), M("models/gemini-2.5-pro")]


class FakeGenaiClient:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


def api_error(cls: type[genai_errors.APIError], code: int, message: str, status: str) -> genai_errors.APIError:
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


@pytest.fixture
def cache(tmp_path: Path) -> LLMCache:
    c = LLMCache(tmp_path / "llm_cache.sqlite")
    yield c
    c.close()


@pytest.fixture
def offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """No key, no cache-only, no mock, and a genai Client constructor that explodes if touched."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CADENCE_CACHE_ONLY", "CADENCE_LLM"):
        monkeypatch.delenv(var, raising=False)

    def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("genai.Client must not be constructed in this test")

    monkeypatch.setattr(gemini_mod.genai, "Client", boom)


def make_client(tmp_path: Path, clock: FakeClock, **kwargs: Any) -> GeminiClient:
    return GeminiClient(
        "gemini-2.5-flash",
        rpm=kwargs.pop("rpm", 100),
        rpd=kwargs.pop("rpd", 1000),
        api_key=kwargs.pop("api_key", "fake-key"),
        cache_path=tmp_path / "cache.sqlite",
        clock=clock,
        sleeper=clock.sleep,
        **kwargs,
    )


# --------------------------------------------------------------------------- cache


def test_cache_roundtrip_and_stats(cache: LLMCache) -> None:
    sjson = schema_json(Ping)
    key = cache.key("gemini-2.5-flash", "sys", "hello", sjson, 0.2)
    assert cache.get(key) is None
    assert cache.count() == 0

    cache.put(
        key,
        model="gemini-2.5-flash",
        system="sys",
        prompt="hello",
        schema_json=sjson,
        temperature=0.2,
        response_json='{"greeting":"hi","mood":"happy"}',
        prompt_tokens=10,
        output_tokens=5,
        latency_ms=123,
    )
    row = cache.get(key)
    assert row is not None
    assert row["model"] == "gemini-2.5-flash"
    assert row["prompt"] == "hello"
    assert row["temperature"] == 0.2
    assert Ping.model_validate_json(row["response_json"]).mood == "happy"
    assert row["created_at"]
    assert cache.count() == 1

    other = cache.key("gemini-2.5-pro", None, "hello", sjson, 0.0)
    cache.put(other, model="gemini-2.5-pro", system=None, prompt="hello", schema_json=sjson,
              temperature=0.0, response_json="{}", prompt_tokens=7, output_tokens=3)
    stats = cache.stats()
    assert stats == {
        "entries": 2,
        "by_model": {"gemini-2.5-flash": 1, "gemini-2.5-pro": 1},
        "total_prompt_tokens": 17,
        "total_output_tokens": 8,
    }

    # INSERT OR REPLACE keeps the primary key unique.
    cache.put(key, model="gemini-2.5-flash", system="sys", prompt="hello", schema_json=sjson,
              temperature=0.2, response_json='{"greeting":"yo","mood":"neutral"}')
    assert cache.count() == 2
    assert cache.get(key)["response_json"].startswith('{"greeting":"yo"')


def test_cache_key_sensitivity() -> None:
    sjson = schema_json(Ping)
    base = LLMCache.key("m", "s", "p", sjson, 0.2)
    assert base == LLMCache.key("m", "s", "p", sjson, 0.2)
    assert base != LLMCache.key("m", None, "p", sjson, 0.2)
    assert base != LLMCache.key("m", "s", "p", sjson, 0.0)
    assert base != LLMCache.key("m", "s", "p", schema_json(Verdict), 0.2)
    assert base != LLMCache.key("m2", "s", "p", sjson, 0.2)
    assert len(base) == 64


def test_cache_quota_counters(cache: LLMCache) -> None:
    assert cache.quota_get("m", "2026-09-09") == 0
    assert cache.quota_incr("m", "2026-09-09") == 1
    assert cache.quota_incr("m", "2026-09-09") == 2
    assert cache.quota_get("m", "2026-09-09") == 2
    assert cache.quota_get("m", "2026-09-10") == 0
    assert cache.quota_get("other", "2026-09-09") == 0


def test_cache_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "persist.sqlite"
    first = LLMCache(path)
    first.quota_incr("m", "2026-09-09")
    first.close()
    second = LLMCache(path)
    try:
        assert second.quota_get("m", "2026-09-09") == 1
    finally:
        second.close()


# --------------------------------------------------------------------------- rate limiter


def test_rate_limiter_sliding_window_sleeps(cache: LLMCache) -> None:
    clock = FakeClock()
    limiter = RateLimiter(rpm=2, rpd=100, cache=cache, model="m", clock=clock, sleeper=clock.sleep,
                          today=lambda: "2026-09-09")
    assert limiter.acquire() == 1
    clock.now += 10
    assert limiter.acquire() == 2
    assert clock.sleeps == []

    # Third request inside the same minute must wait until the first one leaves the window.
    clock.now += 5  # t = 1015; first request at 1000 -> expires at 1060
    assert limiter.acquire() == 3
    assert clock.sleeps == pytest.approx([45.0])
    assert clock.now == pytest.approx(1060.0)

    # After the window passes there is no wait.
    clock.now += 120
    limiter.acquire()
    assert len(clock.sleeps) == 1
    assert cache.quota_get("m", "2026-09-09") == 4


def test_rate_limiter_daily_quota_raises_and_persists(cache: LLMCache) -> None:
    clock = FakeClock()
    day = {"value": "2026-09-09"}
    limiter = RateLimiter(rpm=100, rpd=3, cache=cache, model="m", clock=clock, sleeper=clock.sleep,
                          today=lambda: day["value"])
    for _ in range(3):
        limiter.acquire()
    assert limiter.remaining_today() == 0
    with pytest.raises(QuotaExhausted, match="3/3"):
        limiter.acquire()
    assert clock.sleeps == []  # quota is checked before any sleeping
    assert cache.quota_get("m", "2026-09-09") == 3

    # Counter is per UTC day: a new day starts fresh, and a new limiter sees the persisted count.
    day["value"] = "2026-09-10"
    assert limiter.acquire() == 1
    day["value"] = "2026-09-09"
    fresh = RateLimiter(rpm=100, rpd=3, cache=cache, model="m", clock=clock, sleeper=clock.sleep,
                        today=lambda: day["value"])
    with pytest.raises(QuotaExhausted):
        fresh.acquire()


def test_rate_limiter_rejects_bad_limits(cache: LLMCache) -> None:
    with pytest.raises(ValueError):
        RateLimiter(rpm=0, rpd=10, cache=cache, model="m")


# --------------------------------------------------------------------------- mock client


def test_mock_fills_nested_schema_deterministically() -> None:
    client = MockClient()
    obj, meta = client.generate_json("classify this", Verdict, system="sys", temperature=0.3)
    assert isinstance(obj, Verdict)
    assert obj.intent == "billing_or_charge"
    assert obj.sentiment is Sentiment.POS
    assert obj.confidence == 0.5
    assert obj.n_steps == 1
    assert obj.secondary is None
    assert obj.reply == "mock-reply"
    assert obj.evidence == []
    assert obj.must_have == ["mock-must_have"]
    assert obj.notes == "default-note"
    assert obj.tags == ["seed"]
    assert obj.example_field == "from-example"
    assert fill_schema(Verdict) == fill_schema(Verdict)

    assert meta == CallMeta(model="mock", cached=False, latency_ms=1, prompt_tokens=3,
                            output_tokens=meta.output_tokens, attempts=1)
    assert client.calls == [{"prompt": "classify this", "schema": "Verdict", "system": "sys", "temperature": 0.3}]


def test_mock_nested_model_with_min_length() -> None:
    class Wrapper(BaseModel):
        items: list[Evidence] = Field(min_length=1)
        inner: Evidence

    obj = Wrapper.model_validate(fill_schema(Wrapper))
    assert obj.items == [Evidence(thread_id="mock-thread_id", score=0.5, cited=False)]
    assert obj.inner == Evidence(thread_id="mock-thread_id", score=0.5, cited=False)


def test_mock_responder_and_validation_errors() -> None:
    seen: list[str] = []

    def responder(prompt: str, schema: type[BaseModel]) -> dict[str, Any]:
        seen.append(schema.__name__)
        return {"greeting": prompt.upper(), "mood": "neutral"}

    client = MockClient(responder=responder)
    obj, _ = client.generate_json("hey", Ping)
    assert obj == Ping(greeting="HEY", mood="neutral")
    assert seen == ["Ping"]

    bad = MockClient(responder=lambda p, s: {"greeting": "x", "mood": "angry"})
    with pytest.raises(LLMError, match="Ping"):
        bad.generate_json("hey", Ping)
    assert bad.calls == []


def test_mock_rejects_unsupported_types() -> None:
    class Weird(BaseModel):
        blob: bytes

    with pytest.raises(LLMError, match="blob"):
        fill_schema(Weird)


# --------------------------------------------------------------------------- gemini client (offline)


def test_gemini_defaults_come_from_config(tmp_path: Path, offline: None) -> None:
    client = GeminiClient("gemini-2.5-flash", cache_path=tmp_path / "c.sqlite")
    assert (client.rpm, client.rpd) == (8, 240)  # per-key limits from config/models.yaml
    assert client.temperature == 0.2
    assert client.max_output_tokens == 4096
    custom = GeminiClient("unknown-model", rpm=1, rpd=2, temperature=0.7, cache_path=tmp_path / "d.sqlite",
                          max_output_tokens=64)
    assert (custom.rpm, custom.rpd, custom.temperature, custom.max_output_tokens) == (1, 2, 0.7, 64)


def test_gemini_cache_only_raises_cache_miss(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CADENCE_CACHE_ONLY", "1")
    client = GeminiClient("gemini-2.5-flash", cache_path=tmp_path / "c.sqlite")
    prompt = "Classify: " + "x" * 200
    with pytest.raises(CacheMissError) as info:
        client.generate_json(prompt, Ping)
    message = str(info.value)
    assert "gemini-2.5-flash" in message
    assert prompt[:80] in message
    assert prompt[:81] not in message
    assert client.cache.count() == 0


def test_gemini_no_key_is_a_clear_error(tmp_path: Path, offline: None) -> None:
    client = GeminiClient("gemini-2.5-flash", cache_path=tmp_path / "c.sqlite")
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        client.generate_json("hi", Ping)


def test_gemini_cache_hit_returns_validated_object(tmp_path: Path, offline: None) -> None:
    clock = FakeClock()
    client = make_client(tmp_path, clock)
    prompt, system = "Say hi", "be brief"
    key = client.cache.key(client.model, system, prompt, schema_json(Ping), client.temperature)
    client.cache.put(key, model=client.model, system=system, prompt=prompt, schema_json=schema_json(Ping),
                     temperature=client.temperature, response_json='{"greeting":"hi","mood":"happy"}',
                     prompt_tokens=11, output_tokens=4, latency_ms=900)

    obj, meta = client.generate_json(prompt, Ping, system=system)
    assert obj == Ping(greeting="hi", mood="happy")
    assert meta == CallMeta(model="gemini-2.5-flash", cached=True, latency_ms=0, prompt_tokens=11,
                            output_tokens=4, attempts=0)
    # A different temperature is a different key -> would need the network -> clear failure, no crash.
    with pytest.raises(AssertionError, match="must not be constructed"):
        client.generate_json(prompt, Ping, system=system, temperature=0.9)


def test_gemini_retries_429_then_parses_fenced_text(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    quota_error = api_error(genai_errors.ClientError, 429, "Quota exceeded. retryDelay: '7s'", "RESOURCE_EXHAUSTED")
    server_error = api_error(genai_errors.ServerError, 503, "overloaded", "UNAVAILABLE")
    fenced = FakeResponse('```json\n{"greeting": "hey", "mood": "neutral"}\n```', usage=FakeUsage(20, 6, 30))
    models = FakeModels([quota_error, server_error, fenced])
    monkeypatch.setattr(gemini_mod.genai, "Client", lambda api_key: FakeGenaiClient(models))

    client = make_client(tmp_path, clock, rpm=10, rpd=10)
    obj, meta = client.generate_json("hello", Ping, system="sys")
    assert obj == Ping(greeting="hey", mood="neutral")
    assert meta.attempts == 3
    assert meta.cached is False
    assert (meta.prompt_tokens, meta.output_tokens) == (20, 36)
    assert len(models.requests) == 3
    cfg = models.requests[0]["config"]
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is Ping
    assert cfg.system_instruction == "sys"
    assert cfg.temperature == 0.2
    assert cfg.max_output_tokens == 4096

    # Backoff: server hint (7s + jitter) then the schedule's second step (4s + jitter <= 25 %).
    assert 7.5 <= clock.sleeps[0] <= 8.5
    assert 4.0 <= clock.sleeps[1] <= 5.0
    assert client.limiter.cache.quota_get("gemini-2.5-flash", utc_day()) == 3

    # Result stored: a second call is a cache hit and does not touch the fake API.
    obj2, meta2 = client.generate_json("hello", Ping, system="sys")
    assert obj2 == obj and meta2.cached is True
    assert len(models.requests) == 3


def test_gemini_uses_parsed_when_present_and_invalid_json_retries(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    good = FakeResponse('{"greeting":"hi","mood":"happy"}', parsed=Ping(greeting="hi", mood="happy"),
                        usage=FakeUsage(5, 2, None))
    models = FakeModels([FakeResponse("not json at all"), FakeResponse('{"greeting":"hi","mood":"sad"}'), good])
    monkeypatch.setattr(gemini_mod.genai, "Client", lambda api_key: FakeGenaiClient(models))
    client = make_client(tmp_path, clock)
    obj, meta = client.generate_json("hello", Ping, cache=False)
    assert obj is good.parsed
    assert meta.attempts == 3
    assert (meta.prompt_tokens, meta.output_tokens) == (5, 2)
    assert client.cache.count() == 1  # cache=False still stores for later replay


def test_gemini_non_retryable_client_error(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    models = FakeModels([api_error(genai_errors.ClientError, 400, "bad schema", "INVALID_ARGUMENT")])
    monkeypatch.setattr(gemini_mod.genai, "Client", lambda api_key: FakeGenaiClient(models))
    client = make_client(tmp_path, clock)
    with pytest.raises(LLMError, match="400") as info:
        client.generate_json("hello", Ping)
    assert not isinstance(info.value, CacheMissError)
    assert clock.sleeps == []
    assert client.cache.count() == 0


def test_gemini_gives_up_after_max_attempts(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    models = FakeModels([api_error(genai_errors.ServerError, 500, "boom", "INTERNAL")] * gemini_mod.MAX_ATTEMPTS)
    monkeypatch.setattr(gemini_mod.genai, "Client", lambda api_key: FakeGenaiClient(models))
    client = make_client(tmp_path, clock)
    with pytest.raises(LLMError, match="after 6 attempts"):
        client.generate_json("hello", Ping)
    assert len(models.requests) == gemini_mod.MAX_ATTEMPTS
    assert len(clock.sleeps) == gemini_mod.MAX_ATTEMPTS - 1
    assert clock.sleeps == sorted(clock.sleeps)  # exponential growth: 2,4,8,16,32 (+jitter)
    assert clock.sleeps[-1] >= 32.0


def test_gemini_daily_quota_stops_before_network(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = FakeClock()
    models = FakeModels([])
    monkeypatch.setattr(gemini_mod.genai, "Client", lambda api_key: FakeGenaiClient(models))
    client = make_client(tmp_path, clock, rpd=1)
    client.cache.quota_incr(client.model, utc_day())
    with pytest.raises(QuotaExhausted):
        client.generate_json("hello", Ping)
    assert models.requests == []


def test_gemini_list_models(tmp_path: Path, offline: None, monkeypatch: pytest.MonkeyPatch) -> None:
    constructed: list[str] = []

    def fake_ctor(api_key: str) -> FakeGenaiClient:
        constructed.append(api_key)
        return FakeGenaiClient(FakeModels([]))

    monkeypatch.setattr(gemini_mod.genai, "Client", fake_ctor)
    client = make_client(tmp_path, FakeClock(), api_key="secret-key")
    assert client.list_models() == ["embedding-001", "gemini-2.5-flash", "gemini-2.5-pro"]
    assert client.list_models()  # second call reuses the lazily built client
    assert constructed == ["secret-key"]
    assert "secret-key" not in repr(client)


def test_helpers() -> None:
    assert strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert strip_code_fences('```\n{"a": 1}```') == '{"a": 1}'
    assert strip_code_fences('  {"a": 1} ') == '{"a": 1}'
    assert json.loads(strip_code_fences('```json\n{"a": [1, 2]}\n```')) == {"a": [1, 2]}
    assert retry_hint_seconds("429 RESOURCE_EXHAUSTED. {'retryDelay': '12s'}") == 12.0
    assert retry_hint_seconds("Please retry in 3.5s.") == 3.5
    assert retry_hint_seconds("no hint here") is None


# --------------------------------------------------------------------------- factory


def test_get_client_mock_and_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CADENCE_LLM", "mock")
    assert isinstance(get_client("agent"), MockClient)

    monkeypatch.delenv("CADENCE_LLM")
    monkeypatch.delenv("CADENCE_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("CADENCE_AGENT_MODEL", raising=False)
    built: list[dict[str, Any]] = []

    class RecordingGemini:
        def __init__(self, model: str, **kwargs: Any) -> None:
            built.append({"model": model, **kwargs})

    monkeypatch.setattr(llm_pkg, "GeminiClient", RecordingGemini)
    get_client("judge")
    get_client("agent")
    assert built[0] == {"model": "gemini-3.1-flash-lite", "rpm": 12, "rpd": 800, "temperature": 0.0}
    assert built[1] == {"model": "gemini-3.5-flash-lite", "rpm": 12, "rpd": 800, "temperature": 0.2}

    monkeypatch.setenv("CADENCE_AGENT_MODEL", "gemini-2.0-flash")
    get_client("agent")
    assert built[2] == {"model": "gemini-2.0-flash", "rpm": 5, "rpd": 100, "temperature": 0.2}  # falls back to `default` limits

    with pytest.raises(ValueError, match="unknown LLM role"):
        get_client("oracle")
