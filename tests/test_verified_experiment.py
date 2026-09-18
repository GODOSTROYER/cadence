import importlib.util
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence.eval.review import reply_hash
from cadence.eval.verified import (
    FLAGS,
    acceptance,
    challenge_outcomes,
    coverage,
    human_agreement,
    paired_useful,
    review_packet,
    runtime,
    validate_ratings,
)


def script(name, folder="scripts"):
    path = Path(__file__).resolve().parents[1] / folder / name
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample():
    labels = [{"id": str(i), "gold": {"intent": "playback_or_app_bug", "should_escalate": i == 1,
                "escalation_reason_code": "legal_or_safety_risk" if i == 1 else "none"}} for i in range(3)]
    rows = [{"id": str(i), "system": "verified", "outcome": "success", "decision": "auto_handle",
             "intent": "playback_or_app_bug", "input_text": "Music does not play", "reply_draft": f"Reply {i}", "evidence": []}
            for i in range(3)]
    packet, mapping = review_packet(rows, "test-run", 123)
    ratings = [{**{k: p[k] for k in ("id", "alias", "reply_hash", "run_id", "rubric_version")},
                "scores": {d: 5 for d in ("grounded", "resolves", "tone", "safe", "overall")},
                "flags": dict.fromkeys(FLAGS, False), "severity": "none", "verdict": "ship",
                "response_kind": "resolution", "reviewer_id": "test-ai", "reviewer_type": "ai",
                "rated_at": "2026-09-18T01:00:00Z", "rationale": "Synthetic test fixture"} for p in packet]
    return labels, rows, ratings, mapping


def test_primary_metric_excludes_useful_words_on_ineligible_routes():
    labels, rows, ratings, _ = sample()
    result = coverage(labels, rows, ratings)
    assert result["counts"]["legacy_useful_automatic"] == 3
    assert result["counts"]["policy_compliant_useful_automatic"] == 2
    assert result["counts"]["missed_escalations"] == 1
    assert result["per_reason"]["legal_or_safety_risk"]["missed"] == 1
    assert result["rates"]["policy_compliant_useful_coverage"] == 2 / 3


def test_failures_are_in_population_and_never_successful_handoffs():
    labels, rows, ratings, _ = sample()
    rows[1]["outcome"] = "failed"
    rows[1]["decision"] = "escalate"  # Engine's safe generic fallback does not make execution successful.
    result = coverage(labels, rows, ratings)
    assert result["counts"]["failed"] == 1
    assert result["counts"]["n"] == 3
    assert result["counts"]["missed_escalations"] == 1
    assert result["intent"]["accuracy"] == 2 / 3


@pytest.mark.parametrize("problem", ["missing_review", "changed_reply", "duplicate_prediction", "wrong_label_type"])
def test_incomplete_or_unbound_coverage_is_rejected(problem):
    labels, rows, ratings, _ = sample()
    if problem == "missing_review":
        ratings.pop()
    elif problem == "changed_reply":
        rows[0]["reply_draft"] = "Changed after review"
    elif problem == "duplicate_prediction":
        rows.append(rows[0])
    else:
        labels[0]["gold"]["should_escalate"] = "false"
    with pytest.raises(ValueError):
        coverage(labels, rows, ratings)


def test_wrong_issue_counts_independently_from_routing_and_severity():
    labels, rows, ratings, _ = sample()
    ratings[0]["flags"]["wrong_issue"] = True
    ratings[0]["severity"] = "minor"
    result = coverage(labels, rows, ratings)
    assert result["counts"]["automatic_wrong_issue"] == 1
    assert result["counts"]["policy_compliant_useful_automatic"] == 1
    assert result["per_severity"]["minor"]["wrong_issue"] == 1


def test_paired_bootstrap_uses_matched_differences():
    same = paired_useful([1, 0, 1], [1, 0, 1], n_boot=100)
    assert same["estimate"] == 0
    assert same["ci95"] == [0, 0]
    distinct = paired_useful([1] * 20, [0] * 20, n_boot=100)
    assert distinct["ci95"] == [1, 1]


