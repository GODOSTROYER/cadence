"""Tests for the FastAPI server, the UI export script and the typer CLI (no network, no API key)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cadence import cli
from cadence.api import rating_queue, state
from cadence.api.decisions import parse_decision_log, parse_decision_log_text
from cadence.api.merge import merge_golden
from cadence.api.server import app
from cadence.config import JUDGED_SYSTEMS, Paths
from cadence.utils.io import read_jsonl, write_json, write_jsonl

INTENTS = ("playback_or_app_bug", "billing_or_charge", "login_or_password", "other")
N_TEST = 12
N_DEV = 2

_PATH_ATTRS = {
    "RESULTS": "results",
    "STATS": "data/processed/stats.json",
    "THREADS": "data/processed/spotify_threads.jsonl.gz",
    "GOLDEN": "data/golden/golden_set.jsonl",
    "HUMAN_RATINGS": "data/golden/human_ratings.jsonl",
    "LLM_CACHE": "cache/llm_cache.sqlite",
    "BM25_INDEX": "cache/bm25_index.pkl",
    "PREDICTIONS": "results/predictions.jsonl",
    "JUDGE_SCORES": "results/judge_scores.jsonl",
    "EVAL_SUMMARY": "results/eval_summary.json",
    "FAILURE_MODES": "results/failure_modes.json",
    "UI_DIST": "ui/dist",
    "UI_PUBLIC_DATA": "ui/public/data",
    "DECISION_LOG": "DECISION_LOG.md",
}


# ---------------------------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------------------------
@pytest.fixture
def paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every on-disk artifact at an empty temp tree, reset lazy state and strip secrets."""
    for attr, rel in _PATH_ATTRS.items():
        monkeypatch.setattr(Paths, attr, tmp_path / rel)
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CADENCE_CACHE_ONLY"):
        monkeypatch.delenv(var, raising=False)
    state.STATE.reset()
    yield tmp_path
    state.STATE.reset()


@pytest.fixture
def client(paths: Path) -> TestClient:
    return TestClient(app)


def _golden_rows() -> list[dict[str, Any]]:
    rows = []
    for i in range(N_TEST + N_DEV):
        example_id = f"g_{i + 1:03d}"
        rows.append(
            {
                "id": example_id,
                "thread_id": f"t_{2200000 + i}",
                "split": "dev" if i >= N_TEST else "test",
                "text": f"customer message {i} about {INTENTS[i % len(INTENTS)]} 🎧",
                "text_raw": f"@SpotifyCares customer message {i}",
                "created_at": "2017-10-31T22:10:47Z",
                "historical_brand_reply": f"historical reply {i}",
                "historical_thread": [],
                "gold": {
                    "intent": INTENTS[i % len(INTENTS)],
                    "secondary_intent": None,
                    "should_escalate": i % 2 == 0,
                    "escalation_reason_code": "billing_dispute" if i % 2 == 0 else None,
                    "sentiment": "neutral",
                    "media_only": False,
                    "notes": "",
                },
                "annotations": {},
                "agreement": {"intent": True, "should_escalate": True},
                "adjudicated": False,
                "sampling_bucket": "kw:test",
            }
        )
    return rows


def _prediction(example_id: str, system: str) -> dict[str, Any]:
    return {
        "id": example_id,
        "system": system,
        "input_text": "x",
        "intent": "other",
        "intent_confidence": 0.5,
        "sentiment": "neutral",
        "reply_draft": f"{system} reply for {example_id}",
        "citations": [],
        "grounding_notes": "",
        "decision": "auto_handle",
        "escalation": None,
        "rule_flags": [],
        "evidence": [{"thread_id": "t_1", "score": 1.0, "customer_text": "c", "brand_reply": "b", "cited": True}],
        "model": "fake",
        "latency_ms": 1,
        "cached": True,
        "trace": {},
    }


def _judge(example_id: str, system: str) -> dict[str, Any]:
    return {
        "id": example_id,
        "system": system,
        "rater": "fake-judge",
        "scores": {"grounded": 4, "resolves": 4, "tone": 5, "safe": 5, "overall": 4},
        "flags": {"hallucinated_link_or_policy": False, "asks_sensitive_info": False, "wrong_issue": False},
        "verdict": "ship",
        "rationale": "fine",
        "rated_at": "2026-01-01T00:00:00Z",
    }


@pytest.fixture
def golden(paths: Path) -> list[dict[str, Any]]:
    rows = _golden_rows()
    write_jsonl(Paths.GOLDEN, rows)
    return rows


