"""Inter-annotator and human-vs-judge agreement statistics (CONTRACT.md §8, §13)."""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from typing import Any, Literal

import numpy as np
from scipy.stats import ConstantInputWarning, spearmanr
from sklearn.metrics import cohen_kappa_score

from cadence.config import JUDGE_DIMENSIONS

KappaWeights = Literal["quadratic", "linear"] | None
SCORE_LABELS: tuple[int, ...] = (1, 2, 3, 4, 5)


def _finite(x: float) -> float | None:
    return float(x) if x is not None and math.isfinite(x) else None


def cohens_kappa(
    a: Sequence[Any],
    b: Sequence[Any],
    weights: KappaWeights = None,
    labels: Sequence[Any] | None = None,
) -> float | None:
    """Cohen's kappa between two raters (``weights="quadratic"`` for ordinal scores).

    Returns ``None`` for empty input or identical constant ratings (expected agreement is one).
    Perfect agreement across multiple categories returns ``1.0``.
    """
    if len(a) != len(b):
        raise ValueError(f"rater arrays must be aligned (got {len(a)} vs {len(b)})")
    if not a:
        return None
    if len(set(a) | set(b)) == 1:
        return None
    kappa = cohen_kappa_score(
        list(a), list(b), labels=list(labels) if labels is not None else None, weights=weights
    )
    return _finite(kappa)