@pytest.mark.parametrize("problem", ["old_hash", "missing_flag", "fake_human_method", "unknown_severity", "duplicate", "missing_expected"])
def test_review_import_rejects_identity_or_provenance_gaps(problem):
    _, _, ratings, mapping = sample()
    if problem == "old_hash":
        ratings[0]["reply_hash"] = "old"
    elif problem == "missing_flag":
        ratings[0]["flags"].pop("unsupported_action")
    elif problem == "fake_human_method":
        ratings[0].update(reviewer_type="human", review_method="verified_ai_scores")
    elif problem == "unknown_severity":
        ratings[0]["severity"] = "acceptable_for_our_model"
    elif problem == "duplicate":
        ratings.append(ratings[0])
    else:
        ratings.pop()
    with pytest.raises(ValueError):
        validate_ratings(ratings, mapping, expected_keys={(m["id"], m["system"]) for m in mapping})


def test_blind_packet_has_no_route_system_or_scores():
    _, rows, _, _ = sample()
    packet, _ = review_packet(rows, "test", 1)
    assert set(packet[0]) == {"id", "alias", "run_id", "reply_hash", "rubric_version", "text", "reply_draft", "evidence"}
    assert packet[0]["reply_hash"] == reply_hash(rows[0]["reply_draft"])


def test_runtime_counts_failed_retries_billed_usage_from_complete_request_budget():
    rows = [{"outcome": "success", "measurement": {
        "elapsed_ms": 4200, "calls": [{"status": "success", "cached": False, "attempts": 2,
                                       "prompt_tokens": 100, "output_tokens": 30}],
        "budget": {"network_attempts": 2, "failed_attempts": 1, "prompt_tokens": 200,
                   "output_tokens": 80, "unknown_failed_usage": False}}}]
    result = runtime(rows)
    assert result["tokens_known"] == 280  # Includes the billed malformed first response.
    assert result["network_attempts_known"] == 2
    assert result["calls_with_unknown_usage"] == 0
    rows[0]["measurement"]["budget"]["unknown_failed_usage"] = True
    assert runtime(rows)["calls_with_unknown_usage"] == 1
    rows[0]["measurement"]["budget"].update(unknown_failed_usage=False, unknown_usage=True)
    assert runtime(rows)["calls_with_unknown_usage"] == 1  # Missing successful usage also blocks complete-cost claims.


def test_runtime_failures_and_unknown_usage_do_not_disappear():
    rows = [{"outcome": "failed", "measurement": {"elapsed_ms": 9000, "calls": [{"status": "error"}], "budget": None}},
            {"outcome": "success", "measurement": {"elapsed_ms": 1000, "calls": [{"status": "success", "cached": True,
              "attempts": 0, "prompt_tokens": 0, "output_tokens": 0}], "budget": None}}]
    result = runtime(rows)
    assert result["n_requests"] == 2 and result["failures"] == 1
    assert result["p95_end_to_end_ms"] == 8600
    assert result["calls_with_unknown_usage"] == 1
    assert result["fully_fresh_requests"] == 1


def test_invocation_wrapper_delegates_budget_and_counts_engine_failure():
    runner = script("25_verified_experiment.py")
    class Client:
        model = "test"
        @contextmanager
        def request_budget(self, **kwargs):
            assert kwargs == {"seconds": 2, "max_attempts": 4}
            yield SimpleNamespace(as_dict=lambda: {"network_attempts": 0})
        def budget_status(self):
            return {"network_attempts": 0}
    class Agent:
        def handle(self, text, **kwargs):
            return {"id": "x", "trace": {"execution_error": "TimeoutError"}, "decision": "escalate"}
    wrapped = runner.InvocationClient(Client())
    row = runner.invocation(Agent(), wrapped, {"id": "x", "text": "help"}, set(), seconds=2, max_attempts=4)
    assert row["outcome"] == "failed"
    assert row["measurement"]["budget"]["network_attempts"] == 0
    assert wrapped.budget_status() == {"network_attempts": 0}


def test_human_agreement_preserves_message_clusters_and_identity():
    _, _, ratings, mapping = sample()
    ai = validate_ratings(ratings, mapping)
    human = deepcopy(ai)
    for row in human:
        row.update(reviewer_type="human", reviewer_id="test-human", review_method="independent_blind")
    result = human_agreement(human, ai, n_boot=20)
    assert result["n_messages"] == 3 and result["n_reply_ratings"] == 3
    assert result["per_dimension"]["overall"]["exact"] == 1
    human[0]["reply_hash"] = "wrong"
    with pytest.raises(ValueError):
        human_agreement(human, ai, n_boot=20)


