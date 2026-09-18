"""Matched-population and immutable-evidence checks using synthetic sealed runs."""
import importlib.util
from copy import deepcopy
from pathlib import Path

import pytest

from cadence.eval.verified import FLAGS, RUBRIC, runtime
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / "analysis_tools/compare_verified_variants.py"
    spec = importlib.util.spec_from_file_location("verified_variant_comparison", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def study(helper, tmp_path, monkeypatch):
    """Real execution/packet/review validators; only dependency storage is temporary."""
    full = [{"id": str(i), "text": f"Synthetic customer {i}", "label_source": "ai", "gold": {
        "intent": "other", "should_escalate": i in (1, 2), "escalation_reason_code": "security"}}
        for i in range(80)]
    original = tmp_path / "labels.jsonl"
    selected = tmp_path / "selected.jsonl"
    selection = tmp_path / "selection.json"
    write_jsonl(original, full)
    write_jsonl(selected, full[:21])
    write_json(selection, {"n": 21, "ids": [r["id"] for r in full[:21]],
                          "original_labels_sha256": helper.sha256(original),
                          "subset_sha256": helper.sha256(selected), "labels_modified": False,
                          "human_review": False, "purpose": "Inspected development diagnostics"})
    taxonomy = tmp_path / "intents.yaml"
    taxonomy.write_text("intents:\n  - id: other\n", encoding="utf-8")
    policy = tmp_path / "policy.json"
    write_json(policy, {"version": "v2"})
    source = tmp_path / "candidate.py"
    source.write_text("# Frozen synthetic candidate\n", encoding="utf-8")
    reserved = tmp_path / "reserved.jsonl"
    reserved.write_text("[]\n", encoding="utf-8")
    files = {"data/dev/labels.jsonl": original, "data/dev/selected.jsonl": selected,
             "config/intents.yaml": taxonomy, "config/policy_v2.json": policy,
             "src/cadence/agent/verified.py": source, "data/future/examples.jsonl": reserved}
    evaluators = ("src/cadence/config.py", "src/cadence/eval/verified.py", "src/cadence/eval/metrics.py",
                  "src/cadence/eval/agreement.py", "src/cadence/eval/review.py", "src/cadence/eval/archive.py",
                  "src/cadence/eval/provenance.py", "src/cadence/utils/io.py",
                  "scripts/26_lock_verified_confirmation.py", "analysis_tools/reproduce_verified.py")
    files.update({name: helper.Paths.ROOT / name for name in evaluators})

    def resolve(directory, name, digest):
        path = files[name]
        if helper.sha256(path) != digest:
            raise ValueError("Frozen dependency missing or changed: " + name)
        return path

    validator = helper.reproduction()
    monkeypatch.setattr(validator, "resolve_input", resolve)
    monkeypatch.setattr(helper, "resolve_input", resolve)
    monkeypatch.setattr(helper, "reproduction", lambda: validator)
    directories = {v: tmp_path / v for v in helper.VARIANTS}
    for variant, directory in directories.items():
        population = full if variant == "combined" else full[:21]
        rubric_name = f"results/{variant}/rubric.json"
        write_json(directory / "rubric.json", RUBRIC)
        files[rubric_name] = directory / "rubric.json"
        labels_name = "data/dev/labels.jsonl" if variant == "combined" else "data/dev/selected.jsonl"
        names = {*evaluators, "config/intents.yaml", "config/policy_v2.json", "src/cadence/agent/verified.py",
                 "data/future/examples.jsonl", "data/dev/labels.jsonl", labels_name, rubric_name}
        frozen = {"inputs": {name: helper.sha256(files[name]) for name in names}, "labels": labels_name,
                  "rubric": rubric_name, "rubric_version": RUBRIC["version"], "policy": "config/policy_v2.json",
                  "phase": "development", "policy_version": "v2", "variant": variant,
                  "systems": ["verified"], "n": len(population), "run_mode": "live",
                  "model": "synthetic-model", "source_as_of": "2026-09-18", "seed": 123,
                  "human_reply_ids": [], "message_ids": [r["id"] for r in population],
                  "reserved_samples": ["data/future/examples.jsonl"] + ([] if variant == "combined" else ["data/dev/labels.jsonl"]),
                  "resources": {"planned_generation_calls": len(population) * 2, "invocation_seconds": 45,
                                "max_network_attempts": 6, "max_consecutive_failures": 3},
                  "retrieval": {"exclude_transitive_components": True, "fuzzy_cutoff": 85}, "acceptance": {}}
        write_json(directory / "manifest.json", {"frozen": frozen})
        rows = []
        for i, label in enumerate(population):
            row = {"id": label["id"], "input_text": label["text"], "system": "verified", "intent": "other",
                   "reply_draft": "Synthetic exact reply " + label["id"], "evidence": [],
                   "outcome": "success" if i != 2 else "failed",
                   "decision": "escalate" if i in (1, 2) else "auto_handle",
                   "measurement": {"elapsed_ms": 10 if i < 21 else 100000,
                                   "calls": [{"status": "success", "cached": False, "attempts": 1,
                                              "prompt_tokens": 7, "output_tokens": 3}],
                                   "budget": {"network_attempts": 1, "prompt_tokens": 7 if i < 21 else 99997,
                                              "output_tokens": 3, "unknown_usage": i == 2,
                                              "unknown_failed_usage": i == 2}}}
            if i == 2:
                row["measurement"]["calls"] = [{"status": "error", "error_type": "SyntheticError"}]
            rows.append(row)
        write_jsonl(directory / "predictions.jsonl", rows)
        write_json(directory / "status.json", {"status": "complete", "completed": len(rows), "expected": len(rows)})
        write_json(directory / "runtime.json", {"verified": runtime(rows)})
        (directory / "calls.sqlite").write_bytes(b"Synthetic sealed cache")
        write_jsonl(directory / "invocations_started.jsonl", [{"id": r["id"]} for r in rows])
        artifacts = ("manifest.json", "predictions.jsonl", "status.json", "runtime.json", "calls.sqlite", "invocations_started.jsonl")
        write_json(directory / "EXECUTION.json", {"artifacts": {n: helper.sha256(directory / n) for n in artifacts},
                                                 "excluded_retrieval_threads": 402})
        validator.prepare(directory)
        ratings = []
        for row in read_jsonl(directory / "blind_packet.jsonl"):
            flagged = row["id"] == "3"
            ratings.append({**{k: row[k] for k in ("id", "alias", "run_id", "reply_hash", "rubric_version")},
                            "reviewer_type": "ai", "reviewer_id": "Synthetic independent reviewer",
                            "rated_at": "2026-09-18T12:00:00Z", "scores": dict.fromkeys(RUBRIC["dimensions"], 5),
                            "flags": {f: flagged and f == "wrong_issue" for f in FLAGS},
                            "verdict": "edit" if flagged else "ship", "response_kind": "clarification" if row["id"] == "0" else "resolution",
                            "severity": "major" if flagged else "none", "rationale": "Synthetic fixture"})
        submission = tmp_path / f"{variant}-ratings.jsonl"
        write_jsonl(submission, ratings)
        validator.import_ratings(directory, submission, "ai")
    joint = tmp_path / "joint"
    selected_ids = {r["id"] for r in full[:21]}
    packets = [r for d in directories.values() for r in read_jsonl(d / "blind_packet.jsonl") if r["id"] in selected_ids]
    ratings = [r for d in directories.values() for r in read_jsonl(d / "ai_review_submission.jsonl") if r["id"] in selected_ids]
    write_jsonl(joint / "blind_packet_v2.jsonl", packets)
    write_json(joint / "rubric.json", RUBRIC)
    sources = [selection, *(d / name for d in directories.values() for name in ("blind_packet.jsonl", "REVIEW.lock.json"))]
    write_json(joint / "BLIND_REVIEW_V2.lock.json", {"n": 84, "n_messages": 21,
        "human_review": False, "system_and_variant_identity_hidden": True,
        "sources": {str(p): helper.sha256(p) for p in sources},
        "artifacts": {n: helper.sha256(joint / n) for n in ("blind_packet_v2.jsonl", "rubric.json")}})
    write_jsonl(joint / "blind_ai_ratings.jsonl", ratings)
    write_json(joint / "AI_REVIEW.json", {"reviewer_type": "ai", "reviewer_id": "Synthetic independent reviewer",
        "n_ratings": 84, "n_messages": 21,
        "artifacts": {n: helper.sha256(joint / n) for n in ("blind_ai_ratings.jsonl", "BLIND_REVIEW_V2.lock.json")}})
    return {"directories": directories, "labels": selected, "selection": selection, "source": source, "joint": joint}


def summarize(helper, study):
    return helper.summarize(study["directories"], study["labels"], study["selection"], study["joint"])


def test_matched_denominator_and_failed_usage_are_retained(helper, study):
    result = summarize(helper, study)
    for variant in helper.VARIANTS:
        count = result["metrics"][variant]["counts"]
        observed = result["runtime"][variant]
        assert count["n"] == 21 and count["failed"] == count["missed_escalations"] == count["flagged_automatic"] == 1
        assert count["policy_compliant_useful_automatic"] == 18
        assert count["resolution"] == 17 and count["clarification"] == 1
        assert observed["n_requests"] == 21 and observed["tokens_known"] == 210
        assert observed["p50_end_to_end_ms"] == observed["p95_end_to_end_ms"] == 10
        assert observed["calls_with_unknown_usage"] == observed["calls_with_unknown_cache_status"] == 1
        assert observed["requests_with_all_calls_observed_uncached"] == 20
        assert observed["requests_with_unknown_cache_status"] == 1
        assert observed["tokens_per_policy_compliant_useful_reply_known"] == 210 / 18
    assert result["all_observed_calls_uncached"] is False
    assert result["all_matched_requests_observed_uncached"] is False
    assert result["source_population_n"]["combined"] == 80
    assert result["paired_useful_combined_minus_variant"]["core"]["estimate"] == 0
    assert result["paired_useful_combined_minus_variant"]["core"]["n_messages"] == 21
    assert result["promote"] is False and result["new_model_calls"] == 0
    assert "Synthetic customer" not in str(result) and "Synthetic exact reply" not in str(result)


@pytest.mark.parametrize("change", ["model", "source_as_of", "policy_version", "resources", "source", "config", "gold", "text", "missing_id"])
def test_rejects_identity_or_selected_population_changes(helper, study, monkeypatch, change):
    original = helper.sealed_run

    def altered(directory, variant):
        run = original(directory, variant)
        if variant == "core":
            frozen = run["frozen"]
            if change in ("model", "source_as_of", "policy_version"):
                frozen[change] = "different"
            elif change == "resources":
                frozen["resources"]["max_network_attempts"] += 1
            elif change in ("source", "config"):
                key = "src/cadence/agent/verified.py" if change == "source" else "config/policy_v2.json"
                frozen["inputs"][key] = "different-hash"
            elif change == "gold":
                run["labels"][0]["gold"]["should_escalate"] = True
            elif change == "text":
                run["labels"][0]["text"] = "Different context"
            else:
                run["labels"].pop()
        return run

    monkeypatch.setattr(helper, "sealed_run", altered)
    with pytest.raises(ValueError, match="identity|label mismatch|selected IDs"):
        summarize(helper, study)


@pytest.mark.parametrize("name", ["predictions.jsonl", "ai_review_submission.jsonl", "ai_reviews.jsonl", "blind_packet.jsonl"])
def test_modified_execution_and_review_artifacts_are_rejected(helper, study, name):
    path = study["directories"]["core"] / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="changed|Changed"):
        summarize(helper, study)


