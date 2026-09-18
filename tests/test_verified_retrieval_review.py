"""Development retrieval packets stay reproducible, leakage-safe and human-unrated."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cadence.agent.request_frame import RequestFrame
from cadence.retrieval.index import Hit
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

SPEC = importlib.util.spec_from_file_location(
    "verified_retrieval_review", Path(__file__).resolve().parents[1] / "analysis_tools/verified_retrieval_review.py"
)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def thread(identity, text, tweets=(), replies=None):
    replies = replies or [{"tweet_id": str(identity) + "-reply", "text": "What device plays your music?"}]
    return {"thread_id": identity, "customer_text": text, "brand_replies": replies,
            "first_reply_text": replies[0]["text"], "turns": [{"tweet_id": value} for value in tweets]}


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    # Never let tests inspect or depend on actual reserved samples in the repository.
    monkeypatch.setattr(review.Paths, "DATA", tmp_path / "data")
    labels = tmp_path / "labels.jsonl"
    corpus = tmp_path / "threads.jsonl"
    rows = [
        {"id": "a", "thread_id": "t_1", "text": "My music pauses on Android after ten seconds",
         "split": "development", "gold": {"intent": "SECRET_PRIMARY_LABEL"}},
        {"id": "b", "thread_id": "t_2", "text": "I cannot create a playlist with my account",
         "split": "development", "gold": {"intent": "SECRET_PRIMARY_LABEL"}},
    ]
    candidate = thread("t_10", "Android music playback failure interrupts songs", replies=[
        {"tweet_id": 11, "text": "What device and app version plays your music?", "created_at": "2017-01-01"},
        {"tweet_id": 13, "text": "Does music playback pause while the screen is unlocked?", "created_at": "2017-01-02"},
    ])
    candidate["turns"] = [
        {"role": "customer", "tweet_id": 10, "text": candidate["customer_text"]},
        {"role": "brand", "tweet_id": 11, "text": candidate["brand_replies"][0]["text"]},
        {"role": "customer", "tweet_id": 12, "text": "Android; it pauses only when locked"},
        {"role": "brand", "tweet_id": 13, "text": candidate["brand_replies"][1]["text"]},
    ]
    threads = [thread("t_1", rows[0]["text"], [1, 3]), thread("t_3", "Related indirect followup", [3, 4]),
               thread("t_4", "No shared words; same conversation", [4, 5]),
               thread("t_2", rows[1]["text"], [2]),
               thread("t_20", "I CANNOT create a playlist with my account!", [20, 21]),
               thread("t_21", "Unselected fuzzy case has connected unrelated text", [21]),
               candidate,
               thread("t_30", "The app plays a track and then freezes on Android", [30])]
    write_jsonl(labels, rows)
    write_jsonl(corpus, threads)
    return labels, corpus, tmp_path / "diagnostic", rows, threads


def freeze(inputs, **kwargs):
    labels, corpus, out, _, _ = inputs
    return review.freeze(labels, corpus, out, sample_size=1, seed=0, k=2, **kwargs)


def source_run(inputs, *, invalid_frame=False, phase="development", reserved_samples=()):
    labels, corpus, out, label_rows, _ = inputs
    run = out.parent / "source-run"
    run.mkdir()
    rows = []
    for label in label_rows:
        frame = RequestFrame(intent="playback_or_app_bug", intent_confidence=.8,
                             issues=["playback_failure"], requested_outcome="Restore music playback",
                             facts=[{"slot": "device", "value": "Android", "quote": "Android"}]
                             if label["id"] == "a" else []).model_dump()
        rows.append({"id": label["id"], "system": "verified", "input_text": label["text"],
                     "reply_draft": "Does playback pause while the screen is unlocked?",
                     "trace": {"request_frame": {} if invalid_frame else frame}})
    write_jsonl(run / "predictions.jsonl", rows)
    write_json(run / "manifest.json", {"frozen": {"phase": phase, "labels": str(labels),
               "inputs": {str(labels): review.logical_sha256(labels), str(corpus): review.logical_sha256(corpus),
                          **{str(path): review.logical_sha256(path) for path in reserved_samples}},
               "reserved_samples": [str(path) for path in reserved_samples],
               "message_ids": ["a", "b"], "n": 2, "systems": ["verified"]}})
    write_json(run / "status.json", {"status": "complete", "completed": 2, "expected": 2})
    reseal(run)
    return run


def reseal(run):
    write_json(run / "EXECUTION.json", {"artifacts": {
        name: review.logical_sha256(run / name) for name in ("predictions.jsonl", "manifest.json", "status.json")}})


def prepared(inputs):
    freeze(inputs)
    run = source_run(inputs)
    seal = review.prepare(inputs[2], run)
    return inputs[2], run, seal


def filled_rows(out):
    rows = read_jsonl(out / "review_worksheet.jsonl")
    items = {item["review_id"]: item for item in read_jsonl(out / "blind_packet.jsonl")}
    for row in rows:
        unavailable = items[row["review_id"]]["availability"] == "unavailable"
        row.update(issue_relevance="not_applicable" if unavailable else "1",
                   useful_diagnostic_pattern="not_applicable" if unavailable else "uncertain",
                   supports_proposed_action="not_applicable" if unavailable else "uncertain",
                   context_sufficient="not_applicable" if unavailable else "uncertain",
                   current_authority="unsupported", rationale="Synthetic test fixture human judgment",
                   reviewer_id="fixture-person", reviewer_type="human", rated_at=datetime.now(UTC).isoformat())
    return rows


def test_exact_existing_exclusion_has_transitive_components_and_inclusive_fuzzy_boundary():
    labels = [{"thread_id": "a", "text": "exposed seed"}, {"thread_id": "absent", "text": "abcdefghijklmnopqrst"}]
    threads = [thread("a", "exposed seed", [1, 2]), thread("b", "indirect bridge", [2, 3]),
               thread("c", "unrelated-looking continuation", [3]),
               thread("f", "ABCDEFGHIJKLMNOPQXYZ", [5]),
               thread("g", "connected to a fuzzy duplicate", [5]),
               thread("h", "abcdefghijklmnopZZZZ", [6])]
    assert review.excluded_retrieval(threads, labels) == {"a", "b", "c", "f", "g"}


def test_exclusion_recognizes_implicit_opener_identity():
    threads = [thread("t_1", "old root"), thread("b", "continuation", [1]), thread("other", "different", [99])]
    assert review.excluded_retrieval(threads, [{"thread_id": "t_1", "text": "old root"}]) == {"t_1", "b"}


def test_freeze_is_seeded_hash_bound_and_excludes_all_labels_not_just_subset(inputs):
    record = freeze(inputs)
    payload = record["payload"]
    assert payload["selected_ids"] == ["a"]
    assert payload["exclusions"]["thread_ids"] == ["t_1", "t_2", "t_20", "t_21", "t_3", "t_4"]
    assert record["payload_sha256"] == review.digest(payload)
    assert payload["labels"]["raw_sha256"] == review.raw_sha256(inputs[0])
    assert payload["corpus"]["raw_sha256"] == review.raw_sha256(inputs[1])
    again = inputs[2].parent / "another-lock"
    second = review.freeze(inputs[0], inputs[1], again, sample_size=1, seed=0, k=2)
    assert payload == second["payload"]
    with pytest.raises(ValueError, match="replace"):
        freeze(inputs)


@pytest.mark.parametrize("split", ["confirmation", "calibration", "challenge", "", None])
def test_freeze_refuses_every_non_development_split(inputs, split):
    labels, _, out, rows, _ = inputs
    rows[1]["split"] = split
    write_jsonl(labels, rows)
    with pytest.raises(ValueError, match="split=development"):
        freeze(inputs)
    assert not out.exists()


@pytest.mark.parametrize("change", ["labels", "corpus", "selection", "implementation"])
def test_prepare_rejects_mutation_before_opening_results(inputs, change, monkeypatch):
    freeze(inputs)
    if change in {"labels", "corpus"}:
        with inputs[0 if change == "labels" else 1].open("a", encoding="utf-8") as stream:
            stream.write("\n")
    elif change == "selection":
        lock = read_json(inputs[2] / review.LOCK_NAME)
        lock["payload"]["selected_ids"] = ["b"]
        write_json(inputs[2] / review.LOCK_NAME, lock)
    else:
        monkeypatch.setattr(review, "_dependencies", lambda: {})
    with pytest.raises(ValueError, match="changed"):
        review.prepare(inputs[2], inputs[2].parent / "nonexistent-results-must-not-open")


@pytest.mark.parametrize("phase", ["confirmation", "calibration", "challenge", None])
def test_run_phase_guard_precedes_predictions_read(inputs, phase, monkeypatch):
    freeze(inputs)
    run = source_run(inputs, phase=phase)
    original = review.read_jsonl
    def guarded(path):
        assert Path(path).name != "predictions.jsonl", "Protected predictions were opened"
        return original(path)
    monkeypatch.setattr(review, "read_jsonl", guarded)
    with pytest.raises(ValueError, match="explicitly development"):
        review.prepare(inputs[2], run)


def test_request_frame_query_and_rerank_are_explicit_lexical_heuristics():
    frame = RequestFrame(intent="playback_or_app_bug", intent_confidence=.99, issues=["playback_failure"],
                         facts=[{"slot": "device", "value": "Android", "quote": "Android"}],
                         requested_outcome="Resume songs")
    assert review.frame_query(frame) == "playback failure device Android Resume songs"
    hits = [Hit("unmatched", 1.1, {"customer_text": "unrelated words"}),
            Hit("matched", 1.0, {"customer_text": "Android playback failure"})]
    ranked = review.token_rerank(hits, frame)
    assert ranked[0][0].thread_id == "matched"
    assert ranked[0][1]["heuristic_score"] == 2.0
    assert ranked[1][1]["heuristic_score"] == 1.1


def test_same_exclusions_reach_raw_and_frame_queries_and_filtered_index(inputs, monkeypatch):
    freeze(inputs)
    run = source_run(inputs)
    calls = []
    original = review.Retriever.search
    def observed(self, query, k, exclude_thread_ids):
        calls.append((query, set(exclude_thread_ids)))
        assert self.get("t_1") is None and self.get("t_20") is None
        return original(self, query, k, exclude_thread_ids)
    monkeypatch.setattr(review.Retriever, "search", observed)
    review.prepare(inputs[2], run)
    assert len(calls) == 2
    assert calls[0][0] == inputs[3][0]["text"]
    assert calls[1][0] == "playback failure device Android Restore music playback"
    assert calls[0][1] == calls[1][1] == {"t_1", "t_2", "t_3", "t_4", "t_20", "t_21"}


def test_packet_is_blinded_worksheets_blank_and_sources_unchanged(inputs):
    freeze(inputs)
    run = source_run(inputs)
    sources = [inputs[0], inputs[1], *(run / name for name in ("manifest.json", "predictions.jsonl", "EXECUTION.json"))]
    hashes = {str(path): review.raw_sha256(path) for path in sources}
    seal = review.prepare(inputs[2], run)
    packet = read_jsonl(inputs[2] / "blind_packet.jsonl")
    assert packet and seal["ratings_supplied"] is False
    forbidden = {"gold", "intent", "should_escalate", "id", "system", "arm", "rank", "scores", "request_frame", "reply_kind"}
    assert all(not forbidden.intersection(row) for row in packet)
    assert "SECRET_PRIMARY_LABEL" not in json.dumps(packet)
    for row in packet:
        assert row["item_sha256"] == review.digest({key: value for key, value in row.items() if key != "item_sha256"})
        assert row["outcome"] == "not_assessed" and row["authority_default"] == "unsupported"
    for name in ("review_worksheet.jsonl", "review_worksheet.csv"):
        if name.endswith(".jsonl"):
            worksheet = read_jsonl(inputs[2] / name)
        else:
            with (inputs[2] / name).open(encoding="utf-8", newline="") as stream:
                worksheet = list(csv.DictReader(stream))
        assert len(worksheet) == len(packet)
        assert all(row[field] == "" for row in worksheet for field in review.RATING_FIELDS)
    assert hashes == {str(path): review.raw_sha256(path) for path in sources}
    with pytest.raises(ValueError, match="already exist"):
        review.prepare(inputs[2], run)


def test_first_last_selection_preserves_intermediate_context_without_resolution_claim(inputs):
    corpus_thread = inputs[4][-2]
    views = review.reply_views(corpus_thread)
    assert [view["reply_kind"] for view in views] == ["first_brand_reply", "last_later_brand_reply"]
    assert views[1]["preceding_turns"][-1]["text"] == "Android; it pauses only when locked"
    assert len(views[0]["preceding_turns"]) == 1
    later = deepcopy(corpus_thread)
    later["brand_replies"].insert(1, {"tweet_id": "middle", "text": "Potentially enticing middle reply"})
    assert review.reply_views(later)[1]["reply_tweet_id"] == 13  # Fixed last, never cherry-picked middle.
    missing = review.reply_views(inputs[4][-1])
    assert missing[0]["context_status"] == "unavailable"
    assert missing[1]["availability"] == "unavailable" and missing[1]["text"] == ""


def test_missing_frame_stays_in_frozen_selection_and_does_not_become_raw_frame_arm(inputs):
    freeze(inputs)
    run = source_run(inputs, invalid_frame=True)
    review.prepare(inputs[2], run)
    diagnostics = read_json(inputs[2] / "private_diagnostics.json")["cases"]
    assert [row["id"] for row in diagnostics] == ["a"]
    assert diagnostics[0]["arms"]["request_frame"]["status"] == "frame_unavailable"
    assert diagnostics[0]["arms"]["request_frame_token_rerank"]["thread_ids"] == []
    assert {row["arm"] for row in read_jsonl(inputs[2] / "private_mapping.jsonl")} == {"raw_text"}


def test_changed_prediction_seal_is_rejected(inputs):
    freeze(inputs)
    run = source_run(inputs)
    with (run / "predictions.jsonl").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="sealed"):
        review.prepare(inputs[2], run)


def test_blank_worksheet_is_not_a_human_review(inputs):
    out, _, _ = prepared(inputs)
    with pytest.raises(ValueError, match="human reviewer"):
        review.validate_ratings(out, out / "review_worksheet.jsonl")


def test_complete_external_human_review_validates_without_mutating_packet(inputs):
    out, _, seal = prepared(inputs)
    submission = out.parent / "filled-copy.jsonl"
    write_jsonl(submission, filled_rows(out))
    result = review.validate_ratings(out, submission)
    assert result["valid"] and result["n_ratings"] == seal["n_review_items"]
    assert result["reviewer_type"] == "human" and result["human_review"] is True
    assert all(review.raw_sha256(out / name) == value for name, value in seal["artifacts"].items())


def test_ai_development_review_requires_explicit_type_and_never_counts_as_human(inputs):
    out, _, seal = prepared(inputs)
    rows = filled_rows(out)
    for row in rows:
        row.update(reviewer_type="ai", reviewer_id="fixture-independent-ai")
    submission = out.parent / "ai-filled-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError, match="explicit human reviewer"):
        review.validate_ratings(out, submission)
    result = review.validate_ratings(out, submission, reviewer_type="ai")
    assert result["valid"] and result["n_ratings"] == seal["n_review_items"]
    assert result["reviewer_type"] == "ai" and result["human_review"] is False
    assert "not human review" in result["attribution"]


@pytest.mark.parametrize("change", ["identity", "timestamp", "hash", "human", "authority"])
def test_explicit_ai_review_keeps_identity_timestamp_hash_type_and_authority_checks(inputs, change):
    out, _, _ = prepared(inputs)
    rows = filled_rows(out)
    for row in rows:
        row.update(reviewer_type="ai", reviewer_id="fixture-independent-ai")
    available = next(row for row in rows if row["issue_relevance"] != "not_applicable")
    if change == "identity":
        rows[0]["reviewer_id"] = ""
    elif change == "timestamp":
        rows[0]["rated_at"] = "2099-09-18T12:00:00Z"
    elif change == "hash":
        rows[0]["item_sha256"] = "wrong"
    elif change == "human":
        rows[0]["reviewer_type"] = "human"
    else:
        available["current_authority"] = "yes"
    submission = out.parent / "ai-filled-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError):
        review.validate_ratings(out, submission, reviewer_type="ai")


@pytest.mark.parametrize("reviewer_type", ["human", "ai"])
def test_validate_ratings_cli_passes_explicit_type(tmp_path, monkeypatch, capsys, reviewer_type):
    def validate(out, submission, *, reviewer_type):
        return {"reviewer_type": reviewer_type}
    monkeypatch.setattr(review, "validate_ratings", validate)
    monkeypatch.setattr(sys, "argv", ["review", "validate-ratings", "--out", str(tmp_path),
                                      "--submission", str(tmp_path / "ratings.jsonl"),
                                      "--reviewer-type", reviewer_type])
    review.main()
    assert json.loads(capsys.readouterr().out)["reviewer_type"] == reviewer_type


@pytest.mark.parametrize("reviewer_type", ["human", "ai"])
@pytest.mark.parametrize("field", ["reviewer_id", "rationale"])
@pytest.mark.parametrize("value", [None, 42])
def test_each_review_type_requires_text_identity_and_rationale(inputs, reviewer_type, field, value):
    out, _, _ = prepared(inputs)
    rows = filled_rows(out)
    for row in rows:
        row["reviewer_type"] = reviewer_type
    rows[0][field] = value
    submission = out.parent / "typed-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError):
        review.validate_ratings(out, submission, reviewer_type=reviewer_type)


def test_current_authority_yes_requires_actual_current_snapshot_and_verbatim_support(inputs):
    out, _, _ = prepared(inputs)
    rows = filled_rows(out)
    row = next(row for row in rows if row["issue_relevance"] != "not_applicable")
    row["current_authority"] = "yes"
    submission = out.parent / "filled-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError, match="official HTTPS"):
        review.validate_ratings(out, submission)
    row["current_source_url"] = "https://support.spotify.com/article/example"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError, match="actual source snapshot"):
        review.validate_ratings(out, submission)
    source = out.parent / "fixture-current-source.txt"
    source.write_text("Synthetic official-source test fixture about Android diagnostics.", encoding="utf-8")
    row.update(current_evidence_path=source.name, current_evidence_sha256=review.raw_sha256(source),
               current_source_excerpt="Android diagnostics",
               current_checked_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
               current_authority_rationale="Synthetic rationale matching the exact proposed diagnostic")
    write_jsonl(submission, rows)
    assert review.validate_ratings(out, submission)["valid"]
    row["current_checked_at"] = "2017-09-18T10:00:00Z"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError, match="freshness"):
        review.validate_ratings(out, submission)


@pytest.mark.parametrize("change", ["duplicate", "incomplete", "hash", "ai"])
def test_human_review_rejects_missing_or_unbound_ratings(inputs, change):
    out, _, _ = prepared(inputs)
    rows = filled_rows(out)
    if change == "duplicate":
        rows.append(rows[0])
    elif change == "incomplete":
        rows.pop()
    elif change == "hash":
        rows[0]["item_sha256"] = "wrong"
    else:
        rows[0]["reviewer_type"] = "ai"
    submission = out.parent / "filled-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError):
        review.validate_ratings(out, submission)


@pytest.mark.parametrize("change", ["manifest_hash", "missing_row", "input_text", "corpus", "status"])
def test_source_results_must_match_the_complete_sealed_development_run(inputs, change):
    freeze(inputs)
    run = source_run(inputs)
    if change in {"manifest_hash", "corpus"}:
        manifest = read_json(run / "manifest.json")
        manifest["frozen"]["inputs"][str(inputs[1])] = "different-corpus"
        write_json(run / "manifest.json", manifest)
    elif change == "status":
        write_json(run / "status.json", {"status": "partial", "completed": 1, "expected": 2})
    else:
        rows = read_jsonl(run / "predictions.jsonl")
        if change == "missing_row":
            rows.pop()
        else:
            rows[0]["input_text"] = "An unrelated request which the frame was extracted from"
        write_jsonl(run / "predictions.jsonl", rows)
    if change != "manifest_hash":
        reseal(run)
    with pytest.raises(ValueError):
        review.prepare(inputs[2], run)
    assert not (inputs[2] / "blind_packet.jsonl").exists()


def test_future_human_rating_and_authority_date_are_rejected(inputs):
    out, _, _ = prepared(inputs)
    rows = filled_rows(out)
    rows[0]["rated_at"] = "2099-09-18T12:00:00Z"
    rows[0]["current_checked_at"] = "2099-09-18T10:00:00Z"
    submission = out.parent / "filled-copy.jsonl"
    write_jsonl(submission, rows)
    with pytest.raises(ValueError, match="future-dated"):
        review.validate_ratings(out, submission)


def reserved_sample(inputs, name="reserved.jsonl", rows=None):
    path = inputs[2].parent / name
    write_jsonl(path, rows or [{"id": "reserved-case", "thread_id": "t_9000",
                              "text": "SYNTHETIC_RESERVED_TEXT_NOT_FOR_THE_REVIEW_PACKET",
                              "gold": {"intent": "SECRET_RESERVED_GOLD"}}])
    return path


def test_reserved_text_fuzzy_matches_and_connected_conversation_never_enter_packets(inputs):
    protected_text = "ANDROID MUSIC PLAYBACK FAILURE INTERRUPTS SONGS!"
    reserved = reserved_sample(inputs, rows=[{"id": "future", "thread_id": "absent-reserved-root",
                                            "text": protected_text, "gold": {"intent": "SECRET_RESERVED_GOLD"}}])
    threads = inputs[4] + [thread("t_40", "RESERVED_CONNECTED_RETRIEVAL_CONTENT", [13, 40])]
    write_jsonl(inputs[1], threads)
    record = freeze(inputs, reserved_samples=[reserved])
    assert {"t_10", "t_40"} <= set(record["payload"]["exclusions"]["thread_ids"])
    assert record["payload"]["reserved_samples"] == [{"path": str(reserved.resolve()),
        "raw_sha256": review.raw_sha256(reserved), "logical_sha256": review.logical_sha256(reserved), "n": 1}]
    run = source_run(inputs, reserved_samples=[reserved])
    review.prepare(inputs[2], run)
    mapping = read_jsonl(inputs[2] / "private_mapping.jsonl")
    assert mapping and not {"t_10", "t_40"} & {row["thread_id"] for row in mapping}
    for artifact in inputs[2].iterdir():
        text = artifact.read_text(encoding="utf-8")
        assert protected_text not in text
        assert "SECRET_RESERVED_GOLD" not in text
        assert "RESERVED_CONNECTED_RETRIEVAL_CONTENT" not in text


@pytest.mark.parametrize("problem", ["missing", "duplicate", "empty", "bad_text"])
def test_reserved_inputs_fail_closed_without_creating_selection(inputs, problem):
    reserved = reserved_sample(inputs)
    paths = [reserved]
    if problem == "missing":
        paths = [reserved.parent / "missing.jsonl"]
    elif problem == "duplicate":
        paths.append(reserved.parent / "." / reserved.name)
    elif problem == "empty":
        write_jsonl(reserved, [])
    else:
        write_jsonl(reserved, [{"text": None, "gold": "PRIVATE"}])
    with pytest.raises(ValueError, match="Reserved samples"):
        freeze(inputs, reserved_samples=paths)
    assert not inputs[2].exists()


def test_reserved_bytes_are_revalidated_before_prediction_reads(inputs):
    reserved = reserved_sample(inputs)
    freeze(inputs, reserved_samples=[reserved])
    with reserved.open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="Frozen input bytes changed"):
        review.prepare(inputs[2], inputs[2].parent / "must-not-read-results")


@pytest.mark.parametrize("stage", ["freeze", "load"])
def test_existing_final_confirmation_requires_explicit_reservation(inputs, stage):
    final = review.Paths.DATA / "verified_confirmation/examples.jsonl"
    if stage == "load":
        freeze(inputs)
    write_jsonl(final, [{"id": "final", "thread_id": "t_9999", "text": "SYNTHETIC_FINAL_PRIVATE_TEXT"}])
    with pytest.raises(ValueError, match="locked confirmation sample"):
        if stage == "freeze":
            freeze(inputs)
        else:
            review.load_lock(inputs[2])


def test_final_confirmation_is_required_in_run_manifest_before_predictions(inputs, monkeypatch):
    final = review.Paths.DATA / "verified_confirmation/examples.jsonl"
    write_jsonl(final, [{"id": "final", "thread_id": "t_9999", "text": "SYNTHETIC_FINAL_PRIVATE_TEXT"}])
    freeze(inputs, reserved_samples=[final])
    run = source_run(inputs)
    original = review.read_jsonl
    def guarded(path):
        assert Path(path).name != "predictions.jsonl", "Predictions opened before reservation validation"
        return original(path)
    monkeypatch.setattr(review, "read_jsonl", guarded)
    with pytest.raises(ValueError, match="locked confirmation sample"):
        review.prepare(inputs[2], run)


@pytest.mark.parametrize("case", ["exact", "diagnostic_superset", "diagnostic_subset", "changed_hash"])
def test_source_run_reservations_must_be_covered_by_locked_diagnostic(inputs, monkeypatch, case):
    first = reserved_sample(inputs, "reserved-first.jsonl")
    second = reserved_sample(inputs, "reserved-second.jsonl", [{"text": "OTHER_SYNTHETIC_PRIVATE_TEXT"}])
    locked_paths = [first, second] if case == "diagnostic_superset" else [first]
    run_paths = [first, second] if case == "diagnostic_subset" else [first]
    freeze(inputs, reserved_samples=locked_paths)
    run = source_run(inputs, reserved_samples=run_paths)
    if case == "changed_hash":
        manifest = read_json(run / "manifest.json")
        manifest["frozen"]["inputs"][str(first)] = "incorrect-hash"
        write_json(run / "manifest.json", manifest)
        reseal(run)
    if case in {"exact", "diagnostic_superset"}:
        seal = review.prepare(inputs[2], run)
        assert seal["source"]["reserved_binding"]["comparison"] == case
    else:
        original = review.read_jsonl
        def guarded(path):
            assert Path(path).name != "predictions.jsonl", "Predictions opened before reservation validation"
            return original(path)
        monkeypatch.setattr(review, "read_jsonl", guarded)
        with pytest.raises(ValueError, match="reservation|reserved sample hash"):
            review.prepare(inputs[2], run)


def test_superseded_lock_is_untouched_and_reserved_lock_keeps_seeded_selection(inputs):
    original = freeze(inputs)
    old_path = inputs[2] / review.LOCK_NAME
    original_bytes = old_path.read_bytes()
    reserved = reserved_sample(inputs)
    new_out = inputs[2].parent / "diagnostic-v2"
    protected = review.freeze(inputs[0], inputs[1], new_out, sample_size=1, seed=0, k=2,
                              reserved_samples=[reserved])
    assert protected["payload"]["selected_ids"] == original["payload"]["selected_ids"]
    assert old_path.read_bytes() == original_bytes


def test_freeze_cli_forwards_repeated_reserved_samples(tmp_path, monkeypatch):
    captured = {}
    def mocked_freeze(labels, threads, out, **kwargs):
        captured.update(kwargs)
        return {"payload": {"selected_ids": ["fixture"]}}
    monkeypatch.setattr(review, "freeze", mocked_freeze)
    paths = [tmp_path / "first.jsonl", tmp_path / "second.jsonl"]
    monkeypatch.setattr(sys, "argv", ["review", "freeze", "--labels", str(tmp_path / "labels.jsonl"),
                                      "--out", str(tmp_path / "out"), "--reserved-sample", str(paths[0]),
                                      "--reserved-sample", str(paths[1])])
    review.main()
    assert captured["reserved_samples"] == paths
