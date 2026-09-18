"""Integrity and metric-boundary checks for the mixed-run development analysis."""
import importlib.util
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence.eval.verified import FLAGS, RUBRIC
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / "analysis_tools/compare_verified_development.py"
    spec = importlib.util.spec_from_file_location("verified_development_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prepared(tmp_path, monkeypatch, helper):
    """Small synthetic sources; production source verification is separately tested."""
    source_path = tmp_path / "original.json"
    write_json(source_path, {"sealed": True})
    context = tmp_path / "intents.yaml"
    context.write_text("intents:\n  - id: playback_or_app_bug\n", encoding="utf-8")
    labels = [{"id": str(i), "text": f"Music stopped {i}", "label_source": "ai", "gold": {
        "intent": "playback_or_app_bug", "should_escalate": i == 1, "escalation_reason_code": "security"}}
        for i in range(2)]
    rows = [{"id": str(i), "system": system, "input_text": f"Music stopped {i}",
             "intent": "playback_or_app_bug", "reply_draft": f"Response {system} {i}", "evidence": [],
             "outcome": "success", "decision": "auto_handle"}
            for i in range(2) for system in helper.SYSTEMS]
    rows[-1]["outcome"] = "failed"
    rows[-1]["decision"] = "escalate"
    source = {"labels": labels, "predictions": rows, "rubric": deepcopy(RUBRIC),
              "inputs": {"source": helper.binding(source_path)},
              "context": {"config/intents.yaml": context}, "source_as_of": "2026-09-18",
              "runtime": {"verified_new_run": {"tokens_known": 12, "calls_with_unknown_usage": 1},
                          "archived_original_runs": {"agent": {"prompt_tokens": 1}}, "controlled_comparison": False},
              "historical_v0": {"note": "Original historical results stay separate"}}
    monkeypatch.setattr(helper, "load_sources", lambda *args: source)
    monkeypatch.setattr(helper, "evaluator_bindings", lambda: {})
    out = tmp_path / "comparison"
    helper.prepare(out, tmp_path, tmp_path, tmp_path)
    return out, source_path, source


def ratings(packet):
    return [{**{key: row[key] for key in ("id", "alias", "run_id", "reply_hash", "rubric_version")},
             "reviewer_type": "ai", "reviewer_id": "test independent AI", "rated_at": "2026-09-18T12:00:00Z",
             "scores": {dimension: 5 for dimension in RUBRIC["dimensions"]}, "flags": dict.fromkeys(FLAGS, False),
             "verdict": "ship", "response_kind": "resolution", "severity": "none", "rationale": "Test fixture"}
            for row in packet]


def test_exact_blinded_context_and_failed_replies_are_preserved(helper, prepared):
    out, _, source = prepared
    lock, mapping = helper.verify_prepared(out)
    packet = read_jsonl(out / "blind_packet.jsonl")
    assert lock["n"] == 2 and lock["n_replies"] == 8
    assert read_jsonl(out / "predictions.jsonl") == source["predictions"]
    assert all("system" not in row and "decision" not in row and "gold" not in row for row in packet)
    assert {(row["id"], row["alias"]) for row in packet} == {(row["id"], row["alias"]) for row in mapping}
    assert len({row["system"] for row in mapping}) == 4


@pytest.mark.parametrize("name", ["blind_packet.jsonl", "labels.jsonl", "rubric.json", "context/config/intents.yaml"])
def test_prepared_context_tampering_is_rejected(helper, prepared, name):
    out, _, _ = prepared
    with (out / name).open("a", encoding="utf-8") as stream:
        stream.write("changed")
    with pytest.raises(ValueError, match="Changed prepared"):
        helper.verify_prepared(out)


def test_changed_original_source_is_rejected(helper, prepared):
    out, path, _ = prepared
    write_json(path, {"sealed": False})
    with pytest.raises(ValueError, match="Changed comparison input"):
        helper.verify_prepared(out)


def test_text_line_ending_normalization_preserves_portable_hashes(helper, prepared):
    out, path, _ = prepared
    path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    for item in out.rglob("*"):
        if item.is_file():
            item.write_bytes(item.read_bytes().replace(b"\r\n", b"\n"))
    helper.verify_prepared(out)


@pytest.mark.parametrize("change", ["human", "old_rubric", "old_flags", "missing", "duplicate", "wrong_hash"])
def test_requires_new_complete_ai_ratings_under_exact_rubric(helper, prepared, change):
    out, _, _ = prepared
    review = ratings(read_jsonl(out / "blind_packet.jsonl"))
    if change == "human":
        review[0]["reviewer_type"] = "human"
    elif change == "old_rubric":
        review[0]["rubric_version"] = "old-review-v1"
    elif change == "old_flags":
        review[0]["flags"].pop("wrong_handoff")
    elif change == "missing":
        review.pop()
    elif change == "duplicate":
        review.append(review[0])
    else:
        review[0]["reply_hash"] = "0" * 64
    submission = out.parent / "submission.jsonl"
    write_jsonl(submission, review)
    with pytest.raises(ValueError):
        helper.import_ratings(out, [submission])
    assert not (out / "AI_REVIEW.json").exists()


def test_summary_keeps_failed_routes_denominators_and_mixed_runtime_separate(helper, prepared):
    out, _, source = prepared
    review = ratings(read_jsonl(out / "blind_packet.jsonl"))
    paths = [out.parent / "part1.jsonl", out.parent / "part2.jsonl"]
    write_jsonl(paths[0], review[:4])
    write_jsonl(paths[1], review[4:])
    helper.import_ratings(out, paths)
    result = helper.summarize(out)
    verified = result["metrics"]["verified"]["counts"]
    assert verified["n"] == 2 and verified["failed"] == 1 and verified["missed_escalations"] == 1
    assert verified["policy_compliant_useful_automatic"] == 1
    assert result["runtime"] == source["runtime"]
    assert result["paired_content_usefulness"]["agent"]["estimate"] == 0
    assert result["promote"] is False and result["human_review_pending"] is True
    assert result["human_agreement"] is None
    with pytest.raises(ValueError, match="immutable"):
        helper.import_ratings(out, paths)


def test_imported_review_and_summary_cannot_silently_change(helper, prepared):
    out, _, _ = prepared
    path = out.parent / "ratings.jsonl"
    write_jsonl(path, ratings(read_jsonl(out / "blind_packet.jsonl")))
    helper.import_ratings(out, [path])
    mapped = read_jsonl(out / "ai_reviews.jsonl")
    mapped[0]["scores"]["overall"] = 1
    write_jsonl(out / "ai_reviews.jsonl", mapped)
    with pytest.raises(ValueError, match="Changed external AI review"):
        helper.summarize(out)


def test_source_loader_rejects_incomplete_or_non_development_candidate(helper, tmp_path, monkeypatch):
    for invalid in ({"phase": "confirmation"}, {"phase": "development", "policy_version": "v0"},
                    {"phase": "development", "policy_version": "v2", "systems": ["verified"], "n": 79}):
        monkeypatch.setattr(helper, "verified_execution", lambda _, frozen=invalid: (frozen, [], [], {}))
        with pytest.raises(ValueError, match="80-message"):
            helper.load_sources(tmp_path, tmp_path, tmp_path)


@pytest.fixture
def source_run(helper, tmp_path, monkeypatch):
    candidate, archive, label_dir = (tmp_path / name for name in ("candidate", "archive", "labels"))
    labels = [{"id": str(i), "text": f"Customer {i}", "gold": {"intent": "other", "should_escalate": False}}
              for i in range(80)]
    new = [{"id": r["id"], "input_text": r["text"], "system": "verified", "outcome": "failed"}
           for r in labels]
    old = [{"id": r["id"], "input_text": r["text"], "system": system}
           for r in labels for system in helper.SYSTEMS[:-1]]
    label_path = label_dir / "labels.jsonl"
    write_jsonl(label_path, labels)
    write_json(label_dir / "LABEL_REVIEW.json", {"label_source": "ai", "human_reviewed": False, "status": "frozen",
        "labels": {"sha256": helper.sha256(label_path)}, "policy": {"sha256": "policy-hash"}})
    frozen = {"phase": "development", "policy_version": "v2", "systems": ["verified"], "n": 80,
              "inputs": {"config/policy_v2.json": "policy-hash"}, "source_as_of": "2026-09-18"}
    policy = tmp_path / "policy.json"
    write_json(policy, {"policy": 2})
    write_json(candidate / "EXECUTION.json", {"artifacts": {}})
    write_json(candidate / "rubric.json", RUBRIC)
    write_json(archive / "VERIFICATION.json", {"artifacts": {}})
    write_json(archive / "manifest.json", {"frozen": {"n": 80, "systems": list(helper.SYSTEMS[:-1])}})
    write_json(archive / "summary.json", {"runtime": {"archived": True}})
    write_json(archive / "ACCEPTANCE.json", {"promote": False})
    write_jsonl(archive / "predictions.jsonl", old)
    monkeypatch.setattr(helper, "verified_execution", lambda _: (frozen, labels, new, {"verified": {"fresh": True}}))
    monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0))
    monkeypatch.setattr(helper, "resolve_input", lambda *a: policy)
    return candidate, archive, label_path, new


