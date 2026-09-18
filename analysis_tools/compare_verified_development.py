"""Re-review archived comparators and fresh Verified replies on development cases.

This is a paired content comparison, not a contemporaneous runtime experiment.
No model calls, old score conversion, human attribution, or promotion occur here.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from cadence.config import Paths
from cadence.eval.archive import resolve_input
from cadence.eval.provenance import sha256
from cadence.eval.verified import (
    RUBRIC,
    coverage,
    index_unique,
    paired_useful,
    review_packet,
    validate_ratings,
)
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

SYSTEMS = ("agent", "quality", "balanced", "verified")
DEFAULT_SEED = 2026091811
LIMITATION = (
    "Inspected development messages; AI policy-v2 labels and new AI reply ratings. "
    "Three comparator outputs are reused unchanged from an earlier policy-v0 run. "
    "Re-scoring their decisions against v2 does not re-run their policy. Runtime and "
    "cost observations come from different runs and instrumentation; they do not "
    "establish a controlled speed or cost improvement. No human agreement or promotion."
)


def verified_execution(directory):
    """Use the original fail-closed execution validator, without its review workflow."""
    path = Paths.ROOT / "analysis_tools/reproduce_verified.py"
    spec = importlib.util.spec_from_file_location("_verified_reproduction", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verified_execution(directory)


def binding(path):
    path = path.resolve()
    return {"path": path.relative_to(Paths.ROOT).as_posix() if path.is_relative_to(Paths.ROOT) else str(path),
            "sha256": sha256(path)}


def bound_path(record):
    path = Paths.ROOT / record["path"]
    if sha256(path) != record["sha256"]:
        raise ValueError("Changed comparison input: " + record["path"])
    return path


def load_sources(candidate, archive, labels):
    frozen, locked_labels, new_rows, fresh_runtime = verified_execution(candidate)
    if (frozen["phase"] != "development" or frozen["policy_version"] != "v2"
            or frozen["systems"] != ["verified"] or frozen["n"] != 80):
        raise ValueError("Requires a sealed 80-message policy-v2 Verified development run")
    if read_jsonl(labels) != locked_labels:
        raise ValueError("Policy-v2 labels differ from the exact candidate population")
    label_record = labels.parent / "LABEL_REVIEW.json"
    review = read_json(label_record)
    if (review.get("label_source") != "ai" or review.get("human_reviewed") is not False
            or review.get("status") != "frozen" or review["labels"]["sha256"] != sha256(labels)
            or review.get("policy", {}).get("sha256") != frozen["inputs"].get("config/policy_v2.json")):
        raise ValueError("Expected explicit frozen AI development label provenance")
    # Reuse the established archive verifier: receipts, old labels, old review and
    # runtime retain their original contract. Nothing from its scores is imported.
    result = subprocess.run([sys.executable, str(Paths.ROOT / "analysis_tools/reproduce_balanced.py"),
                             "--experiment", str(archive.resolve())], cwd=Paths.ROOT,
                            capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Archived comparator verification failed: " + result.stderr[-1500:])
    old_manifest = read_json(archive / "manifest.json")["frozen"]
    old_rows = read_jsonl(archive / "predictions.jsonl")
    if old_manifest["n"] != 80 or set(old_manifest["systems"]) != set(SYSTEMS[:-1]):
        raise ValueError("Expected the complete historical three-arm 80-message study")
    gold = index_unique(locked_labels, ("id",))
    joined = [{**row, "outcome": "success"} for row in old_rows] + new_rows
    keys = index_unique(joined, ("id", "system"))
    if set(keys) != {(r["id"], system) for r in locked_labels for system in SYSTEMS}:
        raise ValueError("Every locked message requires all four source predictions")
    if any(row["input_text"] != gold[(row["id"],)]["text"] for row in joined):
        raise ValueError("Customer context differs between labels and source predictions")
    rubric = read_json(candidate / "rubric.json")
    if rubric != RUBRIC:
        raise ValueError("Use the evaluator matching the candidate's frozen rubric")
    inputs = {"labels": binding(labels), "label_provenance": binding(label_record),
              "archive/ACCEPTANCE.json": binding(archive / "ACCEPTANCE.json")}
    for prefix, directory, seal in (("candidate", candidate, "EXECUTION.json"),
                                    ("archive", archive, "VERIFICATION.json")):
        inputs[f"{prefix}/{seal}"] = binding(directory / seal)
        for name in read_json(directory / seal)["artifacts"]:
            inputs[f"{prefix}/{name}"] = binding(directory / name)
    context = {}
    for name, digest in frozen["inputs"].items():
        if name.startswith("config/knowledge/") or name in ("config/intents.yaml", "config/policy_v2.json"):
            context[name] = resolve_input(candidate, name, digest)
            inputs[name] = binding(context[name])
    inputs["candidate/rubric.json"] = binding(candidate / "rubric.json")
    old_summary = read_json(archive / "summary.json")
    return {"labels": locked_labels, "predictions": joined, "rubric": rubric, "inputs": inputs,
            "context": context, "source_as_of": frozen["source_as_of"],
            "runtime": {"verified_new_run": fresh_runtime["verified"],
                        "archived_original_runs": old_summary["runtime"],
                        "controlled_comparison": False,
                        "note": "Keep schemas separate: archived successful-call totals omit failed-attempt usage. "
                                "The candidate retains its measured cache status; a new run is not necessarily fully fresh."},
            "historical_v0": {"summary": binding(archive / "summary.json"),
                              "acceptance": binding(archive / "ACCEPTANCE.json"),
                              "note": "Original v0 results remain in their archived files; not comparable to v2 totals."}}


def evaluator_bindings():
    return {name: binding(Paths.ROOT / name) for name in (
        "analysis_tools/compare_verified_development.py", "analysis_tools/reproduce_verified.py",
        "analysis_tools/reproduce_balanced.py", "analysis_tools/reproduce_quality.py",
        "src/cadence/eval/verified.py", "src/cadence/eval/review.py", "src/cadence/eval/metrics.py",
        "src/cadence/eval/agreement.py", "src/cadence/eval/archive.py",
        "src/cadence/eval/provenance.py", "src/cadence/config.py", "src/cadence/utils/io.py")}


def prepare(directory, candidate, archive, labels, seed=DEFAULT_SEED):
    if directory.exists() and any(directory.iterdir()):
        raise ValueError("Comparison directory must be empty; existing studies are immutable")
    source = load_sources(candidate, archive, labels)
    inputs = {**source["inputs"], **evaluator_bindings()}
    identity = json.dumps({"inputs": inputs, "seed": seed}, sort_keys=True).encode()
    run_id = "verified-development-" + hashlib.sha256(identity).hexdigest()[:16]
    packet, mapping = review_packet(source["predictions"], run_id, seed)
    directory.mkdir(parents=True, exist_ok=True)
    write_jsonl(directory / "predictions.jsonl", source["predictions"])
    write_jsonl(directory / "labels.jsonl", source["labels"])
    write_jsonl(directory / "blind_packet.jsonl", packet)
    write_json(directory / "blind_mapping.json", mapping)
    write_json(directory / "rubric.json", source["rubric"])
    write_json(directory / "runtime.json", source["runtime"])
    for name, path in source["context"].items():
        target = directory / "context" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    instructions = {
        "run_id": run_id, "reviewer_type": "ai", "rubric": "rubric.json",
        "packet": "blind_packet.jsonl", "current_sources": "context/config/knowledge/v2.json",
        "source_as_of": source["source_as_of"],
        "instructions": "Read only this file, rubric, blind packet and current source snapshots. "
                        "Rate every exact reply anew. Historical evidence supports tone, not current procedures. "
                        "Use all seven flags, all five scores, verdict, response_kind, severity and rationale. "
                        "Retain id, alias, run_id, reply_hash and rubric_version. Add reviewer_id, "
                        "reviewer_type=ai and timezone-aware rated_at. Do not read mapping, labels, "
                        "predictions, source runs, earlier ratings or implementation.",
        "blinding_limit": "Identity, gold labels and old scores are hidden; reply style and evidence may reveal architecture.",
        "failure_note": "Some replies may be safe fallback text; rate visible content only. Execution failures remain failures in metrics."
    }
    write_json(directory / "REVIEW_INSTRUCTIONS.json", instructions)
    artifacts = {p.relative_to(directory).as_posix(): {"sha256": sha256(p)}
                 for p in sorted(directory.rglob("*")) if p.is_file()}
    write_json(directory / "COMPARISON.lock.json", {
        "version": "verified-development-comparison-v1", "phase": "development", "seed": seed,
        "run_id": run_id, "n": len(source["labels"]), "n_replies": len(packet), "systems": list(SYSTEMS),
        "inputs": inputs, "artifacts": artifacts, "historical_v0": source["historical_v0"],
        "source_as_of": source["source_as_of"], "limitation": LIMITATION, "promote": False})
    return {"n_messages": len(source["labels"]), "n_replies": len(packet), "new_model_calls": 0}


def verify_prepared(directory):
    lock = read_json(directory / "COMPARISON.lock.json")
    if lock["phase"] != "development" or lock["promote"] is not False or lock["systems"] != list(SYSTEMS):
        raise ValueError("Unsupported comparison contract")
    for record in lock["inputs"].values():
        bound_path(record)
    for name, record in lock["artifacts"].items():
        path = directory / name
        if sha256(path) != record["sha256"]:
            raise ValueError("Changed prepared comparison artifact: " + name)
    predictions = read_jsonl(directory / "predictions.jsonl")
    packet, mapping = review_packet(predictions, lock["run_id"], lock["seed"])
    if packet != read_jsonl(directory / "blind_packet.jsonl") or mapping != read_json(directory / "blind_mapping.json"):
        raise ValueError("Review packet differs from exact joined predictions")
    if len(packet) != lock["n_replies"] or len(read_jsonl(directory / "labels.jsonl")) != lock["n"]:
        raise ValueError("Locked review counts differ")
    return lock, mapping


def import_ratings(directory, submissions):
    lock, mapping = verify_prepared(directory)
    if any((directory / name).exists() for name in ("ai_reviews.jsonl", "AI_REVIEW.json", "submissions")):
        raise ValueError("Ratings are immutable; create a separate adjudication study")
    combined = [r for path in submissions for r in read_jsonl(path)]
    expected = {(m["id"], m["system"]) for m in mapping}
    validated = validate_ratings(combined, mapping, reviewer_type="ai", expected_keys=expected)
    if not validated:
        raise ValueError("No submitted reply ratings")
    target = directory / "submissions"
    target.mkdir()
    for i, path in enumerate(submissions):
        shutil.copyfile(path, target / f"{i:03}.jsonl")
    write_jsonl(directory / "ai_reviews.jsonl", validated)
    paths = [directory / "ai_reviews.jsonl", directory / "COMPARISON.lock.json", *sorted(target.glob("*.jsonl"))]
    write_json(directory / "AI_REVIEW.json", {"run_id": lock["run_id"], "reviewer_type": "ai",
        "reviewer_ids": sorted({r["reviewer_id"] for r in validated}), "n_ratings": len(validated),
        "provenance": "New external AI review of exact replies under one frozen rubric; human review pending.",
        "artifacts": {p.relative_to(directory).as_posix(): sha256(p) for p in paths}})
    return {"n_ratings": len(validated), "reviewer_type": "ai", "new_model_calls": 0}


def summarize(directory):
    lock, mapping = verify_prepared(directory)
    record = read_json(directory / "AI_REVIEW.json")
    for name, digest in record["artifacts"].items():
        if sha256(directory / name) != digest:
            raise ValueError("Changed external AI review: " + name)
    submitted = [r for p in sorted((directory / "submissions").glob("*.jsonl")) for r in read_jsonl(p)]
    ratings = validate_ratings(submitted, mapping, reviewer_type="ai",
                               expected_keys={(m["id"], m["system"]) for m in mapping})
    if ratings != read_jsonl(directory / "ai_reviews.jsonl"):
        raise ValueError("Ratings changed while unblinding")
    if (record["run_id"] != lock["run_id"] or record["reviewer_type"] != "ai"
            or record["n_ratings"] != len(ratings)
            or record["reviewer_ids"] != sorted({r["reviewer_id"] for r in ratings})):
        raise ValueError("Review declaration differs from submissions")
    labels, rows = read_jsonl(directory / "labels.jsonl"), read_jsonl(directory / "predictions.jsonl")
    taxonomy = yaml.safe_load((directory / "context/config/intents.yaml").read_text(encoding="utf-8"))
    metrics = {system: coverage(labels, [r for r in rows if r["system"] == system],
                [r for r in ratings if r["system"] == system], intent_labels=[r["id"] for r in taxonomy["intents"]])
               for system in SYSTEMS}
    paired = {system: paired_useful(metrics["verified"]["vectors"]["policy_compliant_useful"],
                  metrics[system]["vectors"]["policy_compliant_useful"], seed=lock["seed"])
              for system in SYSTEMS[:-1]}
    for metric in metrics.values():
        metric.pop("vectors")
    return {"phase": "development", "policy_version": "v2", "n": len(labels), "metrics": metrics,
            "paired_content_usefulness": paired, "runtime": read_json(directory / "runtime.json"),
            "historical_v0": lock["historical_v0"], "human_agreement": None, "human_review_pending": True,
            "promote": False, "limitation": LIMITATION, "new_model_calls": 0,
            "input_hashes": {name: sha256(directory / name) for name in ("COMPARISON.lock.json", "AI_REVIEW.json")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "import", "summarize", "verify"))
    parser.add_argument("--out", type=Path, default=Paths.ROOT / "results/verified_development_comparison")
    parser.add_argument("--candidate-dir", type=Path, default=Paths.ROOT / "results/verified_dev")
    parser.add_argument("--archive-dir", type=Path, default=Paths.ROOT / "results/balanced_confirmation")
    parser.add_argument("--labels", type=Path, default=Paths.ROOT / "data/verified_dev/labels.jsonl")
    parser.add_argument("--ratings", type=Path, nargs="+")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    if args.action == "prepare":
        result = prepare(args.out, args.candidate_dir, args.archive_dir, args.labels, args.seed)
    elif args.action == "import":
        if not args.ratings:
            parser.error("--ratings requires one or more completed AI review submissions")
        result = import_ratings(args.out, args.ratings)
    elif args.action == "summarize":
        result = summarize(args.out)
        path = args.out / "summary.json"
        if path.exists() and read_json(path) != result:
            raise ValueError("Existing summary is immutable")
        write_json(path, result)
    else:
        verify_prepared(args.out)
        has_reviews = (args.out / "AI_REVIEW.json").exists()
        if any((args.out / name).exists() for name in ("ai_reviews.jsonl", "submissions", "summary.json")) and not has_reviews:
            raise ValueError("Unsealed review artifacts or summary")
        if has_reviews:
            result = summarize(args.out)
            if (args.out / "summary.json").exists() and read_json(args.out / "summary.json") != result:
                raise ValueError("Summary does not reproduce")
        result = {"verified": True, "new_model_calls": 0, "promote": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
