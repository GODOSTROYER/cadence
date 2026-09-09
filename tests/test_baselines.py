"""Tests for cadence.baselines — no network, no API key, < 5 s."""

from __future__ import annotations

import random
import re
import shutil
import tempfile
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from cadence.baselines import (
    BASELINE_SYSTEMS,
    keyword_intent,
    majority_intent,
    run_baselines,
    run_simple,
    run_simple_keyword,
    run_trivial,
    run_zero_shot,
    tfidf_lr_oof,
    top_template,
)
from cadence.baselines import trivial as trivial_mod
from cadence.baselines.simple import rules_decision
from cadence.baselines.zero_shot import MISSING_REASON, ZeroShotBatch
from cadence.config import Paths, intent_ids, reason_codes

INTENTS = intent_ids()
Responder = Callable[[str, type], dict[str, Any]]


def _plain(value: Any) -> Any:
    """Pydantic sub-models -> dicts so assertions read the same for model and dict rows."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def field(response: Any, name: str) -> Any:
    """Read a field from an AgentResponse model or a dict row."""
    return _plain(response[name] if isinstance(response, Mapping) else getattr(response, name))


@pytest.fixture
def tmp_dir() -> Iterator[Path]:
    """Own temp dir: pytest's shared basetemp is not writable in every sandbox."""
    path = Path(tempfile.mkdtemp(prefix="cadence-baselines-"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def no_llm_access(tmp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No API key, no mock override, no cache file: the zero-shot system must skip itself."""
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CADENCE_LLM"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(Paths, "LLM_CACHE", tmp_dir / "absent.sqlite")


# ---------------------------------------------------------------------------
# Fixtures: retriever, threads, golden rows
# ---------------------------------------------------------------------------
@dataclass
class FakeHit:
    thread_id: str
    score: float
    thread: dict[str, Any]


class FakeRetriever:
    """Word-overlap retriever with the §15.2 search signature."""

    def __init__(self, threads: list[dict[str, Any]]) -> None:
        self.threads = threads
        self.calls: list[dict[str, Any]] = []

    def search(self, query: str, k: int = 6, exclude_thread_ids: set[str] | None = None) -> list[FakeHit]:
        excluded = exclude_thread_ids or set()
        self.calls.append({"query": query, "k": k, "exclude": set(excluded)})
        words = set(query.lower().split())
        hits = [
            FakeHit(t["thread_id"], float(len(words & set(t["customer_text"].lower().split()))), t)
            for t in self.threads
            if t["thread_id"] not in excluded
        ]
        hits.sort(key=lambda h: (-h.score, h.thread_id))
        return hits[:k]


def thread(thread_id: str, customer_text: str, reply: str) -> dict[str, Any]:
    return {
        "thread_id": thread_id,
        "customer_text": customer_text,
        "first_reply_text": reply,
        "brand_replies": [{"text": reply, "resolved_links": ["https://support.spotify.com/x"]}],
    }


def golden(i: int, text: str, intent: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": f"g_{i:03d}",
        "thread_id": thread_id or f"t_{i}",
        "text": text,
        "split": "test",
    }
    if intent:
        row["gold"] = {"intent": intent, "should_escalate": False}
    return row


VOCAB: dict[str, list[str]] = {
    "playback_or_app_bug": [
        "app crashes",
        "keeps freezing",
        "won't play songs",
        "web player broken",
        "skipping tracks",
    ],
    "download_or_offline": [
        "downloads vanished",
        "offline mode broken",
        "redownload everything",
        "sd card storage",
        "downloaded albums gone",
    ],
    "login_or_password": [
        "can't log in",
        "forgot password",
        "reset email missing",
        "facebook login broken",
        "locked out account",
    ],
    "billing_or_charge": [
        "charged twice",
        "need a refund",
        "payment declined",
        "billed after cancelling",
        "double charge card",
    ],
    "content_or_availability": [
        "album greyed out",
        "artist missing",
        "not available in my country",
        "song removed",
        "add this podcast",
    ],
    "playlist_or_library": [
        "playlist songs gone",
        "library disappeared",
        "discover weekly missing",
        "wrapped not showing",
        "daily mix broken",
    ],
}


def synthetic_rows(n_per_class: int = 10, seed: int = 7) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    fillers = ["please help", "since yesterday", "on my phone", "again today", "any idea why"]
    i = 1
    for intent, phrases in VOCAB.items():
        for _ in range(n_per_class):
            text = f"{rng.choice(phrases)} {rng.choice(fillers)} {rng.choice(phrases)}"
            rows.append(golden(i, text, intent))
            i += 1
    rng.shuffle(rows)
    return rows


@pytest.fixture
def retriever() -> FakeRetriever:
    return FakeRetriever(
        [
            thread("t_1", "i was charged twice this month", "Own thread reply — must never be cited"),
            thread(
                "t_2", "charged twice for premium", "Hey! Sorry about the double charge, DM us your email /JI"
            ),
            thread(
                "t_3", "app crashing on android after update", "Hey! Try a clean reinstall of the app /NS"
            ),
        ]
    )


# ---------------------------------------------------------------------------
# keyword_intent
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the app keeps crashing since the update", "playback_or_app_bug"),
        ("my downloads disappeared in offline mode", "download_or_offline"),
        ("can't log in, forgot my password", "login_or_password"),
        ("someone else is playing music on a device i don't own, hacked?", "account_hacked_or_security"),
        ("i was charged twice this month, need a refund", "billing_or_charge"),
        ("how do i add my sister to the family plan", "subscription_or_plan"),
        ("why is this album greyed out and not available in my country", "content_or_availability"),
        ("my playlist songs vanished from my library", "playlist_or_library"),
        ("please add dark mode, would be nice", "feature_request_or_feedback"),
        ("hola no puedo entrar en mi cuenta", "non_english"),
        ("crash refund", "billing_or_charge"),  # 1-1 tie -> earlier intent wins
        ("zzz qqq nothing here", "other"),  # no hit at all
    ],
)
def test_keyword_intent(text: str, expected: str) -> None:
    assert keyword_intent(text) == expected


def test_keyword_short_keywords_need_word_boundaries() -> None:
    assert keyword_intent("this is weird") == "other"  # "hi" must not fire inside "this"
    assert keyword_intent("hi") == "other"  # whole-word "hi" is an `other` keyword
    assert keyword_intent("Thanks!!") == "other"
    assert keyword_intent("") == "other"


# ---------------------------------------------------------------------------
# tfidf_lr_oof
# ---------------------------------------------------------------------------
def test_tfidf_lr_oof_predicts_every_row_deterministically() -> None:
    rows = synthetic_rows()
    first = tfidf_lr_oof(rows)
    second = tfidf_lr_oof(rows)
    assert len(first) == len(rows) == 60
    assert set(first) <= set(INTENTS)
    assert first == second
    accuracy = sum(p == r["gold"]["intent"] for p, r in zip(first, rows, strict=True)) / len(rows)
    assert accuracy > 0.8, accuracy


def test_tfidf_lr_oof_falls_back_to_kfold_for_rare_classes() -> None:
    rows = synthetic_rows(n_per_class=3)  # every class < 5 rows -> stratification impossible
    preds = tfidf_lr_oof(rows)
    assert len(preds) == len(rows) and set(preds) <= set(INTENTS)


def test_tfidf_lr_oof_without_gold_uses_keywords() -> None:
    rows = [golden(1, "app keeps crashing"), golden(2, "charged twice, refund please")]
    assert tfidf_lr_oof(rows) == ["playback_or_app_bug", "billing_or_charge"]


def test_tfidf_lr_oof_mixed_labelled_and_candidates() -> None:
    rows = synthetic_rows() + [golden(999, "charged twice need a refund")]
    preds = tfidf_lr_oof(rows)
    assert len(preds) == 61 and preds[-1] in INTENTS


# ---------------------------------------------------------------------------
# trivial
# ---------------------------------------------------------------------------
def test_trivial_rows(tmp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Paths, "REPLY_TEMPLATES", tmp_dir / "missing.json")
    rows = [
        golden(1, "charged twice", "billing_or_charge"),
        golden(2, "refund please", "billing_or_charge"),
        golden(3, "app crashes", "playback_or_app_bug"),
        golden(4, "no gold here"),
    ]
    out = run_trivial(rows)
    assert [field(r, "id") for r in out] == ["g_001", "g_002", "g_003", "g_004"]
    for r in out:
        assert field(r, "system") == "trivial"
        assert field(r, "intent") == "billing_or_charge"
        assert field(r, "decision") == "escalate"
        escalation = field(r, "escalation")
        assert escalation["reason_code"] == "low_confidence"
        assert escalation["reason"] == "trivial baseline escalates everything"
        assert field(r, "reply_draft") == trivial_mod.FALLBACK_TEMPLATE
        assert field(r, "citations") == [] and field(r, "evidence") == []


def test_majority_intent_ties_and_empty() -> None:
    assert majority_intent([]) == "other"
    assert majority_intent([golden(1, "x")]) == "other"
    rows = [golden(1, "a", "billing_or_charge"), golden(2, "b", "playback_or_app_bug")]
    assert majority_intent(rows) == "billing_or_charge"  # tie -> earlier intent in intents.yaml (v1 order: billing first)


def test_top_template_reads_json_shapes(tmp_dir: Path) -> None:
    path = tmp_dir / "reply_templates.json"
    path.write_text('[{"template": "Hey! DM us /AI", "count": 10}, {"template": "second"}]', encoding="utf-8")
    assert top_template(path) == "Hey! DM us /AI"
    path.write_text('["plain string first"]', encoding="utf-8")
    assert top_template(path) == "plain string first"
    path.write_text('{"templates": [{"text": "nested"}]}', encoding="utf-8")
    assert top_template(path) == "nested"
    path.write_text("[]", encoding="utf-8")
    assert top_template(path) == trivial_mod.FALLBACK_TEMPLATE


# ---------------------------------------------------------------------------
# simple / simple_keyword
# ---------------------------------------------------------------------------
def test_simple_rows(retriever: FakeRetriever) -> None:
    rows = [
        golden(1, "i was charged twice this month", "billing_or_charge", thread_id="t_1"),
        golden(2, "app crashing on android", "playback_or_app_bug", thread_id="t_9"),
    ]
    out = run_simple(rows, retriever)
    assert [field(r, "id") for r in out] == ["g_001", "g_002"]
    assert all(field(r, "system") == "simple" for r in out)

    billing = out[0]
    assert field(billing, "decision") == "escalate"
    assert field(billing, "escalation")["reason_code"] == "billing_dispute"
    assert "money_keywords" in field(billing, "rule_flags")
    assert field(billing, "reply_draft") == "Hey! Sorry about the double charge, DM us your email /JI"
    assert field(billing, "citations") == ["t_2"]
    evidence = field(billing, "evidence")
    assert len(evidence) == 1 and evidence[0]["thread_id"] == "t_2" and evidence[0]["cited"] is True
    assert set(evidence[0]) >= {
        "thread_id",
        "score",
        "customer_text",
        "brand_reply",
        "resolved_links",
        "cited",
    }
    assert retriever.calls[0]["exclude"] == {"t_1"} and retriever.calls[0]["k"] == 1
    assert field(billing, "trace")["forced_by_rules"] is True

    crash = out[1]
    assert field(crash, "decision") == "auto_handle" and field(crash, "escalation") is None
    assert field(crash, "citations") == ["t_3"]
    assert field(crash, "trace")["forced_by_rules"] is False


def test_simple_handles_no_retrieval_hit() -> None:
    out = run_simple([golden(1, "app crashing on my phone", "playback_or_app_bug")], FakeRetriever([]))
    assert (
        field(out[0], "reply_draft") == ""
        and field(out[0], "citations") == []
        and field(out[0], "evidence") == []
    )


def test_simple_keyword_copies_simple_rows(retriever: FakeRetriever) -> None:
    rows = [
        golden(1, "hola no puedo iniciar sesión", "non_english"),
        golden(2, "charged twice", "billing_or_charge"),
    ]
    simple_rows = run_simple(rows, retriever)
    kw_rows = run_simple_keyword(rows, simple_rows)
    assert [field(r, "system") for r in kw_rows] == ["simple_keyword", "simple_keyword"]
    assert [field(r, "intent") for r in kw_rows] == ["non_english", "billing_or_charge"]
    for kw, base in zip(kw_rows, simple_rows, strict=True):
        for name in (
            "id",
            "decision",
            "escalation",
            "reply_draft",
            "citations",
            "evidence",
            "rule_flags",
            "trace",
        ):
            assert field(kw, name) == field(base, name)
    assert [field(r, "system") for r in simple_rows] == ["simple", "simple"]  # originals untouched


@pytest.mark.parametrize(
    ("text", "decision", "code"),
    [
        ("you charged me twice", "escalate", "billing_dispute"),
        ("my account was hacked", "escalate", "account_security"),
        ("i will sue you", "escalate", "legal_or_safety"),
        ("<url>", "escalate", "ambiguous_or_media_only"),
        ("help", "escalate", "ambiguous_or_media_only"),
        ("the app keeps crashing since the update", "auto_handle", None),
    ],
)
def test_rules_decision(text: str, decision: str, code: str | None) -> None:
    outcome = rules_decision(text)
    assert outcome.decision == decision
    assert (outcome.escalation or {}).get("reason_code") == code
    if code:
        assert code in reason_codes()


# ---------------------------------------------------------------------------
# zero-shot
# ---------------------------------------------------------------------------
ID_LINE = re.compile(r"^\[(g_\d{3})\] ", re.MULTILINE)
STUB_META = SimpleNamespace(
    model="stub", cached=True, latency_ms=3, prompt_tokens=100, output_tokens=40, attempts=1
)


def echo_responder(prompt: str, schema: type) -> dict[str, Any]:
    """Echo every id in the prompt except g_003; g_002 escalates."""
    items = []
    for id_ in ID_LINE.findall(prompt):
        if id_ == "g_003":
            continue
        escalate = id_ == "g_002"
        items.append(
            {
                "id": id_,
                "intent": "billing_or_charge" if escalate else "playback_or_app_bug",
                "intent_confidence": 0.9,
                "decision": "escalate" if escalate else "auto_handle",
                "escalation_reason_code": "billing_dispute" if escalate else None,
            }
        )
    return {"items": items}


class StubClient:
    """Minimal LLMClient (§12) driven by a ``responder(prompt, schema)``; stands in for cadence.llm.mock."""

    def __init__(self, responder: Responder) -> None:
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

    def generate_json(
        self, prompt: str, schema: type, *, system: str | None = None, temperature=None, cache=True
    ):
        self.calls.append({"prompt": prompt, "schema": schema.__name__, "system": system})
        return schema.model_validate(self.responder(prompt, schema)), STUB_META


def make_client(responder: Responder) -> Any:
    try:
        from cadence.llm.mock import MockClient

        return MockClient(responder=responder)
    except Exception:
        return StubClient(responder)


def test_zero_shot_batches_and_maps_by_id() -> None:
    client = make_client(echo_responder)
    rows = [golden(i, f"message number {i}", "other") for i in range(1, 26)]
    out = run_zero_shot(rows, client)
    assert out is not None and [field(r, "id") for r in out] == [f"g_{i:03d}" for i in range(1, 26)]

    assert len(client.calls) == 3  # 10 + 10 + 5
    assert client.calls[0]["schema"] == ZeroShotBatch.__name__
    prompt = client.calls[0]["prompt"]
    assert "[g_010] message number 10" in prompt and "[g_011]" not in prompt
    assert "billing_or_charge" in prompt and "billing_dispute" in prompt  # taxonomy + policy present
    assert "evidence" not in prompt.lower()  # no retrieval in the zero-shot prompt
    assert client.calls[0]["system"]

    for r in out:
        assert field(r, "system") == "llm_zero_shot" and field(r, "reply_draft") == ""
        assert field(r, "citations") == [] and field(r, "evidence") == []
        assert field(r, "model") and isinstance(field(r, "cached"), bool)

    assert field(out[0], "intent") == "playback_or_app_bug" and field(out[0], "decision") == "auto_handle"
    assert field(out[0], "intent_confidence") == pytest.approx(0.9) and field(out[0], "escalation") is None
    assert field(out[0], "trace")["llm_decision"] == "auto_handle"
    assert (
        field(out[1], "decision") == "escalate"
        and field(out[1], "escalation")["reason_code"] == "billing_dispute"
    )
    missing = out[2]  # g_003 was dropped by the responder
    assert field(missing, "intent") == "other" and field(missing, "intent_confidence") == 0.0
    assert field(missing, "decision") == "escalate"
    assert field(missing, "escalation") == {"reason_code": "low_confidence", "reason": MISSING_REASON}


def test_zero_shot_skips_without_client_key_or_cache(no_llm_access: None) -> None:
    assert run_zero_shot([golden(1, "hello there")]) is None


def test_zero_shot_leaves_out_cache_miss_batches() -> None:
    class CacheMissError(Exception):
        pass

    class FlakyClient(StubClient):
        def generate_json(self, prompt: str, schema: type, *, system=None, temperature=None, cache=True):
            if "[g_001]" in prompt:
                raise CacheMissError("cache-only mode")
            return super().generate_json(prompt, schema, system=system)

    rows = [golden(i, f"message {i}") for i in range(1, 13)]
    out = run_zero_shot(rows, FlakyClient(echo_responder))
    assert out is not None and [field(r, "id") for r in out] == ["g_011", "g_012"]


def test_zero_shot_reraises_other_errors() -> None:
    class BrokenClient(StubClient):
        def generate_json(self, *args, **kwargs):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        run_zero_shot([golden(1, "x")], BrokenClient(echo_responder))


# ---------------------------------------------------------------------------
# run_baselines
# ---------------------------------------------------------------------------
def test_run_baselines_all_systems(retriever: FakeRetriever) -> None:
    rows = synthetic_rows(n_per_class=2)
    out = run_baselines(rows, retriever, zero_shot_client=make_client(echo_responder))
    assert set(out) == set(BASELINE_SYSTEMS) == {"trivial", "simple", "simple_keyword", "llm_zero_shot"}
    ids = [r["id"] for r in rows]
    for system, responses in out.items():
        assert [field(r, "id") for r in responses] == ids, system
        assert all(field(r, "system") == system for r in responses), system
        for r in responses:
            assert field(r, "intent") in INTENTS
            assert field(r, "decision") in {"auto_handle", "escalate"}
            assert (field(r, "decision") == "escalate") == (field(r, "escalation") is not None)
            assert len(field(r, "reply_draft")) <= 280


def test_run_baselines_rows_are_agent_responses_when_available(retriever: FakeRetriever) -> None:
    pytest.importorskip("cadence.agent.models")
    from cadence.agent.models import AgentResponse

    out = run_baselines(
        [golden(1, "charged twice", "billing_or_charge")], retriever, systems=("trivial", "simple")
    )
    assert all(isinstance(r, AgentResponse) for rows in out.values() for r in rows)


def test_run_baselines_subset_and_skip(retriever: FakeRetriever, no_llm_access: None) -> None:
    rows = [golden(1, "charged twice", "billing_or_charge")]
    out = run_baselines(rows, retriever, systems=("simple_keyword", "llm_zero_shot"))
    assert list(out) == ["simple_keyword"]  # simple computed internally but not returned; zero-shot skipped
    with pytest.raises(ValueError, match="unknown baseline system"):
        run_baselines(rows, retriever, systems=("nope",))


# ---------------------------------------------------------------------------
# Local rules fallback stays in step with cadence.agent.rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text",
    [
        "you charged me twice and i want a refund",
        "my account was hacked, someone changed my email",
        "i will sue you, this is harassment",
        "<url>",
        "help",
        "again? still not working after the update, third time asking",
        "the app keeps crashing since the update",
        "cancelling my premium, switching to apple music",
    ],
)
def test_local_rules_match_agent_rules(text: str) -> None:
    agent_rules = pytest.importorskip("cadence.agent.rules")
    from cadence.baselines.simple import _local_apply_rules

    expected = agent_rules.apply_rules(text)
    local = _local_apply_rules(text)
    assert local.force_escalate == expected.force_escalate
    assert local.reason_code == expected.reason_code
    assert sorted(local.flags) == sorted(expected.flags)
    assert sorted(local.soft_flags) == sorted(expected.soft_flags)
