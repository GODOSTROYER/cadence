"""Offline development controls; no model calls, deployment or promotion.

First export the independent request-extraction stage from a completed Verified
development run. Then replay all three veto overlays against frozen Balanced
outputs, alongside an unchanged-output old/new-policy routing rescore.
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from cadence.config import Paths
from cadence.eval.archive import archive_inputs, resolve_input, snapshot_dependencies
from cadence.eval.provenance import sha256
from cadence.eval.verified import RUBRIC, review_packet
from cadence.eval.verified_ablations import (
    ACTIONS,
    CONTROLS,
    VERSION,
    customer_text,
    development_labels,
    digest,
    overlay,
    policy_rescore,
    render,
    routing_counts,
    validate_frame_record,
)
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def now():
    return datetime.now(UTC).isoformat()


def _fresh_output(out):
    if out.exists() and any(out.iterdir()):
        raise ValueError("Use an empty output directory; diagnostic records are immutable")
    out.mkdir(parents=True, exist_ok=True)


def export_frames(run, labels_path, out):
    labels = read_jsonl(labels_path)
    development_labels(labels)
    manifest = read_json(run / "manifest.json")
    frozen = manifest["frozen"]
    if frozen["phase"] != "development" or "verified" not in frozen["systems"]:
        raise ValueError("Frames must come from a completed Verified DEVELOPMENT run")
    status = read_json(run / "status.json")
    if status != {"status": "complete", "completed": frozen["n"] * len(frozen["systems"]),
                  "expected": frozen["n"] * len(frozen["systems"])}:
        raise ValueError("Do not extract from a partial or failed-to-seal run")
    for name, expected in read_json(run / "EXECUTION.json")["artifacts"].items():
        if sha256(run / name) != expected:
            raise ValueError("Changed source execution artifact: " + name)
    # This exact stage receives only customer text and policy; no answers/history.
    # Refuse a changed implementation rather than assume every field called frame
    # came from that experimental design.
    for name in ("src/cadence/agent/verified.py", "src/cadence/agent/request_frame.py",
                 "src/cadence/agent/policy_v2.py", "config/policy_v2.json"):
        expected = frozen["inputs"][name]
        resolve_input(run, name, expected)
        if sha256(Paths.ROOT / name) != expected:
            raise ValueError("Extraction implementation changed; export using the matching checkout: " + name)
    source = [r for r in read_jsonl(run / "predictions.jsonl") if r["system"] == "verified"]
    by_id = {row["id"]: row for row in source}
    if len(source) != len(by_id) or set(by_id) != {row["id"] for row in labels}:
        raise ValueError("Frames and labels require the same complete development population")
    records = []
    for label in labels:
        row = by_id[label["id"]]
        trace = row.get("trace", {})
        record = {"id": label["id"], "text": row["input_text"], "frame": trace.get("request_frame", {}),
                  "policy_sha256": trace.get("policy_sha256"), "status": "valid",
                  "source_prediction_completed_at": row.get("completed_at"),
                  "source_execution_outcome": row.get("outcome"),
                  "source_execution_error": trace.get("execution_error"),
                  "source_extraction_stage": "request_extraction", "reviewer_type": "ai"}
        from cadence.agent.request_frame import RequestFrame
        try:
            record["frame_sha256"] = digest(RequestFrame.model_validate(record["frame"]).model_dump_json())
            validate_frame_record(record, label)
        except (ValueError, KeyError):
            record.update(status="unavailable", frame_sha256=None)
        if record["text"] != customer_text(label["text"]):
            raise ValueError("Source stage used different customer input")
        records.append(record)
    _fresh_output(out)
    write_jsonl(out / "frames.jsonl", records)
    write_json(out / "FRAMES.lock.json", {
        "version": VERSION, "phase": "development", "created_at": now(),
        "source_run": run.resolve().relative_to(Paths.ROOT).as_posix(),
        "source_frozen_at": manifest["frozen_at"], "source_model": frozen["model"],
        "source_policy": frozen["policy_version"], "source_as_of": frozen["source_as_of"],
        "stage_isolation": "Request extraction receives customer text and policy, before actions/retrieval; AI only",
        "inputs": {str((run / name).resolve().relative_to(Paths.ROOT).as_posix()): sha256(run / name)
                   for name in ("manifest.json", "predictions.jsonl", "EXECUTION.json")},
        "labels_sha256": sha256(labels_path), "frames_sha256": sha256(out / "frames.jsonl"),
        "valid": sum(r["status"] == "valid" for r in records), "n": len(records),
        "fresh_latency_available": False, "new_model_calls": 0, "promotion": False})


def load_frames(directory, labels_path):
    lock = read_json(directory / "FRAMES.lock.json")
    if (lock["phase"] != "development" or lock["version"] != VERSION
            or lock["labels_sha256"] != sha256(labels_path)
            or lock["frames_sha256"] != sha256(directory / "frames.jsonl")):
        raise ValueError("Frame lock, development labels or extracted frames changed")
    for name, expected in lock["inputs"].items():
        if sha256(Paths.ROOT / name) != expected:
            raise ValueError("Source execution changed after frame extraction")
    frames = read_jsonl(directory / "frames.jsonl")
    indexed = {r["id"]: r for r in frames}
    if len(indexed) != len(frames) or len(frames) != lock["n"]:
        raise ValueError("Frame population is not unique and complete")
    return indexed, lock


RENDER_INPUTS = ("src/cadence/agent/balanced.py", "src/cadence/agent/quality.py",
                 "src/cadence/agent/pipeline.py", "src/cadence/agent/integrity.py",
                 "src/cadence/agent/links.py", "src/cadence/agent/models.py",
                 "src/cadence/config.py", "src/cadence/utils/text.py",
                 "config/canonical_links.json", "config/intents.yaml", "config/escalation.yaml")


def frozen_balanced_source(predictions_path, old_labels_path):
    """Refuse edited archives or a different renderer instead of mislabeling a veto."""
    directory = predictions_path.parent
    if predictions_path.name != "predictions.jsonl":
        raise ValueError("Use the source run's sealed predictions.jsonl")
    seal_path = directory / "VERIFICATION.json"
    if not seal_path.exists():
        seal_path = directory / "EXECUTION.json"
    seal = read_json(seal_path)
    for name in ("predictions.jsonl", "manifest.json"):
        if seal.get("artifacts", {}).get(name) != sha256(directory / name):
            raise ValueError("Changed or unsealed historical Balanced artifact: " + name)
    if seal_path.name == "VERIFICATION.json" and seal.get("status") != "complete":
        raise ValueError("Historical Balanced execution is not complete")
    frozen = read_json(directory / "manifest.json")["frozen"]
    old_name = old_labels_path.resolve().relative_to(Paths.ROOT).as_posix()
    if frozen["inputs"].get(old_name) != sha256(old_labels_path):
        raise ValueError("Old routing labels do not match the historical run")
    for name in RENDER_INPUTS:
        expected = frozen["inputs"].get(name)
        if expected != sha256(Paths.ROOT / name):
            raise ValueError("Old-card renderer changed; use the matching archived checkout: " + name)
        resolve_input(directory, name, expected, root=Paths.ROOT)
    source = [row for row in read_jsonl(predictions_path) if row["system"] == "balanced"]
    return source, {"manifest_sha256": sha256(directory / "manifest.json"),
                    "predictions_sha256": sha256(predictions_path),
                    "seal": seal_path.resolve().relative_to(Paths.ROOT).as_posix(),
                    "seal_sha256": sha256(seal_path), "model": frozen["model"],
                    "renderer_inputs": {name: frozen["inputs"][name] for name in RENDER_INPUTS},
                    "exact_card_sha256": {name: digest(render(name)) for name in ACTIONS}}


def prepare(predictions_path, labels_path, old_labels_path, frames_dir, out, seed):
    labels = read_jsonl(labels_path)
    development_labels(labels)
    frames, frame_lock = load_frames(frames_dir, labels_path)
    source, base_lock = frozen_balanced_source(predictions_path, old_labels_path)
    indexed = {row["id"]: row for row in source}
    if (len(indexed) != len(source) or set(indexed) != set(frames)
            or set(indexed) != {row["id"] for row in labels}):
        raise ValueError("Use complete matched Balanced outputs and independent frames")
    old_labels = read_jsonl(old_labels_path)
    rescore = policy_rescore(old_labels, labels, source)
    rows = [overlay(indexed[label["id"]], frames[label["id"]], label, control)
            for label in labels for control in CONTROLS]
    _fresh_output(out)
    write_json(out / "rubric.json", RUBRIC)
    files = [Path(__file__), predictions_path, predictions_path.parent / "manifest.json",
             Paths.ROOT / base_lock["seal"], labels_path, old_labels_path,
             frames_dir / "frames.jsonl", frames_dir / "FRAMES.lock.json", out / "rubric.json"]
    inputs = snapshot_dependencies(out, files, root=Paths.ROOT)
    write_json(out / "manifest.json", {"frozen": {"version": VERSION, "phase": "development", "created_at": now(),
        "inputs": inputs, "seed": seed, "controls": list(CONTROLS), "n": len(labels), "promotion": False,
        "label_source": "See frozen development labels; no human review is inferred",
        "frame_source": frame_lock, "balanced_source": base_lock,
        "source_base_policy": "Archived Balanced policy v0 behavior retained",
        "scoring_policy": "v2", "fresh_model_calls": 0, "fresh_latency_available": False,
        "interpretation": "Veto-only counterfactuals, not fresh complete agents; no de-escalation or knowledge expansion",
        "required_followup": "Blind review changed replies; full live controls needed for latency/cost claims"}})
    archive_inputs(out, inputs, root=Paths.ROOT)
    write_jsonl(out / "predictions.jsonl", rows)
    write_json(out / "routing_summary.json", {
        "policy_rescore": rescore, "controls": {
            control: {**routing_counts(labels, [r for r in rows if r["system"] == control]),
                      "changed_ids": [r["id"] for r in rows if r["system"] == control and r["ablation"]["changed"]]}
            for control in CONTROLS},
        "useful_coverage": None, "why_unmeasured": "New exact replies require independent blind review"})
    packet, mapping = review_packet(rows, "ablation-" + sha256(out / "manifest.json")[:16], seed)
    write_jsonl(out / "blind_packet.jsonl", packet)
    write_json(out / "blind_mapping.json", mapping)
    artifacts = ("manifest.json", "predictions.jsonl", "routing_summary.json", "rubric.json",
                 "blind_packet.jsonl", "blind_mapping.json")
    write_json(out / "EXECUTION.json", {"artifacts": {name: sha256(out / name) for name in artifacts},
                                       "live_model_calls": 0, "promotion": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frames = sub.add_parser("frames", help="Reuse isolated extraction from a completed development run")
    frames.add_argument("--run", type=Path, required=True)
    frames.add_argument("--labels", type=Path, required=True)
    frames.add_argument("--out", type=Path, required=True)
    run = sub.add_parser("prepare", help="Offline replay diagnostics and blinded output review packet")
    run.add_argument("--predictions", type=Path, required=True)
    run.add_argument("--labels", type=Path, required=True)
    run.add_argument("--old-labels", type=Path, required=True)
    run.add_argument("--frames", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--seed", type=int, default=2026091807)
    args = parser.parse_args()
    if args.command == "frames":
        export_frames(args.run, args.labels, args.out)
    else:
        prepare(args.predictions, args.labels, args.old_labels, args.frames, args.out, args.seed)


if __name__ == "__main__":
    main()
