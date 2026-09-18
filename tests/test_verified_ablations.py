"""Counterfactual controls must isolate vetoes and never invent fresh evidence."""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from cadence.agent.balanced import ACTIONS, render
from cadence.agent.request_frame import POLICY_V2_SHA256, RISK_KINDS, RequestFrame
from cadence.eval.verified_ablations import (
    CONTROLS,
    HOLDING_REPLY,
    applicable,
    customer_text,
    development_labels,
    digest,
    overlay,
    policy_rescore,
    routing_counts,
    validate_frame_record,
)


def frame(issues=("playback_failure",), facts=(), risks=()):
    risk_values = {r["kind"]: r for r in risks}
    return RequestFrame(intent="playback_or_app_bug", intent_confidence=.5,
                        issues=list(issues), facts=list(facts), language_supported=True, intelligible=True,
                        risks=[risk_values.get(kind, {"kind": kind, "state": "absent"}) for kind in RISK_KINDS])


def label(text="Spotify keeps pausing", required=False):
    return {"id": "dev1", "text": text, "split": "development", "gold": {"should_escalate": required}}


def record(extracted, text="Spotify keeps pausing"):
    return {"id": "dev1", "text": text, "status": "valid", "frame": extracted.model_dump(),
            "frame_sha256": digest(extracted.model_dump_json()), "policy_sha256": POLICY_V2_SHA256}


def base(action="ask_device", text="Spotify keeps pausing", decision="auto_handle"):
    return {"id": "dev1", "system": "balanced", "input_text": text, "decision": decision,
            "reply_draft": render(action), "citations": [], "evidence": [],
            "latency_ms": 800, "cached": False, "trace": {"prompt_tokens": 1000},
            "measurement": {"fully_fresh_invocation": True}}


@pytest.mark.parametrize("split", ["confirmation", "challenge", "calibration", None])
def test_only_explicit_development_is_permitted(split):
    row = label()
    row["split"] = split
    with pytest.raises(ValueError, match="development"):
        development_labels([row])


def test_all_old_cards_have_a_contract():
    for action in ACTIONS:
        permitted, reason = applicable(action, frame(), "Spotify keeps pausing")
        assert isinstance(permitted, bool) and reason


def test_risk_overlay_never_changes_successful_eligible_reply_or_invents_new_latency():
    original = base()
    output = overlay(original, record(frame()), label(), "independent_policy_veto")
    assert output["reply_draft"] == original["reply_draft"]
    assert output["decision"] == "auto_handle"
    assert output["ablation"]["fresh_latency_ms"] is None
    assert output["ablation"]["source_runtime"]["latency_ms"] == 800
    assert "latency_ms" not in output and "measurement" not in output
    assert original == base()  # The archive is not mutated.


def test_risk_veto_is_independent_of_applicability():
    text = "Fuck Spotify, it keeps pausing"
    extracted = frame()
    risk = overlay(base(text=text), record(extracted, text), label(text, True), "independent_policy_veto")
    prerequisites = overlay(base(text=text), record(extracted, text), label(text, True), "prerequisite_veto")
    assert risk["decision"] == "escalate"
    assert risk["reply_draft"] == HOLDING_REPLY
    assert prerequisites["decision"] == "auto_handle"
    assert not prerequisites["ablation"]["blocked_by"]


def test_prerequisite_veto_does_not_use_risk_confidence_or_authority():
    text = "My playback stopped."
    extracted = frame(risks=[{"kind": "churn", "state": "unknown"}])
    output = overlay(base(text=text), record(extracted, text), label(text), "prerequisite_veto")
    assert output["decision"] == "auto_handle"
    assert "policy" not in output["ablation"]


def test_exact_old_compound_question_rejects_one_known_fact():
    text = "Playback keeps pausing on my iPhone"
    extracted = frame(facts=[{"slot": "device", "value": "iPhone", "quote": "iPhone"}])
    assert applicable("ask_device", extracted, text)[0] is False
    output = overlay(base(text=text), record(extracted, text), label(text), "prerequisite_veto")
    assert output["reply_draft"] == HOLDING_REPLY  # No newly rendered narrower question.
    assert output["ablation"]["action_id"] == "ask_device"


