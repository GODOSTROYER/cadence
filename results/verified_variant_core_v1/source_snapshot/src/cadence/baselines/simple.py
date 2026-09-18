"""Simple baselines (CONTRACT.md §15.1 ``simple`` and ``simple_keyword``).

* ``keyword_intent``   — keyword hit counting over ``config/intents.yaml``.
* ``tfidf_lr_oof``     — TF-IDF + LogisticRegression, 5-fold out-of-fold predictions over the golden set.
* ``rules_decision``   — deterministic escalation rules only (``cadence.agent.rules`` when available,
                          otherwise the same regexes compiled here from ``config/escalation.yaml``).
* ``run_simple``       — intent (TF-IDF+LR) + rules decision + nearest-neighbour historical reply.
* ``run_simple_keyword`` — copies of the ``simple`` rows with the keyword intent.
"""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.pipeline import Pipeline

from cadence.baselines._common import (
    Response,
    build_response,
    copy_response,
    escalation_payload,
    gold_intent,
    row_id,
    row_text,
    row_thread_id,
    trace_payload,
)
from cadence.baselines.nn_reply import SupportsSearch, nearest_reply
from cadence.config import SEED, escalation_config, intents_config
from cadence.utils.log import get_logger
from cadence.utils.text import word_count

logger = get_logger(__name__)

SYSTEM_SIMPLE = "simple"
SYSTEM_KEYWORD = "simple_keyword"
MODEL_SIMPLE = "tfidf_lr+rules+bm25_nn"
MODEL_KEYWORD = "keyword+rules+bm25_nn"
FALLBACK_INTENT = "other"
N_SPLITS = 5
WORD_BOUNDARY_MAX_LEN = 4
"""Keywords this short or shorter must match as whole words ("hi" must not fire on "this")."""
FALLBACK_REASON_CODE = "ambiguous_or_media_only"
TOO_SHORT_FLAG = "too_short"
"""Same flag name as ``cadence.agent.rules`` for messages under ``min_words_for_auto_handle``."""


