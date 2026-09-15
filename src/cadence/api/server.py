"""Cadence HTTP API (CONTRACT.md §10) — ``uvicorn cadence.api.server:app``.

Every heavy artifact is loaded lazily through :mod:`cadence.api.state`; a missing artifact yields a
``503`` whose ``detail`` names the ``make`` target that produces it. When ``ui/dist`` exists the
built React app is served with an SPA fallback for every non-``/api`` path.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, field_validator

from cadence import __version__
from cadence.api import rating_queue
from cadence.api.core import HandleRequest, install_observability
from cadence.api.decisions import parse_decision_log
from cadence.api.merge import merge_example
from cadence.api.state import STATE, cache_only_env, health_payload, require_path
from cadence.config import JUDGE_DIMENSIONS, JUDGE_FLAGS, VERDICTS, Paths, api_key, cache_only
from cadence.utils.io import write_jsonl
from cadence.utils.log import get_logger

log = get_logger(__name__)

CORS_ORIGINS: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
MAX_TEXT_CHARS = 1000

app = FastAPI(title="Cadence API", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
install_observability(app)
app.add_middleware(
    CORSMiddleware, allow_origins=list(CORS_ORIGINS), allow_methods=["*"], allow_headers=["*"], allow_credentials=True
)


# ---------------------------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------------------------
class RatingIn(BaseModel):
    """Body of ``POST /api/ratings``: a blind rating with the system hidden behind an alias."""

    id: str
    system_alias: str
    scores: dict[str, int]
    flags: dict[str, bool]
    verdict: str
    rationale: str = ""

    @field_validator("scores")
    @classmethod
    def _scores_complete(cls, value: dict[str, int]) -> dict[str, int]:
        missing = [d for d in JUDGE_DIMENSIONS if d not in value]
        if missing:
            raise ValueError(f"scores missing dimensions: {', '.join(missing)}")
        bad = {k: v for k, v in value.items() if not 1 <= v <= 5}
        if bad:
            raise ValueError(f"scores must be integers 1-5, got {bad}")
        return value

    @field_validator("flags")
    @classmethod
    def _flags_complete(cls, value: dict[str, bool]) -> dict[str, bool]:
        missing = [f for f in JUDGE_FLAGS if f not in value]
        if missing:
            raise ValueError(f"flags missing: {', '.join(missing)}")
        return value

    @field_validator("verdict")
    @classmethod
    def _verdict_known(cls, value: str) -> str:
        if value not in VERDICTS:
            raise ValueError(f"verdict must be one of {', '.join(VERDICTS)}")
        return value


# ---------------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------------
def _exception_named(exc: BaseException, name: str) -> bool:
    """True when ``exc`` (or a base class) is called ``name``.

    The LLM layer's exception classes are matched by name so this module does not need to know
    which submodule of ``cadence.llm`` defines them.
    """
    return any(cls.__name__ == name for cls in type(exc).__mro__)


def _as_row(response: Any) -> dict[str, Any]:
    """Serialise an ``AgentResponse`` (pydantic) or an already-plain dict."""
    if isinstance(response, dict):
        return response
    return response.model_dump(mode="json")


def _merged_example(example: dict[str, Any]) -> dict[str, Any]:
    return merge_example(example, STATE.predictions(), STATE.judge_scores())


# ---------------------------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    """Liveness plus what is available on disk; works with nothing built yet."""
    return health_payload(STATE)


@app.post("/api/agent/handle")
def agent_handle(body: HandleRequest) -> dict[str, Any]:
    """Run the support agent on one customer message.

    ``mode="cache_only"`` (or no API key, or ``CADENCE_CACHE_ONLY=1``) forbids network calls: a
    message absent from the replay cache yields ``503``.
    """
    replay = body.mode == "cache_only" or cache_only() or api_key() is None
    try:
        with STATE.agent_lock, cache_only_env(replay):
            agent = STATE.agent(replay)
            response = agent.handle(body.text)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - translated into HTTP errors below
        if _exception_named(exc, "CacheMissError"):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Model network calls are disabled and this exact request is not cached. "
                    "Use the recorded evaluation for archived outputs, or enable live mode with a confirmed free-tier key."
                ),
            ) from exc
        if _exception_named(exc, "QuotaExhausted"):
            raise HTTPException(status_code=429, detail=f"Gemini daily quota exhausted: {exc}") from exc
        log.error("agent error_class=%s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Agent failed; retry later.") from exc
    return _as_row(response)


@app.get("/api/results")
def results() -> dict[str, Any]:
    return STATE.eval_summary()


@app.get("/api/failures")
def failures() -> list[dict[str, Any]]:
    return STATE.failure_modes()


@app.get("/api/golden")
def golden() -> list[dict[str, Any]]:
    """Every golden example merged with per-system predictions and judge scores."""
    predictions, judge = STATE.predictions(), STATE.judge_scores()
    return [merge_example(row, predictions, judge) for row in STATE.golden()]


@app.get("/api/golden/{example_id}")
def golden_one(example_id: str) -> dict[str, Any]:
    example = STATE.golden_by_id().get(example_id)
    if example is None:
        raise HTTPException(status_code=404, detail=f"unknown golden example {example_id!r}")
    return _merged_example(example)


@app.get("/api/ratings")
def ratings() -> list[dict[str, Any]]:
    return STATE.human_ratings()


@app.post("/api/ratings", status_code=201)
def post_rating(body: RatingIn) -> dict[str, Any]:
    """Store one blind human rating; the alias is resolved to the real system server-side."""
    if body.id not in STATE.golden_by_id():
        raise HTTPException(status_code=404, detail=f"unknown golden example {body.id!r}")
    try:
        system = rating_queue.resolve_alias(body.id, body.system_alias)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc.args[0])) from exc
    if (body.id, system) in rating_queue.rated_pairs(STATE.human_ratings()):
        raise HTTPException(status_code=409, detail=f"{body.id} already has a human rating for alias {body.system_alias}")
    row = {
        "id": body.id,
        "system": system,
        "rater": "human",
        "scores": body.scores,
        "flags": body.flags,
        "verdict": body.verdict,
        "rationale": body.rationale,
        "rated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    write_jsonl(Paths.HUMAN_RATINGS, [row], append=True)
    return row


@app.get("/api/rating-queue")
def rating_queue_route() -> list[dict[str, Any]]:
    """Blind queue of (example, system) pairs the human has not rated yet."""
    require_path(Paths.PREDICTIONS, "predictions")
    done = rating_queue.rated_pairs(STATE.human_ratings())
    return rating_queue.build_queue(STATE.golden(), STATE.predictions(), done)


@app.get("/api/decisions")
def decisions() -> list[dict[str, Any]]:
    return parse_decision_log(Paths.DECISION_LOG)


@app.get("/api/threads/{thread_id}")
def thread(thread_id: str) -> dict[str, Any]:
    found = STATE.thread(thread_id)
    if found is None:
        raise HTTPException(status_code=404, detail=f"unknown thread {thread_id!r}")
    return found


# ---------------------------------------------------------------------------------------------
# Static UI (SPA fallback) — must be registered last
# ---------------------------------------------------------------------------------------------
def _static_file(dist: Path, request_path: str) -> Path:
    """Resolve ``request_path`` inside ``dist``; anything outside or missing falls back to index.html."""
    root = dist.resolve()
    candidate = (root / request_path).resolve() if request_path else root
    if candidate.is_file() and candidate.is_relative_to(root):
        return candidate
    return root / "index.html"


@app.get("/{full_path:path}", include_in_schema=False, response_model=None)
def spa(full_path: str) -> Response:
    """Serve ``ui/dist`` assets and ``index.html`` for every other path when the UI has been built."""
    if full_path == "api" or full_path.startswith("api/"):
        return JSONResponse({"detail": f"unknown API route /{full_path}"}, status_code=404)
    dist = Paths.UI_DIST
    if not (dist / "index.html").is_file():
        return JSONResponse({"detail": "UI not built; run: make ui (or use the API under /api)"}, status_code=404)
    return FileResponse(_static_file(dist, full_path))
