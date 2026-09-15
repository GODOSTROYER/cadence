"""Shared pytest fixtures.

Tests must never see real API keys (or reach the network): `cadence.config` loads `.env` at import time,
so every test starts with the key variables removed. A test that needs a key sets a fake one explicitly.
"""

from __future__ import annotations

import pytest

KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEYS", "ADMIN_USER", "ADMIN_PASSWORD_HASH", "SESSION_SECRET")


@pytest.fixture(autouse=True)
def _no_real_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in KEY_VARS:
        monkeypatch.delenv(var, raising=False)