@pytest.fixture
def predictions(golden: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_prediction(row["id"], system) for row in golden for system in JUDGED_SYSTEMS]
    write_jsonl(Paths.PREDICTIONS, rows)
    return rows


@pytest.fixture
def judge_scores(golden: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_judge(row["id"], system) for row in golden for system in ("agent", "simple")]
    write_jsonl(Paths.JUDGE_SCORES, rows)
    return rows


DECISION_LOG = """# Decision log

Intro paragraph that is not a decision.

## 1. Use BM25 rather than embeddings
**Decision:** Retrieval uses BM25 over cleaned openers.
**Why:** It is deterministic, rebuilds in seconds
and needs no API key.

## 2. Judge model differs from agent model
**Decision:** gemini-2.5-pro judges, gemini-2.5-flash acts.
**Why:** Reduces self-preference bias.
"""


# ---------------------------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------------------------
def test_health_with_nothing_on_disk(client: TestClient) -> None:
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["has_api_key"] is False
    assert body["cache_only"] is False
    assert body["agent_model"] and body["judge_model"]
    assert body["cache_entries"] == 0
    assert body["index_size"] == 0
    assert body["n_golden"] == 0


def test_health_counts_cache_entries_and_golden(client: TestClient, golden: list[dict[str, Any]]) -> None:
    Paths.LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(Paths.LLM_CACHE))
    conn.execute("CREATE TABLE calls(key TEXT PRIMARY KEY, model TEXT)")
    conn.executemany("INSERT INTO calls VALUES (?, ?)", [("k1", "m"), ("k2", "m"), ("k3", "m")])
    conn.commit()
    conn.close()
    body = client.get("/api/health").json()
    assert body["cache_entries"] == 3
    assert body["n_golden"] == len(golden)


# ---------------------------------------------------------------------------------------------
# /api/results, /api/failures
# ---------------------------------------------------------------------------------------------
def test_results_503_when_missing_then_200(client: TestClient) -> None:
    resp = client.get("/api/results")
    assert resp.status_code == 503
    assert "run: make eval" in resp.json()["detail"]

    write_json(Paths.EVAL_SUMMARY, {"meta": {"n_golden": 14}, "headline": {"intent_macro_f1": 0.8}})
    resp = client.get("/api/results")
    assert resp.status_code == 200
    assert resp.json()["headline"]["intent_macro_f1"] == 0.8


def test_failures_503_then_200(client: TestClient) -> None:
    assert client.get("/api/failures").status_code == 503
    write_json(Paths.FAILURE_MODES, [{"id": "fm1", "title": "t", "count": 1, "share": 0.1, "examples": []}])
    assert client.get("/api/failures").json()[0]["id"] == "fm1"


# ---------------------------------------------------------------------------------------------
# /api/golden
# ---------------------------------------------------------------------------------------------
def test_golden_503_when_missing(client: TestClient) -> None:
    resp = client.get("/api/golden")
    assert resp.status_code == 503
    assert "golden_set.jsonl" in resp.json()["detail"]


def test_golden_merge_shape(
    client: TestClient, golden: list[dict[str, Any]], predictions: list[dict[str, Any]], judge_scores: list[dict[str, Any]]
) -> None:
    rows = client.get("/api/golden").json()
    assert [r["id"] for r in rows] == [g["id"] for g in golden]
    first = rows[0]
    assert set(first["predictions"]) == set(JUDGED_SYSTEMS)
    assert first["predictions"]["agent"]["reply_draft"] == "agent reply for g_001"
    assert set(first["judge"]) == {"agent", "simple"}
    assert first["judge"]["simple"]["scores"]["overall"] == 4
    assert first["gold"]["intent"] == golden[0]["gold"]["intent"]

    one = client.get("/api/golden/g_002").json()
    assert one["id"] == "g_002" and one["predictions"]["trivial"]["system"] == "trivial"
    assert client.get("/api/golden/g_999").status_code == 404


def test_golden_without_predictions_has_empty_maps(client: TestClient, golden: list[dict[str, Any]]) -> None:
    rows = client.get("/api/golden").json()
    assert rows[0]["predictions"] == {} and rows[0]["judge"] == {}


def test_merge_golden_ignores_rows_without_keys() -> None:
    merged = merge_golden([{"id": "g_001"}], [{"id": "g_001"}, _prediction("g_001", "agent")], [{"system": "agent"}])
    assert list(merged[0]["predictions"]) == ["agent"] and merged[0]["judge"] == {}


