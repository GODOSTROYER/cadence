"""Read-only reproduction with narrowly bounded cross-platform float comparison.

Frozen evaluators, source seals, ratings and saved summaries stay unchanged. Only
finite float-to-float summary differences of at most 1e-12 absolute are accepted.
Every accepted difference is counted and a bounded numeric diagnostic is emitted.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import math
import platform
from pathlib import Path

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, read_jsonl

ABSOLUTE_TOLERANCE = 1e-12
DIAGNOSTIC_LIMIT = 20


def compare_json(expected, actual, *, absolute_tolerance=ABSOLUTE_TOLERANCE):
    """Compare JSON structures without bool/int coercion or relative tolerance.

    Strings and other nonnumeric values are never printed in diagnostics. A
    mismatch after the first 20 differences still fails: only display is bounded.
    """
    if absolute_tolerance not in (0, ABSOLUTE_TOLERANCE):
        raise ValueError("Unsupported numeric tolerance")
    result = {"accepted_float_differences": 0, "mismatches": 0, "max_accepted_absolute_delta": 0.0,
              "accepted_samples": [], "mismatch_samples": []}

    def record(kind, path, reason, left, right, delta=None):
        accepted = kind == "accepted"
        result["accepted_float_differences" if accepted else "mismatches"] += 1
        samples = result["accepted_samples" if accepted else "mismatch_samples"]
        if accepted:
            result["max_accepted_absolute_delta"] = max(result["max_accepted_absolute_delta"], delta)
        if len(samples) < DIAGNOSTIC_LIMIT:
            item = {"path": path or "/", "reason": reason,
                    "expected_type": type(left).__name__, "actual_type": type(right).__name__}
            if type(left) in (int, float) and type(right) in (int, float):
                if (type(left) is int or math.isfinite(left)) and (type(right) is int or math.isfinite(right)):
                    item.update(expected=left, actual=right)
                    if delta is not None and math.isfinite(delta):
                        item["absolute_delta"] = delta
            samples.append(item)

    def visit(left, right, path):
        if type(left) is not type(right):
            record("mismatch", path, "type differs", left, right)
        elif isinstance(left, dict):
            if left.keys() != right.keys():
                record("mismatch", path, "object keys differ", left, right)
            for key in sorted(left.keys() & right.keys()):
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                visit(left[key], right[key], path + "/" + escaped)
        elif isinstance(left, list):
            if len(left) != len(right):
                record("mismatch", path, "list length differs", left, right)
            for i, (a, b) in enumerate(zip(left, right, strict=False)):
                visit(a, b, path + "/" + str(i))
        elif type(left) is float:
            if not math.isfinite(left) or not math.isfinite(right):
                record("mismatch", path, "non-finite float", left, right)
            elif left != right:
                delta = abs(left - right)
                record("accepted" if delta <= absolute_tolerance else "mismatch", path,
                       "finite float rounding" if delta <= absolute_tolerance else "float exceeds absolute tolerance",
                       left, right, delta)
        elif left != right:
            record("mismatch", path, "value differs", left, right)

    visit(expected, actual, "")
    return result


def require_match(expected, actual, *, absolute_tolerance=ABSOLUTE_TOLERANCE):
    diagnostic = compare_json(expected, actual, absolute_tolerance=absolute_tolerance)
    if diagnostic["mismatches"]:
        raise ValueError("Summary reproduction mismatch: " + json.dumps(diagnostic, allow_nan=False))
    return diagnostic


def helper(name):
    path = Paths.ROOT / "analysis_tools" / name
    spec = importlib.util.spec_from_file_location("_portable_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def controls_summary(directory):
    """Retain every original controls check; only summary float equality differs."""
    original = helper("summarize_verified_controls.py")
    summary, unblinded, provenance = original.calculate(directory, directory / "blind_ai_ratings.jsonl")
    record = read_json(directory / "AI_REVIEW.json")
    for name, expected in record.get("artifacts", {}).items():
        if name not in original.OUTPUTS[:-1] or sha256(original._member(directory, name)) != expected:
            raise ValueError("Quality artifact changed: " + name)
    artifacts = {name: sha256(directory / name) for name in original.OUTPUTS[:-1]}
    require_match(record, {**provenance, "artifacts": artifacts}, absolute_tolerance=0)
    require_match(read_jsonl(directory / "ai_reviews.jsonl"), unblinded, absolute_tolerance=0)
    for name, expected in provenance["analysis_sources"].items():
        if sha256(directory / "quality_analysis_snapshot" / name) != expected:
            raise ValueError("Archived quality-analysis source changed: " + name)
    return summary


def reproduce(study, directory=None):
    """Explicit read-only study mappings, never arbitrary modules or functions."""
    if study == "development":
        directory = directory or Paths.ROOT / "results/verified_development_comparison"
        summary_path = directory / "summary.json"
        def calculate():
            return helper("compare_verified_development.py").summarize(directory)
    elif study == "verified":
        if directory is None:
            raise ValueError("verified requires --experiment")
        summary_path = directory / "summary.json"
        def calculate():
            return helper("reproduce_verified.py").summary(directory)
    elif study == "variants":
        directory = directory or Paths.ROOT / "results/verified_variant_comparison_v1"
        summary_path = directory / "summary.json"

        def calculate():
            original = helper("compare_verified_variants.py")
            runs = {v: Paths.ROOT / "results" / ("verified_dev_v4" if v == "combined" else f"verified_variant_{v}_v1")
                    for v in original.VARIANTS}
            return original.summarize(runs, Paths.ROOT / "data/verified_dev/v3_regression_labels.jsonl",
                                      Paths.ROOT / "data/verified_dev/V3_REGRESSION_SELECTION.json", directory)
    elif study == "controls":
        if directory is None:
            raise ValueError("controls requires --experiment")
        summary_path = directory / "quality_summary.json"
        def calculate():
            return controls_summary(directory)
    else:
        raise ValueError("Unsupported study")
    # Missing saved output is an error, never permission to generate one.
    expected = read_json(summary_path)
    actual = calculate()  # Original seal, context, provenance and score checks run first.
    diagnostic = require_match(expected, actual)
    return {"verified": True, "study": study, "new_model_calls": 0, "writes": 0,
            "absolute_float_tolerance": ABSOLUTE_TOLERANCE, "relative_float_tolerance": 0,
            "summary_sha256": sha256(summary_path), **diagnostic}


def environment():
    versions = {}
    for name in ("numpy", "scipy", "scikit-learn"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return {"platform": platform.system(), "python": platform.python_version(), "packages": versions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", choices=("development", "verified", "variants", "controls"))
    parser.add_argument("--experiment", type=Path, help="Study directory; required for verified and controls")
    args = parser.parse_args()
    result = reproduce(args.study, args.experiment)
    print(json.dumps({**result, "environment": environment()}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
