"""Baseline systems (CONTRACT.md §13 and §15.1): trivial, simple, simple_keyword, llm_zero_shot."""

from cadence.baselines.nn_reply import NNReply, nearest_reply
from cadence.baselines.runner import BASELINE_SYSTEMS, run_baselines
from cadence.baselines.simple import (
    keyword_hits,
    keyword_intent,
    rules_decision,
    run_simple,
    run_simple_keyword,
    tfidf_lr_oof,
)
from cadence.baselines.trivial import majority_intent, run_trivial, top_template
from cadence.baselines.zero_shot import ZeroShotBatch, ZeroShotItem, build_prompt, run_zero_shot

__all__ = [
    "BASELINE_SYSTEMS",
    "NNReply",
    "ZeroShotBatch",
    "ZeroShotItem",
    "build_prompt",
    "keyword_hits",
    "keyword_intent",
    "majority_intent",
    "nearest_reply",
    "rules_decision",
    "run_baselines",
    "run_simple",
    "run_simple_keyword",
    "run_trivial",
    "run_zero_shot",
    "tfidf_lr_oof",
    "top_template",
]
