"""Failure-mode mining for the agent's predictions (CONTRACT.md §9).

Candidate groups are counted, ranked by size and the top ``k`` are emitted with real examples and a
templated hypothesis / proposed fix that a human refines in the report.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cadence.utils.text import normalize_ws, truncate

CONFIDENT = 0.8
EXAMPLE_TEXT_CHARS = 200


def _as_dict(row: Any) -> dict[str, Any]:
    return row.model_dump() if hasattr(row, "model_dump") else dict(row)


def _agent_rows(predictions: Any, system: str) -> dict[str, dict[str, Any]]:
    rows = predictions.get(system, []) if isinstance(predictions, dict) else predictions
    return {str(_as_dict(r).get("id")): _as_dict(r) for r in rows}


def _example(golden: dict[str, Any], pred: dict[str, Any], why: str) -> dict[str, Any]:
    gold = golden.get("gold") or {}
    return {
        "golden_id": golden.get("id"),
        "text": truncate(normalize_ws(str(golden.get("text") or "")), EXAMPLE_TEXT_CHARS),
        "gold_intent": gold.get("intent"),
        "pred_intent": pred.get("intent"),
        "gold_decision": "escalate" if gold.get("should_escalate") else "auto_handle",
        "pred_decision": pred.get("decision"),
        "reply_draft": truncate(normalize_ws(str(pred.get("reply_draft") or "")), 280),
        "why": why,
    }


class _Group:
    """A candidate failure mode accumulating examples."""

    def __init__(self, kind: str, title: str, hypothesis: str, proposed_fix: str) -> None:
        self.kind = kind
        self.title = title
        self.hypothesis = hypothesis
        self.proposed_fix = proposed_fix
        self.examples: list[dict[str, Any]] = []

    @property
    def count(self) -> int:
        return len(self.examples)


def _collect_groups(
    golden: Sequence[dict[str, Any]],
    agent: dict[str, dict[str, Any]],
    judge_by_id: dict[str, dict[str, Any]],
) -> list[_Group]:
    groups: dict[tuple[str, str], _Group] = {}

    def group(kind: str, key: str, title: str, hypothesis: str, fix: str) -> _Group:
        return groups.setdefault((kind, key), _Group(kind, title, hypothesis, fix))

    for g in golden:
        gid = str(g.get("id"))
        pred = agent.get(gid)
        if pred is None:
            continue
        gold = g.get("gold") or {}
        gold_intent = gold.get("intent")
        pred_intent = pred.get("intent")
        gold_esc = bool(gold.get("should_escalate"))
        pred_esc = pred.get("decision") == "escalate"
        conf = pred.get("intent_confidence")
        pred_reason = (pred.get("escalation") or {}).get("reason_code")

        if gold_intent and pred_intent != gold_intent:
            group(
                "intent_confusion",
                f"{gold_intent}->{pred_intent}",
                f"Gold intent '{gold_intent}' predicted as '{pred_intent}'",
                f"Messages about {gold_intent} share surface vocabulary with {pred_intent}; the model latches onto "
                "the more frequent reading instead of the customer's actual ask.",
                f"Add contrastive examples of '{gold_intent}' vs '{pred_intent}' to the taxonomy description and "
                "sharpen the boundary rule in the classification prompt.",
            ).examples.append(_example(g, pred, f"gold intent {gold_intent}, predicted {pred_intent}"))
            if conf is not None and float(conf) >= CONFIDENT:
                group(
                    "confidently_wrong",
                    "all",
                    f"Confidently wrong intent (confidence >= {CONFIDENT:.1f})",
                    "Confidence is poorly calibrated: the model reports high certainty on examples it misreads, "
                    "so the low-confidence escalation safety net never triggers for them.",
                    "Calibrate confidence against dev accuracy (e.g. temperature scaling or a stricter rubric for "
                    "reporting confidence) and route high-confidence disagreements with the rules to review.",
                ).examples.append(_example(g, pred, f"confidence {float(conf):.2f} but intent wrong"))

        if gold_esc and not pred_esc:
            reason = gold.get("escalation_reason_code") or "unspecified"
            group(
                "missed_escalation",
                reason,
                f"Missed escalation: gold reason '{reason}' auto-handled",
                f"Cases that need a human for '{reason}' are phrased without the trigger words the rules look "
                "for, and the LLM treats them as routine self-serve issues.",
                f"Extend the '{reason}' rule patterns with the phrasings seen here and add an explicit "
                "escalation example for this reason code to the agent prompt.",
            ).examples.append(_example(g, pred, f"gold escalation reason {reason}; agent auto-handled"))

        if pred_esc and not gold_esc:
            reason = pred_reason or "unspecified"
            group(
                "unnecessary_escalation",
                reason,
                f"Unnecessary escalation with reason '{reason}'",
                f"The '{reason}' trigger fires on benign mentions (e.g. a keyword used in a different sense), so "
                "self-serve cases are pushed to humans and the auto-handle rate suffers.",
                f"Narrow the '{reason}' trigger (negative look-arounds, require co-occurring intent) or let the "
                "LLM overrule it when the message is clearly self-serve.",
            ).examples.append(_example(g, pred, f"agent escalated with {reason}; gold says auto-handle"))

        judge = judge_by_id.get(gid)
        flags = (judge or {}).get("flags") or {}
        if flags.get("hallucinated_link_or_policy"):
            group(
                "judge_flag",
                "hallucinated_link_or_policy",
                "Reply invents a link or policy (judge flag)",
                "The draft reaches beyond retrieved evidence, inventing help links or promises the brand never "
                "made historically.",
                "Constrain replies to links present in the evidence (post-generation link whitelist) and "
                "instruct the model to ask for a DM instead of stating policy.",
            ).examples.append(
                _example(g, pred, (judge or {}).get("rationale") or "judge flagged hallucination")
            )
        if flags.get("wrong_issue"):
            group(
                "judge_flag",
                "wrong_issue",
                "Reply addresses the wrong issue (judge flag)",
                "Retrieval surfaces a superficially similar thread and the draft mirrors that thread's fix "
                "instead of the customer's actual problem.",
                "Weight the intent label in retrieval (filter evidence by predicted intent) and ask the model to "
                "restate the issue before drafting.",
            ).examples.append(
                _example(g, pred, (judge or {}).get("rationale") or "judge flagged wrong issue")
            )

        if gold.get("media_only") and not pred_esc:
            group(
                "media_only",
                "all",
                "Screenshot-only messages are auto-handled",
                "With only a `<url>` placeholder the model guesses an issue from nothing and answers confidently "
                "instead of asking what the screenshot shows.",
                "Make the media-only rule force `ambiguous_or_media_only` whenever the text has no content words, "
                "and draft a clarifying question rather than a fix.",
            ).examples.append(_example(g, pred, "gold marks the message media-only; agent auto-handled"))
    return list(groups.values())


def mine_failure_modes(
    golden: Sequence[dict[str, Any]],
    predictions: Any,
    judge: Sequence[dict[str, Any]] | None = None,
    *,
    system: str = "agent",
    top_k: int = 5,
    max_examples: int = 3,
) -> list[dict[str, Any]]:
    """Rank the agent's failure modes and return the top ``k`` in the §9 schema.

    Args:
        golden: golden rows (typically the test split).
        predictions: ``{system: rows}`` or a flat list of rows for ``system``.
        judge: JudgeScore rows; only those for ``system`` are used (for hallucination / wrong-issue flags).
        system: which system to mine (defaults to the agent).
        top_k: how many modes to keep.
        max_examples: examples per mode (chosen by golden id for determinism).
    """
    agent = _agent_rows(predictions, system)
    judge_by_id = {str(r.get("id")): r for r in (judge or []) if r.get("system") == system}
    groups = [g for g in _collect_groups(golden, agent, judge_by_id) if g.count]
    groups.sort(key=lambda g: (-g.count, g.kind, g.title))
    n_eval = sum(1 for g in golden if str(g.get("id")) in agent)
    modes: list[dict[str, Any]] = []
    for i, grp in enumerate(groups[:top_k], start=1):
        examples = sorted(grp.examples, key=lambda e: str(e["golden_id"]))[:max_examples]
        modes.append(
            {
                "id": f"fm{i}",
                "kind": grp.kind,
                "title": grp.title,
                "count": grp.count,
                "share": round(grp.count / n_eval, 4) if n_eval else 0.0,
                "hypothesis": grp.hypothesis,
                "examples": examples,
                "proposed_fix": grp.proposed_fix,
            }
        )
    return modes
