"""LLM layer: Gemini structured-output client, SQLite replay cache, rate limiter and offline mock.

Usage::

    from cadence.llm import get_client
    client = get_client("agent")                     # GeminiClient, or MockClient when CADENCE_LLM=mock
    obj, meta = client.generate_json(prompt, MySchema, system=SYSTEM_PROMPT)

Environment: ``GEMINI_API_KEY``/``GOOGLE_API_KEY`` (via .env), ``CADENCE_CACHE_ONLY=1`` (replay only,
raise `CacheMissError` on a miss), ``CADENCE_LLM=mock`` (offline mock), ``CADENCE_*_MODEL`` overrides.

Schema guidance for every module that defines a ``response_schema`` (verified against google-genai
1.45.0 ``_transformers.t_schema`` with a Gemini-API, non-Vertex client):

Supported pydantic constructs
    * scalar fields ``str`` / ``int`` / ``float`` / ``bool`` with ``Field`` constraints
      (``ge``/``le``/``min_length``/``max_length``/``pattern`` are forwarded to the API schema);
    * ``Literal["a", "b"]`` (string literals only, incl. single-value literals) and ``str``-valued ``Enum``;
    * ``Optional[X]`` / ``X | None`` (becomes ``nullable``), nested ``BaseModel`` fields, ``list[X]``
      of scalars or models, ``Field(description=...)`` text (it reaches the model, use it);
    * ``Union[ModelA, ModelB]`` converts (``anyOf``) but is unnecessary here and the mock always picks
      the first member — prefer a single model with a discriminating ``Literal`` field.

Rejected by the SDK (raise ``ValueError``/``ValidationError`` before any network call)
    * ``dict[str, Any]`` / ``dict[str, X]`` and ``model_config = ConfigDict(extra="allow")``
      -> "additionalProperties is not supported in the Gemini API";
    * ``Literal[1, 2]`` / int-valued ``Enum`` (enum values must be strings);
    * ``tuple[int, str]`` (``prefixItems`` is not part of the API ``Schema``);
    * self-referential / recursive models (infinite ``$ref`` expansion).

Keep response schemas flat-ish and small: every field costs output tokens and the free-tier models
are the bottleneck. Token accounting: ``output_tokens`` = candidate tokens + thinking tokens.
"""

from __future__ import annotations

import os

from cadence.config import model_limits, model_name, models_config
from cadence.llm.base import CacheMissError, CallMeta, LLMClient, LLMError, QuotaExhausted
from cadence.llm.cache import LLMCache, schema_json
from cadence.llm.gemini import GeminiClient
from cadence.llm.mock import MockClient, fill_schema
from cadence.llm.ratelimit import RateLimiter

ROLES: tuple[str, ...] = ("agent", "judge", "zero_shot")


def use_mock() -> bool:
    """True when `CADENCE_LLM=mock` selects the offline client."""
    return os.environ.get("CADENCE_LLM", "").strip().lower() == "mock"


def get_client(role: str) -> LLMClient:
    """Factory for the client of a role (`agent` | `judge` | `zero_shot`), CONTRACT.md §12.

    The judge uses `judge_temperature` from `config/models.yaml`, the other roles `temperature`.
    """
    if role not in ROLES:
        raise ValueError(f"unknown LLM role {role!r}; expected one of {ROLES}")
    if use_mock():
        return MockClient()
    cfg = models_config()
    model = model_name(role)
    rpm, rpd = model_limits(model)
    temperature_key = "judge_temperature" if role == "judge" else "temperature"
    temperature = float(cfg.get(temperature_key, cfg.get("temperature", 0.2)))
    return GeminiClient(model, rpm=rpm, rpd=rpd, temperature=temperature)


__all__ = [
    "CallMeta",
    "LLMClient",
    "LLMError",
    "CacheMissError",
    "QuotaExhausted",
    "LLMCache",
    "schema_json",
    "RateLimiter",
    "GeminiClient",
    "MockClient",
    "fill_schema",
    "ROLES",
    "use_mock",
    "get_client",
]
