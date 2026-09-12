"""Cadence on Vercel: a slim ASGI function serving the live agent next to the static dashboard.

Only two endpoints are exposed here — `GET /api/health` and `POST /api/agent/handle` — because everything
else the dashboard needs (results, golden set, failure modes, decisions) ships as static JSON in the build.
The retriever is built at cold start from the committed thread file (about two seconds); the committed
replay cache is copied to /tmp so recorded golden examples answer without an API call, and new messages
go to Gemini with the keys configured as Vercel environment variables (`GEMINI_API_KEYS`).
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import APIRouter, FastAPI, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from cadence import __version__  # noqa: E402
from cadence.config import Paths, api_keys, model_name  # noqa: E402
from cadence.utils.io import read_jsonl  # noqa: E402

TMP_CACHE = Path(os.environ.get("CADENCE_TMP_DIR", "/tmp")) / "llm_cache.sqlite"

app = FastAPI(title="Cadence live agent", version=__version__)
router = APIRouter()
_lock = threading.Lock()
_state: dict[str, Any] = {}


class HandleRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mode: str | None = None


def _cache_path() -> Path:
    """A writable copy of the committed replay cache (the deployment filesystem is read-only)."""
    if not TMP_CACHE.exists():
        TMP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        if Paths.LLM_CACHE.exists():
            shutil.copyfile(Paths.LLM_CACHE, TMP_CACHE)
    return TMP_CACHE


def _agent():
    """Build the retriever and agent once per cold start."""
    with _lock:
        if "agent" not in _state:
            from cadence.agent.pipeline import SupportAgent
            from cadence.llm.gemini import GeminiClient
            from cadence.retrieval.index import Retriever

            retriever = Retriever.build(read_jsonl(Paths.THREADS))
            client = GeminiClient(model_name("agent"), cache_path=_cache_path())
            _state["retriever"] = retriever
            _state["agent"] = SupportAgent(client, retriever)
        return _state["agent"]


@router.get("/api/health")
def health() -> dict[str, Any]:
    n_golden = sum(1 for _ in read_jsonl(Paths.GOLDEN)) if Paths.GOLDEN.exists() else 0
    return {
        "status": "ok",
        "has_api_key": bool(api_keys()),
        "cache_only": False,
        "agent_model": model_name("agent"),
        "judge_model": model_name("judge"),
        "cache_entries": 0,
        "index_size": len(_state["retriever"]) if "retriever" in _state else 0,
        "n_golden": n_golden,
        "deployment": "vercel",
    }


@router.post("/api/agent/handle")
def handle(req: HandleRequest) -> dict[str, Any]:
    if not api_keys():
        raise HTTPException(status_code=503, detail="No Gemini key is configured on this deployment (GEMINI_API_KEYS).")
    from cadence.llm.base import LLMError, QuotaExhausted

    try:
        response = _agent().handle(req.text.strip(), id="live")
    except QuotaExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return response.model_dump()


# The same routes at the root and under the proxied sub-path (www.arnavbule.in/hiver-assignment/api/...).
app.include_router(router)
app.include_router(router, prefix="/hiver-assignment")
