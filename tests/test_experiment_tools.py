import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_experiment_rejects_thread_and_near_duplicate_leakage():
    validate = script("16_routing_experiment.py").validate_splits
    train = [{"id": "train", "thread_id": "t1", "text": "music stops playing after one song"}]
    dev = [{"id": "dev", "thread_id": "t1", "text": "billing issue", "split": "dev", "gold": {"intent": "billing_or_charge", "should_escalate": True}}]
    with pytest.raises(ValueError, match="overlap"):
        validate(train, dev)
    dev[0].update(thread_id="t2", text="music stops playing after one song!")
    with pytest.raises(ValueError, match="Near duplicate"):
        validate(train, dev)


def test_confidence_bins_count_boundaries_exactly_once():
    reliability = script("16_routing_experiment.py").reliability
    rows = [{"id": str(i), "intent": "x", "intent_confidence": c} for i, c in enumerate([0, .2, .4, .6, .8, 1])]
    truth = {r["id"]: {"gold": {"intent": "x"}} for r in rows}
    assert sum(b["n"] for b in reliability(rows, truth)) == len(rows)


def test_useful_coverage_counts_all_messages_and_separates_clarifications():
    coverage = script("18_review_coverage.py").coverage
    predictions = [{"id": str(i), "system": "agent", "decision": "escalate" if i == 2 else "auto_handle"} for i in range(3)]
    ratings = [{"id": str(i), "system": "agent", "reviewer_id": "a", "reviewer_type": "ai", "verdict": "ship",
                "scores": {"safe": 5, "grounded": 5, "resolves": 5}, "flags": {}, "response_kind": kind}
               for i, kind in enumerate(["clarification", "handoff", "resolution"])]
    result = coverage(predictions, ratings)["agent"]
    assert result["useful_automatic_coverage"] == 1 / 3
    assert result["useful_clarification"] == 1 and result["useful_resolution"] == 0
    with pytest.raises(ValueError, match="denominator"):
        coverage(predictions, ratings[:1])
