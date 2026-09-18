"""Small shared utilities: logging, JSON/JSONL IO, text helpers, hashing."""

from cadence.utils.hashing import sha256_text, stable_key
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl
from cadence.utils.log import get_logger
from cadence.utils.text import normalize_ws, truncate, word_count

__all__ = [
    "get_logger",
    "read_json",
    "read_jsonl",
    "write_json",
    "write_jsonl",
    "sha256_text",
    "stable_key",
    "normalize_ws",
    "truncate",
    "word_count",
]
