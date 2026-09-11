"""Tests for the UI data files (ui/public/data/*.json) and the mock generator (ui/mock/generate_mock_data.py).

The UI renders from these files in static mode, so whatever is there (the real export from
scripts/07_export_ui_data.py, or the mock before results exist) must match the CONTRACT schemas and stay
internally consistent: confusion rows sum to support, F1 follows from the matrix, rates lie in [0, 1],
failure-mode examples point at real golden rows. Statistics the eval module cannot compute are ``null``
(never NaN): ``judge_agreement`` until human ratings exist, ``reason_code_accuracy`` for a system with no
true positives. The generator itself must be deterministic for a fixed SEED.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from typing import Any

import pytest

from cadence.config import JUDGED_SYSTEMS, SYSTEMS, Paths, escalation_config, intent_ids, reason_codes

DATA = Paths.UI_PUBLIC_DATA
GENERATOR = Paths.UI / "mock" / "generate_mock_data.py"
FILES = (
    "eval_summary.json",
    "failure_modes.json",
    "golden_merged.json",
    "decisions.json",
    "health.json",
    "intents.json",
    "escalation.json",
)
DECISIONS = {"auto_handle", "escalate"}
SENTIMENTS = {"positive", "neutral", "frustrated", "angry"}
DIMENSIONS = {"grounded", "resolves", "tone", "safe", "overall"}


def _load(name: str) -> Any:
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def _generator_module():
    spec = importlib.util.spec_from_file_location("generate_mock_data", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _in_unit(x: Any) -> bool:
    """A rate that is either undefined (null) or in [0, 1]."""
    return x is None or 0 <= x <= 1


def _forcing_flags() -> set[str]:
    return {r["flag"] for r in escalation_config()["rules"] if r["force_escalate"]}


@pytest.fixture(scope="module")
def summary() -> dict[str, Any]:
    return _load("eval_summary.json")


@pytest.fixture(scope="module")
def golden() -> list[dict[str, Any]]:
    return _load("golden_merged.json")


def test_all_files_exist_and_parse() -> None:
    for name in FILES:
        assert (DATA / name).exists(), name
        _load(name)


def test_intents_json_mirrors_config() -> None:
    rows = _load("intents.json")
    assert [r["id"] for r in rows] == intent_ids()
    for r in rows:
        assert r["default_decision"] in DECISIONS
        assert r["default_reason_code"] in {None, *reason_codes()}
        assert r["name"] and r["description"] and r["keywords"]


def test_escalation_json_mirrors_config() -> None:
    policy = _load("escalation.json")
    assert [rc["id"] for rc in policy["reason_codes"]] == reason_codes()
    assert 0 < policy["confidence_threshold"] < 1
    assert all(r["reason_code"] in reason_codes() for r in policy["rules"])


def test_golden_covers_every_intent_and_both_decisions(golden: list[dict[str, Any]]) -> None:
    assert len(golden) >= 40
    assert {r["gold"]["intent"] for r in golden} == set(intent_ids())
    assert {r["gold"]["should_escalate"] for r in golden} == {True, False}
    assert {r["split"] for r in golden} == {"dev", "test"}
    ids = [r["id"] for r in golden]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_golden_rows_follow_contract_schema(golden: list[dict[str, Any]]) -> None:
    codes = set(reason_codes())
    forcing = _forcing_flags()
    for r in golden:
        assert set(r["predictions"]) == set(SYSTEMS), r["id"]
        assert set(r["judge"]) <= set(JUDGED_SYSTEMS), r["id"]
        assert set(r["annotations"]) == {"a", "b"}
        assert isinstance(r["adjudicated"], bool)
        # Every disagreement was adjudicated; an adjudicator may also revisit agreed rows, so this is one-way.
        if not (r["agreement"]["intent"] and r["agreement"]["should_escalate"]):
            assert r["adjudicated"], r["id"]
        gold = r["gold"]
        assert gold["intent"] in intent_ids()
        assert (gold["escalation_reason_code"] in codes) == gold["should_escalate"]
        for system, pred in r["predictions"].items():
            assert pred["system"] == system and pred["id"] == r["id"]
            assert pred["intent"] in intent_ids()
            assert pred["decision"] in DECISIONS
            assert (pred["escalation"] is not None) == (pred["decision"] == "escalate")
            if pred["escalation"]:
                assert pred["escalation"]["reason_code"] in codes and pred["escalation"]["reason"]
            assert len(pred["reply_draft"]) <= 280
            assert pred["sentiment"] in SENTIMENTS
        agent = r["predictions"]["agent"]
        # A forcing flag always forces; the trace can also record a force from the threshold / length guards.
        if any(f in forcing for f in agent["rule_flags"]):
            assert agent["trace"]["forced_by_rules"], r["id"]
        if agent["trace"]["forced_by_rules"]:
            assert agent["decision"] == "escalate", r["id"]
        assert set(agent["citations"]) == {e["thread_id"] for e in agent["evidence"] if e["cited"]}
        for system, judge in r["judge"].items():
            assert set(judge["scores"]) == DIMENSIONS
            assert all(1 <= v <= 5 for v in judge["scores"].values())
            assert judge["verdict"] in {"ship", "edit", "reject"}
            # The judge may still ask for an edit on a clean 4; but a ship verdict must satisfy the rubric.
            if judge["verdict"] == "ship":
                assert judge["scores"]["overall"] >= 4 and not any(judge["flags"].values()), (r["id"], system)


def test_trivial_baseline_matches_contract(golden: list[dict[str, Any]]) -> None:
    majority = max(intent_ids(), key=lambda i: sum(r["gold"]["intent"] == i for r in golden))
    for r in golden:
        t = r["predictions"]["trivial"]
        assert t["intent"] == majority
        assert t["decision"] == "escalate" and t["escalation"]["reason_code"] == "low_confidence"


def _f1_from_matrix(matrix: list[list[int]], i: int) -> float:
    tp = matrix[i][i]
    fp = sum(row[i] for row in matrix) - tp
    fn = sum(matrix[i]) - tp
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return 2 * p * r / (p + r) if p + r else 0.0


def test_intent_metrics_are_consistent(summary: dict[str, Any]) -> None:
    block = summary["intent"]
    n_test = summary["meta"]["n_test"]
    assert block["labels"] == intent_ids()
    assert sum(block["support"].values()) == n_test
    for name, system in block["systems"].items():
        matrix = system["confusion"]["matrix"]
        assert system["confusion"]["labels"] == block["labels"], name
        for i, label in enumerate(block["labels"]):
            assert sum(matrix[i]) == block["support"][label], (name, label)
            assert system["per_class"][label]["support"] == block["support"][label]
            assert abs(system["per_class"][label]["f1"] - _f1_from_matrix(matrix, i)) < 1e-3, (name, label)
        macro = sum(_f1_from_matrix(matrix, i) for i in range(len(matrix))) / len(matrix)
        assert abs(system["macro_f1"] - macro) < 1e-3, name
        assert abs(system["accuracy"] - sum(matrix[i][i] for i in range(len(matrix))) / n_test) < 1e-3
        lo, hi = system["ci95"]["macro_f1"]
        assert 0 <= lo <= system["macro_f1"] <= hi <= 1


def test_escalation_metrics_are_consistent(summary: dict[str, Any]) -> None:
    n_test = summary["meta"]["n_test"]
    n_pos: int | None = None
    for name, s in summary["escalation"]["systems"].items():
        c = s["confusion"]
        pos = c["tp"] + c["fn"]
        n_pos = n_pos or pos
        assert pos == n_pos, name
        assert c["tp"] + c["fp"] + c["fn"] + c["tn"] == n_test
        assert s["missed_escalations"] == c["fn"] and s["unnecessary_escalations"] == c["fp"]
        recall = c["tp"] / pos
        precision = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
        assert abs(s["recall"] - recall) < 1e-3 and abs(s["precision"] - precision) < 1e-3, name
        assert abs(s["auto_handle_rate"] - (c["fn"] + c["tn"]) / n_test) < 1e-3
        for k in ("recall", "auto_handle_rate", "accuracy"):
            assert 0 <= s[k] <= 1, (name, k)
        for k in ("precision", "f1", "reason_code_accuracy"):
            assert _in_unit(s[k]), (name, k)
        if c["tp"] == 0:
            assert s["reason_code_accuracy"] is None, (name, "reason-code accuracy is undefined without true positives")
    sweep = summary["escalation"]["threshold_sweep"]
    thresholds = [p["threshold"] for p in sweep]
    assert thresholds == sorted(thresholds)
    assert any(abs(p["threshold"] - summary["meta"]["threshold"]) < 1e-9 for p in sweep)
    assert all(a["recall"] <= b["recall"] + 1e-9 for a, b in zip(sweep, sweep[1:], strict=False))
    assert all(a["auto_handle_rate"] >= b["auto_handle_rate"] - 1e-9 for a, b in zip(sweep, sweep[1:], strict=False))


def test_headline_matches_blocks(summary: dict[str, Any]) -> None:
    h = summary["headline"]
    assert h["intent_macro_f1"] == summary["intent"]["systems"]["agent"]["macro_f1"]
    assert h["escalation_recall"] == summary["escalation"]["systems"]["agent"]["recall"]
    assert h["auto_handle_rate"] == summary["escalation"]["systems"]["agent"]["auto_handle_rate"]
    reply = summary["reply_quality"]
    if reply is None:
        assert h["judge_overall_mean"] is None and h["judge_overall_mean_nn"] is None
    else:
        # The nearest-neighbour reply is the `simple` system (CONTRACT §15.1); older exports spelled it `nn_reply`.
        nn = reply["systems"].get("nn_reply") or reply["systems"]["simple"]
        assert h["judge_overall_mean"] == reply["systems"]["agent"]["mean"]["overall"]
        assert h["judge_overall_mean_nn"] == nn["mean"]["overall"]
    for interval in h["ci95"].values():
        if interval is not None:
            lo, hi = interval
            assert lo <= hi
    assert summary["meta"]["n_dev"] + summary["meta"]["n_test"] == summary["meta"]["n_golden"]
    if "caveats" in summary["meta"]:
        caveats = summary["meta"]["caveats"]
        assert 1 <= len(caveats) <= 8 and all(isinstance(c, str) and c.strip() for c in caveats)
    if "dataset" in summary["meta"]:
        d = summary["meta"]["dataset"]
        assert d["n_openers"] > 0 and d["n_brand_tweets"] > 0 and d["date_from"] <= d["date_to"]
        assert all(_in_unit(d[k]) for k in ("share_english", "share_with_link", "share_single_reply"))


def test_reply_quality_and_agreement(summary: dict[str, Any]) -> None:
    n = summary["meta"]["n_test"]
    reply = summary["reply_quality"]
    if reply is None:
        pytest.skip("judge has not run; reply_quality is null")
    for name, s in reply["systems"].items():
        assert sum(s["dist_overall"]) == n, name
        mean = sum((i + 1) * c for i, c in enumerate(s["dist_overall"])) / n
        assert abs(s["mean"]["overall"] - mean) < 1e-3, name
        assert _in_unit(s["ship_rate"]) and all(_in_unit(v) for v in s["flag_rates"].values())
    if reply["pairwise"] is not None:
        assert all(_in_unit(v) for v in reply["pairwise"].values())
    ja = summary["judge_agreement"]
    if ja is None:
        # No human ratings yet: the eval module says so in meta.notes and the UI shows an empty state.
        assert any("judge_agreement" in note for note in summary["meta"].get("notes", []))
        return
    assert ja["n"] == len(ja["pairs"]) >= 1
    if ja["weighted_kappa_overall"] is not None:
        assert -1 <= ja["weighted_kappa_overall"] <= 1
    assert _in_unit(ja["exact_agreement"]) and _in_unit(ja["within_one"])
    assert all(1 <= p["human"] <= 5 and 1 <= p["judge"] <= 5 for p in ja["pairs"])


def _decision_at_threshold(pred: dict[str, Any], threshold: float) -> str:
    """Mirror of cadence.eval.metrics.decision_at_threshold: the evaluated policy's decision for a recorded run."""
    trace = pred.get("trace") or {}
    if "llm_decision" not in trace and "forced_by_rules" not in trace:
        return pred["decision"]
    if trace.get("forced_by_rules") or trace.get("llm_decision") == "escalate":
        return "escalate"
    conf = pred.get("intent_confidence")
    return "escalate" if conf is not None and conf < threshold else "auto_handle"


