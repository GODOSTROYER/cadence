"""Shared live request contract and privacy-safe error/latency middleware."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)


class HandleRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    mode: Literal["live", "cache_only"] = "live"

    @field_validator("text")
    @classmethod
    def not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("text must contain at least one non-whitespace character")
        return text


def install_observability(app):
    @app.middleware("http")
    async def observe(request, call_next):
        request_id = uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Do not log raw exception messages, request text, cookies or key headers.
            log.error("request_id=%s error_class=%s", request_id, type(exc).__name__)
            response = JSONResponse(
                status_code=500, content={"detail": "Internal error; retry later.", "request_id": request_id}
            )
        response.headers["X-Request-ID"] = request_id
        if "/api/" in request.url.path:
            response.headers["Cache-Control"] = "no-store"
        log.info(
            "request_id=%s method=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            response.status_code,
            (time.perf_counter() - start) * 1000,
        )
        return response
