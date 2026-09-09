"""Tests for the intent taxonomy pass: config/intents.yaml, the calibration labels, and the taxonomy documents.

No network, no LLM, no parquet: everything reads small repo files. The keyword classifier is re-implemented here
from the CONTRACT §15.1 spec so the test does not depend on other engineers' modules.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
import yaml

from cadence.config import DECISIONS, Paths, reason_codes

INTENTS_YAML = Paths.CONFIG / "intents.yaml"
CALIBRATION = Paths.ROOT / "docs" / "taxonomy_calibration.jsonl"
TAXONOMY_DOC = Paths.ROOT / "docs" / "TAXONOMY.md"
VOICE_DOC = Paths.ROOT / "docs" / "BRAND_VOICE.md"
GUIDE_DOC = Paths.LABELLING_GUIDE

CONTRACT_DRAFT_IDS = {
    "playback_or_app_bug",
    "download_or_offline",
    "login_or_password",
    "account_hacked_or_security",
    "billing_or_charge",
    "subscription_or_plan",
    "content_or_availability",
    "playlist_or_library",
    "feature_request_or_feedback",
    "non_english",
    "other",
}
SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
WORD_BOUNDARY_MAX_LEN = 4


@pytest.fixture(scope="module")
def cfg() -> dict:
    with open(INTENTS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def calibration() -> list[dict]:
    with open(CALIBRATION, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def compile_keyword(keyword: str) -> re.Pattern[str]:
    """CONTRACT §15.1 / sampling note: word boundaries for short alphanumeric keywords, substring otherwise."""
    kw = keyword.strip().lower()
    escaped = re.escape(kw)
    if len(kw) <= WORD_BOUNDARY_MAX_LEN and re.search(r"\w", kw):
        return re.compile(r"(?<!\w)" + escaped + r"(?!\w)")
    return re.compile(escaped)


def keyword_classify(text: str, cfg: dict) -> str:
    """Intent with the most keyword hits; ties -> earlier intent; no hit -> other."""
    lowered = text.lower()
    best_id, best_hits = "other", 0
    for intent in cfg["intents"]:
        hits = sum(1 for kw in intent["keywords"] if compile_keyword(str(kw)).search(lowered))
        if hits > best_hits:
            best_id, best_hits = intent["id"], hits
    return best_id


def macro_f1(gold: list[str], pred: list[str]) -> float:
    labels = sorted(set(gold) | set(pred))
    scores = []
    for lab in labels:
        tp = sum(1 for g, p in zip(gold, pred, strict=True) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred, strict=True) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred, strict=True) if g == lab and p != lab)
        denom = 2 * tp + fp + fn
        scores.append(2 * tp / denom if denom else 0.0)
    return sum(scores) / len(scores)


# --------------------------------------------------------------------------- config/intents.yaml


def test_top_level_schema(cfg: dict) -> None:
    assert cfg["version"] == 1
    assert cfg["brand"] == "SpotifyCares"
    assert 10 <= len(cfg["intents"]) <= 12


def test_intent_records(cfg: dict) -> None:
    valid_reasons = set(reason_codes())
    ids = [i["id"] for i in cfg["intents"]]
    assert len(ids) == len(set(ids)), "duplicate intent ids"
    for intent in cfg["intents"]:
        assert SNAKE_CASE.match(intent["id"]), intent["id"]
        assert intent["name"].strip()
        assert len(intent["description"].split()) >= 15, f"{intent['id']} description too short"
        assert len(intent["examples"]) == 3, f"{intent['id']} must have exactly 3 verbatim examples"
        assert all(isinstance(e, str) and e.strip() for e in intent["examples"])
        assert intent["default_decision"] in DECISIONS
        if intent["default_decision"] == "escalate":
            assert intent["default_reason_code"] in valid_reasons, intent["id"]
        else:
            assert "default_reason_code" not in intent
        assert intent["keywords"], f"{intent['id']} has no keywords"


def test_contract_ids_are_stable(cfg: dict) -> None:
    ids = {i["id"] for i in cfg["intents"]}
    assert CONTRACT_DRAFT_IDS <= ids
    extra = ids - CONTRACT_DRAFT_IDS
    assert extra == {"metadata_or_artist_issue"}, extra
    assert cfg["intents"][-1]["id"] == "other", "other must be last so it only wins ties as the fallback"


def test_keywords_are_normalised_and_unique(cfg: dict) -> None:
    owner: dict[str, str] = {}
    for intent in cfg["intents"]:
        seen: set[str] = set()
        for kw in intent["keywords"]:
            kw = str(kw)
            assert kw == kw.strip() and kw == kw.lower(), f"{intent['id']}: {kw!r} not normalised"
            assert kw not in seen, f"{intent['id']}: duplicate keyword {kw!r}"
            seen.add(kw)
            assert kw not in owner, f"{kw!r} listed under both {owner.get(kw)} and {intent['id']}"
            owner[kw] = intent["id"]


def test_examples_are_classified_by_their_own_keywords(cfg: dict) -> None:
    """Each intent's verbatim examples should mostly be recovered by the keyword baseline (sanity of keywords)."""
    ok = total = 0
    for intent in cfg["intents"]:
        for example in intent["examples"]:
            total += 1
            ok += keyword_classify(example, cfg) == intent["id"]
    assert ok / total >= 0.8, f"only {ok}/{total} examples recovered by their own keywords"


