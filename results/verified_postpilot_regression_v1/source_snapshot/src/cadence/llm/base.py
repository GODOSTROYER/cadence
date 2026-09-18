"""Shared LLM-layer types: the `LLMClient` protocol, `CallMeta`, and the exception hierarchy.

Every consumer of the LLM layer (agent, judge, zero-shot baseline) codes against `LLMClient`
so that the Gemini client, the replay cache and the offline mock are interchangeable.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, Field

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class CallMeta(BaseModel):
    """Bookkeeping returned alongside every structured LLM call (CONTRACT.md §12)."""

    model: str = Field(description="Model name that produced (or would have produced) the response.")
    cached: bool = Field(description="True when the response was replayed from the SQLite cache.")
    latency_ms: int = Field(ge=0, description="Wall-clock milliseconds of the network call; 0 on cache hits.")
    prompt_tokens: int = Field(ge=0, description="Prompt tokens billed by the API (0 when unknown).")
    output_tokens: int = Field(ge=0, description="Candidate + thinking tokens billed by the API (0 when unknown).")
    attempts: int = Field(ge=0, description="Network attempts made; 0 on cache hits, 1 on a clean first call.")


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a prompt into a validated pydantic object."""

    model: str

    def generate_json(
        self,
        prompt: str,
        schema: type[SchemaT],
        *,
        system: str | None = None,
        temperature: float | None = None,
        cache: bool = True,
    ) -> tuple[SchemaT, CallMeta]:
        """Return an instance of `schema` built from the model's structured JSON output, plus call metadata."""
        ...


class LLMError(Exception):
    """Base class for every failure raised by the LLM layer."""


class CacheMissError(LLMError):
    """Raised in cache-only mode (`CADENCE_CACHE_ONLY=1`) when a prompt is not in the replay cache."""


class QuotaExhausted(LLMError):
    """Raised when the persisted daily request counter for a model has reached its RPD limit."""


__all__ = ["CallMeta", "LLMClient", "LLMError", "CacheMissError", "QuotaExhausted", "SchemaT"]