def test_changed_frozen_candidate_source_is_rejected(helper, study):
    study["source"].write_text("# Changed candidate\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Frozen dependency missing or changed"):
        summarize(helper, study)


@pytest.mark.parametrize("change", ["missing_full_population", "different_count", "missing_count"])
def test_retrieval_exclusion_proof_is_required(helper, study, monkeypatch, change):
    if change == "missing_full_population":
        original = helper.sealed_run

        def altered(directory, variant):
            run = original(directory, variant)
            if variant == "core":
                run["frozen"]["reserved_samples"].remove("data/dev/labels.jsonl")
            return run

        monkeypatch.setattr(helper, "sealed_run", altered)
    else:
        path = study["directories"]["core"] / "EXECUTION.json"
        record = read_json(path)
        if change == "missing_count":
            record.pop("excluded_retrieval_threads")
        else:
            record["excluded_retrieval_threads"] -= 1
        write_json(path, record)
    with pytest.raises(ValueError, match="retrieval|Retrieval"):
        summarize(helper, study)


def test_cached_matched_calls_are_reported_without_removing_requests(helper, study, monkeypatch):
    original = helper.sealed_run

    def cached(directory, variant):
        run = original(directory, variant)
        if variant == "core":
            run["rows"][0]["measurement"]["calls"][0]["cached"] = True
        return run

    monkeypatch.setattr(helper, "sealed_run", cached)
    result = summarize(helper, study)
    observed = result["runtime"]["core"]
    assert observed["n_requests"] == 21 and observed["cached_model_calls"] == 1
    assert observed["fully_fresh_requests"] == 20 and result["all_observed_calls_uncached"] is False
    assert observed["requests_with_all_calls_observed_uncached"] == 19


