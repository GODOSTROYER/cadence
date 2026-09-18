"""Numerical portability never permits changed counts, artifacts or provenance."""
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, write_json, write_jsonl


@pytest.fixture
def portable():
    path = Path(__file__).resolve().parents[1] / "analysis_tools/verify_portable_summaries.py"
    spec = importlib.util.spec_from_file_location("portable_summaries", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nested_exact_json_and_key_order(portable):
    left = {"a": [True, 1, 2.0, None, "text"], "b": {"rate": .5}}
    right = {"b": {"rate": .5}, "a": [True, 1, 2.0, None, "text"]}
    result = portable.require_match(left, right)
    assert result["accepted_float_differences"] == result["mismatches"] == 0


@pytest.mark.parametrize("left,right", [(0.0, 1e-12), (.95, math.nextafter(.95, math.inf))])
def test_small_finite_absolute_difference_is_explicitly_reported(portable, left, right):
    result = portable.require_match({"a/b~c": [left]}, {"a/b~c": [right]})
    assert result["accepted_float_differences"] == 1
    sample = result["accepted_samples"][0]
    assert sample["path"] == "/a~1b~0c/0"
    assert sample["expected"] == left and sample["actual"] == right
    assert sample["absolute_delta"] == abs(left - right)


@pytest.mark.parametrize("left,right", [
    (0.0, math.nextafter(1e-12, math.inf)), (.5, .50000001),
    (10000.0, 10000.00000001), (1, 2), (True, 1), (1, 1.0),
    (None, False), ("ai", "human"), ([1, 2], [2, 1]), ([1], [1, 2]),
    ({"a": 1}, {"a": 1, "b": 2}), ({"a": 1, "b": 2}, {"a": 1}),
    (float("nan"), float("nan")), (float("inf"), float("inf")),
    (-float("inf"), -float("inf")), (1.0, float("nan")),
])
def test_changed_types_counts_structure_or_nonfinite_values_fail(portable, left, right):
    with pytest.raises(ValueError, match="Summary reproduction mismatch"):
        portable.require_match({"nested": [left]}, {"nested": [right]})


def test_numeric_comparison_does_not_print_changed_text(portable):
    result = portable.compare_json({"provenance": "original private text"}, {"provenance": "changed private text"})
    rendered = json.dumps(result)
    assert result["mismatches"] == 1
    assert "private text" not in rendered
    assert "/provenance" in rendered


def test_diagnostics_are_bounded_but_late_mismatch_still_fails(portable):
    expected = [0.0] * 30 + [1]
    actual = [1e-13] * 30 + [2]
    result = portable.compare_json(expected, actual)
    assert result["accepted_float_differences"] == 30
    assert len(result["accepted_samples"]) == 20
    assert result["mismatches"] == 1
    with pytest.raises(ValueError):
        portable.require_match(expected, actual)


@pytest.mark.parametrize("study,method", [("development", "summarize"), ("verified", "summary")])
def test_wrapper_calls_original_validator_without_writing(portable, tmp_path, monkeypatch, study, method):
    expected = {"n": 80, "promote": False, "score": .95, "input_hashes": {"seal": "abc"}}
    actual = {**expected, "score": math.nextafter(.95, math.inf)}
    write_json(tmp_path / "summary.json", expected)
    write_json(tmp_path / "seal.json", {"ratings_sha256": "immutable"})
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    calls = []

    def calculate(path):
        calls.append(path)
        return actual

    monkeypatch.setattr(portable, "helper", lambda _: SimpleNamespace(**{method: calculate}))
    result = portable.reproduce(study, tmp_path)
    assert calls == [tmp_path]
    assert result["accepted_float_differences"] == 1
    assert result["writes"] == result["new_model_calls"] == 0
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_original_seal_failure_is_propagated_without_numeric_fallback(portable, tmp_path, monkeypatch):
    write_json(tmp_path / "summary.json", {"n": 80})

    def failed(_):
        raise ValueError("Changed prepared comparison artifact: blind_packet.jsonl")

    monkeypatch.setattr(portable, "helper", lambda _: SimpleNamespace(summarize=failed))
    with pytest.raises(ValueError, match="Changed prepared comparison artifact"):
        portable.reproduce("development", tmp_path)


def test_missing_saved_summary_is_not_generated(portable, tmp_path, monkeypatch):
    monkeypatch.setattr(portable, "helper", lambda _: pytest.fail("Must require saved summary first"))
    with pytest.raises(FileNotFoundError):
        portable.reproduce("development", tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.fixture
def controls_fixture(portable, tmp_path, monkeypatch):
    outputs = ("quality_summary.json", "ai_reviews.jsonl", "AI_REVIEW.json")
    summary = {"n": 1, "score": .95}
    ratings = [{"reviewer_type": "ai", "scores": {"overall": 4}}]
    source = tmp_path / "quality_analysis_snapshot" / "helper.py"
    source.parent.mkdir()
    source.write_text("# Original frozen helper\n", encoding="utf-8")
    provenance = {"reviewer_type": "ai", "analysis_sources": {"helper.py": sha256(source)}}
    write_json(tmp_path / outputs[0], summary)
    write_jsonl(tmp_path / outputs[1], ratings)
    write_json(tmp_path / outputs[2], {**provenance, "artifacts": {n: sha256(tmp_path / n) for n in outputs[:-1]}})
    original = SimpleNamespace(OUTPUTS=outputs, _member=lambda directory, name: directory / name,
                               calculate=lambda *a: ({**summary, "score": math.nextafter(.95, math.inf)}, ratings, provenance))
    monkeypatch.setattr(portable, "helper", lambda _: original)
    return tmp_path, ratings, provenance


def test_controls_preserve_output_hash_and_provenance_validation(portable, controls_fixture):
    directory, _, _ = controls_fixture
    before = {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}
    assert portable.reproduce("controls", directory)["accepted_float_differences"] == 1
    assert before == {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


@pytest.mark.parametrize("problem", ["rating", "provenance", "archive", "seal"])
def test_controls_reject_changed_ratings_provenance_archives_and_seals(portable, controls_fixture, problem):
    directory, _, _ = controls_fixture
    if problem == "rating":
        write_jsonl(directory / "ai_reviews.jsonl", [{"reviewer_type": "human"}])
    elif problem == "archive":
        (directory / "quality_analysis_snapshot/helper.py").write_text("changed", encoding="utf-8")
    else:
        record = read_json(directory / "AI_REVIEW.json")
        if problem == "provenance":
            record["reviewer_type"] = "human"
        else:
            record["artifacts"]["quality_summary.json"] = "0" * 64
        write_json(directory / "AI_REVIEW.json", record)
    with pytest.raises(ValueError):
        portable.reproduce("controls", directory)