@pytest.mark.parametrize("control", CONTROLS)
def test_no_control_releases_an_archived_escalation(control):
    output = overlay(base("handoff", decision="escalate"), record(frame()), label(), control)
    assert output["decision"] == "escalate"
    assert output["reply_draft"] == render("handoff")
    assert not output["ablation"]["changed"]


@pytest.mark.parametrize(("action", "issues", "facts", "text"), [
    ("library_filters", ("downloads_missing",), [{"slot": "device", "value": "mobile", "quote": "mobile"}], "mobile downloads disappeared"),
    ("feature_idea", ("feature_request", "playback_failure"), [], "Please improve the app; it crashes"),
    ("feature_idea", ("playlist_create",), [], "I want to create a playlist"),
    ("catalog_availability", ("track_unplayable",), [], "The visible song won't play"),
    ("ask_catalog_item", ("catalog_missing",), [{"slot": "artist", "value": "Artist", "quote": "Artist"}], "Where is Artist?"),
    ("smart_shuffle_off", ("smart_shuffle",), [{"slot": "device", "value": "mobile", "quote": "mobile"}], "Disable smart shuffle on mobile"),
    ("restart_playback", ("playback_failure",), [], "I already restarted Spotify but playback fails"),
    ("update_playback", ("playback_failure",), [{"slot": "app_version", "value": "latest", "quote": "latest"}], "Playback fails on latest version"),
    ("student_browser", ("student_bundle_linking",), [], "My Hulu bundle won't reconnect"),
])
def test_measured_failure_families_block_old_exact_cards(action, issues, facts, text):
    assert applicable(action, frame(issues, facts), text)[0] is False


def test_applicability_requires_exact_card_not_untrusted_action_metadata():
    original = base()
    original["reply_draft"] += " invented procedure"
    output = overlay(original, record(frame()), label(), "prerequisite_veto")
    assert output["decision"] == "escalate" and output["ablation"]["action_id"] is None


def test_named_device_does_not_mask_explicit_platform():
    text = "I use Premium on Samsung Galaxy S8 mobile; disable Smart Shuffle"
    facts = [{"slot": slot, "value": value, "quote": value} for slot, value in (
        ("device", "Samsung Galaxy S8"), ("platform", "mobile"), ("plan", "Premium"))]
    assert applicable("smart_shuffle_off", frame(("smart_shuffle",), facts), text)[0]
    assert applicable("library_filters", frame(("library_missing",), facts), text)[0]


def test_invalid_frame_is_failure_even_with_safe_holding_reply():
    invalid = record(frame())
    invalid["frame_sha256"] = "changed"
    output = overlay(base(), invalid, label(required=True), "combined_veto")
    assert output["decision"] == "escalate" and output["outcome"] == "failed"
    counts = routing_counts([label(required=True)], [output])
    assert counts["failed"] == counts["missed_escalations"] == 1


