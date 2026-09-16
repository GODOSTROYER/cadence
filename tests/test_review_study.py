from copy import deepcopy

import pytest

from cadence.config import JUDGE_DIMENSIONS, JUDGE_FLAGS
from cadence.eval.review import review_report, validate_reviews


def fixtures():
    mapping = [{"id": "x", "alias": "A", "system": "agent", "reply_hash": "hash", "run_id": "run", "rubric_version": "support-review-v1"}]
    rating = {**mapping[0], "reviewer_id": "astra", "reviewer_type": "ai", "rated_at": "2026-09-17T00:00:00Z",
              "rationale": "No supported next step", "scores": dict.fromkeys(JUDGE_DIMENSIONS, 2),
              "flags": dict.fromkeys(JUDGE_FLAGS, False), "verdict": "edit", "response_kind": "clarification"}
    judges = [{**rating, "order_id": order} for order in (0, 1)]
    return mapping, rating, judges


def test_ai_scores_never_fill_human_agreement():
    mapping, rating, judges = fixtures()
    report = review_report([rating], mapping, judges)
    assert report["human_agreement"] is None
    assert report["reviewers"]["astra"]["agreement_kind"] == "ai_vs_judge"
    human = {**rating, "reviewer_id": "reviewer", "reviewer_type": "human"}
    report = review_report([rating, human], mapping, judges)
    assert report["human_agreement"]["n"] == 2
    assert len(report["reviewers"]) == 2


@pytest.mark.parametrize("field,value", [("reply_hash", "wrong"), ("reviewer_type", "unknown"), ("response_kind", "invalid")])
def test_review_identity_and_type_rejected(field, value):
    mapping, rating, _ = fixtures()
    rating[field] = value
    with pytest.raises(ValueError):
        validate_reviews([rating], mapping)


def test_boolean_score_is_not_an_integer_rating():
    mapping, rating, _ = fixtures()
    bad = deepcopy(rating)
    bad["scores"]["overall"] = True
    with pytest.raises(ValueError, match="integers"):
        validate_reviews([bad], mapping)