def test_source_loader_keeps_failed_new_outcomes_and_historical_successes(helper, source_run):
    candidate, archive, labels, _ = source_run
    source = helper.load_sources(candidate, archive, labels)
    assert len(source["predictions"]) == 320
    assert sum(r["outcome"] == "failed" for r in source["predictions"]) == 80
    assert source["runtime"]["controlled_comparison"] is False
    assert "archive/ACCEPTANCE.json" in source["inputs"]


@pytest.mark.parametrize("problem", ["customer", "missing_row", "duplicate_row", "changed_labels", "different_policy", "failed_archive"])
def test_source_loader_refuses_mixed_populations_or_unverified_sources(helper, source_run, monkeypatch, problem):
    candidate, archive, labels, new = source_run
    if problem == "customer":
        new[0]["input_text"] = "Different customer context"
    elif problem == "missing_row":
        new.pop()
    elif problem == "duplicate_row":
        new.append(new[0])
    elif problem == "changed_labels":
        changed = read_jsonl(labels)
        changed[0]["gold"]["should_escalate"] = True
        write_jsonl(labels, changed)
    elif problem == "different_policy":
        path = labels.parent / "LABEL_REVIEW.json"
        changed = read_json(path)
        changed["policy"]["sha256"] = "wrong-policy"
        write_json(path, changed)
    else:
        monkeypatch.setattr(helper.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="Bad receipts"))
    with pytest.raises(ValueError):
        helper.load_sources(candidate, archive, labels)
