"""Confirmation locking must exclude indirect leakage and require real human input."""

import csv
import importlib.util
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

SPEC = importlib.util.spec_from_file_location(
    "verified_sampling", Path(__file__).resolve().parents[1] / "scripts/26_lock_verified_confirmation.py"
)
sampler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sampler)


def thread(identity, text, tweets=()):
    return {"thread_id": identity, "customer_text": text, "language": "en",
            "turns": [{"tweet_id": value} for value in tweets],
            "brand_replies": [{"text": "Historical answer MUST NOT appear in human packet"}]}


@pytest.fixture
def registry(tmp_path):
    corpus = tmp_path / "corpus.jsonl"
    write_jsonl(corpus, [
        thread("fresh1", "The radio keeps playing after I stop the song", [101]),
        thread("fresh2", "Which country offers discounted memberships for families?", [102]),
        thread("fresh3", "An album release from my band has the wrong artist attached", [103]),
    ])
    exposures = []
    for identity, count in sampler.REQUIRED_EXPOSURES.items():
        source = tmp_path / f"{identity}.jsonl"
        n = count or 1
        write_jsonl(source, [{"thread_id": f"seen-{identity}-{i}", "text": f"Already seen example {i}",
                              "gold": {"intent": "SECRET_AI_LABEL"}} for i in range(n)])
        exposures.append({"id": identity, "path": source.name, "sha256": sha256(source),
                          "n": n, "state": "locked"})
    path = tmp_path / "registry.json"
    write_json(path, {"version": 1, "known_exposure_inventory_complete": True,
                      "exposure_limitations": ["Unrecorded historical inspections cannot be ruled out."],
                      "corpus": {"path": corpus.name, "sha256": sha256(corpus)}, "exposures": exposures})
    return path


@pytest.fixture
def locked(tmp_path, registry):
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: verified-test\n", encoding="utf-8")
    out = tmp_path / "confirmation"
    sampler.prepare(registry, out, policy, n=2, seed=11)
    return out, policy


def submit(out, policy, **kwargs):
    examples = read_jsonl(out / "examples.jsonl")
    partition = read_json(out / "SAMPLE.lock.json").get("partition")
    data = io.StringIO(newline="")
    writer = csv.DictWriter(data, fieldnames=sampler._packet_fields(partition))
    writer.writeheader()
    for example in examples:
        writer.writerow({"id": example["id"], "text": example["text"], "intent": "other",
                         "should_escalate": "true", "escalation_reason_code": "out_of_scope",
                         "sentiment": "neutral", "notes": "Fixture-only human rationale",
                         "annotator": "fixture-reviewer", "label_source": "human",
                         **({"scenario_setup": sampler._scenario_setup(example)} if partition == "challenge" else {})})
    submission = out / "fixture-filled.csv"
    submission.write_bytes(data.getvalue().encode("utf-8"))
    options = {"out": out, "submission": submission, "reviewer_id": "fixture-reviewer",
               "reviewed_at": datetime.now(UTC).isoformat(), "policy": policy,
               "attest_independent_human_labeling": True, **kwargs}
    return options


def test_components_exclude_transitive_overlap_and_selected_components():
    threads = [thread("a", "exposed", [1, 2]), thread("b", "intermediary", [2, 3]),
               thread("c", "otherwise unrelated customer issue", [3, 4]),
               thread("d", "A standalone eligible question", [5]),
               thread("e", "Completely distinct language and query", [5])]
    seen = [{"thread_id": "a", "text": "exposed"}]
    chosen = sampler.select_examples(threads, seen, n=1, seed=4)
    assert chosen[0]["thread_id"] in {"d", "e"}
    with pytest.raises(ValueError, match="Insufficient independent"):
        sampler.select_examples(threads, seen, n=2, seed=4)


def test_fuzzy_exclusion_is_casefold_and_threshold_85():
    seen = [{"thread_id": "old", "text": "My saved playlist disappeared after I updated my phone"}]
    threads = [thread("duplicate", "MY saved playlist disappeared after I updated the phone"),
               thread("independent", "Can a family plan include people living abroad?")]
    assert sampler.select_examples(threads, seen, 1, 5)[0]["thread_id"] == "independent"


