"""Quality replay binds exact archived data, independent AI identity and failed cases."""
from __future__ import annotations

import copy
import importlib.util
import shutil
from pathlib import Path

import pytest
import yaml

from cadence.eval.archive import archive_inputs
from cadence.eval.provenance import sha256
from cadence.eval.verified import FLAGS, RUBRIC, review_packet
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


@pytest.fixture
def study(tmp_path):
    project = Path(__file__).parents[1]
    script = project / "analysis_tools/summarize_verified_controls.py"
    spec = importlib.util.spec_from_file_location("control_quality", script)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    for name in helper.ANALYSIS_SOURCES:
        destination = tmp_path / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project / name, destination)
    out = tmp_path / "results/control"
    out.mkdir(parents=True)
    labels_name = "data/dev/labels.jsonl"
    labels_path = tmp_path / labels_name
    labels_path.parent.mkdir(parents=True)
    labels = [{"id": "d1", "text": "I need a refund", "split": "development",
               "gold": {"intent": "billing_or_charge", "should_escalate": True,
                        "escalation_reason_code": "billing_dispute"}},
              {"id": "d2", "text": "The app pauses", "split": "development",
               "gold": {"intent": "playback_or_app_bug", "should_escalate": False}}]
    write_jsonl(labels_path, labels)
    taxonomy_path = tmp_path / "config/intents.yaml"
    taxonomy_path.parent.mkdir()
    taxonomy_path.write_text(yaml.safe_dump({"intents": [{"id": row["gold"]["intent"]} for row in labels]}), encoding="utf-8")
    inputs = {labels_name: sha256(labels_path), "config/intents.yaml": sha256(taxonomy_path)}
    frozen = {"version": "balanced-development-veto-v1", "phase": "development", "inputs": inputs,
              "created_at": "2026-01-01T00:00:00+00:00", "controls": list(helper.CONTROLS),
              "promotion": False, "scoring_policy": "v2", "fresh_model_calls": 0, "n": 2, "seed": 17,
              "frame_source": {"labels_sha256": inputs[labels_name], "source_run": "results/old_frames"}}
    write_json(out / "manifest.json", {"frozen": frozen})
    archive_inputs(out, inputs, root=tmp_path)
    rows = []
    routing = {}
    for control in helper.CONTROLS:
        system_rows = []
        for label in labels:
            escalate = (label["id"] == "d1" and control in {"independent_policy_veto", "combined_veto"}
                        or label["id"] == "d2" and control == "prerequisite_veto")
            system_rows.append({"id": label["id"], "input_text": label["text"], "system": control,
                "decision": "escalate" if escalate else "auto_handle", "intent": label["gold"]["intent"],
                "outcome": "failed" if label["id"] == "d1" and control == "combined_veto" else "success",
                "reply_draft": "A human needs to review this request. /AI" if escalate else "Which device are you using? /AI",
                "evidence": []})
        rows += system_rows
        routing[control] = {"n": 2, "required": 1,
            "automatic": sum(r["outcome"] == "success" and r["decision"] == "auto_handle" for r in system_rows),
            "missed_escalations": int(system_rows[0]["outcome"] != "success" or system_rows[0]["decision"] != "escalate"),
            "unnecessary_escalations": int(system_rows[1]["decision"] == "escalate"),
            "failed": sum(r["outcome"] == "failed" for r in system_rows)}
    write_jsonl(out / "predictions.jsonl", rows)
    write_json(out / "routing_summary.json", {"controls": routing, "useful_coverage": None})
    write_json(out / "rubric.json", RUBRIC)
    packet, mapping = review_packet(rows, "ablation-" + sha256(out / "manifest.json")[:16], frozen["seed"])
    write_jsonl(out / "blind_packet.jsonl", packet)
    write_json(out / "blind_mapping.json", mapping)
    write_json(out / "EXECUTION.json", {"artifacts": {name: sha256(out / name) for name in helper.SEALED_ARTIFACTS},
                                       "live_model_calls": 0, "promotion": False})
    ratings = []
    for item in packet:
        ratings.append({**{key: item[key] for key in ("id", "alias", "run_id", "reply_hash", "rubric_version")},
            "reviewer_type": "ai", "reviewer_id": "independent-test-reviewer", "rated_at": "2026-01-02T00:00:00+00:00",
            "scores": dict.fromkeys(RUBRIC["dimensions"], 4), "flags": dict.fromkeys(FLAGS, False),
            "verdict": "ship", "response_kind": "handoff" if "human" in item["reply_draft"] else "clarification",
            "severity": "none", "rationale": "A test-only exact-context judgment.", "review_method": "independent_blind"})
    submission = out / "blind_ai_ratings.jsonl"
    write_jsonl(submission, ratings)
    return helper, tmp_path, out, submission