# ---------------------------------------------------------------------------------------------
# /api/decisions
# ---------------------------------------------------------------------------------------------
def test_decisions_parser() -> None:
    parsed = parse_decision_log_text(DECISION_LOG)
    assert [d["n"] for d in parsed] == [1, 2]
    assert parsed[0]["title"] == "Use BM25 rather than embeddings"
    assert parsed[0]["decision"] == "Retrieval uses BM25 over cleaned openers."
    assert parsed[0]["why"] == "It is deterministic, rebuilds in seconds and needs no API key."
    assert parsed[1]["why"] == "Reduces self-preference bias."


def test_decisions_endpoint(client: TestClient) -> None:
    assert client.get("/api/decisions").json() == []
    assert parse_decision_log(Paths.DECISION_LOG) == []
    Paths.DECISION_LOG.write_text(DECISION_LOG, encoding="utf-8")
    body = client.get("/api/decisions").json()
    assert len(body) == 2 and body[1]["title"] == "Judge model differs from agent model"


# ---------------------------------------------------------------------------------------------
# /api/rating-queue and /api/ratings
# ---------------------------------------------------------------------------------------------
def test_rating_queue_requires_predictions(client: TestClient, golden: list[dict[str, Any]]) -> None:
    resp = client.get("/api/rating-queue")
    assert resp.status_code == 503
    assert "run: make run" in resp.json()["detail"]


