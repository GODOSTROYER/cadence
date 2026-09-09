"""Tests for cadence.eval (metrics, bootstrap, agreement, judge, failures, run_eval)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sklearn.metrics import f1_score

from cadence.config import SEED, Paths
from cadence.eval import agreement, bootstrap, failures, judge, metrics
from cadence.eval.run_eval import run_eval
from cadence.utils.io import read_jsonl, write_jsonl

LABELS = ["a", "b", "c"]
GOLD8 = ["a", "a", "a", "b", "b", "c", "c", "c"]
PRED8 = ["a", "a", "b", "b", "b", "c", "a", "c"]


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def test_intent_metrics_hand_computed() -> None:
    m = metrics.intent_metrics(GOLD8, PRED8, LABELS)
    assert m["accuracy"] == pytest.approx(0.75)
    assert m["per_class"]["a"] == {
        "precision": pytest.approx(2 / 3),
        "recall": pytest.approx(2 / 3),
        "f1": pytest.approx(2 / 3),
        "support": 3,
    }
    assert m["per_class"]["b"]["f1"] == pytest.approx(0.8)
    assert m["per_class"]["c"]["f1"] == pytest.approx(0.8)
    assert m["macro_f1"] == pytest.approx((2 / 3 + 0.8 + 0.8) / 3)
    assert m["weighted_f1"] == pytest.approx((3 * 2 / 3 + 2 * 0.8 + 3 * 0.8) / 8)
    assert m["confusion"] == {"labels": LABELS, "matrix": [[2, 1, 0], [0, 2, 0], [1, 0, 2]]}


def test_intent_metrics_unknown_prediction_counts_as_wrong() -> None:
    m = metrics.intent_metrics(["a", "b"], [None, "b"], LABELS)
    assert m["accuracy"] == pytest.approx(0.5)
    assert m["confusion"]["labels"][-1] == metrics.UNKNOWN_LABEL
    assert m["confusion"]["matrix"][0][-1] == 1
    assert metrics.intent_metrics([], [], LABELS)["macro_f1"] == 0.0


def test_fast_macro_f1_matches_sklearn() -> None:
    fast = metrics.macro_f1(GOLD8, PRED8, LABELS)
    assert fast == pytest.approx(f1_score(GOLD8, PRED8, labels=LABELS, average="macro", zero_division=0))


def test_escalation_metrics_hand_computed() -> None:
    gold = [True, True, True, True, False, False, False, False]
    pred = [True, True, True, False, True, False, False, False]
    gold_reason = [
        "billing_dispute",
        "billing_dispute",
        "account_security",
        "legal_or_safety",
        None,
        None,
        None,
        None,
    ]
    pred_reason = [
        "billing_dispute",
        "account_security",
        "account_security",
        None,
        "low_confidence",
        None,
        None,
        None,
    ]
    m = metrics.escalation_metrics(gold, pred, gold_reason, pred_reason)
    assert m["confusion"] == {"tp": 3, "fp": 1, "fn": 1, "tn": 3}
    assert m["precision"] == pytest.approx(0.75)
    assert m["recall"] == pytest.approx(0.75)
    assert m["f1"] == pytest.approx(0.75)
    assert m["accuracy"] == pytest.approx(0.75)
    assert m["auto_handle_rate"] == pytest.approx(0.5)
    assert m["missed_escalations"] == 1
    assert m["unnecessary_escalations"] == 1
    assert m["reason_code_accuracy"] == pytest.approx(2 / 3)
    assert metrics.escalation_metrics([False], [False])["reason_code_accuracy"] is None


def _agent_row(
    conf: float | None,
    llm: str = "auto_handle",
    forced: bool = False,
    code: str | None = None,
    rid: str = "g_001",
) -> dict:
    return {
        "id": rid,
        "system": "agent",
        "intent": "playback_or_app_bug",
        "intent_confidence": conf,
        "decision": "escalate" if forced or llm == "escalate" else "auto_handle",
        "escalation": {"reason_code": code, "reason": "rule fired"} if code else None,
        "trace": {
            "llm_decision": llm,
            "llm_reason_code": code if llm == "escalate" else None,
            "forced_by_rules": forced,
        },
    }


def test_decision_at_threshold_cases() -> None:
    assert (
        metrics.decision_at_threshold(_agent_row(0.99, forced=True, code="billing_dispute"), 0.0)
        == "escalate"
    )
    assert (
        metrics.decision_at_threshold(_agent_row(0.99, llm="escalate", code="needs_account_lookup"), 0.0)
        == "escalate"
    )
    assert metrics.decision_at_threshold(_agent_row(0.4), 0.6) == "escalate"
    assert metrics.decision_at_threshold(_agent_row(0.6), 0.6) == "auto_handle"
    assert metrics.decision_at_threshold(_agent_row(None), 0.9) == "auto_handle"
    baseline = {
        "decision": "escalate",
        "intent_confidence": 1.0,
        "escalation": {"reason_code": "low_confidence"},
    }
    assert metrics.decision_at_threshold(baseline, 0.0) == "escalate"
    assert (
        metrics.reason_code_at_threshold(_agent_row(0.99, forced=True, code="billing_dispute"), 0.0)
        == "billing_dispute"
    )
    assert metrics.reason_code_at_threshold(_agent_row(0.4), 0.6) == "low_confidence"
    assert metrics.reason_code_at_threshold(_agent_row(0.9), 0.6) is None
    rethresholded = metrics.apply_threshold([_agent_row(0.4)], 0.6)[0]
    assert rethresholded["decision"] == "escalate"
    assert rethresholded["escalation"]["reason_code"] == "low_confidence"
    assert metrics.apply_threshold([_agent_row(0.4)], 0.2)[0]["escalation"] is None


def test_threshold_sweep_and_choose_threshold() -> None:
    rows = [_agent_row(c, rid=f"g_{i:03d}") for i, c in enumerate([0.2, 0.3, 0.5, 0.7, 0.9, 0.95])]
    gold = [True, True, False, False, False, False]
    sweep = metrics.threshold_sweep(rows, gold)
    assert len(sweep) == 21 and sweep[0]["threshold"] == 0.0 and sweep[-1]["threshold"] == 1.0
    at_0 = sweep[0]
    assert at_0["recall"] == 0.0 and at_0["auto_handle_rate"] == 1.0
    chosen = metrics.choose_threshold(rows, gold, min_recall=0.9)
    # thresholds 0.35..0.5 all catch both escalations with the same auto-handle rate; the tie goes to the highest
    assert chosen == pytest.approx(0.5)
    # an escalation the LLM auto-handles at confidence 1.0 can never be caught -> fall back to the highest-recall
    # thresholds (0.35..1.0, recall 2/3), tie-broken by auto-handle rate (0.35..0.5) then highest threshold
    unreachable = rows + [_agent_row(1.0, rid="g_999")]
    assert metrics.choose_threshold(unreachable, gold + [True], min_recall=0.9) == pytest.approx(0.5)
    assert metrics.choose_threshold([], [], min_recall=0.9) == pytest.approx(metrics.default_threshold())


# ---------------------------------------------------------------------------
# bootstrap
# ---------------------------------------------------------------------------
def test_bootstrap_ci_contains_point_estimate_and_is_deterministic() -> None:
    point = metrics.accuracy(GOLD8, PRED8)
    ci1 = bootstrap.bootstrap_ci(metrics.accuracy, GOLD8, PRED8, n=200)
    ci2 = bootstrap.bootstrap_ci(metrics.accuracy, GOLD8, PRED8, n=200, seed=SEED)
    assert ci1 == ci2
    assert ci1[0] <= point <= ci1[1]
    assert ci1[0] < ci1[1]
    vec = bootstrap.bootstrap_ci_vector(lambda g, p: metrics.per_class_f1(g, p, LABELS), GOLD8, PRED8, n=50)
    assert len(vec) == 3 and all(lo <= hi for lo, hi in vec)
    with pytest.raises(ValueError):
        bootstrap.bootstrap_ci(metrics.accuracy, [], [], n=10)


# ---------------------------------------------------------------------------
# agreement
# ---------------------------------------------------------------------------
def test_kappa_perfect_chance_and_total_disagreement() -> None:
    assert agreement.cohens_kappa(["x", "y", "x"], ["x", "y", "x"]) == 1.0
    assert agreement.cohens_kappa([1, 1, 1], [1, 1, 1]) == 1.0
    assert agreement.cohens_kappa([1, 2, 1, 2], [1, 1, 2, 2]) == pytest.approx(0.0)
    assert agreement.cohens_kappa([1, 1, 2, 2], [2, 2, 1, 1]) == pytest.approx(-1.0)
    assert (
        agreement.cohens_kappa([1, 2, 3, 4], [1, 2, 3, 5], weights="quadratic", labels=agreement.SCORE_LABELS)
        > 0.8
    )
    assert agreement.cohens_kappa([], []) is None
    assert agreement.spearman([1, 2, 3, 4], [1, 2, 3, 5]) == pytest.approx(1.0)
    assert agreement.spearman([1, 1, 1], [1, 2, 3]) is None
    assert agreement.exact_agreement([1, 2, 3], [1, 2, 4]) == pytest.approx(2 / 3)
    assert agreement.within_one([1, 2, 5], [2, 2, 3]) == pytest.approx(2 / 3)


def test_annotator_and_judge_agreement() -> None:
    golden = [
        {
            "annotations": {
                "a": {"intent": "a", "should_escalate": True},
                "b": {"intent": "a", "should_escalate": True},
            }
        },
        {
            "annotations": {
                "a": {"intent": "a", "should_escalate": False},
                "b": {"intent": "b", "should_escalate": False},
            }
        },
        {
            "annotations": {
                "a": {"intent": "b", "should_escalate": True},
                "b": {"intent": "b", "should_escalate": False},
            }
        },
        {"id": "no-annotations"},
    ]
    ann = agreement.annotator_agreement(golden)
    assert ann["n"] == 3 and ann["n_disagreements"] == 2
    assert ann["intent_raw"] == pytest.approx(2 / 3) and ann["escalation_raw"] == pytest.approx(2 / 3)

    def rating(gid: str, system: str, overall: int, rater: str) -> dict:
        return {
            "id": gid,
            "system": system,
            "rater": rater,
            "scores": {"grounded": overall, "resolves": overall, "tone": 5, "safe": 5, "overall": overall},
        }

    human = [
        rating("g_001", "agent", 4, "human"),
        rating("g_002", "agent", 2, "human"),
        rating("g_003", "simple", 3, "human"),
    ]
    judged = [
        rating("g_001", "agent", 5, "j"),
        rating("g_002", "agent", 2, "j"),
        rating("g_009", "agent", 1, "j"),
    ]
    ja = agreement.judge_agreement(human, judged)
    assert ja is not None and ja["n"] == 2
    assert ja["pairs"] == [
        {"id": "g_001", "system": "agent", "human": 4, "judge": 5},
        {"id": "g_002", "system": "agent", "human": 2, "judge": 2},
    ]
    assert ja["exact_agreement"] == 0.5 and ja["within_one"] == 1.0
    assert set(ja["per_dimension"]) == {"grounded", "resolves", "tone", "safe", "overall"}
    assert agreement.judge_agreement(human, []) is None


# ---------------------------------------------------------------------------
# judge
# ---------------------------------------------------------------------------
@dataclass
class _Meta:
    model: str = "mock-judge"
    cached: bool = False
    latency_ms: int = 1
    prompt_tokens: int = 10
    output_tokens: int = 10
    attempts: int = 1


class ResponderClient:
    """Fake LLM that scores a candidate by the marker word found in its reply text."""

    QUALITY = {"AGENTREPLY": 5, "NNREPLY": 3, "TEMPLATEREPLY": 1}

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.model = "mock-judge"

    def generate_json(
        self,
        prompt: str,
        schema: type,
        *,
        system: str | None = None,
        temperature: float | None = None,
        cache: bool = True,
    ):
        self.prompts.append(prompt)
        found = re.findall(r"^Reply ([ABC]): (.*)$", prompt, flags=re.M)
        candidates = []
        for label, text in found:
            score = next((v for k, v in self.QUALITY.items() if k in text), 2)
            candidates.append(
                {
                    "label": label,
                    "scores": {"grounded": score, "resolves": score, "tone": 4, "safe": 5, "overall": score},
                    "flags": {
                        "hallucinated_link_or_policy": score == 1,
                        "asks_sensitive_info": False,
                        "wrong_issue": False,
                    },
                    "verdict": "ship" if score >= 4 else "edit" if score >= 3 else "reject",
                    "rationale": f"candidate {label} scored {score}.",
                }
            )
        ranking = [c["label"] for c in sorted(candidates, key=lambda c: -c["scores"]["overall"])]
        return schema.model_validate({"candidates": candidates, "ranking": ranking}), _Meta()


def _golden(
    gid: str, split: str, intent: str, escalate: bool, code: str | None = None, media_only: bool = False
) -> dict:
    return {
        "id": gid,
        "thread_id": f"t_{gid}",
        "split": split,
        "text": f"message for {gid}",
        "historical_brand_reply": "Hey! Try a clean reinstall and let us know how it goes.",
        "gold": {
            "intent": intent,
            "should_escalate": escalate,
            "escalation_reason_code": code,
            "sentiment": "neutral",
            "media_only": media_only,
        },
        "annotations": {
            "a": {"intent": intent, "should_escalate": escalate},
            "b": {"intent": intent, "should_escalate": escalate},
        },
    }


def _pred(gid: str, system: str, reply: str, evidence: list | None = None, **overrides: Any) -> dict:
    row = {
        "id": gid,
        "system": system,
        "input_text": "x",
        "intent": "playback_or_app_bug",
        "intent_confidence": 0.9,
        "decision": "auto_handle",
        "escalation": None,
        "reply_draft": reply,
        "evidence": evidence or [],
        "model": "gemini-x" if system in ("agent", "llm_zero_shot") else None,
        "cached": False,
        "latency_ms": 100,
        "trace": {
            "llm_decision": "auto_handle",
            "forced_by_rules": False,
            "prompt_tokens": 100,
            "output_tokens": 20,
        },
    }
    row.update(overrides)
    return row


def test_run_judge_deanonymises_and_resumes() -> None:
    golden = [_golden("g_001", "test", "a", False), _golden("g_002", "test", "b", True, "billing_dispute")]
    evidence = [
        {"thread_id": "t_1", "customer_text": "app crashes", "brand_reply": "reinstall please", "score": 1.0}
    ]
    preds = {
        "agent": [
            _pred("g_001", "agent", "AGENTREPLY one", evidence),
            _pred("g_002", "agent", "AGENTREPLY two"),
        ],
        "simple": [_pred("g_001", "simple", "NNREPLY one"), _pred("g_002", "simple", "NNREPLY two")],
        "trivial": [_pred("g_001", "trivial", "TEMPLATEREPLY"), _pred("g_002", "trivial", "TEMPLATEREPLY")],
    }
    client = ResponderClient()
    sunk: list[dict] = []
    rows = judge.run_judge(golden, preds, client, sink=sunk.extend)
    assert len(rows) == 6 and sunk == rows
    by_key = {(r["id"], r["system"]): r for r in rows}
    for gid in ("g_001", "g_002"):
        assert by_key[(gid, "agent")]["scores"]["overall"] == 5 and by_key[(gid, "agent")]["rank"] == 1
        assert by_key[(gid, "simple")]["scores"]["overall"] == 3 and by_key[(gid, "simple")]["rank"] == 2
        assert by_key[(gid, "trivial")]["verdict"] == "reject" and by_key[(gid, "trivial")]["rank"] == 3
        assert by_key[(gid, "trivial")]["flags"]["hallucinated_link_or_policy"] is True
    assert all(r["rater"] == "mock-judge" and r["rated_at"] for r in rows)
    prompt = client.prompts[0]
    assert judge.RUBRIC in prompt
    assert "customer: app crashes" in prompt and "brand: reinstall please" in prompt
    assert "Historical brand reply" in prompt
    assert judge.judged_ids(rows, judge.JUDGED_SYSTEMS) == {"g_001", "g_002"}
    assert judge.run_judge(golden, preds, client, skip_ids={"g_001", "g_002"}) == []
    assert len(client.prompts) == 2


def test_judge_shuffle_is_seeded_and_deanonymisation_handles_omissions() -> None:
    golden = [_golden(f"g_{i:03d}", "test", "a", False) for i in range(6)]
    preds = {s: [_pred(g["id"], s, f"{s} reply") for g in golden] for s in ("agent", "simple", "trivial")}
    client = ResponderClient()
    judge.run_judge(golden, preds, client)
    orders = [tuple(re.findall(r"^Reply [ABC]: (\w+)", p, flags=re.M)) for p in client.prompts]
    assert len(set(orders)) > 1  # candidates really are shuffled across examples
    client2 = ResponderClient()
    judge.run_judge(golden, preds, client2)
    assert client2.prompts == client.prompts  # deterministic given SEED + index
    output = judge.JudgeOutput.model_validate(
        {
            "candidates": [
                {
                    "label": "A",
                    "scores": {"grounded": 9, "resolves": 0, "tone": 3, "safe": 3, "overall": 3},
                    "flags": {
                        "hallucinated_link_or_policy": False,
                        "asks_sensitive_info": False,
                        "wrong_issue": False,
                    },
                    "verdict": "edit",
                    "rationale": "ok",
                }
            ],
            "ranking": ["Z"],
        }
    )
    rows = judge.deanonymise("g_000", [("A", "agent"), ("B", "simple")], output, rater="m", rated_at="now")
    assert len(rows) == 1 and rows[0]["scores"] == {
        "grounded": 5,
        "resolves": 1,
        "tone": 3,
        "safe": 3,
        "overall": 3,
    }
    assert rows[0]["rank"] == 1


# ---------------------------------------------------------------------------
# failures + run_eval on a synthetic fixture
# ---------------------------------------------------------------------------
INTENTS = ["playback_or_app_bug", "billing_or_charge", "login_or_password", "other"]


def _fixture(tmp_path: Path) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    golden: list[dict] = []
    preds: list[dict] = []
    judged: list[dict] = []
    human: list[dict] = []
    for i in range(30):
        gid = f"g_{i:03d}"
        split = "dev" if i < 10 else "test"
        intent = INTENTS[i % 4]
        escalate = intent in ("billing_or_charge", "login_or_password") or i % 7 == 0
        code = {"billing_or_charge": "billing_dispute", "login_or_password": "needs_account_lookup"}.get(
            intent, "ambiguous_or_media_only"
        )
        golden.append(
            _golden(gid, split, intent, escalate, code if escalate else None, media_only=(i % 7 == 0))
        )
        # agent: mostly right, wrong on every 5th, confidence varies, rules force money cases
        pred_intent = INTENTS[(i + 1) % 4] if i % 5 == 0 else intent
        conf = 0.95 if i % 5 == 0 else 0.5 + 0.05 * (i % 10)
        forced = intent == "billing_or_charge"
        llm = "escalate" if intent == "login_or_password" and i % 3 else "auto_handle"
        decision = "escalate" if forced or llm == "escalate" else "auto_handle"
        esc = (
            {"reason_code": "billing_dispute" if forced else "needs_account_lookup", "reason": "r"}
            if decision == "escalate"
            else None
        )
        preds.append(
            _pred(
                gid,
                "agent",
                f"agent reply {i}",
                [{"thread_id": "t_x", "customer_text": "c", "brand_reply": "b", "score": 1}],
                intent=pred_intent,
                intent_confidence=conf,
                decision=decision,
                escalation=esc,
                trace={
                    "llm_decision": llm,
                    "llm_reason_code": "needs_account_lookup" if llm == "escalate" else None,
                    "forced_by_rules": forced,
                    "prompt_tokens": 100,
                    "output_tokens": 20,
                },
                cached=(i % 2 == 0),
            )
        )
        preds.append(
            _pred(
                gid,
                "trivial",
                "template",
                intent="playback_or_app_bug",
                intent_confidence=None,
                decision="escalate",
                escalation={"reason_code": "low_confidence", "reason": "trivial"},
                trace={},
            )
        )
        preds.append(
            _pred(
                gid, "simple", f"nn reply {i}", intent=INTENTS[(i + 2) % 4], intent_confidence=None, trace={}
            )
        )
        preds.append(
            _pred(gid, "simple_keyword", "", intent=INTENTS[i % 4], intent_confidence=None, trace={})
        )
        if split == "test":
            for system, overall in (
                ("agent", 4 + (i % 2)),
                ("simple", 2 + (i % 3)),
                ("trivial", 1 + (i % 2)),
            ):
                judged.append(
                    {
                        "id": gid,
                        "system": system,
                        "rater": "gemini-judge",
                        "rank": {"agent": 1, "simple": 2, "trivial": 3}[system],
                        "scores": {
                            "grounded": overall,
                            "resolves": overall,
                            "tone": 4,
                            "safe": 5,
                            "overall": overall,
                        },
                        "flags": {
                            "hallucinated_link_or_policy": system == "trivial",
                            "asks_sensitive_info": False,
                            "wrong_issue": i % 9 == 0 and system == "agent",
                        },
                        "verdict": "ship" if overall >= 4 else "edit",
                        "rationale": "r",
                        "rated_at": "2026-01-01T00:00:00+00:00",
                    }
                )
            if i % 2 == 0:
                human.append(
                    {
                        "id": gid,
                        "system": "agent",
                        "rater": "human",
                        "scores": {
                            "grounded": 4,
                            "resolves": 4,
                            "tone": 4,
                            "safe": 5,
                            "overall": 4 + (i % 4 == 0),
                        },
                        "flags": {
                            "hallucinated_link_or_policy": False,
                            "asks_sensitive_info": False,
                            "wrong_issue": False,
                        },
                        "verdict": "ship",
                        "rationale": "h",
                        "rated_at": "2026-01-02T00:00:00+00:00",
                    }
                )
    return golden, preds, judged, human


def _patch_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Paths, "GOLDEN", tmp_path / "golden_set.jsonl")
    monkeypatch.setattr(Paths, "PREDICTIONS", tmp_path / "predictions.jsonl")
    monkeypatch.setattr(Paths, "JUDGE_SCORES", tmp_path / "judge_scores.jsonl")
    monkeypatch.setattr(Paths, "HUMAN_RATINGS", tmp_path / "human_ratings.jsonl")
    monkeypatch.setattr(Paths, "EVAL_SUMMARY", tmp_path / "eval_summary.json")
    monkeypatch.setattr(Paths, "FAILURE_MODES", tmp_path / "failure_modes.json")
    monkeypatch.setattr(Paths, "FIGURES", tmp_path / "figures")


def test_mine_failure_modes_ranks_groups() -> None:
    golden, preds, judged, _ = _fixture(Path("."))
    test = [g for g in golden if g["split"] == "test"]
    agent = [p for p in preds if p["system"] == "agent"]
    modes = failures.mine_failure_modes(test, {"agent": agent}, judged)
    assert 1 <= len(modes) <= 5
    assert [m["count"] for m in modes] == sorted((m["count"] for m in modes), reverse=True)
    assert modes[0]["id"] == "fm1" and modes[0]["examples"] and len(modes[0]["examples"]) <= 3
    kinds = {m["kind"] for m in modes}
    assert kinds & {"intent_confusion", "missed_escalation", "judge_flag", "confidently_wrong", "media_only"}
    example = modes[0]["examples"][0]
    assert {
        "golden_id",
        "text",
        "gold_intent",
        "pred_intent",
        "gold_decision",
        "pred_decision",
        "reply_draft",
        "why",
    } <= set(example)
    assert failures.mine_failure_modes(test, {"agent": []}, []) == []


def test_run_eval_writes_section8_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden, preds, judged, human = _fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    write_jsonl(Paths.GOLDEN, golden)
    write_jsonl(Paths.PREDICTIONS, preds)
    write_jsonl(Paths.JUDGE_SCORES, judged)
    write_jsonl(Paths.HUMAN_RATINGS, human)

    summary = run_eval(n_boot=30, make_figures=True)

    assert set(summary) == {
        "meta",
        "headline",
        "intent",
        "escalation",
        "reply_quality",
        "judge_agreement",
        "annotator_agreement",
        "cost",
    }
    meta = summary["meta"]
    assert meta["n_golden"] == 30 and meta["n_dev"] == 10 and meta["n_test"] == 20
    assert {
        "brand",
        "generated_at",
        "agent_model",
        "judge_model",
        "git_sha",
        "cache_hit_rate",
        "threshold",
    } <= set(meta)
    assert meta["agent_model"] == "gemini-x" and meta["judge_model"] == "gemini-judge"
    assert 0.0 <= meta["threshold"] <= 1.0

    head = summary["headline"]
    assert {
        "intent_macro_f1",
        "escalation_recall",
        "auto_handle_rate",
        "judge_overall_mean",
        "judge_overall_mean_nn",
        "ci95",
    } <= set(head)
    assert head["judge_overall_mean"] > head["judge_overall_mean_nn"]
    assert len(head["ci95"]["intent_macro_f1"]) == 2

    intent = summary["intent"]
    assert set(intent["systems"]) == {"agent", "trivial", "simple", "simple_keyword"}
    agent_i = intent["systems"]["agent"]
    assert {"accuracy", "macro_f1", "weighted_f1", "per_class", "confusion", "ci95"} <= set(agent_i)
    assert agent_i["n"] == 20 and "per_class_f1" in agent_i["ci95"]
    assert sum(intent["support"].values()) == 20

    esc = summary["escalation"]
    assert {"agent", "trivial", "simple", "trivial_always_escalate", "trivial_never_escalate"} <= set(
        esc["systems"]
    )
    agent_e = esc["systems"]["agent"]
    assert {
        "precision",
        "recall",
        "f1",
        "auto_handle_rate",
        "accuracy",
        "missed_escalations",
        "unnecessary_escalations",
        "reason_code_accuracy",
        "confusion",
        "ci95",
        "missed_examples",
    } <= set(agent_e)
    assert esc["systems"]["trivial_always_escalate"]["recall"] == 1.0
    assert len(esc["threshold_sweep"]) == 21 and {
        "threshold",
        "recall",
        "precision",
        "auto_handle_rate",
    } <= set(esc["threshold_sweep"][0])

    quality = summary["reply_quality"]
    assert set(quality["systems"]) == {"agent", "simple", "trivial"}
    assert {"mean", "dist_overall", "ship_rate", "flag_rates", "ci95"} <= set(quality["systems"]["agent"])
    assert sum(quality["systems"]["agent"]["dist_overall"]) == 20
    assert (
        quality["pairwise"]["agent_vs_nn_win_rate"] == 1.0
        and quality["pairwise"]["agent_vs_trivial_win_rate"] == 1.0
    )

    ja = summary["judge_agreement"]
    assert ja["n"] == 10 and {
        "weighted_kappa_overall",
        "spearman_overall",
        "exact_agreement",
        "within_one",
        "per_dimension",
        "pairs",
    } <= set(ja)
    assert summary["annotator_agreement"]["intent_kappa"] == 1.0
    assert summary["cost"]["n_llm_calls"] == 15 and summary["cost"]["total_prompt_tokens"] == 3000

    written = json.loads(Paths.EVAL_SUMMARY.read_text(encoding="utf-8"))
    assert written["headline"]["intent_macro_f1"] == pytest.approx(head["intent_macro_f1"])
    modes = json.loads(Paths.FAILURE_MODES.read_text(encoding="utf-8"))
    assert modes and {"id", "title", "count", "share", "hypothesis", "examples", "proposed_fix"} <= set(
        modes[0]
    )
    figures = {p.name for p in Paths.FIGURES.glob("*.png")}
    assert figures == {
        "confusion_matrix.png",
        "per_intent_f1.png",
        "threshold_sweep.png",
        "judge_scores.png",
        "judge_agreement.png",
        "baselines.png",
    }


def test_run_eval_survives_missing_files_and_systems(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    golden, preds, _, _ = _fixture(tmp_path)
    _patch_paths(monkeypatch, tmp_path)
    write_jsonl(Paths.GOLDEN, golden)
    write_jsonl(Paths.PREDICTIONS, [p for p in preds if p["system"] == "simple"])
    summary = run_eval(n_boot=20, make_figures=False, quiet=True)
    assert set(summary["intent"]["systems"]) == {"simple"}
    assert summary["headline"]["intent_macro_f1"] is None
    assert summary["reply_quality"] is None and summary["judge_agreement"] is None
    assert summary["escalation"]["threshold_sweep"] == []
    assert any("judge_scores" in n for n in summary["meta"]["notes"]) and any(
        "human_ratings" in n for n in summary["meta"]["notes"]
    )
    assert Paths.EVAL_SUMMARY.exists() and read_jsonl(Paths.GOLDEN)

    Paths.PREDICTIONS.unlink()
    summary = run_eval(n_boot=20, make_figures=False, quiet=True)
    assert summary["intent"]["systems"] == {} and summary["meta"]["systems"] == []
    with pytest.raises(FileNotFoundError):
        run_eval(golden_path=tmp_path / "nope.jsonl", make_figures=False, quiet=True)
