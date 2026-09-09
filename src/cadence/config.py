"""Central paths, constants and YAML config loaders.

Every module imports paths from here so that the on-disk layout in CONTRACT.md §1 is defined once.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from cadence import BRAND, SEED

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT: Path = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


class Paths:
    """All file locations used by the pipeline (CONTRACT.md §1)."""

    ROOT = ROOT
    CONFIG = ROOT / "config"
    DATA = ROOT / "data"
    RAW = DATA / "raw"
    RAW_TWCS = RAW / "twcs" / "twcs.csv"
    PROCESSED = DATA / "processed"
    THREADS = PROCESSED / "spotify_threads.jsonl.gz"
    OPENERS = PROCESSED / "spotify_openers.parquet"
    LINK_MAP = PROCESSED / "link_map.json"
    REPLY_TEMPLATES = PROCESSED / "reply_templates.json"
    STATS = PROCESSED / "stats.json"
    GOLDEN_DIR = DATA / "golden"
    CANDIDATES = GOLDEN_DIR / "candidates.jsonl"
    GOLDEN = GOLDEN_DIR / "golden_set.jsonl"
    ANNOTATIONS_A = GOLDEN_DIR / "annotations_a.jsonl"
    ANNOTATIONS_B = GOLDEN_DIR / "annotations_b.jsonl"
    ADJUDICATION = GOLDEN_DIR / "adjudication.jsonl"
    HUMAN_RATINGS = GOLDEN_DIR / "human_ratings.jsonl"
    LABELLING_GUIDE = GOLDEN_DIR / "LABELLING_GUIDE.md"
    CACHE = ROOT / "cache"
    LLM_CACHE = CACHE / "llm_cache.sqlite"
    BM25_INDEX = CACHE / "bm25_index.pkl"
    RESULTS = ROOT / "results"
    PREDICTIONS = RESULTS / "predictions.jsonl"
    JUDGE_SCORES = RESULTS / "judge_scores.jsonl"
    EVAL_SUMMARY = RESULTS / "eval_summary.json"
    FAILURE_MODES = RESULTS / "failure_modes.json"
    FIGURES = RESULTS / "figures"
    UI = ROOT / "ui"
    UI_DIST = UI / "dist"
    UI_PUBLIC_DATA = UI / "public" / "data"
    DECISION_LOG = ROOT / "DECISION_LOG.md"

    @classmethod
    def ensure_dirs(cls) -> None:
        for p in (cls.PROCESSED, cls.GOLDEN_DIR, cls.CACHE, cls.RESULTS, cls.FIGURES, cls.UI_PUBLIC_DATA):
            p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SPOTIFY_HANDLES: tuple[str, ...] = ("@SpotifyCares", "@spotifycares", "@115888", "@117168", "@117153")
"""Anonymised + real handles that all refer to Spotify accounts (CONTRACT.md §2)."""

SYSTEMS: tuple[str, ...] = ("agent", "trivial", "simple", "simple_keyword", "llm_zero_shot")
"""All prediction systems (CONTRACT.md §15.1)."""
JUDGED_SYSTEMS: tuple[str, ...] = ("agent", "simple", "trivial")
"""Systems whose reply drafts are scored by the LLM judge."""
DECISIONS: tuple[str, ...] = ("auto_handle", "escalate")
SENTIMENTS: tuple[str, ...] = ("positive", "neutral", "frustrated", "angry")
JUDGE_DIMENSIONS: tuple[str, ...] = ("grounded", "resolves", "tone", "safe", "overall")
JUDGE_FLAGS: tuple[str, ...] = ("hallucinated_link_or_policy", "asks_sensitive_info", "wrong_issue")
VERDICTS: tuple[str, ...] = ("ship", "edit", "reject")

__all__ = [
    "BRAND",
    "SEED",
    "ROOT",
    "Paths",
    "SPOTIFY_HANDLES",
    "SYSTEMS",
    "JUDGED_SYSTEMS",
    "DECISIONS",
    "SENTIMENTS",
    "JUDGE_DIMENSIONS",
    "JUDGE_FLAGS",
    "VERDICTS",
    "load_yaml",
    "intents_config",
    "intent_ids",
    "escalation_config",
    "reason_codes",
    "models_config",
    "model_name",
    "model_limits",
    "cache_only",
    "api_key",
]


# ---------------------------------------------------------------------------
# YAML configs
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file as a dict (cached)."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def intents_config() -> dict[str, Any]:
    return load_yaml(Paths.CONFIG / "intents.yaml")


def intent_ids() -> list[str]:
    """Ordered list of intent ids from config/intents.yaml."""
    return [i["id"] for i in intents_config()["intents"]]


def escalation_config() -> dict[str, Any]:
    return load_yaml(Paths.CONFIG / "escalation.yaml")


def reason_codes() -> list[str]:
    return [r["id"] for r in escalation_config()["reason_codes"]]


def models_config() -> dict[str, Any]:
    return load_yaml(Paths.CONFIG / "models.yaml")


def model_name(role: str) -> str:
    """Resolve the model for a role ('agent' | 'judge' | 'zero_shot'), honouring env overrides."""
    env = {"agent": "CADENCE_AGENT_MODEL", "judge": "CADENCE_JUDGE_MODEL", "zero_shot": "CADENCE_ZERO_SHOT_MODEL"}[role]
    return os.environ.get(env) or models_config()[f"{role}_model"]


def model_limits(model: str) -> tuple[int, int]:
    """(rpm, rpd) for a model, falling back to the `default` entry."""
    limits = models_config().get("limits", {})
    entry = limits.get(model) or limits.get("default") or {"rpm": 5, "rpd": 100}
    return int(entry["rpm"]), int(entry["rpd"])


def cache_only() -> bool:
    """True when network LLM calls are forbidden (replay mode)."""
    return os.environ.get("CADENCE_CACHE_ONLY", "").strip() in {"1", "true", "yes"}


def api_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None