def test_prefixed_opener_ids_join_components_even_when_missing_from_turns():
    threads = [{**thread("t_1", "Previously inspected root", [2]), "opener_tweet_id": 1},
               {**thread("t_2", "A very different-looking continuation", [3]), "opener_tweet_id": 2},
               thread("t_3", "Indirect continuation with omitted opener field", [4]),
               thread("t_99", "Unrelated playlist creation request", [100])]
    seen = [{"thread_id": "t_1", "text": "Previously inspected root"}]
    assert sampler.select_examples(threads, seen, 1, 3)[0]["thread_id"] == "t_99"
    with pytest.raises(ValueError, match="Insufficient independent"):
        sampler.select_examples(threads, seen, 2, 3)


@pytest.mark.parametrize("change", ["missing", "initialized", "hash", "count", "attestation", "corpus",
                                    "absolute_attestation", "limits_missing", "limits_type", "limits_empty_entry"])
def test_registry_fails_closed(registry, change):
    value = read_json(registry)
    if change == "missing":
        value["exposures"].pop()
    elif change == "initialized":
        value["exposures"][-1]["state"] = "initialized"
    elif change == "hash":
        value["exposures"][0]["sha256"] = "0" * 64
    elif change == "count":
        value["exposures"][-1]["n"] = 79
    elif change == "attestation":
        value["known_exposure_inventory_complete"] = False
    elif change == "absolute_attestation":
        value["all_inspected_sets_included"] = True
    elif change == "limits_missing":
        value.pop("exposure_limitations")
    elif change == "limits_type":
        value["exposure_limitations"] = "Unrecorded examples might exist"
    elif change == "limits_empty_entry":
        value["exposure_limitations"] = [""]
    else:
        value["corpus"]["sha256"] = "0" * 64
    write_json(registry, value)
    with pytest.raises(ValueError):
        sampler.load_registry(registry)


def test_packet_is_blank_without_replies_or_ai_labels_and_lock_is_nonreplaceable(locked, registry):
    out, policy = locked
    packet = (out / "human_labels.csv").read_text(encoding="utf-8")
    assert "SECRET_AI_LABEL" not in packet and "Historical answer" not in packet
    rows = list(csv.DictReader(io.StringIO(packet)))
    assert all(not row["intent"] and not row["annotator"] for row in rows)
    lock = read_json(out / "SAMPLE.lock.json")
    assert lock["exposure_limitations"] == read_json(registry)["exposure_limitations"]
    assert "recorded/reconstructed" in lock["population"] and "unrecorded historical exposure" in lock["limitations"]
    with pytest.raises(ValueError, match="replace"):
        sampler.prepare(registry, out, policy, n=2)
    with pytest.raises(FileNotFoundError):
        sampler.validate_confirmation(out / "labels.jsonl", policy, expected_n=2)


def test_import_preserves_submission_and_validates_exact_bindings(locked):
    out, policy = locked
    options = submit(out, policy)
    original = options["submission"].read_bytes()
    review = sampler.import_labels(**options)
    assert (out / "submitted_human_labels.csv").read_bytes() == original
    assert review["reviewer_id"] == "fixture-reviewer" and review["ai_labels_visible"] is False
    assert sampler.validate_confirmation(out / "labels.jsonl", policy, expected_n=2) == review
    with pytest.raises(ValueError, match="count"):
        sampler.validate_confirmation(out / "labels.jsonl", policy)
    with pytest.raises(ValueError, match="replace"):
        sampler.import_labels(**options)


