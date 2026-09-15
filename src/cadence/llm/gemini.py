"""Gemini client with structured (JSON-schema) output, replay cache, key rotation, rate limiting and retries.

This is the only module in Cadence allowed to talk to the Gemini API (CONTRACT.md §0). The
`google.genai` clients are created lazily on the first network call so that cache-only replay and
the test-suite never need an API key.

Key pool
--------
Provider quotas are per project, not per key. The client accepts several keys (env `GEMINI_API_KEYS`,
comma-separated, or a single `GEMINI_API_KEY`) with conservative local scheduling budgets. Keys in the
same project share provider quotas. Local counters use UTC days; provider resets use Pacific time.
A 429 cools the key before another credential is tried. Deadlines bound waits and retries; adding keys
does not imply extra quota. The client supports concurrent callers, subject to these local budgets.

Thinking models
---------------
Gemini 3.x Flash models think before answering; their thinking tokens count against `max_output_tokens`,
so the default budget is large and `thinking_budget` (config/models.yaml) caps the thinking. If a model
rejects the thinking config the call is retried without it.
"""

from __future__ import annotations

import json
import random
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from cadence.config import SEED, Paths, api_keys, cache_only, model_limits, models_config
from cadence.llm.base import CacheMissError, CallMeta, LLMError, QuotaExhausted, SchemaT
from cadence.llm.cache import LLMCache, schema_json
from cadence.llm.ratelimit import RateLimiter
from cadence.utils.log import get_logger

log = get_logger(__name__)

MAX_ATTEMPTS: int = 6
BACKOFF_SECONDS: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
"""Base delay before attempt n+1 (index n-1); each is jittered by up to +25 %."""
DEFAULT_COOLDOWN_SECONDS: float = 30.0
"""Cooldown for a key that answered 429 without a retry hint."""
_RETRY_HINT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s?", re.IGNORECASE),
    re.compile(r"Please retry in\s+(\d+(?:\.\d+)?)\s*s", re.IGNORECASE),
)
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_PROMPT_PREVIEW_CHARS = 80


class _Retryable(Exception):
    """Internal marker wrapping an error that warrants another attempt."""

    def __init__(self, cause: BaseException, *, rotate: bool = False) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.rotate = rotate
        """True when the failure was key-specific (429): try another key before backing off."""


def strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` fence if the model added one despite JSON mode."""
    match = _CODE_FENCE.match(text)
    return match.group(1) if match else text.strip()


def extract_json_object(text: str) -> str:
    """Best-effort recovery of the JSON object inside `text` (fences, leading prose, trailing notes)."""
    candidate = strip_code_fences(text)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        start, end = candidate.find("{"), candidate.rfind("}")
        if start != -1 and end > start:
            return candidate[start : end + 1]
        return candidate


def retry_hint_seconds(message: str) -> float | None:
    """Extract the server-suggested delay from an error message (`retryDelay: '7s'` / `Please retry in 7s`)."""
    for pattern in _RETRY_HINT_PATTERNS:
        match = pattern.search(message)
        if match:
            return float(match.group(1))
    return None


class _KeySlot:
    """One API key with its own lazily created client, limiter and cooldown."""

    def __init__(self, index: int, key: str, limiter: RateLimiter) -> None:
        self.index = index
        self.key = key
        self.limiter = limiter
        self.cooldown_until: float = 0.0
        self._genai: genai.Client | None = None

    @property
    def label(self) -> str:
        return f"k{self.index + 1}"

    def client(self) -> genai.Client:
        if self._genai is None:
            self._genai = genai.Client(api_key=self.key, http_options=genai_types.HttpOptions(timeout=12000, retry_options=genai_types.HttpRetryOptions(attempts=1)))
        return self._genai


class GeminiClient:
    """`LLMClient` implementation over `google-genai` structured output.

    Defaults for `rpm`/`rpd`/`temperature`/`max_output_tokens`/`thinking_budget` come from
    `config/models.yaml`. `rpm`/`rpd` are per key. `clock` and `sleeper` are injection points for
    tests (they drive the retry backoff, cooldowns and the rate limiters).
    """

    def __init__(
        self,
        model: str,
        rpm: int | None = None,
        rpd: int | None = None,
        temperature: float | None = None,
        api_key: str | None = None,
        cache_path: Path = Paths.LLM_CACHE,
        max_output_tokens: int | None = None,
        *,
        api_keys: list[str] | None = None,
        thinking_budget: int | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        deadline_s: float = 45.0,
        persist_responses: bool = True,
    ) -> None:
        cfg = models_config()
        default_rpm, default_rpd = model_limits(model)
        self.model = model
        self.rpm = int(rpm if rpm is not None else default_rpm)
        self.rpd = int(rpd if rpd is not None else default_rpd)
        self.temperature = float(temperature if temperature is not None else cfg.get("temperature", 0.2))
        configured_max = cfg.get("max_output_tokens")
        self.max_output_tokens = (
            int(max_output_tokens) if max_output_tokens is not None
            else (int(configured_max) if configured_max is not None else None)
        )
        configured_thinking = (cfg.get("thinking_budget") or {}).get(model) if isinstance(cfg.get("thinking_budget"), dict) else cfg.get("thinking_budget")
        self.thinking_budget = int(thinking_budget) if thinking_budget is not None else (
            int(configured_thinking) if configured_thinking is not None else None
        )
        self._thinking_supported = True
        self.cache = LLMCache(cache_path)
        self._clock = clock
        self._sleep = sleeper
        self._rng = random.Random(SEED)
        self._lock = threading.Lock()
        keys = list(api_keys) if api_keys else ([api_key] if api_key else None)
        self._explicit_keys = keys
        self._slots: list[_KeySlot] | None = None
        self.deadline_s = deadline_s
        self.persist_responses = persist_responses
        self._request = threading.local()

    # ------------------------------------------------------------ key pool
    def _make_limiter(self, model_id: str) -> RateLimiter:
        return RateLimiter(self.rpm, self.rpd, self.cache, model_id, clock=self._clock, sleeper=self._sleep)

    @property
    def limiter(self) -> RateLimiter:
        """The first key's limiter (kept for callers/tests that inspect a single limiter)."""
        return self._ensure_slots()[0].limiter

    def _ensure_slots(self) -> list[_KeySlot]:
        """Resolve keys on first use; raise a clear error when none is configured."""
        with self._lock:
            if self._slots is None:
                keys = self._explicit_keys or api_keys()
                if not keys:
                    raise LLMError(
                        "No Gemini API key configured. Put GEMINI_API_KEY (or GEMINI_API_KEYS=k1,k2,...) in .env, "
                        "or run with CADENCE_CACHE_ONLY=1 (replay) / CADENCE_LLM=mock (offline)."
                    )
                self._slots = [
                    _KeySlot(i, key, self._make_limiter(self.model if len(keys) == 1 else f"{self.model}#k{i + 1}"))
                    for i, key in enumerate(keys)
                ]
                log.info("gemini %s ready with %d key(s)", self.model, len(self._slots))
            return self._slots

    def _pick_slot(self) -> _KeySlot:
        """Choose the usable key with the most remaining daily quota; wait for cooldowns; raise when all are spent."""
        slots = self._ensure_slots()
        while True:
            with self._lock:
                now = self._clock()
                usable = [s for s in slots if s.cooldown_until <= now and s.limiter.remaining_today() > 0]
                if usable:
                    usable.sort(key=lambda s: (-s.limiter.remaining_today(), s.index))
                    return usable[0]
                cooling = [s for s in slots if s.limiter.remaining_today() > 0]
                if not cooling:
                    used = ", ".join(f"{s.label}={self.rpd - s.limiter.remaining_today()}/{self.rpd}" for s in slots)
                    raise QuotaExhausted(
                        f"daily quota exhausted for {self.model} on every key ({used}). "
                        "Wait for the UTC day to roll over, lower the workload, or run with CADENCE_CACHE_ONLY=1."
                    )
                wait = max(min(s.cooldown_until for s in cooling) - now, 0.1)
                if now + wait >= getattr(self._request, "deadline", float("inf")):
                    raise QuotaExhausted("All configured keys are cooling down; retry later.")
            log.info("all %d key(s) for %s cooling down; sleeping %.1fs", len(slots), self.model, wait)
            self._sleep(wait)

    def _cool_down(self, slot: _KeySlot, message: str) -> None:
        hinted = retry_hint_seconds(message)
        seconds = (hinted + 1.0) if hinted is not None else DEFAULT_COOLDOWN_SECONDS
        with self._lock:
            slot.cooldown_until = self._clock() + seconds
        log.warning("gemini %s key %s hit 429; cooling down for %.0fs", self.model, slot.label, seconds)

    def list_models(self) -> list[str]:
        """Model ids visible to the first key (the `models/` prefix stripped), sorted."""
        names = {
            (m.name or "").removeprefix("models/") for m in self._ensure_slots()[0].client().models.list() if m.name
        }
        return sorted(names)

    # ------------------------------------------------------------- request
    def _config(self, schema: type[BaseModel], system: str | None, temperature: float) -> Any:
        remaining_ms = int((getattr(self._request, "deadline", self._clock() + 12) - self._clock()) * 1000)
        # Gemini rejects short server deadlines. Fail before network rather than extending our budget.
        if remaining_ms < 11000:
            raise QuotaExhausted("Insufficient request time remains after queueing; retry later.")
        thinking = None
        if self.thinking_budget is not None and self._thinking_supported:
            thinking = genai_types.ThinkingConfig(thinking_budget=self.thinking_budget)
        return genai_types.GenerateContentConfig(
            http_options=genai_types.HttpOptions(timeout=min(12000, remaining_ms)),
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=thinking,
        )

    # -------------------------------------------------------------- parsing
    @staticmethod
    def _parse(response: Any, schema: type[SchemaT]) -> SchemaT:
        """Turn a `GenerateContentResponse` into a validated `schema` instance."""
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("empty response: no text candidate returned (blocked or truncated output)")
        return schema.model_validate_json(extract_json_object(text))

    @staticmethod
    def _usage(response: Any) -> tuple[int, int]:
        """(prompt_tokens, output_tokens) where output includes thinking tokens; zeros when absent."""
        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            return 0, 0
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        output_tokens = int(getattr(usage, "candidates_token_count", 0) or 0) + int(
            getattr(usage, "thoughts_token_count", 0) or 0
        )
        return prompt_tokens, output_tokens

    # --------------------------------------------------------------- retries
    def _backoff(self, attempt: int, message: str) -> float:
        """Seconds to wait after failed `attempt` (1-based): server hint when present, else the schedule."""
        hinted = retry_hint_seconds(message)
        if hinted is not None:
            return hinted + self._rng.uniform(0.5, 1.5)
        base = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]
        return base * (1.0 + self._rng.uniform(0.0, 0.25))

    def _attempt(
        self, prompt: str, schema: type[SchemaT], system: str | None, temperature: float
    ) -> tuple[SchemaT, int, int, int]:
        """One rate-limited network call on the best key. Returns (object, prompt_tokens, output_tokens, latency_ms)."""
        slot = self._pick_slot()
        deadline = getattr(self._request, "deadline", None)
        # Reserve a full provider request window after any local rate-limit wait.
        slot.limiter.acquire(deadline=deadline - 12 if deadline is not None else None)
        started = self._clock()
        try:
            response = slot.client().models.generate_content(
                model=self.model, contents=prompt, config=self._config(schema, system, temperature)
            )
            obj = self._parse(response, schema)
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                self._cool_down(slot, str(exc))
                raise _Retryable(exc, rotate=True) from exc
            if exc.code == 400 and "thinking" in str(exc).lower() and self._thinking_supported:
                log.warning("gemini %s rejected thinking_config; retrying without it", self.model)
                self._thinking_supported = False
                raise _Retryable(exc, rotate=True) from exc
            raise LLMError(f"Gemini rejected the request (HTTP {exc.code}); check model availability and credentials.") from exc
        except genai_errors.ServerError as exc:
            raise _Retryable(exc) from exc
        except RuntimeError as exc:
            # httpx raises "Cannot send a request, as the client has been closed" when a transport is torn
            # down under a concurrent caller; drop this key's client so the next attempt rebuilds it.
            if "closed" not in str(exc).lower():
                raise
            with self._lock:
                slot._genai = None
            raise _Retryable(exc, rotate=True) from exc
        except (httpx.HTTPError, ConnectionError, TimeoutError, OSError) as exc:
            # Transport-level failures (server disconnected, reset, DNS, timeouts): rebuild the client and retry.
            with self._lock:
                slot._genai = None
            raise _Retryable(exc, rotate=True) from exc
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise _Retryable(exc) from exc
        latency_ms = int(round((self._clock() - started) * 1000))
        prompt_tokens, output_tokens = self._usage(response)
        return obj, prompt_tokens, output_tokens, latency_ms

    def _has_free_slot(self) -> bool:
        with self._lock:
            now = self._clock()
            return any(s.cooldown_until <= now and s.limiter.remaining_today() > 0 for s in (self._slots or []))

    def _call_with_retry(
        self, prompt: str, schema: type[SchemaT], system: str | None, temperature: float
    ) -> tuple[SchemaT, CallMeta]:
        last_error: BaseException | None = None
        self._request.deadline = self._clock() + self.deadline_s
        started = self._clock()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                obj, prompt_tokens, output_tokens, latency_ms = self._attempt(prompt, schema, system, temperature)
            except _Retryable as retryable:
                last_error = retryable.cause
                if attempt == MAX_ATTEMPTS:
                    break
                if retryable.rotate and self._has_free_slot():
                    log.info("gemini %s attempt %d/%d: switching key", self.model, attempt, MAX_ATTEMPTS)
                    continue
                delay = self._backoff(attempt, str(retryable.cause))
                if self._clock() + delay >= self._request.deadline:
                    break
                log.warning(
                    "gemini %s attempt %d/%d failed (%s); retrying in %.1fs",
                    self.model, attempt, MAX_ATTEMPTS, type(retryable.cause).__name__, delay,
                )
                self._sleep(delay)
                continue
            meta = CallMeta(
                model=self.model,
                cached=False,
                latency_ms=int(round((self._clock() - started) * 1000)),
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                attempts=attempt,
            )
            log.info("gemini %s ok in %dms (attempt %d, %d+%d tokens)", self.model, latency_ms, attempt, prompt_tokens, output_tokens)
            return obj, meta
        if isinstance(last_error, genai_errors.ClientError) and last_error.code == 429:
            raise QuotaExhausted("Gemini quota unavailable across configured keys; retry later.") from last_error
        raise LLMError(
            f"Gemini call to {self.model} failed after {attempt} attempts; "
            f"last error {type(last_error).__name__}"
        ) from last_error

    # ---------------------------------------------------------------- public
    def generate_json(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float | None = None,
        cache: bool = True,
    ) -> tuple[SchemaT, CallMeta]:
        """Structured call with cache replay.

        `cache=False` skips the lookup (forces a fresh call) but still stores the result so that
        later cache-only runs can replay it.
        """
        temp = float(temperature if temperature is not None else self.temperature)
        sjson = schema_json(schema)
        key = self.cache.key(self.model, system, prompt, sjson, temp)
        if cache and self.persist_responses:
            row = self.cache.get(key)
            if row is not None:
                log.debug("cache hit %s for %s", key[:12], self.model)
                obj = schema.model_validate_json(row["response_json"])
                meta = CallMeta(
                    model=self.model,
                    cached=True,
                    latency_ms=0,
                    prompt_tokens=int(row["prompt_tokens"] or 0),
                    output_tokens=int(row["output_tokens"] or 0),
                    attempts=0,
                )
                return obj, meta
        if cache_only():
            preview = prompt[:_PROMPT_PREVIEW_CHARS].replace("\n", " ")
            raise CacheMissError(
                f"cache miss for model {self.model} while CADENCE_CACHE_ONLY=1 forbids network calls; "
                f"prompt starts: {preview!r}"
            )
        obj, meta = self._call_with_retry(prompt, schema, system, temp)
        if self.persist_responses:
            self.cache.put(
            key,
            model=self.model,
            system=system,
            prompt=prompt,
            schema_json=sjson,
            temperature=temp,
            response_json=obj.model_dump_json(),
            prompt_tokens=meta.prompt_tokens,
            output_tokens=meta.output_tokens,
            latency_ms=meta.latency_ms,
        )
        return obj, meta

    @property
    def n_keys(self) -> int:
        """Number of configured keys (resolved lazily; 0 when none is configured)."""
        try:
            return len(self._ensure_slots())
        except LLMError:
            return 0

    def __repr__(self) -> str:
        return f"GeminiClient(model={self.model!r}, rpm={self.rpm}, rpd={self.rpd}, temperature={self.temperature})"

    def close(self) -> None:
        """Release request-owned clients (shared clients live for the server process)."""
        for slot in self._slots or []:
            if slot._genai is not None:
                slot._genai.close()
        self.cache.close()


__all__ = [
    "GeminiClient",
    "MAX_ATTEMPTS",
    "BACKOFF_SECONDS",
    "DEFAULT_COOLDOWN_SECONDS",
    "strip_code_fences",
    "extract_json_object",
    "retry_hint_seconds",
]
