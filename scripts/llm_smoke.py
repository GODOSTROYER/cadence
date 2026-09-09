"""Smoke-test the Gemini connection: list models, then make one tiny structured call.

Run from the repo root: ``python scripts/llm_smoke.py``. Without an API key it explains how to
configure one and exits 0; with a key it exits 0 even on failure, printing the error type/message
so that quota problems are visible without breaking a Makefile pipeline. The API key is never printed.
"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field

from cadence.config import api_key, model_name
from cadence.llm import GeminiClient


class Ping(BaseModel):
    """Two-field schema used for the smoke call."""

    greeting: str = Field(description="A one-word greeting.")
    mood: Literal["happy", "neutral"] = Field(description="Your mood right now.")


def _print_models(client: GeminiClient) -> None:
    names = [name for name in client.list_models() if "gemini" in name.lower()]
    print(f"{len(names)} gemini models visible to this key:")
    for name in names:
        print(f"  - {name}")


def _smoke_call(client: GeminiClient) -> None:
    obj, meta = client.generate_json(
        "Reply with a one-word greeting and say whether your mood is happy or neutral.",
        Ping,
        system="You are a terse assistant that answers only in the requested JSON.",
    )
    print(f"parsed: {obj.model_dump()}")
    print(f"meta:   {meta.model_dump()}")


def main(argv: list[str] | None = None) -> int:
    """Entry point; always returns 0 so that the pipeline is never blocked by a flaky smoke test."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not api_key():
        print(
            "No GEMINI_API_KEY / GOOGLE_API_KEY found. Copy .env.example to .env and add a key from "
            "https://aistudio.google.com/apikey, or run offline with CADENCE_LLM=mock / CADENCE_CACHE_ONLY=1."
        )
        return 0
    model = model_name("agent")
    client = GeminiClient(model)
    print(f"smoke-testing {client!r}")
    try:
        _print_models(client)
        _smoke_call(client)
    except Exception as exc:  # noqa: BLE001 - the whole point is to report any failure and keep going
        print(f"smoke test failed: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