def test_every_gate_passing_still_never_promotes():
    labels, rows, ratings, _ = sample()
    labels[1]["gold"]["should_escalate"] = False
    metric = coverage(labels, rows, ratings)
    metrics = {s: metric for s in ("verified", "agent", "quality", "balanced")}
    times = {s: {"fully_fresh_requests": 3, "n_requests": 3, "p95_end_to_end_ms": 1000,
                 "tokens_per_request_known": 100, "calls_with_unknown_usage": 0} for s in metrics}
    result = acceptance(metrics, times, {"estimate": .1, "ci95": [.01, .2]}, phase="confirmation",
                        rules={"intent_f1_margin": .03, "max_p95_ms": 7500, "token_ratio_target": 1.25},
                        human_labels=True, human_reply_subset=True, challenge_accepted=True)
    assert result["eligible_for_release_review"] is True
    assert result["promote"] is False


def test_confirmation_human_gate_precedes_freeze_and_model_initialization(tmp_path, monkeypatch):
    runner = script("25_verified_experiment.py")
    path = tmp_path / "labels.jsonl"
    path.write_text(json.dumps({"id": "x", "gold": {"should_escalate": False}}) + "\n", encoding="utf-8")
    def rejected(*args, **kwargs):
        raise ValueError("Actual human review missing")
    monkeypatch.setattr(runner, "sampler_module", lambda: SimpleNamespace(validate_confirmation=rejected))
    monkeypatch.setattr(sys, "argv", ["runner", "--labels", str(path), "--out", str(tmp_path / "run"),
                                      "--policy", str(tmp_path / "policy.yaml"), "--policy-version", "v2", "--phase", "confirmation", "--live-free-tier"])
    with pytest.raises(ValueError, match="Actual human review"):
        runner.main()
    assert not (tmp_path / "run").exists()


def test_snapshot_resume_binds_recursive_config_and_execution_settings(tmp_path, monkeypatch):
    runner = script("25_verified_experiment.py")
    root = tmp_path / "repo"
    files = ["scripts/25_verified_experiment.py", "scripts/26_lock_verified_confirmation.py",
             "analysis_tools/reproduce_verified.py", "pyproject.toml", "src/cadence/example.py",
             "config/nested/knowledge.json", "policy.yaml", "labels.jsonl", "threads.jsonl", "docs/BRAND_VOICE.md"]
    for name in files:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(runner, "__file__", str(root / files[0]))
    monkeypatch.setattr(runner, "Paths", SimpleNamespace(ROOT=root, CONFIG=root / "config", THREADS=root / "threads.jsonl"))
    args = SimpleNamespace(out=root / "results/run", labels=root / "labels.jsonl", policy=root / "policy.yaml",
                           phase="development", policy_version="v2", variant="combined", seed=1,
                           deadline=45, max_attempts=6, max_consecutive_failures=3, reserved_sample=[],
                           live_free_tier=False, systems=["verified"], limit=1)
    labels = [{"id": "x"}]
    before = runner.freeze(args, labels)
    assert "config/nested/knowledge.json" in before["inputs"]
    assert runner.freeze(args, labels) == before
    (root / "config/nested/knowledge.json").write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        runner.freeze(args, labels)


def test_legacy_usefulness_keeps_original_flag_definition():
    labels, rows, ratings, _ = sample()
    ratings[0]["flags"]["repeated_known_question"] = True
    ratings[0]["severity"] = "minor"
    result = coverage(labels, rows, ratings)
    assert result["counts"]["legacy_useful_automatic"] == 3
    assert result["counts"]["policy_compliant_useful_automatic"] == 1


def test_invalid_gold_cannot_become_correct_unknown_prediction():
    labels, rows, ratings, _ = sample()
    rows[0]["outcome"] = "failed"
    with pytest.raises(ValueError, match="frozen taxonomy"):
        coverage(labels, rows, ratings, intent_labels=["other"])


def test_runner_excludes_overlapping_opener_missing_from_turn_list():
    runner = script("25_verified_experiment.py")
    threads = [
        {"thread_id": "t_1", "opener_tweet_id": 1, "customer_text": "one", "turns": []},
        {"thread_id": "t_2", "customer_text": "different", "turns": [{"tweet_id": 1}]},
        {"thread_id": "t_3", "customer_text": "unrelated", "turns": [{"tweet_id": 99}]},
    ]
    assert runner.excluded_retrieval(threads, [{"thread_id": "t_1", "text": "one"}]) == {"t_1", "t_2"}