def test_saved_summary_binds_inputs_helper_evaluator_and_output(helper, study, tmp_path):
    result = summarize(helper, study)
    path = tmp_path / "summary.json"
    helper.save_or_check(path, result)
    helper.save_or_check(path, summarize(helper, study), check=True)
    assert "analysis_tools/compare_verified_variants.py" in result["bindings"]
    assert "src/cadence/eval/verified.py" in result["bindings"]
    assert "combined/EXECUTION.json" in result["bindings"]
    assert "core/ai_review_submission.jsonl" in result["bindings"]
    changed = deepcopy(result)
    changed["metrics"]["core"]["counts"]["policy_compliant_useful_automatic"] += 1
    write_json(path, changed)
    with pytest.raises(ValueError, match="does not reproduce"):
        helper.save_or_check(path, result, check=True)
    with pytest.raises(ValueError, match="immutable"):
        helper.save_or_check(path, result)


@pytest.mark.parametrize("name", ["analysis_tools/compare_verified_variants.py", "src/cadence/eval/verified.py"])
def test_saved_summary_rejects_changed_helper_or_evaluator_binding(helper, study, tmp_path, monkeypatch, name):
    path = tmp_path / "summary.json"
    helper.save_or_check(path, summarize(helper, study))
    bindings = helper.evaluator_bindings()
    bindings[name]["sha256"] = "changed-code"
    monkeypatch.setattr(helper, "evaluator_bindings", lambda: bindings)
    with pytest.raises(ValueError, match="does not reproduce"):
        helper.save_or_check(path, summarize(helper, study), check=True)


