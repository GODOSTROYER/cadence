"""Protect the explicit two-stage review provenance and unchanged-score confirmation."""
from pathlib import Path

from cadence.eval.provenance import sha256
from cadence.eval.review import validate_reviews
from cadence.utils.io import read_json, read_jsonl


def test_author_verified_exact_astra_scores_with_separate_provenance():
    directory = Path(__file__).resolve().parents[1] / "results/review_study"
    original = read_jsonl(directory / "astra_ratings.jsonl")
    verified = read_jsonl(directory / "arnav_verified_ratings.jsonl")
    confirmation = read_json(directory / "HUMAN_VERIFICATION.json")
    validate_reviews(verified, read_json(directory / "mapping.json"))
    assert len(original) == len(verified) == confirmation["n_reply_ratings"] == 100
    assert confirmation["status"] == "completed"
    originals = {(r["id"], r["alias"]): r for r in original}
    for row in verified:
        source = originals[row["id"], row["alias"]]
        assert row["reviewer_id"] == "Arnav Bule" and row["reviewer_type"] == "human"
        assert row["review_method"] == "human_verification_of_ai_ratings"
        assert row["initial_review"]["model"] == "gpt-6-astra"
        assert row["initial_review"]["reasoning_effort"] == "xhigh"
        assert source["reviewer_type"] == "ai"
        for field in ("scores", "flags", "verdict", "response_kind", "reply_hash", "run_id", "rubric_version", "rationale"):
            assert row[field] == source[field]
    root = directory.parents[1]
    for path, digest in confirmation["artifacts"].items():
        assert sha256(root / path) == digest
