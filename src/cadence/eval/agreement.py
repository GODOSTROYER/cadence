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

    Returns ``1.0`` for perfect agreement even when only one label occurs (sklearn yields NaN
    there because expected agreement is 1), ``None`` when the statistic is undefined otherwise
    (e.g. both raters constant but disagreeing), and ``None`` for empty input.
    """
    if len(a) != len(b):
        raise ValueError(f"rater arrays must be aligned (got {len(a)} vs {len(b)})")
    if not a:
        return None
    if all(x == y for x, y in zip(a, b, strict=True)):
        return 1.0
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
    return int(value) if value is not None else None


def judge_agreement(
    human_rows: Sequence[dict[str, Any]],
    judge_rows: Sequence[dict[str, Any]],
    dimensions: Sequence[str] = JUDGE_DIMENSIONS,
) -> dict[str, Any] | None:
    """The §8 ``judge_agreement`` block: human ratings joined to judge scores on ``(id, system)``.

    Uses quadratic-weighted kappa and Spearman per dimension, plus exact/within-one agreement on
    ``overall``. When several human ratings exist for one pair the latest (by ``rated_at``) wins.
    Returns ``None`` when there are no joined pairs.
    """
    judge_by_key = {(r.get("id"), r.get("system")): r for r in judge_rows}
    human_by_key: dict[tuple[Any, Any], dict[str, Any]] = {}
    for r in sorted(human_rows, key=lambda x: str(x.get("rated_at") or "")):
        human_by_key[(r.get("id"), r.get("system"))] = r
    keys = sorted((k for k in human_by_key if k in judge_by_key), key=lambda k: (str(k[0]), str(k[1])))
    pairs: list[dict[str, Any]] = []
    columns: dict[str, tuple[list[int], list[int]]] = {d: ([], []) for d in dimensions}
    for key in keys:
        h, j = human_by_key[key], judge_by_key[key]
        h_overall, j_overall = _score(h, "overall"), _score(j, "overall")
        if h_overall is None or j_overall is None:
            continue
        pairs.append({"id": key[0], "system": key[1], "human": h_overall, "judge": j_overall})
        for d in dimensions:
            hs, js = _score(h, d), _score(j, d)
            if hs is not None and js is not None:
                columns[d][0].append(hs)
                columns[d][1].append(js)
    if not pairs:
        return None
    h_all = [p["human"] for p in pairs]
    j_all = [p["judge"] for p in pairs]
    return {
        "n": len(pairs),
        "weighted_kappa_overall": cohens_kappa(h_all, j_all, weights="quadratic", labels=SCORE_LABELS),
        "spearman_overall": spearman(h_all, j_all),
        "exact_agreement": exact_agreement(h_all, j_all),
        "within_one": within_one(h_all, j_all),
        "per_dimension": {
            d: {
                "n": len(columns[d][0]),
                "weighted_kappa": cohens_kappa(
                    columns[d][0], columns[d][1], weights="quadratic", labels=SCORE_LABELS
                ),
                "spearman": spearman(columns[d][0], columns[d][1]),
            }
            for d in dimensions
        },
        "pairs": pairs,
    }