def test_resealed_rating_for_different_exact_reply_is_rejected(helper, study):
    directory = study["directories"]["core"]
    submission = directory / "ai_review_submission.jsonl"
    ratings = read_jsonl(submission)
    ratings[0]["reply_hash"] = "0" * 64
    write_jsonl(submission, ratings)
    path = directory / "AI_REVIEW.json"
    record = read_json(path)
    record["artifacts"][submission.name] = helper.sha256(submission)
    write_json(path, record)
    with pytest.raises(ValueError, match="mismatched exact reply rating"):
        summarize(helper, study)


@pytest.mark.parametrize("field", ["model", "variant", "policy_version", "policy_sha256", "source_as_of"])
def test_resealed_prediction_identity_cannot_contradict_manifest(helper, study, field):
    directory = study["directories"]["core"]
    path = directory / "predictions.jsonl"
    rows = read_jsonl(path)
    if field == "model":
        rows[0][field] = "different"
    else:
        rows[0].setdefault("trace", {})[field] = "different"
    write_jsonl(path, rows)
    for name in ("EXECUTION.json", "REVIEW.lock.json"):
        seal = directory / name
        record = read_json(seal)
        record["artifacts"][path.name] = helper.sha256(path)
        write_json(seal, record)
    seal = directory / "AI_REVIEW.json"
    record = read_json(seal)
    record["artifacts"]["REVIEW.lock.json"] = helper.sha256(directory / "REVIEW.lock.json")
    write_json(seal, record)
    with pytest.raises(ValueError, match="identity contradicts"):
        summarize(helper, study)