def spearman(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Spearman rank correlation via scipy; ``None`` when undefined (constant input or n < 2)."""
    if len(a) != len(b):
        raise ValueError(f"arrays must be aligned (got {len(a)} vs {len(b)})")
    if len(a) < 2:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        rho = spearmanr(np.asarray(a, dtype=float), np.asarray(b, dtype=float)).statistic
    return _finite(rho)


def exact_agreement(a: Sequence[Any], b: Sequence[Any]) -> float | None:
    """Share of positions where both raters gave the same value."""
    if len(a) != len(b):
        raise ValueError(f"arrays must be aligned (got {len(a)} vs {len(b)})")
    if not a:
        return None
    return float(sum(x == y for x, y in zip(a, b, strict=True)) / len(a))


def within_one(a: Sequence[float], b: Sequence[float]) -> float | None:
    """Share of positions where the two scores differ by at most one point."""
    if len(a) != len(b):
        raise ValueError(f"arrays must be aligned (got {len(a)} vs {len(b)})")
    if not a:
        return None
    return float(sum(abs(float(x) - float(y)) <= 1 for x, y in zip(a, b, strict=True)) / len(a))


# ---------------------------------------------------------------------------
# Annotators (golden set passes A and B)
# ---------------------------------------------------------------------------
def annotator_agreement(golden_rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Agreement between annotation passes ``a`` and ``b`` stored on each golden row.

    Rows without both annotations are skipped. ``n_disagreements`` counts rows where the intent
    or the escalation decision differs.
    """
    intents_a: list[str] = []
    intents_b: list[str] = []
    esc_a: list[bool] = []
    esc_b: list[bool] = []
    for row in golden_rows:
        ann = row.get("annotations") or {}
        a, b = ann.get("a"), ann.get("b")
        if not a or not b:
            continue
        intents_a.append(str(a.get("intent")))
        intents_b.append(str(b.get("intent")))
        esc_a.append(bool(a.get("should_escalate")))
        esc_b.append(bool(b.get("should_escalate")))
    n_dis = sum(
        ia != ib or ea != eb for ia, ib, ea, eb in zip(intents_a, intents_b, esc_a, esc_b, strict=True)
    )
    return {
        "n": len(intents_a),
        "intent_kappa": cohens_kappa(intents_a, intents_b),
        "intent_raw": exact_agreement(intents_a, intents_b),
        "escalation_kappa": cohens_kappa(esc_a, esc_b),
        "escalation_raw": exact_agreement(esc_a, esc_b),
        "n_disagreements": int(n_dis),
    }


# ---------------------------------------------------------------------------
# Human vs LLM judge
# ---------------------------------------------------------------------------
def _score(row: dict[str, Any], dim: str) -> int | None:
    value = (row.get("scores") or {}).get(dim)
    if value is not None and (type(value) is not int or value not in SCORE_LABELS):
        raise ValueError("Scores must be integers from 1 to 5")
    return value


def _statistics(matches, dimensions):
    pairs = []
    columns = {d: ([], []) for d in dimensions}
    for h, j in matches:
        if _score(h, "overall") is None or _score(j, "overall") is None:
            continue
        pairs.append({"id": h["id"], "system": h["system"],
                      "reviewer_id": h.get("reviewer_id", h.get("rater", "legacy")),
                      "order_id": j.get("order_id", 0),
                      "human": _score(h, "overall"), "judge": _score(j, "overall")})
        for d in dimensions:
            hs, js = _score(h, d), _score(j, d)
            if hs is not None and js is not None:
                if hs not in SCORE_LABELS or js not in SCORE_LABELS:
                    raise ValueError("Scores must be integers from 1 to 5")
                columns[d][0].append(hs)
                columns[d][1].append(js)
    h_all, j_all = [p["human"] for p in pairs], [p["judge"] for p in pairs]
    kappa = cohens_kappa(h_all, j_all, weights="quadratic", labels=SCORE_LABELS)
    return {
        "n": len(pairs), "weighted_kappa_overall": kappa,
        "kappa_status": "defined" if kappa is not None else "insufficient_rating_variation",
        "spearman_overall": spearman(h_all, j_all),
        "exact_agreement": exact_agreement(h_all, j_all), "within_one": within_one(h_all, j_all),
        "per_dimension": {d: {"n": len(a), "weighted_kappa": cohens_kappa(a, b, weights="quadratic", labels=SCORE_LABELS),
                              "spearman": spearman(a, b)} for d, (a, b) in columns.items()},
        "pairs": pairs,
    }


def judge_agreement(human_rows, judge_rows, dimensions=JUDGE_DIMENSIONS, *, strict=False):
    """Preserve reviewers and presentation orders; revisions apply within one reviewer.

    Strict mode requires run/reply/rubric identities and both orders for every rated reply.
    Legacy single-order exports remain readable but are explicitly marked unverified.
    Top-level statistics pool rating/order observations, not independent customer examples.
    """
    from itertools import combinations

    identity = ("run_id", "reply_hash", "rubric_version")
    def key(r):
        return (r.get("run_id", "legacy"), r["id"], r["system"])
    def reviewer(r):
        return str(r.get("reviewer_id") or r.get("annotator") or r.get("rater") or "legacy")
    for r in [*human_rows, *judge_rows]:
        if strict and any(not r.get(f) for f in identity):
            raise ValueError("Missing run_id, reply_hash or rubric_version")
    judges = {}
    for r in judge_rows:
        k = (*key(r), r.get("order_id", 0))
        if k in judges:
            raise ValueError("Duplicate judge order")
        judges[k] = r
    humans = {}
    for r in human_rows:
        if strict and not r.get("reviewer_id"):
            raise ValueError("Missing reviewer_id")
        k = (*key(r), reviewer(r))
        old = humans.get(k)
        if old and old.get("rated_at", "") == r.get("rated_at", "") and old != r:
            raise ValueError("Ambiguous human revision timestamp")
        if old is None or r.get("rated_at", "") > old.get("rated_at", ""):
            humans[k] = r
    groups, matches = {}, []
    for k, h in sorted(humans.items()):
        orders = sorted((o, j) for (*base, o), j in judges.items() if tuple(base) == k[:-1])
        if strict and [o for o, _ in orders] != [0, 1]:
            raise ValueError("Every rated reply requires judge orders 0 and 1")
        for order, j in orders:
            if any(h.get(f) != j.get(f) for f in identity):
                raise ValueError("Reply/run/rubric mismatch")
            groups.setdefault((reviewer(h), order), []).append((h, j))
            matches.append((h, j))
    if not matches:
        return None
    result = _statistics(matches, dimensions)
    result["identity_verified"] = strict
    result["aggregation"] = "rating-order observations; use per_reviewer_order for separate estimates"
    result["n_examples"] = len({(key(h)[0], h["id"]) for h, _ in matches})
    result["per_reviewer_order"] = [
        {"reviewer_id": r, "order_id": o, **_statistics(rs, dimensions)}
        for (r, o), rs in sorted(groups.items())]
    result["human_human"] = []
    for a, b in combinations(sorted({reviewer(h) for h in humans.values()}), 2):
        common = []
        for k, h in humans.items():
            other = humans.get((*k[:-1], b)) if k[-1] == a else None
            if other:
                if any(h.get(f) != other.get(f) for f in identity):
                    raise ValueError("Human reply/run/rubric mismatch")
                common.append((h, other))
        result["human_human"].append({"reviewers": [a, b], **_statistics(common, dimensions)})
    unique = {key(h) for h, _ in matches}
    both = [(judges.get((*k, 0)), judges.get((*k, 1))) for k in sorted(unique)]
    both = [(a, b) for a, b in both if a and b]
    result["order_sensitivity"] = {"n_replies": len(both), "overall_score_changed":
        sum(_score(a, "overall") != _score(b, "overall") for a, b in both)}
    unsafe = [(h, j) for h, j in matches if (_score(h, "safe") or 5) <= 2]
    result["judge_ship_on_human_unsafe"] = {"n": len(unsafe), "count": sum(j.get("verdict") == "ship" for _, j in unsafe),
        "rate": sum(j.get("verdict") == "ship" for _, j in unsafe) / len(unsafe) if unsafe else None}
    result["disagreements"] = [p for p in result["pairs"] if p["human"] != p["judge"]]
    return result