# --------------------------------------------------------------------------- calibration labels


def test_calibration_file(cfg: dict, calibration: list[dict]) -> None:
    ids = {i["id"] for i in cfg["intents"]}
    assert len(calibration) == 150
    assert len({r["thread_id"] for r in calibration}) == 150
    for row in calibration:
        assert set(row) == {"thread_id", "text", "intent"}
        assert row["thread_id"].startswith("t_")
        assert row["intent"] in ids
    counts = Counter(r["intent"] for r in calibration)
    assert len(counts) >= 10, counts


def test_keyword_baseline_quality(cfg: dict, calibration: list[dict]) -> None:
    gold = [r["intent"] for r in calibration]
    pred = [keyword_classify(r["text"], cfg) for r in calibration]
    accuracy = sum(g == p for g, p in zip(gold, pred, strict=True)) / len(gold)
    f1 = macro_f1(gold, pred)
    assert accuracy >= 0.78, f"keyword baseline accuracy dropped to {accuracy:.3f}"
    assert f1 >= 0.78, f"keyword baseline macro-F1 dropped to {f1:.3f}"


def test_keyword_classifier_matches_sampler_implementation(cfg: dict, calibration: list[dict]) -> None:
    sample = pytest.importorskip("cadence.data.sample")
    matchers = sample.load_intent_keywords(cfg)
    for row in calibration:
        bucket = sample.assign_bucket(row["text"], matchers)
        assert (bucket[3:] if bucket else "other") == keyword_classify(row["text"], cfg)


# --------------------------------------------------------------------------- documents


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_taxonomy_doc_sections(cfg: dict) -> None:
    doc = _read(TAXONOMY_DOC)
    for heading in (
        "## 1. Method",
        "## 2. Cluster table",
        "## 3. Final taxonomy",
        "## 4. Estimated distribution",
        "## 6. Deliberately left out",
    ):
        assert heading in doc, heading
    for intent in cfg["intents"]:
        assert intent["id"] in doc


def test_voice_guide_section(cfg: dict) -> None:
    doc = _read(VOICE_DOC)
    assert doc.count("\n## Voice guide\n") == 1
    guide = doc.split("\n## Voice guide\n", 1)[1]
    guide = guide.split("\n## ", 1)[0]
    lines = [ln for ln in guide.rstrip().splitlines() if ln.strip()]
    assert 8 <= len(lines) <= 25, f"voice guide has {len(lines)} lines"
    assert " /AI" in guide
    for intent in cfg["intents"]:
        assert f"### {intent['id']}" in doc, f"BRAND_VOICE.md lacks a section for {intent['id']}"


def test_labelling_guide_mentions_every_label(cfg: dict) -> None:
    doc = _read(GUIDE_DOC)
    for intent in cfg["intents"]:
        assert intent["id"] in doc
    for code in reason_codes():
        assert code in doc
    for sentiment in ("positive", "neutral", "frustrated", "angry"):
        assert f"`{sentiment}`" in doc
    for field in (
        "intent",
        "secondary_intent",
        "should_escalate",
        "escalation_reason_code",
        "sentiment",
        "media_only",
        "notes",
    ):
        assert f"`{field}`" in doc
    assert "## 6. Sampling" in doc