@pytest.mark.parametrize("change", ["labels", "policy", "submission", "examples", "chronology"])
def test_mutated_or_posthoc_review_fails(locked, change):
    out, policy = locked
    sampler.import_labels(**submit(out, policy))
    paths = {"labels": out / "labels.jsonl", "policy": policy,
             "submission": out / "submitted_human_labels.csv", "examples": out / "examples.jsonl"}
    if change == "chronology":
        review = read_json(out / "LABEL_REVIEW.json")
        write_json(out / "INFERENCE_STARTED.json", {"started_at": review["reviewed_at"],
                                                    "labels_sha256": review["labels_sha256"]})
    else:
        paths[change].write_bytes(paths[change].read_bytes() + b"\n")
    with pytest.raises(ValueError):
        sampler.validate_confirmation(out / "labels.jsonl", policy, expected_n=2)


@pytest.mark.parametrize("change", ["no_attestation", "future", "before_lock", "already_inferred", "ai_labels"])
def test_import_rejects_incomplete_or_unverified_labels(locked, change):
    out, policy = locked
    options = submit(out, policy)
    if change == "no_attestation":
        options["attest_independent_human_labeling"] = False
    elif change == "future":
        options["reviewed_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    elif change == "before_lock":
        options["reviewed_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    elif change == "already_inferred":
        write_json(out / "INFERENCE_STARTED.json", {"started_at": datetime.now(UTC).isoformat()})
    else:
        submission = options["submission"]
        submission.write_bytes(submission.read_bytes().replace(b",human", b",ai"))
    with pytest.raises(ValueError):
        sampler.import_labels(**options)
    assert not (out / "labels.jsonl").exists()


def test_valid_first_inference_can_be_validated_again(locked):
    out, policy = locked
    review = sampler.import_labels(**submit(out, policy))
    write_json(out / "INFERENCE_STARTED.json", {"started_at": datetime.now(UTC).isoformat(),
                                                "labels_sha256": review["labels_sha256"]})
    assert sampler.validate_confirmation(out / "labels.jsonl", policy, 2)["n"] == 2


def test_calibration_bootstraps_without_circular_partition_requirements(tmp_path, registry):
    value = read_json(registry)
    value["exposures"] = [entry for entry in value["exposures"] if entry["id"] in sampler.PRIOR_EXPOSURES]
    write_json(registry, value)
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: fixture\n", encoding="utf-8")
    out = tmp_path / "calibration"
    lock = sampler.prepare_calibration(registry, out, policy, n=2)
    assert lock["partition"] == "calibration"
    assert "AI labels require explicit attribution" in lock["status"]
    assert all(row["split"] == "calibration" and row["id"].startswith("vc5_")
               for row in read_jsonl(out / "examples.jsonl"))
    with pytest.raises(ValueError, match="omits"):
        sampler.prepare(registry, tmp_path / "confirmation", policy, n=1)
    with pytest.raises(ValueError, match="replace"):
        sampler.prepare_calibration(registry, out, policy, n=2)


@pytest.fixture
def challenge_inputs(tmp_path, registry):
    value = read_json(registry)
    value["exposures"] = [entry for entry in value["exposures"] if entry["id"] != "verified_challenge"]
    write_json(registry, value)
    policy = tmp_path / "challenge_policy.yaml"
    policy.write_text("version: fixture\n", encoding="utf-8")
    cases = tmp_path / "authored_cases.jsonl"
    rows = [
        {"id": "risk", "text": "A stranger accessed my private account using credentials I never shared.",
         "origin": "synthetic", "category": "risk_morphology"},
        {"id": "mixed", "text": "I enjoy recommendations but this episode refuses to play with no error.",
         "origin": "synthetic", "category": "mixed_intent"},
        {"id": "missing", "text": "Which country offers discounted memberships for families?",
         "origin": "real", "thread_id": "fresh2", "category": "missing_context"},
        {"id": "known", "text": "My Android phone has version 15 installed and only downloaded albums stutter.",
         "origin": "synthetic", "category": "known_context"},
        {"id": "ops", "text": "Where is the button for creating a playlist?",
         "origin": "synthetic", "category": "operational_failure", "setup": {"inject": "provider_timeout"}},
    ]
    write_jsonl(cases, rows)
    return {"exposure_registry": registry, "out": tmp_path / "challenge", "policy": policy,
            "cases": cases, "author_id": "fixture-AI-author", "author_type": "ai", "n": 5,
            "attest_independent_authoring": True}


def test_challenge_import_preserves_authorship_and_human_setup_review(challenge_inputs):
    args = challenge_inputs
    original = args["cases"].read_bytes()
    lock = sampler.prepare_challenge(**args)
    assert lock["author_type"] == "ai" and lock["origin_counts"] == {"synthetic": 4, "real": 1}
    assert lock["partition"] == "challenge" and "not a representative coverage" in lock["limitations"]
    assert (args["out"] / "submitted_challenge_cases.jsonl").read_bytes() == original
    packet = (args["out"] / "human_labels.csv").read_text(encoding="utf-8")
    assert "provider_timeout" in packet and "risk_morphology" not in packet and "fixture-AI-author" not in packet
    sampler.import_labels(**submit(args["out"], args["policy"]))
    assert sampler.validate_challenge(args["out"] / "labels.jsonl", args["policy"], expected_n=5)["n"] == 5
    with pytest.raises(ValueError, match="Expected confirmation partition"):
        sampler.validate_confirmation(args["out"] / "labels.jsonl", args["policy"], expected_n=5)


@pytest.mark.parametrize("change", ["unknown_origin", "fake_real", "overlap", "prior_fuzzy",
                                    "no_calibration", "no_category", "no_setup", "no_attestation", "ai_label",
                                    "setup_labels", "unrelated_setup"])
def test_challenge_rejects_unfounded_or_leaking_cases(challenge_inputs, change):
    args = challenge_inputs
    rows = read_jsonl(args["cases"])
    if change == "unknown_origin":
        rows[0]["origin"] = "human"
    elif change == "fake_real":
        rows[2]["text"] += " invented"
    elif change == "overlap":
        registry = read_json(args["exposure_registry"])
        source = args["exposure_registry"].parent / registry["exposures"][0]["path"]
        write_jsonl(source, [{"thread_id": "fresh2", "text": "Different wording, same conversation"}])
        registry["exposures"][0]["sha256"] = sha256(source)
        write_json(args["exposure_registry"], registry)
    elif change == "prior_fuzzy":
        rows[0]["text"] = "Already seen example 0"
    elif change == "no_calibration":
        registry = read_json(args["exposure_registry"])
        registry["exposures"] = [row for row in registry["exposures"] if row["id"] != "verified_calibration"]
        write_json(args["exposure_registry"], registry)
    elif change == "no_category":
        rows[0]["category"] = "known_context"
    elif change == "no_setup":
        rows[-1].pop("setup")
    elif change == "no_attestation":
        args["attest_independent_authoring"] = False
    elif change == "setup_labels":
        rows[-1]["setup"] = {"gold": {"intent": "other", "should_escalate": True}}
    elif change == "unrelated_setup":
        rows[0]["setup"] = {"inject": "provider_timeout"}
    else:
        rows[0]["gold"] = {"should_escalate": True}
    write_jsonl(args["cases"], rows)
    with pytest.raises(ValueError):
        sampler.prepare_challenge(**args)
    assert not args["out"].exists()


@pytest.mark.parametrize("paired", [True, False])
def test_synthetic_contrast_pairs_are_explicit_and_not_independent(challenge_inputs, paired):
    args = challenge_inputs
    rows = read_jsonl(args["cases"])
    rows[3]["contrast_pair_id"] = "known-versus-missing"
    variant = {**rows[3], "id": "contrast", "text": rows[3]["text"].replace("15", "14")}
    if not paired:
        variant.pop("contrast_pair_id")
    rows.append(variant)
    write_jsonl(args["cases"], rows)
    args["n"] = 6
    if paired:
        lock = sampler.prepare_challenge(**args)
        assert lock["contrast_group_count"] == 1 and "paired cases dependent" in lock["limitations"]
    else:
        with pytest.raises(ValueError, match="contrast pair"):
            sampler.prepare_challenge(**args)