def test_rating_queue_is_blind_deterministic_and_test_only(
    client: TestClient, golden: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> None:
    queue = client.get("/api/rating-queue").json()
    assert queue == client.get("/api/rating-queue").json()
    assert len(queue) == N_TEST  # fewer test examples than 60 -> every test example, each once
    ids = [item["id"] for item in queue]
    assert len(set(ids)) == len(ids)
    dev_ids = {g["id"] for g in golden if g["split"] == "dev"}
    assert not dev_ids & set(ids)
    for item in queue:
        assert set(item) == {"id", "system_alias", "text", "reply_draft", "evidence", "historical_brand_reply"}
        assert item["system_alias"] in rating_queue.ALIASES
        for system in JUDGED_SYSTEMS:
            assert system not in json.dumps({k: v for k, v in item.items() if k != "reply_draft"})
        hidden = rating_queue.resolve_alias(item["id"], item["system_alias"])
        assert item["reply_draft"] == f"{hidden} reply for {item['id']}"
    hidden_systems = [rating_queue.resolve_alias(i["id"], i["system_alias"]) for i in queue]
    assert {hidden_systems.count(s) for s in JUDGED_SYSTEMS} == {N_TEST // len(JUDGED_SYSTEMS)}


def test_rating_plan_is_stratified_and_20_per_system() -> None:
    rows = []
    for i in range(300):
        rows.append({"id": f"g_{i:03d}", "split": "test", "gold": {"intent": INTENTS[i % 3]}})
    pairs = rating_queue.plan_pairs(rows)
    assert len(pairs) == rating_queue.PER_SYSTEM * len(JUDGED_SYSTEMS)
    assert len({eid for eid, _ in pairs}) == len(pairs)
    for system in JUDGED_SYSTEMS:
        assert sum(1 for _, s in pairs if s == system) == rating_queue.PER_SYSTEM
    by_id = {r["id"]: r for r in rows}
    intents = [by_id[eid]["gold"]["intent"] for eid, _ in pairs]
    assert all(intents.count(label) == 20 for label in INTENTS[:3])
    assert pairs == rating_queue.plan_pairs(list(reversed(rows)))


def test_alias_map_permutes_systems_per_example() -> None:
    mapping = rating_queue.alias_map("g_001")
    assert sorted(mapping.values()) == sorted(JUDGED_SYSTEMS)
    assert mapping == rating_queue.alias_map("g_001")
    assert any(rating_queue.alias_map(f"g_{i:03d}") != mapping for i in range(2, 30))
    with pytest.raises(KeyError):
        rating_queue.resolve_alias("g_001", "Z")


def test_post_rating_resolves_alias_and_appends(
    client: TestClient, golden: list[dict[str, Any]], predictions: list[dict[str, Any]]
) -> None:
    queue = client.get("/api/rating-queue").json()
    item = queue[0]
    body = {
        "id": item["id"],
        "system_alias": item["system_alias"],
        "scores": {"grounded": 4, "resolves": 3, "tone": 5, "safe": 5, "overall": 4},
        "flags": {"hallucinated_link_or_policy": False, "asks_sensitive_info": False, "wrong_issue": False},
        "verdict": "ship",
        "rationale": "good",
        "rater": "sneaky-judge",
    }
    resp = client.post("/api/ratings", json=body)
    assert resp.status_code == 201, resp.text
    stored = resp.json()
    assert stored["system"] == rating_queue.resolve_alias(item["id"], item["system_alias"])
    assert stored["rater"] == "human"
    assert stored["rated_at"] and "system_alias" not in stored
    assert read_jsonl(Paths.HUMAN_RATINGS) == [stored]
    assert client.get("/api/ratings").json() == [stored]

    remaining = client.get("/api/rating-queue").json()
    assert len(remaining) == len(queue) - 1
    assert (item["id"], item["system_alias"]) not in {(i["id"], i["system_alias"]) for i in remaining}

    assert client.post("/api/ratings", json=body).status_code == 409
    assert client.post("/api/ratings", json={**body, "system_alias": "Q"}).status_code == 400
    assert client.post("/api/ratings", json={**body, "id": "g_999"}).status_code == 404
    assert client.post("/api/ratings", json={**body, "scores": {"overall": 9}}).status_code == 422
    assert client.post("/api/ratings", json={**body, "verdict": "maybe"}).status_code == 422


def test_get_ratings_empty_when_missing(client: TestClient) -> None:
    assert client.get("/api/ratings").json() == []


# ---------------------------------------------------------------------------------------------
# /api/agent/handle
# ---------------------------------------------------------------------------------------------
class CacheMissError(Exception):
    """Stand-in for cadence.llm's exception (matched by class name in the server)."""


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def handle(self, text: str, **_: Any) -> dict[str, Any]:
        self.calls.append((text, os.environ.get("CADENCE_CACHE_ONLY")))
        if "miss" in text:
            raise CacheMissError("not cached")
        return {**_prediction("live", "agent"), "input_text": text}


@pytest.fixture
def fake_agent(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeAgent]:
    agents: dict[str, FakeAgent] = {}

    def build(cache_only_mode: bool) -> FakeAgent:
        return agents.setdefault("replay" if cache_only_mode else "live", FakeAgent())

    monkeypatch.setattr(state, "build_agent", build)
    return agents


def test_agent_handle_cache_only_sets_env_for_the_call(client: TestClient, fake_agent: dict[str, FakeAgent]) -> None:
    resp = client.post("/api/agent/handle", json={"text": "my app crashes", "mode": "cache_only"})
    assert resp.status_code == 200
    assert resp.json()["input_text"] == "my app crashes"
    assert fake_agent["replay"].calls == [("my app crashes", "1")]
    assert "CADENCE_CACHE_ONLY" not in os.environ


def test_agent_handle_live_without_key_falls_back_to_replay(client: TestClient, fake_agent: dict[str, FakeAgent]) -> None:
    assert client.post("/api/agent/handle", json={"text": "hello"}).status_code == 200
    assert "live" not in fake_agent and fake_agent["replay"].calls[0][1] == "1"


def test_agent_handle_live_with_key_uses_live_agent(
    client: TestClient, fake_agent: dict[str, FakeAgent], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "not-a-real-key")
    assert client.post("/api/agent/handle", json={"text": "hello", "mode": "live"}).status_code == 200
    assert fake_agent["live"].calls == [("hello", None)]


def test_agent_handle_cache_miss_is_503(client: TestClient, fake_agent: dict[str, FakeAgent]) -> None:
    resp = client.post("/api/agent/handle", json={"text": "a cache miss", "mode": "cache_only"})
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert "API key" in detail and "replay cache" in detail


def test_agent_handle_validates_text(client: TestClient, fake_agent: dict[str, FakeAgent]) -> None:
    assert client.post("/api/agent/handle", json={"text": ""}).status_code == 422
    assert client.post("/api/agent/handle", json={"text": "   "}).status_code == 422
    assert client.post("/api/agent/handle", json={"text": "x" * 1001}).status_code == 422
    assert client.post("/api/agent/handle", json={"text": "ok", "mode": "turbo"}).status_code == 422


def test_agent_handle_503_when_index_missing(client: TestClient) -> None:
    resp = client.post("/api/agent/handle", json={"text": "hello", "mode": "cache_only"})
    assert resp.status_code == 503
    assert "run: make index" in resp.json()["detail"]


# ---------------------------------------------------------------------------------------------
# /api/threads/{thread_id}
# ---------------------------------------------------------------------------------------------
def test_threads_from_processed_file(client: TestClient) -> None:
    assert client.get("/api/threads/t_1").status_code == 503
    Paths.THREADS.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(Paths.THREADS, "wt", encoding="utf-8") as f:
        f.write(json.dumps({"thread_id": "t_1", "customer_text": "hi 🎧"}) + "\n")
    assert client.get("/api/threads/t_1").json()["customer_text"] == "hi 🎧"
    assert client.get("/api/threads/t_2").status_code == 404


# ---------------------------------------------------------------------------------------------
# Static SPA fallback
# ---------------------------------------------------------------------------------------------
def test_static_spa_fallback(client: TestClient) -> None:
    assert client.get("/").status_code == 404
    assert "make ui" in client.get("/golden").json()["detail"]

    dist = Paths.UI_DIST
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Cadence</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('cadence')", encoding="utf-8")

    assert "Cadence" in client.get("/").text
    assert "Cadence" in client.get("/golden/g_001").text
    assert client.get("/assets/app.js").text == "console.log('cadence')"
    assert "Cadence" in client.get("/assets/missing.js").text
    assert client.get("/api/does-not-exist").status_code == 404
    assert client.get("/api/health").status_code == 200


# ---------------------------------------------------------------------------------------------
# scripts/07_export_ui_data.py
# ---------------------------------------------------------------------------------------------
def _load_export_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "07_export_ui_data.py"
    spec = importlib.util.spec_from_file_location("export_ui_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_skips_missing_sources_and_writes_health(paths: Path) -> None:
    out = paths / "out"
    assert _load_export_script().main(["--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["health.json"]
    health = json.loads((out / "health.json").read_text(encoding="utf-8"))
    assert health["static"] is True and health["has_api_key"] is False
    assert health["models"]["agent"] and health["counts"]["n_golden"] == 0


def test_export_matches_api_golden(
    client: TestClient, golden: list[dict[str, Any]], predictions: list[dict[str, Any]], judge_scores: list[dict[str, Any]]
) -> None:
    write_json(Paths.EVAL_SUMMARY, {"meta": {"n_golden": len(golden)}})
    write_json(Paths.FAILURE_MODES, [])
    Paths.DECISION_LOG.write_text(DECISION_LOG, encoding="utf-8")
    out = Paths.RESULTS / "ui"
    assert _load_export_script().main(["--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "decisions.json",
        "eval_summary.json",
        "failure_modes.json",
        "golden_merged.json",
        "health.json",
    ]
    merged = json.loads((out / "golden_merged.json").read_text(encoding="utf-8"))
    assert merged == client.get("/api/golden").json()
    assert len(json.loads((out / "decisions.json").read_text(encoding="utf-8"))) == 2
    health = json.loads((out / "health.json").read_text(encoding="utf-8"))
    assert health["counts"]["n_predictions"] == len(predictions)


# ---------------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------------
def test_cli_runs_script_with_passthrough_args(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    marker = tmp_path / "argv.json"
    (scripts / "04_run_agent.py").write_text(
        "import json, sys\n"
        "def main(argv=None):\n"
        f"    open({str(marker)!r}, 'w', encoding='utf-8').write(json.dumps(list(argv)))\n"
        "    return 0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Paths, "ROOT", tmp_path)
    result = CliRunner().invoke(cli.app, ["run", "--limit", "5", "--systems", "agent"])
    assert result.exit_code == 0, result.output
    assert json.loads(marker.read_text(encoding="utf-8")) == ["--limit", "5", "--systems", "agent"]


def test_cli_missing_script_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Paths, "ROOT", tmp_path)
    result = CliRunner().invoke(cli.app, ["judge"])
    assert result.exit_code == 2
    assert "script not found" in result.output


def test_cli_reproduce_sets_cache_only_and_runs_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    log = tmp_path / "steps.txt"
    for step in cli.REPRODUCE_STEPS:
        (scripts / cli.SCRIPTS[step]).write_text(
            "import os\n"
            "def main(argv=None):\n"
            f"    open({str(log)!r}, 'a', encoding='utf-8').write(__name__.split('.')[-1] + ':' + os.environ['CADENCE_CACHE_ONLY'] + '\\n')\n",
            encoding="utf-8",
        )
    monkeypatch.setattr(Paths, "ROOT", tmp_path)
    monkeypatch.delenv("CADENCE_CACHE_ONLY", raising=False)
    result = CliRunner().invoke(cli.app, ["reproduce"])
    assert result.exit_code == 0, result.output
    lines = log.read_text(encoding="utf-8").splitlines()
    assert lines == [f"{Path(cli.SCRIPTS[s]).stem}:1" for s in cli.REPRODUCE_STEPS]
    assert set(cli.SCRIPTS) >= set(cli.ALL_STEPS)
