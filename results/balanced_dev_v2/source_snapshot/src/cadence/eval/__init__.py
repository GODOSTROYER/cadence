"""Evaluation harness: metrics, bootstrap CIs, agreement, LLM judge, failure mining, figures, run_eval.

See CONTRACT.md §7–§9, §13 and §15.5.
"""

from cadence.eval.agreement import (
    annotator_agreement,
    cohens_kappa,
    exact_agreement,
    judge_agreement,
    spearman,
    within_one,
)
from cadence.eval.bootstrap import bootstrap_ci, bootstrap_distribution
from cadence.eval.failures import mine_failure_modes
from cadence.eval.judge import run_judge
from cadence.eval.metrics import (
    apply_threshold,
    choose_threshold,
    decision_at_threshold,
    escalation_metrics,
    intent_metrics,
    reason_code_at_threshold,
    threshold_sweep,
)
from cadence.eval.run_eval import run_eval

__all__ = [
    "annotator_agreement",
    "apply_threshold",
    "bootstrap_ci",
    "bootstrap_distribution",
    "choose_threshold",
    "cohens_kappa",
    "decision_at_threshold",
    "escalation_metrics",
    "exact_agreement",
    "intent_metrics",
    "judge_agreement",
    "mine_failure_modes",
    "reason_code_at_threshold",
    "run_eval",
    "run_judge",
    "spearman",
    "threshold_sweep",
    "within_one",
]