# ---------------------------------------------------------------------------
# Keyword classifier
# ---------------------------------------------------------------------------
def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Substring match for long keywords, whole-word match for short ones (boundaries only next to \\w)."""
    kw = keyword.lower()
    escaped = re.escape(kw)
    if len(kw) > WORD_BOUNDARY_MAX_LEN:
        return re.compile(escaped)
    prefix = r"(?<!\w)" if kw[0].isalnum() else ""
    suffix = r"(?!\w)" if kw[-1].isalnum() else ""
    return re.compile(prefix + escaped + suffix)


@lru_cache(maxsize=1)
def _intent_patterns() -> tuple[tuple[str, tuple[re.Pattern[str], ...]], ...]:
    """(intent_id, compiled keyword patterns) in taxonomy order."""
    return tuple(
        (intent["id"], tuple(_keyword_pattern(k) for k in intent.get("keywords") or [] if str(k).strip()))
        for intent in intents_config()["intents"]
    )


def keyword_hits(text: str) -> dict[str, int]:
    """Number of keyword occurrences per intent (taxonomy order)."""
    lowered = text.lower()
    return {
        intent: sum(len(pattern.findall(lowered)) for pattern in patterns)
        for intent, patterns in _intent_patterns()
    }


def keyword_intent(text: str) -> str:
    """Intent with the most keyword hits; ties go to the earlier intent; no hits at all -> ``other``."""
    hits = keyword_hits(text)
    best = max(hits.values(), default=0)
    if best == 0:
        return FALLBACK_INTENT
    return next(intent for intent, n in hits.items() if n == best)


# ---------------------------------------------------------------------------
# TF-IDF + LogisticRegression, out-of-fold
# ---------------------------------------------------------------------------
def _make_classifier() -> Pipeline:
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("lr", LogisticRegression(C=4, max_iter=2000, class_weight="balanced")),
        ]
    )


def _fit_predict(
    train_texts: Sequence[str], train_labels: Sequence[str], test_texts: Sequence[str]
) -> list[str]:
    """Fit on the training fold and label the test fold; a single-class fold predicts that class."""
    classes = set(train_labels)
    if len(classes) == 1:
        return [next(iter(classes))] * len(test_texts)
    clf = _make_classifier()
    clf.fit(list(train_texts), list(train_labels))
    return [str(p) for p in clf.predict(list(test_texts))]


def _make_splitter(labels: Sequence[str], n_splits: int) -> KFold | StratifiedKFold:
    """StratifiedKFold when every class has at least ``n_splits`` rows, else plain KFold."""
    n_splits = min(n_splits, len(labels))
    if min(Counter(labels).values()) >= n_splits:
        return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=SEED)
    logger.info("stratification impossible (a class has < %d rows); falling back to KFold", n_splits)
    return KFold(n_splits=n_splits, shuffle=True, random_state=SEED)


def tfidf_lr_oof(rows: Sequence[Mapping[str, Any]], *, n_splits: int = N_SPLITS) -> list[str]:
    """Out-of-fold TF-IDF+LR intent predictions aligned with ``rows``.

    Labelled rows are predicted out-of-fold; unlabelled rows (candidates mixed in) are predicted by a
    model fit on all labelled rows. With fewer than two labelled classes the keyword classifier is used.
    """
    texts = [row_text(r) for r in rows]
    labels = [gold_intent(r) for r in rows]
    labelled = [i for i, y in enumerate(labels) if y]
    predictions = [keyword_intent(t) for t in texts]
    if len(labelled) < 2 or len({labels[i] for i in labelled}) < 2:
        logger.info("tfidf_lr_oof: not enough labelled rows/classes; returning keyword predictions")
        return predictions

    x = np.array([texts[i] for i in labelled], dtype=object)
    y = np.array([labels[i] for i in labelled], dtype=object)
    for train_idx, test_idx in _make_splitter(list(y), n_splits).split(x, y):
        for j, pred in zip(test_idx, _fit_predict(x[train_idx], y[train_idx], x[test_idx]), strict=True):
            predictions[labelled[j]] = pred

    unlabelled = sorted(set(range(len(rows))) - set(labelled))
    if unlabelled:
        for j, pred in zip(unlabelled, _fit_predict(x, y, [texts[i] for i in unlabelled]), strict=True):
            predictions[j] = pred
    return predictions


# ---------------------------------------------------------------------------
# Rules-only decision
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RuleOutcome:
    """Decision derived from deterministic rules alone."""

    decision: str
    escalation: dict[str, str] | None
    rule_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _LocalRuleResult:
    """Mirror of ``cadence.agent.rules.RuleResult`` (§15.3) for the fallback implementation."""

    flags: list[str]
    soft_flags: list[str]
    force_escalate: bool
    reason_code: str | None
    reason: str | None


@dataclass(frozen=True)
class _CompiledRule:
    flag: str
    patterns: tuple[re.Pattern[str], ...]
    force_escalate: bool
    reason_code: str | None
    reason: str | None

    def matches(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


@lru_cache(maxsize=1)
def _compiled_rules() -> tuple[tuple[_CompiledRule, ...], tuple[_CompiledRule, ...], int]:
    """(hard rules, soft flags, min words for auto_handle) compiled from ``config/escalation.yaml``."""
    cfg = escalation_config()

    def compile_rule(entry: Mapping[str, Any], hard: bool) -> _CompiledRule:
        return _CompiledRule(
            flag=str(entry["flag"]),
            patterns=tuple(re.compile(str(p), re.IGNORECASE) for p in entry.get("patterns") or []),
            force_escalate=bool(entry.get("force_escalate", False)) if hard else False,
            reason_code=entry.get("reason_code") if hard else None,
            reason=entry.get("reason") if hard else None,
        )

    hard_rules = tuple(compile_rule(r, hard=True) for r in cfg.get("rules") or [])
    soft_rules = tuple(compile_rule(r, hard=False) for r in cfg.get("soft_flags") or [])
    return hard_rules, soft_rules, int(cfg.get("min_words_for_auto_handle", 0))


def _local_apply_rules(text: str) -> _LocalRuleResult:
    """Same semantics as ``cadence.agent.rules.apply_rules``: the first forcing rule owns the reason,
    and a message shorter than ``min_words_for_auto_handle`` is flagged ``too_short``."""
    hard_rules, soft_rules, min_words = _compiled_rules()
    fired = [r for r in hard_rules if r.matches(text)]
    forcing = next((r for r in fired if r.force_escalate), None)
    flags = [r.flag for r in fired]
    reason_code = forcing.reason_code if forcing else None
    reason = forcing.reason if forcing else None
    n_words = word_count(text)
    if n_words < min_words:
        flags.append(TOO_SHORT_FLAG)
        if forcing is None:
            reason_code = FALLBACK_REASON_CODE
            reason = f"Message has only {n_words} word(s) (fewer than {min_words}); too short to determine the issue."
    return _LocalRuleResult(
        flags=flags,
        soft_flags=[r.flag for r in soft_rules if r.matches(text)],
        force_escalate=reason_code is not None,
        reason_code=reason_code,
        reason=reason,
    )


_AGENT_RULES_UNAVAILABLE_LOGGED = False


def _apply_rules(text: str) -> Any:
    """``cadence.agent.rules.apply_rules`` when importable and healthy, else the local compilation."""
    global _AGENT_RULES_UNAVAILABLE_LOGGED
    try:
        from cadence.agent.rules import apply_rules

        return apply_rules(text)
    except Exception as exc:  # ImportError before the agent lands, or a runtime fault in it — never crash
        if not _AGENT_RULES_UNAVAILABLE_LOGGED:
            logger.info("using baseline-local escalation rules (cadence.agent.rules unavailable: %s)", exc)
            _AGENT_RULES_UNAVAILABLE_LOGGED = True
        return _local_apply_rules(text)


def rules_decision(text: str) -> RuleOutcome:
    """Escalate iff a deterministic rule forces it; otherwise auto_handle."""
    result = _apply_rules(text)
    flags = [str(f) for f in getattr(result, "flags", [])] + [
        str(f) for f in getattr(result, "soft_flags", [])
    ]
    if not getattr(result, "force_escalate", False):
        return RuleOutcome(decision="auto_handle", escalation=None, rule_flags=flags)
    reason_code = str(getattr(result, "reason_code", None) or FALLBACK_REASON_CODE)
    reason = str(getattr(result, "reason", None) or "A deterministic escalation rule fired.")
    return RuleOutcome(
        decision="escalate", escalation=escalation_payload(reason_code, reason), rule_flags=flags
    )


# ---------------------------------------------------------------------------
# Systems
# ---------------------------------------------------------------------------
def run_simple(rows: Sequence[Mapping[str, Any]], retriever: SupportsSearch) -> list[Response]:
    """``simple`` rows: TF-IDF+LR intent, rules-only decision, nearest-neighbour reply."""
    intents = tfidf_lr_oof(rows)
    responses: list[Response] = []
    for row, intent in zip(rows, intents, strict=True):
        started = time.perf_counter()
        text = row_text(row)
        thread_id = row_thread_id(row)
        outcome = rules_decision(text)
        neighbour = nearest_reply(retriever, text, {thread_id} if thread_id else set())
        responses.append(
            build_response(
                id=row_id(row),
                system=SYSTEM_SIMPLE,
                input_text=text,
                intent=intent,
                decision=outcome.decision,
                escalation=outcome.escalation,
                rule_flags=outcome.rule_flags,
                reply_draft=neighbour.reply,
                citations=neighbour.citations,
                evidence=neighbour.evidence,
                grounding_notes=(
                    f"Verbatim first brand reply of nearest thread {neighbour.citations[0]}."
                    if neighbour.citations
                    else "No historical neighbour found."
                ),
                model=MODEL_SIMPLE,
                latency_ms=int((time.perf_counter() - started) * 1000),
                trace=trace_payload(forced_by_rules=outcome.decision == "escalate"),
            )
        )
    return responses


def run_simple_keyword(rows: Sequence[Mapping[str, Any]], simple_rows: Sequence[Response]) -> list[Response]:
    """``simple_keyword`` rows: the ``simple`` rows with the keyword intent swapped in."""
    if len(rows) != len(simple_rows):
        raise ValueError(f"simple rows ({len(simple_rows)}) are not aligned with golden rows ({len(rows)})")
    return [
        copy_response(base, system=SYSTEM_KEYWORD, intent=keyword_intent(row_text(row)), model=MODEL_KEYWORD)
        for row, base in zip(rows, simple_rows, strict=True)
    ]


class TrainedIntentBaseline:
    """Train once on an explicit training split; predictions never accept evaluation labels."""

    def __init__(self):
        self.classifier = _make_classifier()
        self.training_ids = set()
        self.training_texts = set()
        self.fitted = False

    def fit(self, rows):
        if not rows or any(not gold_intent(r) for r in rows):
            raise ValueError("Every training row needs a label")
        if len({gold_intent(r) for r in rows}) < 2:
            raise ValueError("Training needs at least two intent classes")
        self.training_ids = {row_id(r) for r in rows}
        if len(self.training_ids) != len(rows):
            raise ValueError("Duplicate training IDs")
        self.training_texts = {row_text(r).strip().casefold() for r in rows}
        self.classifier.fit([row_text(r) for r in rows], [gold_intent(r) for r in rows])
        self.fitted = True
        return self

    def predict(self, rows):
        if not self.fitted:
            raise ValueError("Fit on designated training data first")
        if self.training_ids & {row_id(r) for r in rows} or self.training_texts & {row_text(r).strip().casefold() for r in rows}:
            raise ValueError("Training/evaluation overlap")
        return self.classifier.predict([row_text(r) for r in rows]).tolist()

    def run(self, rows, retriever, *, exclude_thread_ids=None):
        classify_start = time.perf_counter()
        predictions = self.predict(rows)
        classify_ms = (time.perf_counter() - classify_start) * 1000 / max(1, len(rows))
        output = []
        for row, intent in zip(rows, predictions, strict=True):
            start = time.perf_counter()
            text = row_text(row)
            outcome = rules_decision(text)
            nearest = nearest_reply(retriever, text, set(exclude_thread_ids or ()) | {row_thread_id(row)})
            output.append(build_response(id=row_id(row), system="trained_tfidf_lr", input_text=text,
                intent=intent, decision=outcome.decision, escalation=outcome.escalation,
                rule_flags=outcome.rule_flags, reply_draft=nearest.reply, citations=nearest.citations,
                evidence=nearest.evidence, model="trained_tfidf_lr+rules+nearest",
                latency_ms=round((time.perf_counter()-start)*1000 + classify_ms), trace=trace_payload(forced_by_rules=outcome.decision=="escalate")))
        return output
