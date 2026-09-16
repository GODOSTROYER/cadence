from copy import deepcopy

import pytest

from cadence.eval.agreement import cohens_kappa, judge_agreement


def row(score=4, **kwargs):
    return {"id": "x", "system": "agent", "run_id": "run", "reply_hash": "hash", "rubric_version": "v1",
            "scores": {"overall": score, "safe": score}, "rated_at": "2026-09-17T00:00:00Z", **kwargs}


def test_order_invariance_and_reviewers_are_preserved():
    humans = [row(reviewer_id="a"), row(2, reviewer_id="b")]
    judges = [row(4, order_id=0), row(1, order_id=1)]
    result = judge_agreement(humans, judges, strict=True)
    assert result == judge_agreement(humans[::-1], judges[::-1], strict=True)
    assert result["n"] == 4 and result["n_examples"] == 1
    assert len(result["per_reviewer_order"]) == 4
    assert result["human_human"][0]["n"] == 1
    assert result["order_sensitivity"]["overall_score_changed"] == 1


def test_constant_scores_keep_raw_agreement_but_kappa_undefined():
    assert cohens_kappa([5, 5], [5, 5]) is None
    assert cohens_kappa([1, 5], [1, 5]) == 1
    result = judge_agreement([row(5, reviewer_id="a")], [row(5, order_id=o) for o in (0, 1)], strict=True)
    assert result["exact_agreement"] == 1
    assert result["weighted_kappa_overall"] is None


@pytest.mark.parametrize("field", ["reply_hash", "rubric_version"])
def test_mismatched_identity_is_rejected(field):
    judges = [row(order_id=o) for o in (0, 1)]
    judges[0][field] = "different"
    with pytest.raises(ValueError, match="mismatch"):
        judge_agreement([row(reviewer_id="a")], judges, strict=True)


def test_duplicates_missing_orders_and_ambiguous_revisions_rejected():
    h, j = row(reviewer_id="a"), row(order_id=0)
    with pytest.raises(ValueError, match="Duplicate"):
        judge_agreement([h], [j, j])
    with pytest.raises(ValueError, match="orders"):
        judge_agreement([h], [j], strict=True)
    with pytest.raises(ValueError, match="Ambiguous"):
        judge_agreement([h, row(1, reviewer_id="a")], [j])
    newer = deepcopy(h)
    newer.update(scores={"overall": 1}, rated_at="2026-09-18T00:00:00Z")
    assert judge_agreement([h, newer], [j])["pairs"][0]["human"] == 1