def test_failure_modes_reference_real_golden_rows(golden: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    by_id = {r["id"]: r for r in golden}
    threshold = summary["meta"]["threshold"]
    modes = _load("failure_modes.json")
    assert len(modes) == 5
    for fm in modes:
        assert fm["count"] > 0 and 0 < fm["share"] < 1 and fm["hypothesis"] and fm["proposed_fix"]
        assert 2 <= len(fm["examples"]) <= 3
        for ex in fm["examples"]:
            row = by_id[ex["golden_id"]]
            agent = row["predictions"]["agent"]
            # The eval module may shorten a long tweet to a preview ending in an ellipsis.
            preview = ex["text"].rstrip("…").rstrip()
            assert ex["text"] == row["text"] or (ex["text"].endswith("…") and row["text"].startswith(preview)), ex["golden_id"]
            assert ex["gold_intent"] == row["gold"]["intent"]
            assert ex["pred_intent"] == agent["intent"]
            # Failure modes are mined at the evaluated threshold, so the decision is the re-derived one.
            assert ex["pred_decision"] == _decision_at_threshold(agent, threshold), (fm["id"], ex["golden_id"])
            assert ex["gold_decision"] == ("escalate" if row["gold"]["should_escalate"] else "auto_handle")
            assert ex["reply_draft"] == agent["reply_draft"] and ex["why"]


def test_decisions_and_health() -> None:
    decisions = _load("decisions.json")
    assert len(decisions) >= 10
    assert [d["n"] for d in decisions] == list(range(1, len(decisions) + 1))
    assert all(d["title"] and d["decision"] and d["why"] for d in decisions)
    health = _load("health.json")
    # CONTRACT §10 keys must be present; the export adds static-mode blocks (models, counts, generated_at).
    assert {"status", "has_api_key", "cache_only", "agent_model", "judge_model", "cache_entries", "index_size", "n_golden"} <= set(health)
    if health.get("static"):
        assert health["has_api_key"] is False and health["cache_only"] is True


def test_generator_is_deterministic() -> None:
    module = _generator_module()
    first = module.build_all()
    second = module.build_all()
    assert set(first) == set(FILES)
    for name in FILES:
        assert json.dumps(first[name], sort_keys=True) == json.dumps(second[name], sort_keys=True), name
    assert len(first["golden_merged.json"]) >= 40
    assert {r["gold"]["intent"] for r in first["golden_merged.json"]} == set(intent_ids())
