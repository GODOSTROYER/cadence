"""Compare sealed Verified variants on the same inspected development messages.

Offline only. Reuse the frozen execution/review validator; never promote a variant.
The selected regression cases cannot establish population gains or superiority.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

import yaml

from cadence.config import Paths
from cadence.eval.archive import resolve_input
from cadence.eval.provenance import sha256
from cadence.eval.verified import RUBRIC, coverage, index_unique, paired_useful, runtime, validate_ratings
from cadence.utils.io import read_json, read_jsonl, write_json

VARIANTS = ("combined", "core", "full_context", "no_history")
N_SELECTED = 21
SEED = 2026091812
LIMITATION = (
    "AI-only descriptive comparison on 21 inspected development regression cases, "
    "selected before v3 inference after earlier development review. Selection is not "
    "random or unseen. Paired intervals condition on these selected cases and omit "
    "AI judgment uncertainty; they do not establish population gains or superiority. "
    "Runtime comes from separate executions and can vary with provider conditions. "
    "Known usage is a lower bound when failed-call usage is unknown. No promotion."
)


def reproduction():
    path = Paths.ROOT / "analysis_tools/reproduce_verified.py"
    spec = importlib.util.spec_from_file_location("_variant_reproduction", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def binding(path):
    path = path.resolve()
    name = path.relative_to(Paths.ROOT).as_posix() if path.is_relative_to(Paths.ROOT) else str(path)
    return {"path": name, "sha256": sha256(path)}


def evaluator_bindings():
    return {name: binding(Paths.ROOT / name) for name in (
        "analysis_tools/compare_verified_variants.py", "analysis_tools/reproduce_verified.py",
        "src/cadence/config.py", "src/cadence/eval/verified.py", "src/cadence/eval/review.py",
        "src/cadence/eval/metrics.py", "src/cadence/eval/agreement.py",
        "src/cadence/eval/archive.py", "src/cadence/eval/provenance.py", "src/cadence/utils/io.py")}


def sealed_run(directory, variant):
    # Inspect the manifest first: never parse labels/replies from reserved studies.
    frozen = read_json(directory / "manifest.json")["frozen"]
    expected_n = 80 if variant == "combined" else N_SELECTED
    if (frozen.get("phase") != "development" or frozen.get("policy_version") != "v2"
            or frozen.get("systems") != ["verified"] or frozen.get("variant") != variant
            or frozen.get("n") != expected_n or frozen.get("run_mode") != "live"):
        raise ValueError(f"Requires a sealed live {expected_n}-message development {variant} run")
    required = {
        "EXECUTION.json": {"manifest.json", "predictions.jsonl", "status.json", "runtime.json",
                           "calls.sqlite", "invocations_started.jsonl"},
        "REVIEW.lock.json": {"manifest.json", "predictions.jsonl", "rubric.json", "blind_packet.jsonl",
                             "blind_mapping.json", "human_reply_packet.jsonl"},
        "AI_REVIEW.json": {"ai_review_submission.jsonl", "ai_reviews.jsonl", "REVIEW.lock.json"},
    }
    bindings = {}
    for seal, expected in required.items():
        record = read_json(directory / seal)
        if not expected <= set(record.get("artifacts", {})):
            raise ValueError("Incomplete artifact seal: " + seal)
        bindings[seal] = binding(directory / seal)
        for name in record["artifacts"]:
            bindings[name] = binding(directory / name)
    if (directory / "INPUT_ARCHIVE.json").exists():
        bindings["INPUT_ARCHIVE.json"] = binding(directory / "INPUT_ARCHIVE.json")
    validator = reproduction()
    frozen, labels, rows, _ = validator.verified_execution(directory)
    mapping = validator.verify_packet(directory, frozen, rows)
    ratings = validator.load_ratings(directory, "ai", mapping, frozen)
    if ratings is None:
        raise ValueError("Completed independent AI exact-reply review required")
    if (read_json(directory / "rubric.json") != RUBRIC
            or sha256(directory / "rubric.json") != frozen["inputs"][frozen["rubric"]]):
        raise ValueError("Frozen rubric differs from the evaluator")
    gold = index_unique(labels, ("id",))
    if any(r["input_text"] != gold[(r["id"],)]["text"] for r in rows):
        raise ValueError("Prediction customer text differs from locked labels")
    policy = read_json(resolve_input(directory, frozen["policy"], frozen["inputs"][frozen["policy"]]))
    trace_identity = {"variant": variant, "policy_version": policy["version"],
                      "policy_sha256": frozen["inputs"][frozen["policy"]], "source_as_of": frozen["source_as_of"]}
    for row in rows:
        trace = row.get("trace", {})
        if (not isinstance(trace, dict) or ("model" in row and row["model"] != frozen["model"])
                or any(key in trace and trace[key] != value for key, value in trace_identity.items())):
            raise ValueError("Prediction identity contradicts its frozen manifest")
    return {"directory": directory, "frozen": frozen, "labels": labels,
            "rows": rows, "ratings": ratings, "bindings": bindings}


def execution_identity(frozen, original_labels):
    """Population and variant differ; all other execution dependencies must match."""
    resources = dict(frozen["resources"])
    if resources.pop("planned_generation_calls") != frozen["n"] * 2:
        raise ValueError("Unexpected population-scaled generation budget")
    inputs = {name: digest for name, digest in frozen["inputs"].items()
              if name not in (frozen["labels"], frozen["rubric"], original_labels)}
    if not any(n.startswith("src/") for n in inputs) or not any(n.startswith("config/") for n in inputs):
        raise ValueError("Missing frozen source/config dependency inventory")
    return {"inputs": inputs, "resources": resources,
            **{k: frozen[k] for k in ("policy", "policy_version", "model", "source_as_of",
                                      "rubric_version", "retrieval", "seed", "run_mode",
                                      "acceptance")},
            "rubric_sha256": frozen["inputs"][frozen["rubric"]]}


def retrieval_population(run, combined):
    """A subset run must exclude the entire original development population too."""
    frozen, original = run["frozen"], combined["frozen"]
    original_name = original["labels"]
    reserved = frozen["reserved_samples"]
    expected = set(original["reserved_samples"])
    if frozen["variant"] != "combined":
        expected.add(original_name)
    if (len(reserved) != len(set(reserved)) or set(reserved) != expected
            or frozen["inputs"].get(original_name) != original["inputs"][original_name]):
        raise ValueError("Subset retrieval must exclude the same full development and reserved populations")
    count = read_json(run["directory"] / "EXECUTION.json").get("excluded_retrieval_threads")
    if type(count) is not int or count <= 0:
        raise ValueError("Missing sealed retrieval exclusion count")
    return {"development_labels": original_name, "development_labels_sha256": original["inputs"][original_name],
            "other_reserved_samples": sorted(original["reserved_samples"]), "excluded_retrieval_threads": count}


def joint_ratings(directory, runs, ids, selection_path):
    """One frozen blinded review of all matched replies; preserve per-run identities."""
    packet_name, lock_name = "blind_packet_v2.jsonl", "BLIND_REVIEW_V2.lock.json"
    submission_name = "blind_ai_ratings.jsonl"
    lock = read_json(directory / lock_name)
    if (lock.get("n") != N_SELECTED * len(VARIANTS) or lock.get("n_messages") != N_SELECTED
            or lock.get("human_review") is not False or lock.get("system_and_variant_identity_hidden") is not True):
        raise ValueError("Expected the frozen joint 84-reply blinded AI study")
    bindings = {lock_name: binding(directory / lock_name)}
    for section in ("sources", "artifacts"):
        for name, digest in lock[section].items():
            path = (Paths.ROOT if section == "sources" else directory) / name
            if sha256(path) != digest:
                raise ValueError("Changed joint review context: " + name)
            bindings[f"{section}/{name}"] = binding(path)
    required_sources = {selection_path.resolve(), *(run["directory"].joinpath(name).resolve()
                        for run in runs.values() for name in ("blind_packet.jsonl", "REVIEW.lock.json"))}
    if (not required_sources <= {(Paths.ROOT / name).resolve() for name in lock["sources"]}
            or not {packet_name, "rubric.json"} <= set(lock["artifacts"])
            or read_json(directory / "rubric.json") != RUBRIC):
        raise ValueError("Joint packet seal omits its original source contexts or rubric")
    expected_packet = [row for run in runs.values() for row in read_jsonl(run["directory"] / "blind_packet.jsonl")
                       if row["id"] in ids]
    packet = read_jsonl(directory / packet_name)
    identity_fields = ("run_id", "id", "alias")
    if (len(packet) != lock["n"]
            or index_unique(packet, identity_fields) != index_unique(expected_packet, identity_fields)):
        raise ValueError("Joint packet differs from the exact matched original replies")
    record = read_json(directory / "AI_REVIEW.json")
    if not {submission_name, lock_name} <= set(record.get("artifacts", {})):
        raise ValueError("Joint AI review is not bound to its frozen packet and submission")
    for name, digest in record["artifacts"].items():
        path = directory / name
        if sha256(path) != digest:
            raise ValueError("Changed joint AI review artifact: " + name)
        bindings[name] = binding(path)
    bindings["AI_REVIEW.json"] = binding(directory / "AI_REVIEW.json")
    submitted = read_jsonl(directory / submission_name)
    index_unique(submitted, identity_fields)
    if (len(submitted) != len(packet) or record.get("n_ratings") != len(submitted)
            or record.get("n_messages") != N_SELECTED or record.get("reviewer_type") != "ai"
            or {r.get("reviewer_id") for r in submitted} != {record.get("reviewer_id")}):
        raise ValueError("The joint study requires one explicit AI reviewer and complete coverage")
    ratings, run_ids = {}, set()
    for variant, run in runs.items():
        mapping = [row for row in read_json(run["directory"] / "blind_mapping.json") if row["id"] in ids]
        identities = {row["run_id"] for row in mapping}
        if len(identities) != 1 or identities & run_ids:
            raise ValueError("Joint study requires distinct original run identities")
        run_ids.update(identities)
        ratings[variant] = validate_ratings([r for r in submitted if r["run_id"] in identities], mapping,
                                            reviewer_type="ai", expected_keys={(i, "verified") for i in ids})
    if {r["run_id"] for r in submitted} != run_ids:
        raise ValueError("Unknown run in joint AI review")
    return ratings, bindings, {"reviewer_type": "ai", "reviewer_id": record["reviewer_id"],
                               "n_ratings": len(submitted), "n_messages": N_SELECTED,
                               "note": "One joint matched review supplies every compared quality score. The separate combined80 review remains unchanged."}


def summarize(directories, labels_path, selection_path, joint_directory):
    if set(directories) != set(VARIANTS):
        raise ValueError("Exactly the four named variants are required")
    labels = read_jsonl(labels_path)
    gold = index_unique(labels, ("id",))
    ids = [r["id"] for r in labels]
    selection = read_json(selection_path)
    if (len(labels) != N_SELECTED or selection.get("n") != N_SELECTED
            or selection.get("ids") != ids or selection.get("subset_sha256") != sha256(labels_path)
            or selection.get("labels_modified") is not False or selection.get("human_review") is not False):
        raise ValueError("Selection must bind the exact 21 unchanged AI development labels")
    runs = {variant: sealed_run(directories[variant], variant) for variant in VARIANTS}
    combined = runs["combined"]
    frozen = combined["frozen"]
    if selection.get("original_labels_sha256") != frozen["inputs"][frozen["labels"]]:
        raise ValueError("Selection original labels differ from the combined run")
    identity = execution_identity(frozen, frozen["labels"])
    retrieval = retrieval_population(combined, combined)
    joint, joint_bindings, review = joint_ratings(joint_directory, runs, set(ids), selection_path)
    taxonomy = resolve_input(combined["directory"], "config/intents.yaml", frozen["inputs"]["config/intents.yaml"])
    intents = [r["id"] for r in yaml.safe_load(taxonomy.read_text(encoding="utf-8"))["intents"]]
    metrics, runtimes, vectors = {}, {}, {}
    inputs = {"selected_labels": binding(labels_path), "selection": binding(selection_path), **evaluator_bindings(),
              **{f"joint/{name}": value for name, value in joint_bindings.items()}}
    for variant, run in runs.items():
        if execution_identity(run["frozen"], frozen["labels"]) != identity:
            raise ValueError("Execution identity differs beyond variant/population: " + variant)
        if retrieval_population(run, combined) != retrieval:
            raise ValueError("Sealed retrieval exclusion population differs: " + variant)
        run_gold = index_unique(run["labels"], ("id",))
        if not set(gold) <= set(run_gold) or (variant != "combined" and set(run_gold) != set(gold)):
            raise ValueError("Variant does not cover the exact selected IDs: " + variant)
        if any(any(run_gold[key][field] != label[field] for field in ("text", "gold"))
               for key, label in gold.items()):
            raise ValueError("Selected text or gold label mismatch: " + variant)
        by_id = index_unique(run["rows"], ("id",))
        rows = [by_id[(identity,)] for identity in ids]
        ratings = joint[variant]
        metric = coverage(labels, rows, ratings, intent_labels=intents)
        vectors[variant] = metric.pop("vectors")["policy_compliant_useful"]
        metrics[variant] = metric
        observed = runtime(rows)
        useful_count = metric["counts"]["policy_compliant_useful_automatic"]
        calls = [call for row in rows for call in row["measurement"]["calls"]]
        per_request_calls = [row["measurement"]["calls"] for row in rows]
        observed.update(
            cached_model_calls=sum(c.get("cached") is True for c in calls),
            calls_with_unknown_cache_status=sum(type(c.get("cached")) is not bool for c in calls),
            requests_with_all_calls_observed_uncached=sum(bool(calls) and all(c.get("cached") is False for c in calls)
                                                          for calls in per_request_calls),
            requests_with_unknown_cache_status=sum(any(type(c.get("cached")) is not bool for c in calls)
                                                    for calls in per_request_calls),
            requests_without_observed_model_calls=sum(not calls for calls in per_request_calls),
            freshness_note="The inherited fully_fresh_requests field means no observed cache hit; missing cache status is not proven fresh. Use requests_with_all_calls_observed_uncached for affirmative freshness.",
            tokens_per_policy_compliant_useful_reply_known=(observed["tokens_known"] / useful_count if useful_count else None))
        runtimes[variant] = observed
        inputs.update({f"{variant}/{name}": record for name, record in run["bindings"].items()})
    paired = {variant: paired_useful(vectors["combined"], vectors[variant], seed=SEED)
              for variant in VARIANTS if variant != "combined"}
    return {"version": "verified-variant-comparison-v1", "phase": "development", "n": N_SELECTED,
            "selected_ids": ids, "source_population_n": {v: runs[v]["frozen"]["n"] for v in VARIANTS},
            "selection": selection, "execution_identity": identity, "retrieval_population": retrieval,
            "metrics": metrics, "runtime": runtimes, "quality_review": review,
            "runtime_scope": "Exactly the same 21 selected requests per arm, including failures; never all 80 combined requests.",
            "all_observed_calls_uncached": all(r["cached_model_calls"] == r["calls_with_unknown_cache_status"] == 0
                                                for r in runtimes.values()),
            "all_matched_requests_observed_uncached": all(r["requests_with_all_calls_observed_uncached"] == N_SELECTED
                                                          for r in runtimes.values()),
            "paired_useful_combined_minus_variant": paired,
            "interval_scope": "Descriptive paired message bootstrap on selected cases; not confirmatory population inference.",
            "human_review_pending": True, "human_agreement": None, "promote": False,
            "new_model_calls": 0, "limitation": LIMITATION, "bindings": inputs}


def save_or_check(path, result, *, check=False):
    if check:
        if read_json(path) != result:
            raise ValueError("Saved summary does not reproduce; output, data, helper or evaluator changed")
    elif path.exists():
        if read_json(path) != result:
            raise ValueError("Existing summary is immutable; choose an explicitly named new output")
    else:
        write_json(path, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for variant in VARIANTS:
        directory = "verified_dev_v4" if variant == "combined" else f"verified_variant_{variant}_v1"
        parser.add_argument("--" + variant.replace("_", "-"), type=Path, default=Paths.ROOT / "results" / directory)
    parser.add_argument("--labels", type=Path, default=Paths.ROOT / "data/verified_dev/v3_regression_labels.jsonl")
    parser.add_argument("--selection", type=Path, default=Paths.ROOT / "data/verified_dev/V3_REGRESSION_SELECTION.json")
    parser.add_argument("--out", type=Path, default=Paths.ROOT / "results/verified_variant_comparison_v1/summary.json")
    parser.add_argument("--joint-review", type=Path, help="Directory with the sealed joint 84-reply review; defaults to the output parent")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = summarize({v: getattr(args, v) for v in VARIANTS}, args.labels, args.selection, args.joint_review or args.out.parent)
    save_or_check(args.out, result, check=args.check)
    print(json.dumps({"verified": True, "n": result["n"], "promote": False, "new_model_calls": 0,
                      "summary": str(args.out)}, indent=2))


if __name__ == "__main__":
    main()
