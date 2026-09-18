"""Project-wide logging with rich formatting (falls back to std logging)."""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = os.environ.get("CADENCE_LOG_LEVEL", "INFO").upper()
    try:
        from rich.logging import RichHandler

        logging.basicConfig(
            level=level,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(rich_tracebacks=False, show_path=False, markup=False)],
        )
    except Exception:  # pragma: no cover - rich is a hard dependency, but stay safe
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for `name`."""
    _configure()
    return logging.getLogger(name)
