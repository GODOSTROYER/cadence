"""Prepare blind review, import external ratings, and reproduce Verified evidence offline."""
from __future__ import annotations

import argparse
import importlib.util
import shutil
import tempfile
from pathlib import Path

import yaml

from cadence.config import Paths
from cadence.eval.archive import resolve_input
from cadence.eval.provenance import sha256
from cadence.eval.verified import (
    RUBRIC_VERSION,
    acceptance,
    challenge_outcomes,
    coverage,
    human_agreement,
    paired_useful,
    raw_sha256,
    review_packet,
    runtime,
    validate_ratings,
)
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def verified_execution(directory):
    manifest = read_json(directory / "manifest.json")
    frozen = manifest["frozen"]
    for name, digest in read_json(directory / "EXECUTION.json")["artifacts"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Changed execution artifact: " + name)
    for name, digest in frozen["inputs"].items():
        resolve_input(directory, name, digest)
    # Refuse to silently run newer metric/import/validation semantics against an
    # older rubric identity. Reproduce from the matching checkout if these change.
    evaluators = ("src/cadence/config.py", "src/cadence/eval/verified.py", "src/cadence/eval/metrics.py", "src/cadence/eval/agreement.py",
                  "src/cadence/eval/review.py", "src/cadence/eval/archive.py", "src/cadence/eval/provenance.py",
                  "src/cadence/utils/io.py", "scripts/26_lock_verified_confirmation.py", "analysis_tools/reproduce_verified.py")
    for name in evaluators:
        if frozen["inputs"].get(name) != sha256(Paths.ROOT / name):
            raise ValueError("Evaluator implementation changed; reproduce from this run's matching source checkout: " + name)
    labels = read_jsonl(resolve_input(directory, frozen["labels"], frozen["inputs"][frozen["labels"]]))
    label_index = {r["id"]: r for r in labels}
    if len(label_index) != len(labels) or len(set(frozen["message_ids"])) != len(frozen["message_ids"]):
        raise ValueError("Duplicate locked label selection")
    labels = [label_index[i] for i in frozen["message_ids"]]
    rows = read_jsonl(directory / "predictions.jsonl")
    keys = {(r["id"], r["system"]) for r in rows}
    expected = {(g["id"], s) for g in labels for s in frozen["systems"]}
    status = read_json(directory / "status.json")
    if (keys != expected or len(keys) != len(rows) or len(labels) != frozen["n"]
            or status != {"status": "complete", "completed": len(expected), "expected": len(expected)}):
        raise ValueError("Incomplete/duplicate matched population")
    actual_runtime = {s: runtime([r for r in rows if r["system"] == s]) for s in frozen["systems"]}
    if actual_runtime != read_json(directory / "runtime.json"):
        raise ValueError("Runtime does not reproduce from all invocation observations")
    return frozen, labels, rows, actual_runtime


def prepare(directory):
    frozen, _, rows, _ = verified_execution(directory)
    run_id = "verified-" + sha256(directory / "manifest.json")[:16]
    packet, mapping = review_packet(rows, run_id, frozen["seed"])
    selected = set(frozen["human_reply_ids"])
    artifacts = {"blind_packet.jsonl": packet, "blind_mapping.json": mapping,
                 "human_reply_packet.jsonl": [r for r in packet if r["id"] in selected]}
    if (directory / "REVIEW.lock.json").exists():
        verify_packet(directory, frozen, rows)
        return
    for name, content in artifacts.items():
        if (directory / name).exists():
            raise ValueError("Unsealed review artifact already exists: " + name)
        (write_jsonl if name.endswith("jsonl") else write_json)(directory / name, content)
    write_json(directory / "REVIEW.lock.json", {"run_id": run_id, "rubric_version": RUBRIC_VERSION,
        "human_reply_ids": frozen["human_reply_ids"],
        "blinding": "Customer, exact reply and evidence; no identity, decisions, gold labels, or judge scores",
        "artifacts": {name: sha256(directory / name) for name in (
            "manifest.json", "predictions.jsonl", "rubric.json", *artifacts)}})
    print(f"Prepared {len(packet)} blinded replies and {len(artifacts['human_reply_packet.jsonl'])} prespecified human replies. No ratings supplied.")


def verify_packet(directory, frozen, rows):
    record = read_json(directory / "REVIEW.lock.json")
    for name, digest in record["artifacts"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Review context changed: " + name)
    expected_run = "verified-" + sha256(directory / "manifest.json")[:16]
    if record.get("run_id") != expected_run or record.get("human_reply_ids") != frozen["human_reply_ids"]:
        raise ValueError("Review selection differs from frozen run")
    packet, mapping = review_packet(rows, expected_run, frozen["seed"])
    human_packet = [r for r in packet if r["id"] in set(frozen["human_reply_ids"])]
    if (packet != read_jsonl(directory / "blind_packet.jsonl") or mapping != read_json(directory / "blind_mapping.json")
            or human_packet != read_jsonl(directory / "human_reply_packet.jsonl")):
        raise ValueError("Blind packet changed from exact source context")
    return mapping


def import_ratings(directory, submission, reviewer_type):
    frozen, _, rows, _ = verified_execution(directory)
    mapping = verify_packet(directory, frozen, rows)
    expected = {(m["id"], m["system"]) for m in mapping
                if reviewer_type == "ai" or m["id"] in frozen["human_reply_ids"]}
    # Identity is taken only from the supplied completed review, never synthesized.
    ratings = read_jsonl(submission)
    validated = validate_ratings(ratings, mapping, reviewer_type=reviewer_type, expected_keys=expected)
    if len({r["reviewer_id"] for r in validated}) != 1:
        raise ValueError("Use one explicit reviewer per imported study")
    target = directory / f"{reviewer_type}_reviews.jsonl"
    original = directory / f"{reviewer_type}_review_submission.jsonl"
    lock = directory / f"{reviewer_type.upper()}_REVIEW.json"
    if any(p.exists() for p in (target, original, lock)):
        raise ValueError("Reviews are immutable; preserve initial submission and use a new adjudication record")
    shutil.copyfile(submission, original)
    write_jsonl(target, validated)
    write_json(lock, {"reviewer_type": reviewer_type, "reviewer_id": validated[0]["reviewer_id"],
                      "n_messages": len({r["id"] for r in validated}), "n_ratings": len(validated),
                      "provenance": "External reviewer submission; independent human status is the reviewer's explicit attestation" if reviewer_type == "human" else "AI-generated review; never treated as human",
                      "artifacts": {p.name: raw_sha256(p) for p in (original, target, directory / "REVIEW.lock.json")}})
    print(f"Imported {len(validated)} {reviewer_type} ratings without changing their provenance.")


def load_ratings(directory, kind, mapping, frozen):
    path = directory / f"{kind}_reviews.jsonl"
    if not path.exists():
        return None
    record = read_json(directory / f"{kind.upper()}_REVIEW.json")
    for name, digest in record["artifacts"].items():
        if raw_sha256(directory / name) != digest:
            raise ValueError("Review submission/identity changed: " + name)
    expected = {(m["id"], m["system"]) for m in mapping if kind == "ai" or m["id"] in frozen["human_reply_ids"]}
    mapped = validate_ratings(read_jsonl(directory / f"{kind}_review_submission.jsonl"), mapping,
                              reviewer_type=kind, expected_keys=expected)
    if mapped != read_jsonl(path):
        raise ValueError("Review scores or provenance changed during unblinding")
    if (record["reviewer_type"] != kind or {r["reviewer_id"] for r in mapped} != {record["reviewer_id"]}
            or record["n_ratings"] != len(mapped)):
        raise ValueError("Review declaration differs from submitted ratings")
    return mapped


def human_label_status(directory, frozen):
    if frozen["phase"] not in ("confirmation", "challenge"):
        return False
    spec = importlib.util.spec_from_file_location("verified_sampling", Paths.ROOT / "scripts/26_lock_verified_confirmation.py")
    sampler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sampler)
    # Reconstruct exact archived proof instead of requiring today's mutable policy
    # or labeling directory to remain identical to an old confirmation run.
    marker = read_json(directory / "EXECUTION.json").get("label_inference_started")
    if not marker or marker.get("manifest_sha256") != sha256(directory / "manifest.json"):
        raise ValueError("Missing run-bound pre-inference label marker")
    sample_parent = Path(frozen["labels"]).parent.as_posix() + "/"
    with tempfile.TemporaryDirectory(prefix="cadence-label-proof-") as temporary:
        target = Path(temporary)
        for name, digest in frozen["inputs"].items():
            if name.startswith(sample_parent):
                destination = target / name.removeprefix(sample_parent)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(resolve_input(directory, name, digest), destination)
        write_json(target / "INFERENCE_STARTED.json", marker)
        policy = resolve_input(directory, frozen["policy"], frozen["inputs"][frozen["policy"]])
        method = sampler.validate_challenge if frozen["phase"] == "challenge" else sampler.validate_confirmation
        method(target / Path(frozen["labels"]).name, policy, expected_n=frozen["n"])
    return True


def summary(directory, *, challenge_directory=None):
    frozen, labels, rows, runtimes = verified_execution(directory)
    mapping = verify_packet(directory, frozen, rows)
    ratings = load_ratings(directory, "ai", mapping, frozen)
    if ratings is None:
        raise ValueError("All produced replies require completed blinded AI review before quality claims")
    human = load_ratings(directory, "human", mapping, frozen)
    taxonomy_path = resolve_input(directory, "config/intents.yaml", frozen["inputs"]["config/intents.yaml"])
    taxonomy = [r["id"] for r in yaml.safe_load(taxonomy_path.read_text(encoding="utf-8"))["intents"]]
    metrics = {s: coverage(labels, [r for r in rows if r["system"] == s], [r for r in ratings if r["system"] == s], intent_labels=taxonomy)
               for s in frozen["systems"]}
    comparisons = {s: paired_useful(metrics["verified"]["vectors"]["policy_compliant_useful"],
                                    metrics[s]["vectors"]["policy_compliant_useful"], seed=frozen["seed"])
                   for s in frozen["systems"] if s != "verified"} if "verified" in metrics else {}
    for system, m in metrics.items():
        m.pop("vectors")
        useful = m["counts"]["policy_compliant_useful_automatic"]
        runtimes[system]["tokens_per_policy_compliant_useful_reply_known"] = runtimes[system]["tokens_known"] / useful if useful else None
    labels_checked = human_label_status(directory, frozen)
    challenge_ok = False
    challenge_binding = None
    if challenge_directory:
        challenge = summary(challenge_directory)
        other = read_json(challenge_directory / "manifest.json")["frozen"]
        # Exact candidate/model/policy execution dependencies must match. Data/rubric
        # locations may differ but the rubric content hash must be identical.
        execution_names = [n for n in frozen["inputs"] if n.startswith(("src/", "config/"))]
        same = (other["phase"] == "challenge" and other["n"] == 80
                and all(other.get(k) == frozen[k] for k in ("model", "variant", "policy_version", "source_as_of"))
                and all(other["resources"].get(k) == frozen["resources"][k] for k in ("invocation_seconds", "max_network_attempts"))
                and all(other["inputs"].get(n) == frozen["inputs"][n] for n in execution_names))
        challenge_ok = same and challenge["challenge_outcomes"]["all_passed"] and challenge["human_labels_pre_inference"]
        challenge_binding = {"manifest_sha256": sha256(challenge_directory / "manifest.json"),
                             "execution_sha256": sha256(challenge_directory / "EXECUTION.json"),
                             "ai_review_sha256": raw_sha256(challenge_directory / "AI_REVIEW.json")}
    result = {"status": "complete", "phase": frozen["phase"], "policy_version": frozen["policy_version"],
              "n": len(labels), "metrics": metrics, "runtime": runtimes, "paired_usefulness": comparisons,
              "human_labels_pre_inference": labels_checked,
              "human_agreement": human_agreement(human, ratings, seed=frozen["seed"]) if human else None,
              "challenge_binding": challenge_binding}
    if frozen["phase"] == "challenge":
        result["challenge_outcomes"] = challenge_outcomes(labels, [r for r in rows if r["system"] == "verified"],
                                                          [r for r in ratings if r["system"] == "verified"])
    result["acceptance"] = acceptance(metrics, runtimes, comparisons["balanced"], phase=frozen["phase"],
                                      rules=frozen["acceptance"], human_labels=labels_checked,
                                      human_reply_subset=human is not None, challenge_accepted=challenge_ok) if {"verified", "agent", "balanced", "quality"} <= set(metrics) else {
                                          "eligible_for_release_review": False, "promote": False,
                                          "decision": "Development subset; full matched comparison required", "gates": {"all_four_arms": False}}
    result["inputs"] = {name: sha256(directory / name) for name in (
        "manifest.json", "EXECUTION.json", "REVIEW.lock.json", "AI_REVIEW.json")}
    if human:
        result["inputs"]["HUMAN_REVIEW.json"] = sha256(directory / "HUMAN_REVIEW.json")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--action", choices=("prepare-review", "import-review", "summarize", "verify"), default="verify")
    parser.add_argument("--ratings", type=Path)
    parser.add_argument("--reviewer-type", choices=("ai", "human"))
    parser.add_argument("--challenge", type=Path)
    args = parser.parse_args()
    if args.action == "prepare-review":
        prepare(args.experiment)
    elif args.action == "import-review":
        if not args.ratings or not args.reviewer_type:
            parser.error("--ratings and --reviewer-type are required")
        import_ratings(args.experiment, args.ratings, args.reviewer_type)
    else:
        result = summary(args.experiment, challenge_directory=args.challenge)
        path = args.experiment / "summary.json"
        if args.action == "summarize":
            if path.exists() and read_json(path) != result:
                raise ValueError("Existing summary is immutable; use an explicitly named later analysis instead")
            write_json(path, result)
        elif read_json(path) != result:
            raise ValueError("Summary does not reproduce")
        print({"n": result["n"], "eligible_for_release_review": result["acceptance"]["eligible_for_release_review"],
               "promote": False, "new_model_calls": 0})


if __name__ == "__main__":
    main()