def test_complete_offline_summary_and_readonly_check_preserve_failed_denominator(study):
    helper, root, out, submission = study
    before = {name: sha256(out / name) for name in helper.SEALED_ARTIFACTS}
    result = helper.summarize(out, root=root)
    assert result["n"] == 2 and result["n_ratings"] == 8
    assert result["metrics"]["balanced_replay"]["counts"]["policy_compliant_useful_automatic"] == 1
    assert result["metrics"]["prerequisite_veto"]["counts"]["policy_compliant_useful_automatic"] == 0
    assert result["metrics"]["combined_veto"]["counts"]["failed"] == 1
    assert result["metrics"]["combined_veto"]["counts"]["missed_escalations"] == 1
    assert result["reviewer_type"] == "ai" and result["human_review_complete"] is False
    assert result["promotion"] is False and result["fresh_latency_ms"] is None and result["fresh_cost"] is None
    assert result == helper.summarize(out, check=True, root=root)
    assert before == {name: sha256(out / name) for name in helper.SEALED_ARTIFACTS}
    original = {(r["id"], r["alias"]): r for r in read_jsonl(submission)}
    for row in read_jsonl(out / "ai_reviews.jsonl"):
        assert {k: v for k, v in row.items() if k != "system"} == original[row["id"], row["alias"]]
    with pytest.raises(ValueError, match="immutable"):
        helper.summarize(out, root=root)


def test_analysis_uses_archived_labels_not_current_candidate_labels(study):
    helper, root, out, _ = study
    (root / "data/dev/labels.jsonl").write_text("newer labels must not be read", encoding="utf-8")
    result = helper.summarize(out, root=root)
    assert result["n"] == 2 and result["metrics"]["balanced_replay"]["counts"]["required"] == 1


@pytest.mark.parametrize("alteration", ["missing", "duplicate", "reply_hash", "human", "future", "identity"])
def test_incomplete_or_misattributed_ratings_are_rejected_before_writing(study, alteration):
    helper, root, out, submission = study
    rows = read_jsonl(submission)
    if alteration == "missing":
        rows.pop()
    elif alteration == "duplicate":
        rows[-1] = copy.deepcopy(rows[0])
    elif alteration == "reply_hash":
        rows[0]["reply_hash"] = "0" * 64
    elif alteration == "human":
        rows[0]["reviewer_type"] = "human"
    elif alteration == "future":
        rows[0]["rated_at"] = "2999-01-01T00:00:00+00:00"
    else:
        rows[0]["reviewer_id"] = 123
    write_jsonl(submission, rows)
    with pytest.raises(ValueError):
        helper.summarize(out, root=root)
    assert not any((out / name).exists() for name in helper.OUTPUTS)


def test_resealed_blind_context_change_does_not_pass_source_reconstruction(study):
    helper, root, out, _ = study
    packet = read_jsonl(out / "blind_packet.jsonl")
    packet[0]["evidence"] = [{"new": "context that reviewer did not receive from this output"}]
    write_jsonl(out / "blind_packet.jsonl", packet)
    seal = read_json(out / "EXECUTION.json")
    seal["artifacts"]["blind_packet.jsonl"] = sha256(out / "blind_packet.jsonl")
    write_json(out / "EXECUTION.json", seal)
    with pytest.raises(ValueError, match="context changed"):
        helper.summarize(out, root=root)


@pytest.mark.parametrize("changed", ["summary", "rating", "helper", "snapshot"])
def test_check_rejects_tampered_outputs_ratings_or_evaluator(study, changed):
    helper, root, out, submission = study
    helper.summarize(out, root=root)
    if changed == "summary":
        result = read_json(out / "quality_summary.json")
        result["metrics"]["balanced_replay"]["counts"]["automatic"] += 1
        write_json(out / "quality_summary.json", result)
    elif changed == "rating":
        rows = read_jsonl(submission)
        rows[0]["rationale"] += " altered"
        write_jsonl(submission, rows)
    elif changed == "helper":
        with (root / helper.ANALYSIS_SOURCES[0]).open("a", encoding="utf-8") as stream:
            stream.write("\n# changed evaluator\n")
    else:
        with (out / "quality_analysis_snapshot" / helper.ANALYSIS_SOURCES[0]).open("a", encoding="utf-8") as stream:
            stream.write("\n# changed snapshot\n")
    with pytest.raises(ValueError):
        helper.summarize(out, check=True, root=root)
