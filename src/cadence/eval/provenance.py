"""Portable content hashes and run provenance; never reads credentials."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    data = path.read_bytes()
    # Git checkouts may use CRLF. Hash logical text identically on Windows/Linux.
    if path.suffix in {".json", ".jsonl", ".txt", ".md", ".yaml", ".py"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def revision(root: Path) -> dict:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", *args], cwd=root, text=True).strip()

    try:
        return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}
