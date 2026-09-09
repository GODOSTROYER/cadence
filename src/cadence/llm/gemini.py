"""Gemini client with structured (JSON-schema) output, replay cache, rate limiting and retries.

This is the only module in Cadence allowed to talk to the Gemini API (CONTRACT.md §0). The
`google.genai` client is created lazily on the first network call so that cache-only replay and
the test-suite never need an API key.
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, ValidationError

from cadence.config import SEED, Paths, api_key, cache_only, model_limits, models_config
from cadence.llm.base import CacheMissError, CallMeta, LLMError, SchemaT
from cadence.llm.cache import LLMCache, schema_json
from cadence.llm.ratelimit import RateLimiter
from cadence.utils.log import get_logger

log = get_logger(__name__)

MAX_ATTEMPTS: int = 6
BACKOFF_SECONDS: tuple[float, ...] = (2.0, 4.0, 8.0, 16.0, 32.0, 60.0)
"""Base delay before attempt n+1 (index n-1); each is jittered by up to +25 %."""
_RETRY_HINT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s?", re.IGNORECASE),
    re.compile(r"Please retry in\s+(\d+(?:\.\d+)?)\s*s", re.IGNORECASE),
)
_CODE_FENCE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
_PROMPT_PREVIEW_CHARS = 80


class _Retryable(Exception):
    """Internal marker wrapping an error that warrants another attempt."""

    def __init__(self, cause: BaseException) -> None:
        super().__init__(str(cause))
        self.cause = cause


def strip_code_fences(text: str) -> str:
    """Remove a surrounding ```json ... ``` fence if the model added one despite JSON mode."""
    match = _CODE_FENCE.match(text)
    return match.group(1) if match else text.strip()


def retry_hint_seconds(message: str) -> float | None:
    """Extract the server-suggested delay from an error message (`retryDelay: '7s'` / `Please retry in 7s`)."""
    for pattern in _RETRY_HINT_PATTERNS:
        match = pattern.search(message)
        if match:
            return float(match.group(1))
    return None


class GeminiClient:
    """`LLMClient` implementation over `google-genai` structured output.

    Defaults for `rpm`/`rpd`/`temperature`/`max_output_tokens` come from `config/models.yaml`.
    `clock` and `sleeper` are injection points for tests (they drive both the retry backoff and
    the rate limiter); production code leaves them alone.
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
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
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
        self.cache = LLMCache(cache_path)
        self.limiter = RateLimiter(self.rpm, self.rpd, self.cache, model, clock=clock, sleeper=sleeper)
        self._api_key = api_key
        self._clock = clock
        self._sleep = sleeper
        self._rng = random.Random(SEED)
        self._genai: genai.Client | None = None

    # ------------------------------------------------------------ network glue
    def _client(self) -> genai.Client:
        """Create the `google.genai` client on first use; raise a clear error when no key is configured."""
        if self._genai is None:
            key = self._api_key or api_key()
            if not key:
                raise LLMError(
                    "No Gemini API key configured. Put GEMINI_API_KEY (or GOOGLE_API_KEY) in .env, "
                    "or run with CADENCE_CACHE_ONLY=1 (replay) / CADENCE_LLM=mock (offline)."
                )
            self._genai = genai.Client(api_key=key)
            log.info("gemini client ready for model %s", self.model)
        return self._genai

    def list_models(self) -> list[str]:
        """Model ids visible to this key (the `models/` prefix stripped), sorted."""
        names = {
            (m.name or "").removeprefix("models/") for m in self._client().models.list() if m.name
        }
        return sorted(names)

    def _config(self, schema: type[BaseModel], system: str | None, temperature: float) -> Any:
        return genai_types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_schema=schema,
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
        return schema.model_validate_json(strip_code_fences(text))

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

    def _attempt(self, prompt: str, schema: type[SchemaT], system: str | None, temperature: float) -> tuple[SchemaT, int, int, int]:
        """One rate-limited network call. Returns (object, prompt_tokens, output_tokens, latency_ms)."""
        self.limiter.acquire()
        started = self._clock()
        try:
            response = self._client().models.generate_content(
                model=self.model, contents=prompt, config=self._config(schema, system, temperature)
            )
            obj = self._parse(response, schema)
        except genai_errors.ClientError as exc:
            if exc.code == 429:
                raise _Retryable(exc) from exc
            raise LLMError(f"Gemini rejected the request ({exc.code} {exc.status}): {exc.message}") from exc
        except genai_errors.ServerError as exc:
            raise _Retryable(exc) from exc
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            raise _Retryable(exc) from exc
        latency_ms = int(round((self._clock() - started) * 1000))
        prompt_tokens, output_tokens = self._usage(response)
        return obj, prompt_tokens, output_tokens, latency_ms

    def _call_with_retry(
        self, prompt: str, schema: type[SchemaT], system: str | None, temperature: float
    ) -> tuple[SchemaT, CallMeta]:
        last_error: BaseException | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                obj, prompt_tokens, output_tokens, latency_ms = self._attempt(prompt, schema, system, temperature)
            except _Retryable as retryable:
                last_error = retryable.cause
                if attempt == MAX_ATTEMPTS:
                    break
                delay = self._backoff(attempt, str(retryable.cause))
                log.warning(
                    "gemini %s attempt %d/%d failed (%s); retrying in %.1fs",
                    self.model, attempt, MAX_ATTEMPTS, type(retryable.cause).__name__, delay,
                )
                self._sleep(delay)
                continue
            meta = CallMeta(
                model=self.model,
                cached=False,
                latency_ms=latency_ms,
                prompt_tokens=prompt_tokens,
                output_tokens=output_tokens,
                attempts=attempt,
            )
            log.info("gemini %s ok in %dms (attempt %d, %d+%d tokens)", self.model, latency_ms, attempt, prompt_tokens, output_tokens)
            return obj, meta
        raise LLMError(
            f"Gemini call to {self.model} failed after {MAX_ATTEMPTS} attempts; "
            f"last error {type(last_error).__name__}: {last_error}"
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
        if cache:
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

    def __repr__(self) -> str:
        return f"GeminiClient(model={self.model!r}, rpm={self.rpm}, rpd={self.rpd}, temperature={self.temperature})"


__all__ = ["GeminiClient", "MAX_ATTEMPTS", "BACKOFF_SECONDS", "strip_code_fences", "retry_hint_seconds"]