def test_rejects_mismatched_selection_and_unsealed_review(helper, study):
    record = read_json(study["selection"])
    record["ids"][0] = "other-id"
    write_json(study["selection"], record)
    with pytest.raises(ValueError, match="exact 21"):
        summarize(helper, study)
    path = study["directories"]["core"] / "AI_REVIEW.json"
    record = read_json(path)
    record["artifacts"].pop("ai_review_submission.jsonl")
    write_json(path, record)
    with pytest.raises(ValueError, match="Incomplete artifact seal"):
        helper.sealed_run(study["directories"]["core"], "core")


def reseal_joint_ratings(helper, study, ratings):
    directory = study["joint"]
    path = directory / "blind_ai_ratings.jsonl"
    write_jsonl(path, ratings)
    record = read_json(directory / "AI_REVIEW.json")
    record["artifacts"][path.name] = helper.sha256(path)
    write_json(directory / "AI_REVIEW.json", record)


def test_joint_combined_ratings_are_used_instead_of_separate_full80_review(helper, study):
    before = summarize(helper, study)
    separate = helper.sha256(study["directories"]["combined"] / "ai_reviews.jsonl")
    run_id = read_json(study["directories"]["combined"] / "REVIEW.lock.json")["run_id"]
    ratings = read_jsonl(study["joint"] / "blind_ai_ratings.jsonl")
    row = next(r for r in ratings if r["run_id"] == run_id and r["id"] == "3")
    row.update(flags=dict.fromkeys(FLAGS, False), verdict="ship", severity="none")
    reseal_joint_ratings(helper, study, ratings)
    after = summarize(helper, study)
    assert before["metrics"]["combined"]["counts"]["policy_compliant_useful_automatic"] == 18
    assert after["metrics"]["combined"]["counts"]["policy_compliant_useful_automatic"] == 19
    assert after["metrics"]["core"]["counts"]["policy_compliant_useful_automatic"] == 18
    assert helper.sha256(study["directories"]["combined"] / "ai_reviews.jsonl") == separate
    assert after["quality_review"]["n_ratings"] == 84


@pytest.mark.parametrize("change", ["missing", "duplicate", "other_run", "wrong_reply", "split_reviewer", "human"])
def test_joint_submission_requires_exact_complete_single_ai_review(helper, study, change):
    ratings = read_jsonl(study["joint"] / "blind_ai_ratings.jsonl")
    if change == "missing":
        ratings.pop()
    elif change == "duplicate":
        ratings[-1] = deepcopy(ratings[0])
    elif change == "other_run":
        ratings[0]["run_id"] = "other-run"
    elif change == "wrong_reply":
        ratings[0]["reply_hash"] = "0" * 64
    elif change == "split_reviewer":
        ratings[0]["reviewer_id"] = "Other AI"
    else:
        ratings[0]["reviewer_type"] = "human"
    reseal_joint_ratings(helper, study, ratings)
    with pytest.raises(ValueError):
        summarize(helper, study)


def test_resealed_joint_packet_must_preserve_exact_original_context(helper, study):
    directory = study["joint"]
    path = directory / "blind_packet_v2.jsonl"
    packet = read_jsonl(path)
    packet[0]["text"] = "Changed synthetic context"
    write_jsonl(path, packet)
    record = read_json(directory / "BLIND_REVIEW_V2.lock.json")
    record["artifacts"][path.name] = helper.sha256(path)
    write_json(directory / "BLIND_REVIEW_V2.lock.json", record)
    with pytest.raises(ValueError, match="differs from the exact matched"):
        summarize(helper, study)