def test_frame_quotes_and_policy_hash_are_bound():
    extracted = frame(facts=[{"slot": "device", "value": "iPhone", "quote": "iPhone"}])
    with pytest.raises(ValueError, match="quotation"):
        validate_frame_record(record(extracted), label())
    incorrect = record(frame())
    incorrect["policy_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="different policy"):
        validate_frame_record(incorrect, label())


def test_pure_policy_rescore_changes_labels_not_outputs_or_calls():
    old = label(required=True)
    old["split"] = "test"
    predictions = [base()]
    pristine = copy.deepcopy(predictions)
    result = policy_rescore([old], [label()], predictions)
    assert result["old_policy"]["missed_escalations"] == 1
    assert result["new_policy"]["missed_escalations"] == 0
    assert result["label_route_changed_ids"] == ["dev1"]
    assert result["additional_model_calls"] == 0 and result["behavior_changed"] is False
    assert predictions == pristine


def test_policy_rescore_rejects_population_change():
    with pytest.raises(ValueError, match="same exact messages"):
        policy_rescore([label("Different input")], [label()], [base()])


def test_brand_target_normalization_matches_extraction():
    assert customer_text("Fuck @SpotifyCares") == "Fuck Spotify"
    assert customer_text("Ask @someone") == "Ask @user"


def test_frame_export_rejects_confirmation_before_accessing_predictions(tmp_path):
    from cadence.utils.io import write_json, write_jsonl
    module_path = Path(__file__).parents[1] / "scripts/27_verified_ablation.py"
    spec = importlib.util.spec_from_file_location("ablation_cli", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = tmp_path / "run"
    run.mkdir()
    write_json(run / "manifest.json", {"frozen": {"phase": "confirmation", "systems": ["verified"]}})
    labels_path = tmp_path / "labels.jsonl"
    write_jsonl(labels_path, [label()])
    with pytest.raises(ValueError, match="DEVELOPMENT"):
        module.export_frames(run, labels_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_prepare_archives_and_seals_complete_population(tmp_path, monkeypatch):
    from cadence.eval.provenance import sha256
    from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl
    module_path = Path(__file__).parents[1] / "scripts/27_verified_ablation.py"
    spec = importlib.util.spec_from_file_location("ablation_cli_integration", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    local_script = tmp_path / "scripts/27_verified_ablation.py"
    local_script.parent.mkdir()
    local_script.write_text(module_path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(module, "__file__", str(local_script))
    monkeypatch.setattr(module.Paths, "ROOT", tmp_path)
    labels_path = tmp_path / "labels.jsonl"
    old_path = tmp_path / "old.jsonl"
    predictions = tmp_path / "predictions.jsonl"
    write_jsonl(labels_path, [label()])
    write_jsonl(old_path, [label(required=True)])
    write_jsonl(predictions, [base()])
    write_json(tmp_path / "manifest.json", {"fixture": "Source seal is tested independently"})
    write_json(tmp_path / "VERIFICATION.json", {"fixture": "Source seal is tested independently"})
    monkeypatch.setattr(module, "frozen_balanced_source", lambda *_: ([base()], {"seal": "VERIFICATION.json"}))
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    write_jsonl(frames_dir / "frames.jsonl", [record(frame())])
    write_json(frames_dir / "FRAMES.lock.json", {"phase": "development", "version": module.VERSION,
        "labels_sha256": sha256(labels_path), "frames_sha256": sha256(frames_dir / "frames.jsonl"),
        "inputs": {}, "n": 1})
    out = tmp_path / "out"
    module.prepare(predictions, labels_path, old_path, frames_dir, out, 42)
    rows = read_jsonl(out / "predictions.jsonl")
    assert len(rows) == 4 and {row["system"] for row in rows} == set(CONTROLS)
    manifest = read_json(out / "manifest.json")
    archive = read_json(out / "INPUT_ARCHIVE.json")
    assert archive["manifest_sha256"] == sha256(out / "manifest.json")
    assert set(archive["inputs"]) == set(manifest["frozen"]["inputs"])
    for name, expected in read_json(out / "EXECUTION.json")["artifacts"].items():
        assert sha256(out / name) == expected
    assert read_json(out / "routing_summary.json")["useful_coverage"] is None
    with pytest.raises(ValueError, match="empty output"):
        module.prepare(predictions, labels_path, old_path, frames_dir, out, 42)


def test_frozen_source_rejects_edited_historical_prediction(tmp_path):
    from cadence.utils.io import write_json, write_jsonl
    module_path = Path(__file__).parents[1] / "scripts/27_verified_ablation.py"
    spec = importlib.util.spec_from_file_location("ablation_source_seal", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    write_jsonl(tmp_path / "predictions.jsonl", [base()])
    write_json(tmp_path / "manifest.json", {"frozen": {}})
    write_json(tmp_path / "VERIFICATION.json", {"status": "complete", "artifacts": {
        "predictions.jsonl": "0" * 64, "manifest.json": "0" * 64}})
    with pytest.raises(ValueError, match="unsealed historical"):
        module.frozen_balanced_source(tmp_path / "predictions.jsonl", tmp_path / "labels.jsonl")


def test_actual_balanced_source_renderer_matches_frozen_confirmation():
    root = Path(__file__).parents[1]
    module_path = root / "scripts/27_verified_ablation.py"
    spec = importlib.util.spec_from_file_location("ablation_actual_source", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows, binding = module.frozen_balanced_source(root / "results/balanced_confirmation/predictions.jsonl",
                                                 root / "data/balanced_confirmation/labels.jsonl")
    assert len(rows) == 80
    assert set(binding["exact_card_sha256"]) == set(ACTIONS)
    assert all(binding["exact_card_sha256"][name] == digest(render(name)) for name in ACTIONS)
