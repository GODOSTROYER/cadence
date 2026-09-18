"""Score sealed development veto outputs using completed blinded AI ratings.

No inference, routing overlay, source refresh or candidate execution occurs here.
The historical control outputs remain immutable. AI review never becomes human
review, and replayed controls have no fresh runtime or deployment claim.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import yaml

from cadence.config import Paths
from cadence.eval.archive import resolve_input
from cadence.eval.provenance import sha256
from cadence.eval.verified import RUBRIC, coverage, review_packet, timestamp, validate_ratings
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl

VERSION = "verified-control-quality-v1"
CONTROLS = ("balanced_replay", "independent_policy_veto", "prerequisite_veto", "combined_veto")
SEALED_ARTIFACTS = ("manifest.json", "predictions.jsonl", "routing_summary.json", "rubric.json",
                    "blind_packet.jsonl", "blind_mapping.json")
ANALYSIS_SOURCES = (
    "analysis_tools/summarize_verified_controls.py", "src/cadence/eval/verified.py",
    "src/cadence/eval/metrics.py", "src/cadence/eval/agreement.py", "src/cadence/eval/review.py",
    "src/cadence/eval/archive.py", "src/cadence/eval/provenance.py", "src/cadence/utils/io.py",
    "src/cadence/config.py", "pyproject.toml",
)
OUTPUTS = ("quality_summary.json", "ai_reviews.jsonl", "AI_REVIEW.json")


def _member(directory: Path, name: str) -> Path:
    """Only declared artifacts inside this run may enter its execution seal."""
    path = directory / name
    if Path(name).is_absolute() or not path.resolve().is_relative_to(directory.resolve()):
        raise ValueError("Artifact path escapes the control run")
    return path


def verified_inputs(directory, *, root=Paths.ROOT):
    execution = read_json(directory / "EXECUTION.json")
    if (set(execution.get("artifacts", {})) != set(SEALED_ARTIFACTS)
            or execution.get("live_model_calls") != 0 or execution.get("promotion") is not False):
        raise ValueError("Expected the sealed offline development control execution")
    for name, expected in execution["artifacts"].items():
        if sha256(_member(directory, name)) != expected:
            raise ValueError("Frozen control artifact changed: " + name)
    frozen = read_json(directory / "manifest.json")["frozen"]
    if (frozen.get("version") != "balanced-development-veto-v1" or frozen.get("phase") != "development"
            or frozen.get("controls") != list(CONTROLS) or frozen.get("promotion") is not False
            or frozen.get("scoring_policy") != "v2" or frozen.get("fresh_model_calls") != 0):
        raise ValueError("This analysis requires the frozen v2-policy development veto controls")
    # Resolve archived bytes, never run today's actions/policy/extractor against old outputs.
    resolved = {name: resolve_input(directory, name, expected, root=root)
                for name, expected in frozen["inputs"].items()}
    labels_hash = frozen["frame_source"]["labels_sha256"]
    label_names = [name for name, expected in frozen["inputs"].items()
                   if name.endswith("/labels.jsonl") and expected == labels_hash]
    if len(label_names) != 1:
        raise ValueError("Frozen frame source must identify one exact common development label set")
    labels_name = label_names[0]
    labels = read_jsonl(resolved[labels_name])
    ids = [row["id"] for row in labels]
    if (not labels or len(ids) != len(set(ids)) or len(labels) != frozen["n"]
            or any(row.get("split") != "development" for row in labels)):
        raise ValueError("Expected the complete unique frozen development population")
    rows = read_jsonl(directory / "predictions.jsonl")
    keys = [(row["id"], row["system"]) for row in rows]
    if len(keys) != len(set(keys)) or set(keys) != {(identity, control) for identity in ids for control in CONTROLS}:
        raise ValueError("Missing or duplicate control outputs")
    # The packet is reconstructed from stored exact replies, not from any current agent.
    run_id = "ablation-" + sha256(directory / "manifest.json")[:16]
    packet, mapping = review_packet(rows, run_id, frozen["seed"])
    if (packet != read_jsonl(directory / "blind_packet.jsonl")
            or mapping != read_json(directory / "blind_mapping.json")):
        raise ValueError("Blind review mapping or customer/reply/evidence context changed")
    if read_json(directory / "rubric.json") != RUBRIC:
        raise ValueError("Current evaluator does not implement the exact frozen rubric")
    taxonomy = yaml.safe_load(resolved["config/intents.yaml"].read_text(encoding="utf-8"))
    return frozen, labels, rows, mapping, [row["id"] for row in taxonomy["intents"]], labels_name


def calculate(directory, submission, *, root=Paths.ROOT):
    frozen, labels, rows, mapping, taxonomy, labels_name = verified_inputs(directory, root=root)
    ratings = read_jsonl(submission)
    for row in ratings:
        for field in ("reviewer_id", "rationale"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("A nonempty reviewer identity and rationale are required")
        if not timestamp(frozen["created_at"]) <= timestamp(row.get("rated_at")) <= datetime.now(UTC):
            raise ValueError("AI rating must follow the frozen packet and cannot be future-dated")
    expected = {(row["id"], row["system"]) for row in mapping}
    unblinded = validate_ratings(ratings, mapping, reviewer_type="ai", expected_keys=expected)
    unblinded.sort(key=lambda row: (row["id"], row["system"]))
    metrics = {}
    routing = read_json(directory / "routing_summary.json")["controls"]
    for control in CONTROLS:
        result = coverage(labels, [row for row in rows if row["system"] == control],
                          [row for row in unblinded if row["system"] == control], intent_labels=taxonomy)
        result.pop("vectors")
        for field in ("n", "automatic", "required", "missed_escalations", "unnecessary_escalations", "failed"):
            if result["counts"][field] != routing[control][field]:
                raise ValueError("Quality analysis changed a frozen routing count: " + control + "/" + field)
        metrics[control] = result
    sources = {name: sha256(root / name) for name in ANALYSIS_SOURCES}
    inputs = {name: sha256(directory / name) for name in (*SEALED_ARTIFACTS, "EXECUTION.json", "INPUT_ARCHIVE.json")}
    inputs["blind_ai_ratings_submission"] = sha256(submission)
    summary = {
        "version": VERSION, "status": "complete", "phase": "development", "scoring_policy": "v2",
        "n": len(labels), "n_predictions": len(rows), "n_ratings": len(unblinded), "metrics": metrics,
        "reviewer_type": "ai", "reviewer_ids": sorted({row["reviewer_id"] for row in unblinded}),
        "human_review_complete": False, "human_agreement": None,
        "promotion": False, "fresh_model_calls": 0, "fresh_latency_ms": None, "fresh_cost": None,
        "source_frames": {key: frozen["frame_source"].get(key) for key in
                          ("source_run", "source_model", "source_frozen_at", "source_as_of", "frames_sha256")},
        "labels": {"path": labels_name, "sha256": frozen["inputs"][labels_name]},
        "inputs": inputs, "analysis_sources": sources,
        "limitations": [
            "AI review of already inspected development cases; no independent human ratings or unseen confirmation.",
            "Veto-only counterfactuals over fixed recorded outputs; cannot recover old escalations or prove a deployable optimum.",
            "Original frame/policy/answer versions stay frozen; no replay with the current candidate or newer request frames.",
            "No fresh end-to-end latency or cost; archived source runtime is not a new measurement.",
        ],
    }
    provenance = {
        "version": VERSION, "reviewer_type": "ai", "reviewer_ids": summary["reviewer_ids"],
        "n_messages": len(labels), "n_ratings": len(unblinded), "human_review_complete": False,
        "ratings_completed_at": max(unblinded, key=lambda row: timestamp(row["rated_at"]))["rated_at"],
        "provenance": "AI submission bound to sealed blinded customer/reply/evidence context; reviewer attribution is preserved, never human ratings.",
        "score_reuse": "Any exact-context deduplication remains the reviewer's disclosed AI review method; no ratings synthesized here.",
        "hash_convention": "SHA-256, CRLF normalized to LF for project text extensions; reply hashes are exact UTF-8.",
        "inputs": inputs, "analysis_sources": sources, "promotion": False,
    }
    return summary, unblinded, provenance


def summarize(directory, submission=None, *, check=False, root=Paths.ROOT):
    directory = Path(directory)
    submission = Path(submission) if submission is not None else directory / "blind_ai_ratings.jsonl"
    if not check and any((directory / name).exists() for name in OUTPUTS):
        raise ValueError("Quality artifacts are immutable; use --check to reproduce an existing analysis")
    summary, unblinded, provenance = calculate(directory, submission, root=root)
    if check:
        record = read_json(directory / "AI_REVIEW.json")
        for name, expected in record.get("artifacts", {}).items():
            if name not in OUTPUTS[:-1] or sha256(_member(directory, name)) != expected:
                raise ValueError("Quality artifact changed: " + name)
        expected_artifacts = {name: sha256(directory / name) for name in OUTPUTS[:-1]}
        if (record != {**provenance, "artifacts": expected_artifacts}
                or read_json(directory / "quality_summary.json") != summary
                or read_jsonl(directory / "ai_reviews.jsonl") != unblinded):
            raise ValueError("Quality counts, reviewer provenance or analysis dependencies do not reproduce")
        for name, expected in provenance["analysis_sources"].items():
            if sha256(directory / "quality_analysis_snapshot" / name) != expected:
                raise ValueError("Archived quality-analysis source changed: " + name)
    else:
        # New analysis sources are separate from the original execution snapshot.
        for name, expected in provenance["analysis_sources"].items():
            target = directory / "quality_analysis_snapshot" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write((root / name).read_bytes())
            if sha256(target) != expected:
                raise ValueError("Analysis source changed during snapshot: " + name)
        write_json(directory / "quality_summary.json", summary)
        write_jsonl(directory / "ai_reviews.jsonl", unblinded)
        write_json(directory / "AI_REVIEW.json", {
            **provenance, "artifacts": {name: sha256(directory / name) for name in OUTPUTS[:-1]}})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--ratings", type=Path, help="Defaults to the run's blind_ai_ratings.jsonl")
    parser.add_argument("--check", action="store_true", help="Read-only exact reproduction")
    args = parser.parse_args()
    result = summarize(args.experiment, args.ratings, check=args.check)
    print({"n": result["n"], "n_ratings": result["n_ratings"], "reviewer_type": "ai",
           "new_model_calls": 0, "promotion": False, "check": args.check})


if __name__ == "__main__":
    main()