def test_freeze_cannot_adopt_old_predictions_without_manifest(tmp_path):
    runner = script("25_verified_experiment.py")
    (tmp_path / "predictions.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unbound execution"):
        runner.freeze(SimpleNamespace(out=tmp_path), [{"id": "x"}])


def test_exception_outcome_uses_same_customer_normalization_as_success():
    runner = script("25_verified_experiment.py")
    class Agent:
        def handle(self, *args, **kwargs):
            raise TimeoutError("test")
    wrapped = runner.InvocationClient(SimpleNamespace())
    row = runner.invocation(Agent(), wrapped, {"id": "x", "text": "  music   stopped  "}, set(), seconds=1, max_attempts=1)
    from cadence.data.clean import clean_text
    assert row["input_text"] == clean_text("  music   stopped  ").text


def test_expected_fault_passes_behavior_only_when_exercised_with_safe_handoff():
    labels, rows, ratings, _ = sample()
    labels, rows, ratings = labels[:1], rows[:1], ratings[:1]
    labels[0]["scenario_setup"] = {"inject": "provider_timeout"}
    rows[0].update(outcome="failed", decision="escalate", challenge={"applicable": True, "triggered": True})
    result = challenge_outcomes(labels, rows, ratings)
    assert result["all_passed"] and result["failed_invocations_retained"] == 1
    assert coverage(labels, rows, ratings)["counts"]["failed"] == 1
    rows[0]["challenge"]["triggered"] = False
    assert not challenge_outcomes(labels, rows, ratings)["all_passed"]
    rows[0]["challenge"]["triggered"] = True
    rows[0]["decision"] = "auto_handle"
    assert not challenge_outcomes(labels, rows, ratings)["all_passed"]


def test_circuit_breaker_preserves_all_attempted_failures_and_pending_cohort(tmp_path):
    runner = script("25_verified_experiment.py")
    rows = []
    for i in range(2):
        runner.persist_outcome(tmp_path, rows, {"id": str(i), "outcome": "failed"}, 80, 3)
    with pytest.raises(RuntimeError, match="Circuit breaker"):
        runner.persist_outcome(tmp_path, rows, {"id": "2", "outcome": "failed"}, 80, 3)
    assert len(rows) == 3
    assert len((tmp_path / "predictions.jsonl").read_text().splitlines()) == 3
    state = json.loads((tmp_path / "status.json").read_text())
    assert state == {"status": "partial", "completed": 3, "expected": 80}
    assert not (tmp_path / "EXECUTION.json").exists()


def test_intentional_fault_does_not_trip_provider_outage_breaker(tmp_path):
    runner = script("25_verified_experiment.py")
    rows = []
    for i in range(5):
        runner.persist_outcome(tmp_path, rows, {"id": str(i), "outcome": "failed", "challenge": {"triggered": True}},
                               80, 3, expected_fault=True)
    assert len(rows) == 5 and not (tmp_path / "INTERRUPTION.json").exists()


def test_human_packet_setup_alias_is_executed_and_conflicts_rejected():
    runner = script("25_verified_experiment.py")
    setup = {"inject": "provider_timeout"}
    assert runner.scenario_for({"setup": setup}) == setup
    with pytest.raises(ValueError, match="Conflicting"):
        runner.scenario_for({"setup": setup, "scenario_setup": {}})


def test_review_receipt_survives_checkout_newlines_without_changing_scores(tmp_path):
    from cadence.eval.provenance import sha256
    from cadence.utils.io import write_json, write_jsonl
    tool = script("reproduce_verified.py", "analysis_tools")
    _, _, ratings, mapping = sample()
    mapped = validate_ratings(ratings, mapping)
    paths = [tmp_path / "ai_review_submission.jsonl", tmp_path / "ai_reviews.jsonl", tmp_path / "REVIEW.lock.json"]
    write_jsonl(paths[0], ratings)
    write_jsonl(paths[1], mapped)
    write_json(paths[2], {"run_id": "test-run"})
    record = {"reviewer_type": "ai", "reviewer_id": "test-ai", "n_ratings": len(mapped),
              "artifacts": {p.name: sha256(p) for p in paths}}
    write_json(tmp_path / "AI_REVIEW.json", record)
    for path in paths:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert tool.load_ratings(tmp_path, "ai", mapping, {"human_reply_ids": []}) == mapped
    paths[0].write_text(paths[0].read_text(encoding="utf-8").replace("Synthetic test fixture", "Changed review"), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        tool.load_ratings(tmp_path, "ai", mapping, {"human_reply_ids": []})
