"""Cadence on Vercel: the live agent plus an admin session for the internal dashboards.

Public endpoints (no login): `GET /api/health`, `POST /api/agent/handle` (optional `X-Gemini-Key` header lets a
visitor run the agent on their own free-tier key instead of the pooled deployment keys).
Admin endpoints: `POST /api/admin/login`, `POST /api/admin/logout`, `GET /api/admin/me`,
`GET /api/admin/data/{name}` (eval_summary | failure_modes | golden_merged | decisions | health).

The admin session is a signed, HttpOnly cookie (HMAC over user + expiry with `SESSION_SECRET`); the password is
compared as a SHA-256 digest against `ADMIN_PASSWORD_HASH`, so the plaintext never lives on the server. Internal
JSON is bundled under `results/ui/` and only served to authenticated sessions; the public build ships just the
headline summary. Everything is mounted twice, at `/api/...` and `/hiver-assignment/api/...`, so it works both
directly and behind the www.arnavbule.in proxy.

The retriever is built at cold start from the committed thread file (about two seconds); the committed replay
cache is copied to /tmp so it is writable; new messages go to Gemini with the keys in `GEMINI_API_KEYS`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from cadence import __version__  # noqa: E402
from cadence.config import Paths, api_keys, model_name  # noqa: E402
from cadence.utils.io import read_jsonl  # noqa: E402

TMP_CACHE = Path(os.environ.get("CADENCE_TMP_DIR", "/tmp")) / "llm_cache.sqlite"
ADMIN_DATA_DIR = ROOT / "results" / "ui"
ADMIN_DATA_FILES = ("eval_summary", "failure_modes", "golden_merged", "decisions", "health")
COOKIE_NAME = "cadence_admin"
SESSION_SECONDS = 7 * 24 * 3600

app = FastAPI(title="Cadence live agent", version=__version__)
router = APIRouter()
_lock = threading.Lock()
_state: dict[str, Any] = {}


class HandleRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mode: str | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


# --------------------------------------------------------------------------- agent
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


def _cache_entries() -> int:
    """Number of replayable calls in the committed cache (read from the writable /tmp copy)."""
    try:
        import sqlite3

        with sqlite3.connect(str(_cache_path())) as conn:
            return int(conn.execute("select count(*) from calls").fetchone()[0])
    except Exception:  # noqa: BLE001 - health must never fail because of the cache
        return 0


def _thread_count() -> int:
    """Threads in the committed corpus, counted once per instance (cheap; the index itself builds on first use)."""
    if "thread_count" not in _state:
        _state["thread_count"] = sum(1 for _ in read_jsonl(Paths.THREADS)) if Paths.THREADS.exists() else 0
    return _state["thread_count"]


@router.get("/api/health")
def health() -> dict[str, Any]:
    n_golden = sum(1 for _ in read_jsonl(Paths.GOLDEN)) if Paths.GOLDEN.exists() else 0
    return {
        "status": "ok",
        "has_api_key": bool(api_keys()),
        "cache_only": False,
        "agent_model": model_name("agent"),
        "judge_model": model_name("judge"),
        "cache_entries": _cache_entries(),
        "index_size": len(_state["retriever"]) if "retriever" in _state else _thread_count(),
        "n_golden": n_golden,
        "deployment": "vercel",
        "admin_enabled": bool(_admin_hash() and _secret()),
    }


KEY_HEADER = "x-gemini-key"


def _agent_for(own_key: str | None):
    """The shared agent, or a per-request agent bound to the caller's own Gemini key (never stored or logged)."""
    shared = _agent()
    key = (own_key or "").strip()
    if not key:
        return shared
    from cadence.agent.pipeline import SupportAgent
    from cadence.llm.gemini import GeminiClient

    client = GeminiClient(model_name("agent"), api_keys=[key], cache_path=_cache_path())
    return SupportAgent(client, _state["retriever"])


@router.post("/api/agent/handle")
def handle(req: HandleRequest, request: Request) -> dict[str, Any]:
    own_key = request.headers.get(KEY_HEADER)
    if not api_keys() and not own_key:
        raise HTTPException(
            status_code=503,
            detail="No Gemini key is configured on this deployment; paste your own key in the playground to run it.",
        )
    from cadence.llm.base import LLMError, QuotaExhausted

    try:
        response = _agent_for(own_key).handle(req.text.strip(), id="live")
    except QuotaExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return response.model_dump()


# --------------------------------------------------------------------------- admin session
def _secret() -> bytes:
    return os.environ.get("SESSION_SECRET", "").encode()


def _admin_user() -> str:
    return os.environ.get("ADMIN_USER", "admin")


def _admin_hash() -> str:
    return os.environ.get("ADMIN_PASSWORD_HASH", "").strip().lower()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def _issue_token(user: str) -> str:
    payload = f"{user}|{int(time.time()) + SESSION_SECONDS}"
    return f"{payload}|{_sign(payload)}"


def _session_user(request: Request) -> str | None:
    """The logged-in admin user, or None when the cookie is missing, tampered with or expired."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not _secret():
        return None
    try:
        user, expires, signature = token.rsplit("|", 2)
    except ValueError:
        return None
    payload = f"{user}|{expires}"
    if not hmac.compare_digest(_sign(payload), signature):
        return None
    if int(expires) < time.time():
        return None
    return user


def _require_admin(request: Request) -> str:
    user = _session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="Admin sign-in required.")
    return user


@router.post("/api/admin/login")
def admin_login(req: LoginRequest, response: Response) -> dict[str, Any]:
    expected = _admin_hash()
    if not expected or not _secret():
        raise HTTPException(status_code=503, detail="Admin login is not configured on this deployment.")
    given = hashlib.sha256(req.password.encode()).hexdigest()
    ok_user = hmac.compare_digest(req.username.strip().lower(), _admin_user().lower())
    ok_pass = hmac.compare_digest(given, expected)
    if not (ok_user and ok_pass):
        time.sleep(0.4)  # blunt brute-force damper
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    response.set_cookie(
        COOKIE_NAME,
        _issue_token(_admin_user()),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )
    return {"authenticated": True, "user": _admin_user()}


@router.post("/api/admin/logout")
def admin_logout(response: Response) -> dict[str, Any]:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"authenticated": False}


@router.get("/api/admin/me")
def admin_me(request: Request) -> dict[str, Any]:
    user = _session_user(request)
    return {"authenticated": user is not None, "user": user}


@router.get("/api/admin/data/{name}")
def admin_data(name: str, request: Request) -> Any:
    _require_admin(request)
    if name not in ADMIN_DATA_FILES:
        raise HTTPException(status_code=404, detail=f"unknown dataset {name!r}")
    path = ADMIN_DATA_DIR / f"{name}.json"
    if not path.exists():
        raise HTTPException(status_code=503, detail=f"{name}.json is not bundled; run scripts/07_export_ui_data.py")
    return json.loads(path.read_text(encoding="utf-8"))


# The same routes at the root and under the proxied sub-path (www.arnavbule.in/hiver-assignment/api/...).
app.include_router(router)
app.include_router(router, prefix="/hiver-assignment")
