"""Intent and escalation metrics plus threshold re-derivation (CONTRACT.md §5, §8, §13).

Everything here is pure: lists in, JSON-serialisable dicts out. The threshold helpers recompute the
final escalation decision from the recorded trace so that the confidence threshold can be swept
without new LLM calls.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

from cadence.config import escalation_config

UNKNOWN_LABEL = "<unknown>"
"""Bucket used in the confusion matrix for predictions/golds outside the label universe."""

DEFAULT_THRESHOLDS: tuple[float, ...] = tuple(round(0.05 * i, 2) for i in range(21))
"""0.0, 0.05, ..., 1.0 — the grid swept by `threshold_sweep` and `choose_threshold`."""

LOW_CONFIDENCE = "low_confidence"


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------
def _coerce(values: Iterable[Any], universe: set[str]) -> list[str]:
    return [v if isinstance(v, str) and v in universe else UNKNOWN_LABEL for v in values]


def intent_metrics(gold: Sequence[str], pred: Sequence[Any], labels: Sequence[str]) -> dict[str, Any]:
    """Accuracy, macro/weighted F1, per-class PRF and a confusion matrix for intent classification.

    Args:
        gold: gold intent ids, one per example.
        pred: predicted intent ids (``None`` or unknown ids are counted as wrong and shown in the
            confusion matrix under ``<unknown>``).
        labels: the intent universe in display order; F1 averages run over exactly these labels.

    Returns:
        ``{accuracy, macro_f1, weighted_f1, per_class{id: {precision, recall, f1, support}},
        confusion{labels, matrix}}`` with ``zero_division=0`` everywhere.
    """
    if len(gold) != len(pred):
        raise ValueError(f"gold and pred must be aligned (got {len(gold)} vs {len(pred)})")
    labels = list(labels)
    universe = set(labels)
    if not gold:
        return {
            "accuracy": 0.0,
            "macro_f1": 0.0,
            "weighted_f1": 0.0,
            "per_class": {lab: {"precision": 0.0, "recall": 0.0, "f1": 0.0, "support": 0} for lab in labels},
            "confusion": {"labels": labels, "matrix": [[0] * len(labels) for _ in labels]},
            "n": 0,
        }
    g = _coerce(gold, universe)
    p = _coerce(pred, universe)
    precision, recall, f1, support = precision_recall_fscore_support(g, p, labels=labels, zero_division=0)
    cm_labels = labels + ([UNKNOWN_LABEL] if UNKNOWN_LABEL in g or UNKNOWN_LABEL in p else [])
    matrix = confusion_matrix(g, p, labels=cm_labels)
    return {
        "accuracy": float(accuracy_score(g, p)),
        "macro_f1": float(f1_score(g, p, labels=labels, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(g, p, labels=labels, average="weighted", zero_division=0)),
        "per_class": {
            lab: {
                "precision": float(precision[i]),
                "recall": float(recall[i]),
                "f1": float(f1[i]),
                "support": int(support[i]),
            }
            for i, lab in enumerate(labels)
        },
        "confusion": {"labels": cm_labels, "matrix": matrix.astype(int).tolist()},
        "n": len(g),
    }


def per_class_f1(gold: Sequence[Any], pred: Sequence[Any], labels: Sequence[str]) -> np.ndarray:
    """Per-class F1 vector (order = ``labels``); vectorised so it is cheap inside a bootstrap loop."""
    index = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    g = np.fromiter((index.get(v, k) for v in gold), dtype=np.int64, count=len(gold))
    p = np.fromiter((index.get(v, k) for v in pred), dtype=np.int64, count=len(pred))
    cm = np.bincount(g * (k + 1) + p, minlength=(k + 1) ** 2).reshape(k + 1, k + 1)[:k, :k]
    tp = np.diag(cm).astype(float)
    pred_pos = np.bincount(p, minlength=k + 1)[:k].astype(float)
    gold_pos = np.bincount(g, minlength=k + 1)[:k].astype(float)
    denom = pred_pos + gold_pos
    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where(denom > 0, 2 * tp / np.where(denom > 0, denom, 1), 0.0)
    return f1


def macro_f1(gold: Sequence[Any], pred: Sequence[Any], labels: Sequence[str]) -> float:
    """Macro-F1 over ``labels`` (numpy implementation, identical to sklearn with zero_division=0)."""
    return float(per_class_f1(gold, pred, labels).mean()) if len(labels) else 0.0


def accuracy(gold: Sequence[Any], pred: Sequence[Any]) -> float:
    """Plain accuracy usable inside a bootstrap loop."""
    if len(gold) == 0:
        return 0.0
    return float(np.mean(np.asarray(gold) == np.asarray(pred)))


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------
def _safe_div(num: float, den: float) -> float:
    return float(num / den) if den else 0.0


def escalation_metrics(
    gold_bool: Sequence[bool],
    pred_bool: Sequence[bool],
    gold_reason: Sequence[str | None] | None = None,
    pred_reason: Sequence[str | None] | None = None,
) -> dict[str, Any]:
    """Escalation metrics with ``escalate`` as the positive class (CONTRACT.md §13).

    ``reason_code_accuracy`` is computed over true positives only and is ``None`` when there are
    no true positives or no reason codes were supplied.
    """
    if len(gold_bool) != len(pred_bool):
        raise ValueError(f"gold and pred must be aligned (got {len(gold_bool)} vs {len(pred_bool)})")
    g = np.asarray([bool(x) for x in gold_bool], dtype=bool)
    p = np.asarray([bool(x) for x in pred_bool], dtype=bool)
    tp = int(np.sum(g & p))
    fp = int(np.sum(~g & p))
    fn = int(np.sum(g & ~p))
    tn = int(np.sum(~g & ~p))
    n = int(g.size)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    reason_acc: float | None = None
    if gold_reason is not None and pred_reason is not None and tp:
        hits = [gr == pr for gr, pr, gg, pp in zip(gold_reason, pred_reason, g, p, strict=True) if gg and pp]
        reason_acc = _safe_div(sum(hits), len(hits))
    return {
        "precision": precision,
        "recall": recall,
        "f1": _safe_div(2 * precision * recall, precision + recall),
        "accuracy": _safe_div(tp + tn, n),
        "auto_handle_rate": _safe_div(n - tp - fp, n),
        "missed_escalations": fn,
        "unnecessary_escalations": fp,
        "reason_code_accuracy": reason_acc,
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "n": n,
    }


def escalation_recall(gold_bool: Sequence[bool], pred_bool: Sequence[bool]) -> float:
    """Recall of the ``escalate`` class (bootstrap-friendly scalar)."""
    return escalation_metrics(gold_bool, pred_bool)["recall"]


def escalation_precision(gold_bool: Sequence[bool], pred_bool: Sequence[bool]) -> float:
    """Precision of the ``escalate`` class (bootstrap-friendly scalar)."""
    return escalation_metrics(gold_bool, pred_bool)["precision"]


def auto_handle_rate(pred_bool: Sequence[bool]) -> float:
    """Share of examples the system would answer without a human."""
    p = np.asarray([bool(x) for x in pred_bool], dtype=bool)
    return _safe_div(int(np.sum(~p)), int(p.size))


# ---------------------------------------------------------------------------
# Threshold re-derivation (CONTRACT.md §5)
# ---------------------------------------------------------------------------
def _has_llm_trace(row: dict[str, Any]) -> bool:
    trace = row.get("trace") or {}
    return "llm_decision" in trace or "forced_by_rules" in trace


def decision_at_threshold(row: dict[str, Any], threshold: float) -> str:
    """Recompute the final decision of an agent row for a new confidence ``threshold``.

    Per §5: ``escalate`` if ``trace.forced_by_rules`` OR ``trace.llm_decision == "escalate"`` OR
    ``intent_confidence < threshold``; otherwise ``auto_handle``. Rows without an LLM trace
    (baselines) keep their recorded decision unchanged, so the function is safe on any system.
    """
    if not _has_llm_trace(row):
        return str(row.get("decision") or "auto_handle")
    trace = row.get("trace") or {}
    if trace.get("forced_by_rules"):
        return "escalate"
    if trace.get("llm_decision") == "escalate":
        return "escalate"
    conf = row.get("intent_confidence")
    if conf is not None and float(conf) < threshold:
        return "escalate"
    return "auto_handle"


def reason_code_at_threshold(row: dict[str, Any], threshold: float) -> str | None:
    """Primary reason code that accompanies `decision_at_threshold` (``None`` when auto-handling).

    The stated reason is the rule's when rules forced the escalation, else the LLM's, else
    ``low_confidence`` when only the threshold triggered it.
    """
    if decision_at_threshold(row, threshold) != "escalate":
        return None
    recorded = (row.get("escalation") or {}).get("reason_code")
    if not _has_llm_trace(row):
        return recorded
    trace = row.get("trace") or {}
    if trace.get("forced_by_rules"):
        return trace.get("rule_reason_code") or recorded
    if trace.get("llm_decision") == "escalate":
        return trace.get("llm_reason_code") or recorded
    return LOW_CONFIDENCE


def apply_threshold(rows: Sequence[dict[str, Any]], threshold: float) -> list[dict[str, Any]]:
    """Return deep copies of ``rows`` with ``decision``/``escalation`` recomputed at ``threshold``."""
    out: list[dict[str, Any]] = []
    for row in rows:
        new = copy.deepcopy(row)
        decision = decision_at_threshold(row, threshold)
        new["decision"] = decision
        if decision == "escalate":
            code = reason_code_at_threshold(row, threshold)
            previous = row.get("escalation") or {}
            reason = previous.get("reason") if previous.get("reason_code") == code else None
            new["escalation"] = {
                "reason_code": code,
                "reason": reason
                or f"Escalated with reason code '{code}' at confidence threshold {threshold:.2f}.",
            }
        else:
            new["escalation"] = None
        out.append(new)
    return out


def threshold_sweep(
    rows: Sequence[dict[str, Any]],
    gold: Sequence[bool],
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> list[dict[str, Any]]:
    """Escalation metrics of ``rows`` at every threshold, without any new LLM calls."""
    if len(rows) != len(gold):
        raise ValueError(f"rows and gold must be aligned (got {len(rows)} vs {len(gold)})")
    sweep: list[dict[str, Any]] = []
    for t in thresholds:
        pred = [decision_at_threshold(r, t) == "escalate" for r in rows]
        m = escalation_metrics(gold, pred)
        sweep.append(
            {
                "threshold": float(t),
                "recall": m["recall"],
                "precision": m["precision"],
                "f1": m["f1"],
                "auto_handle_rate": m["auto_handle_rate"],
                "missed_escalations": m["missed_escalations"],
                "unnecessary_escalations": m["unnecessary_escalations"],
            }
        )
    return sweep


def default_threshold() -> float:
    """The policy threshold from ``config/escalation.yaml`` (fallback when no dev rows exist)."""
    return float(escalation_config().get("confidence_threshold", 0.6))


def choose_threshold(
    dev_rows: Sequence[dict[str, Any]],
    dev_gold: Sequence[bool],
    min_recall: float = 0.9,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> float:
    """Pick the confidence threshold on the dev split.

    Rule: among thresholds whose escalation recall on dev is ``>= min_recall``, take the one with
    the highest auto-handle rate; ties go to the *highest* threshold (identical dev decisions, so
    prefer the safer setting — a missed escalation is the costly error). If no threshold reaches
    ``min_recall``, fall back to the threshold with the best recall-weighted F2 on dev (ties → higher
    threshold). ``threshold >= 1.0`` is never chosen: it escalates every message, i.e. it *is* the
    trivial always-escalate baseline. With no dev rows the ``config/escalation.yaml`` default is returned.
    """
    if not dev_rows:
        return default_threshold()
    sweep = [s for s in threshold_sweep(dev_rows, dev_gold, thresholds) if s["threshold"] < 1.0]
    if not sweep:
        return default_threshold()
    eligible = [s for s in sweep if s["recall"] >= min_recall]
    if eligible:
        best = max(eligible, key=lambda s: (s["auto_handle_rate"], s["threshold"]))
    else:
        best = max(sweep, key=lambda s: (_f_beta(s["precision"], s["recall"], beta=2.0), s["threshold"]))
    return float(best["threshold"])


def _f_beta(precision: float, recall: float, beta: float = 2.0) -> float:
    """F-beta score (beta > 1 weights recall more, matching the cost of a missed escalation)."""
    if precision <= 0 and recall <= 0:
        return 0.0
    b2 = beta * beta
    denominator = b2 * precision + recall
    return (1 + b2) * precision * recall / denominator if denominator else 0.0
