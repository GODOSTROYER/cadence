"""End-to-end evaluation: golden + predictions + judge (+ human ratings) → eval_summary.json etc.

Implements CONTRACT.md §8 (summary schema), §9 (failure modes) and §13 (protocol: the dev split only
tunes the confidence threshold; every reported number is on the test split). Missing systems or files
are omitted with a note in ``meta.notes`` — the run never crashes because a baseline is absent.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from cadence.config import (
    BRAND,
    JUDGE_DIMENSIONS,
    JUDGE_FLAGS,
    JUDGED_SYSTEMS,
    SEED,
    SYSTEMS,
    Paths,
    intent_ids,
    model_name,
)
from cadence.eval.agreement import annotator_agreement, judge_agreement
from cadence.eval.bootstrap import bootstrap_ci, bootstrap_ci_vector
from cadence.eval.failures import mine_failure_modes
from cadence.eval.metrics import (
    accuracy,
    apply_threshold,
    auto_handle_rate,
    choose_threshold,
    default_threshold,
    escalation_metrics,
    escalation_precision,
    escalation_recall,
    intent_metrics,
    macro_f1,
    per_class_f1,
    threshold_sweep,
)
from cadence.utils.io import read_jsonl, write_json
from cadence.utils.log import get_logger

log = get_logger(__name__)

LLM_SYSTEMS: tuple[str, ...] = ("agent", "llm_zero_shot")
"""Systems whose rows carry LLM call metadata (used for the cost block)."""


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass
class EvalInputs:
    """Everything `run_eval` reads from disk, already grouped and aligned by id."""

    golden: list[dict[str, Any]]
    predictions: dict[str, dict[str, dict[str, Any]]]
    judge: list[dict[str, Any]]
    human: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)

    @property
    def dev(self) -> list[dict[str, Any]]:
        return [g for g in self.golden if g.get("split") == "dev"]

    @property
    def test(self) -> list[dict[str, Any]]:
        return [g for g in self.golden if g.get("split") != "dev"]


def load_inputs(
    golden_path: Path,
    predictions_path: Path,
    judge_path: Path,
    human_path: Path,
) -> EvalInputs:
    """Read the four input files; only the golden set is mandatory."""
    if not Path(golden_path).exists():
        raise FileNotFoundError(f"golden set not found at {golden_path}; run the golden-set pipeline first")
    golden = sorted(read_jsonl(golden_path), key=lambda g: str(g.get("id")))
    notes: list[str] = []
    predictions: dict[str, dict[str, dict[str, Any]]] = {}
    if Path(predictions_path).exists():
        for row in read_jsonl(predictions_path):
            predictions.setdefault(str(row.get("system")), {})[str(row.get("id"))] = row
    else:
        notes.append(f"predictions file missing ({predictions_path}); no system metrics computed")
    judge = read_jsonl(judge_path) if Path(judge_path).exists() else []
    if not judge:
        notes.append("judge_scores.jsonl missing or empty; reply_quality omitted")
    human = read_jsonl(human_path) if Path(human_path).exists() else []
    if not human:
        notes.append("human_ratings.jsonl missing or empty; judge_agreement is null")
    missing = [s for s in SYSTEMS if s not in predictions]
    if predictions and missing:
        notes.append(f"systems without predictions: {', '.join(missing)}")
    return EvalInputs(golden=golden, predictions=predictions, judge=judge, human=human, notes=notes)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _aligned(golden: Sequence[dict[str, Any]], rows: dict[str, dict[str, Any]]) -> list[tuple[dict, dict]]:
    return [(g, rows[str(g["id"])]) for g in golden if str(g.get("id")) in rows]


def _safe_ci(fn: Callable[..., float], *arrays: Sequence[Any], n: int) -> list[float] | None:
    try:
        lo, hi = bootstrap_ci(fn, *arrays, n=n, seed=SEED)
    except ValueError:
        return None
    return [lo, hi]


def _ordered_systems(present: Sequence[str]) -> list[str]:
    return [s for s in SYSTEMS if s in present] + sorted(set(present) - set(SYSTEMS))


def _sanitize(obj: Any) -> Any:
    """Make a nested structure JSON-safe: numpy scalars → python, NaN/inf → None, tuples → lists."""
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


def _git_sha(root: Path) -> str | None:
    """Read the checked-out commit from ``.git`` without invoking git."""
    head = root / ".git" / "HEAD"
    if not head.exists():
        return None
    content = head.read_text(encoding="utf-8").strip()
    if content.startswith("ref:"):
        ref = root / ".git" / content.split(" ", 1)[1]
        return ref.read_text(encoding="utf-8").strip() if ref.exists() else None
    return content or None


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
def _labels(golden: Sequence[dict[str, Any]]) -> list[str]:
    try:
        labels = list(intent_ids())
    except (FileNotFoundError, KeyError):
        labels = []
    observed = sorted(
        {str((g.get("gold") or {}).get("intent")) for g in golden if (g.get("gold") or {}).get("intent")}
    )
    return labels + [lab for lab in observed if lab not in labels]


def _intent_block(
    inputs: EvalInputs, test_rows: dict[str, dict[str, dict]], labels: list[str], n_boot: int
) -> dict:
    test = inputs.test
    support = Counter(str((g.get("gold") or {}).get("intent")) for g in test)
    systems: dict[str, Any] = {}
    for system in _ordered_systems(list(test_rows)):
        pairs = _aligned(test, test_rows[system])
        if not pairs:
            continue
        gold = [str(g["gold"]["intent"]) for g, _ in pairs]
        pred = [p.get("intent") for _, p in pairs]
        block = intent_metrics(gold, pred, labels)
        block["ci95"] = {
            "accuracy": _safe_ci(accuracy, gold, pred, n=n_boot),
            "macro_f1": _safe_ci(lambda g, p: macro_f1(g, p, labels), gold, pred, n=n_boot),
        }
        if system == "agent":
            cis = bootstrap_ci_vector(
                lambda g, p: per_class_f1(g, p, labels), gold, pred, n=n_boot, seed=SEED
            )
            block["ci95"]["per_class_f1"] = {lab: list(ci) for lab, ci in zip(labels, cis, strict=True)}
        systems[system] = block
    return {"labels": labels, "support": {lab: support.get(lab, 0) for lab in labels}, "systems": systems}


def _escalation_system(pairs: list[tuple[dict, dict]], n_boot: int) -> dict[str, Any]:
    gold = [bool(g["gold"].get("should_escalate")) for g, _ in pairs]
    pred = [p.get("decision") == "escalate" for _, p in pairs]
    gold_reason = [g["gold"].get("escalation_reason_code") for g, _ in pairs]
    pred_reason = [(p.get("escalation") or {}).get("reason_code") for _, p in pairs]
    block = escalation_metrics(gold, pred, gold_reason, pred_reason)
    block["ci95"] = {
        "recall": _safe_ci(escalation_recall, gold, pred, n=n_boot),
        "precision": _safe_ci(escalation_precision, gold, pred, n=n_boot),
        "auto_handle_rate": _safe_ci(auto_handle_rate, pred, n=n_boot),
    }
    block["missed_examples"] = [
        str(g["id"]) for (g, _), gg, pp in zip(pairs, gold, pred, strict=True) if gg and not pp
    ]
    block["unnecessary_examples"] = [
        str(g["id"]) for (g, _), gg, pp in zip(pairs, gold, pred, strict=True) if pp and not gg
    ]
    return block


def _constant_baseline(test: Sequence[dict[str, Any]], escalate: bool, n_boot: int) -> dict[str, Any]:
    gold = [bool(g["gold"].get("should_escalate")) for g in test]
    pred = [escalate] * len(gold)
    block = escalation_metrics(gold, pred)
    block["ci95"] = {"recall": _safe_ci(escalation_recall, gold, pred, n=n_boot)}
    block["missed_examples"] = [str(g["id"]) for g, gg in zip(test, gold, strict=True) if gg and not escalate]
    return block


def _escalation_block(
    inputs: EvalInputs, test_rows: dict[str, dict[str, dict]], threshold: float, n_boot: int
) -> dict[str, Any]:
    test = inputs.test
    systems: dict[str, Any] = {}
    for system in _ordered_systems(list(test_rows)):
        pairs = _aligned(test, test_rows[system])
        if pairs:
            systems[system] = _escalation_system(pairs, n_boot)
    if test:
        systems["trivial_always_escalate"] = _constant_baseline(test, True, n_boot)
        systems["trivial_never_escalate"] = _constant_baseline(test, False, n_boot)
    sweep: list[dict[str, Any]] = []
    agent_pairs = _aligned(test, test_rows.get("agent", {}))
    if agent_pairs:
        sweep = threshold_sweep(
            [p for _, p in agent_pairs], [bool(g["gold"].get("should_escalate")) for g, _ in agent_pairs]
        )
    return {
        "systems": systems,
        "threshold": threshold,
        "threshold_chosen_on": "dev",
        "threshold_sweep": sweep,
    }


def _quality_system(rows: Sequence[dict[str, Any]], n_boot: int) -> dict[str, Any]:
    scores = {
        d: [int(r["scores"][d]) for r in rows if (r.get("scores") or {}).get(d) is not None]
        for d in JUDGE_DIMENSIONS
    }
    overall = scores["overall"]
    dist = [sum(1 for s in overall if s == k) for k in range(1, 6)]
    return {
        "n": len(rows),
        "mean": {d: (float(np.mean(v)) if v else None) for d, v in scores.items()},
        "dist_overall": dist,
        "ship_rate": float(np.mean([r.get("verdict") == "ship" for r in rows])) if rows else None,
        "flag_rates": {
            f: float(np.mean([bool((r.get("flags") or {}).get(f)) for r in rows])) for f in JUDGE_FLAGS
        },
        "ci95": {"overall": _safe_ci(lambda v: float(np.mean(v)), overall, n=n_boot) if overall else None},
    }


def _win_rate(a: dict[str, dict], b: dict[str, dict]) -> float | None:
    """Share of shared ids where system A beats B (rank when both present, else overall; ties = 0.5)."""
    shared = sorted(set(a) & set(b))
    if not shared:
        return None
    wins = 0.0
    for gid in shared:
        ra, rb = a[gid], b[gid]
        if ra.get("rank") is not None and rb.get("rank") is not None:
            wins += 1.0 if ra["rank"] < rb["rank"] else 0.5 if ra["rank"] == rb["rank"] else 0.0
        else:
            oa, ob = ra["scores"]["overall"], rb["scores"]["overall"]
            wins += 1.0 if oa > ob else 0.5 if oa == ob else 0.0
    return wins / len(shared)


def _reply_quality_block(inputs: EvalInputs, n_boot: int) -> dict[str, Any] | None:
    test_ids = {str(g["id"]) for g in inputs.test}
    by_system: dict[str, dict[str, dict]] = {}
    for row in inputs.judge:
        if str(row.get("id")) in test_ids and (row.get("scores") or {}).get("overall") is not None:
            by_system.setdefault(str(row.get("system")), {})[str(row["id"])] = row
    if not by_system:
        return None
    ordered = [s for s in JUDGED_SYSTEMS if s in by_system] + sorted(set(by_system) - set(JUDGED_SYSTEMS))
    systems = {s: _quality_system(list(by_system[s].values()), n_boot) for s in ordered}
    agent = by_system.get("agent", {})
    return {
        "systems": systems,
        "pairwise": {
            "agent_vs_nn_win_rate": _win_rate(agent, by_system.get("simple", {})),
            "agent_vs_trivial_win_rate": _win_rate(agent, by_system.get("trivial", {})),
        },
    }


def _cost_block(inputs: EvalInputs) -> dict[str, Any]:
    rows = [r for s in LLM_SYSTEMS for r in inputs.predictions.get(s, {}).values()]
    traces = [r.get("trace") or {} for r in rows]
    with_model = [r for r in rows if r.get("model")]
    cached = sum(1 for r in with_model if r.get("cached"))
    return {
        "n_llm_calls": sum(1 for r in rows if r.get("cached") is False),
        "n_llm_rows": len(rows),
        "total_prompt_tokens": int(sum(int(t.get("prompt_tokens") or 0) for t in traces)),
        "total_output_tokens": int(sum(int(t.get("output_tokens") or 0) for t in traces)),
        "wall_minutes": round(sum(float(r.get("latency_ms") or 0) for r in rows) / 60000, 3),
        "cache_hit_rate": (cached / len(with_model)) if with_model else None,
    }


def _headline(intent: dict, escalation: dict, quality: dict | None) -> dict[str, Any]:
    agent_i = intent["systems"].get("agent", {})
    agent_e = escalation["systems"].get("agent", {})
    agent_q = (quality or {}).get("systems", {}).get("agent", {})
    nn_q = (quality or {}).get("systems", {}).get("simple", {})
    return {
        "intent_macro_f1": agent_i.get("macro_f1"),
        "escalation_recall": agent_e.get("recall"),
        "auto_handle_rate": agent_e.get("auto_handle_rate"),
        "judge_overall_mean": (agent_q.get("mean") or {}).get("overall"),
        "judge_overall_mean_nn": (nn_q.get("mean") or {}).get("overall"),
        "ci95": {
            "intent_macro_f1": agent_i.get("ci95", {}).get("macro_f1"),
            "escalation_recall": agent_e.get("ci95", {}).get("recall"),
            "auto_handle_rate": agent_e.get("ci95", {}).get("auto_handle_rate"),
            "judge_overall_mean": agent_q.get("ci95", {}).get("overall"),
        },
    }


def _model_from_rows(rows: dict[str, dict[str, Any]], role: str) -> str | None:
    names = Counter(str(r["model"]) for r in rows.values() if r.get("model"))
    if names:
        return names.most_common(1)[0][0]
    try:
        return model_name(role)
    except (FileNotFoundError, KeyError):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run_eval(
    *,
    golden_path: Path | None = None,
    predictions_path: Path | None = None,
    judge_path: Path | None = None,
    human_path: Path | None = None,
    summary_path: Path | None = None,
    failures_path: Path | None = None,
    figures_dir: Path | None = None,
    n_boot: int = 1000,
    min_recall: float = 0.9,
    make_figures: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    """Compute the §8 summary and §9 failure modes, write them (plus figures) and return the summary.

    All paths default to ``cadence.config.Paths`` resolved at call time. ``n_boot`` bootstrap
    resamples (1000 per §13), ``min_recall`` is the dev-split constraint for `choose_threshold`.
    """
    inputs = load_inputs(
        golden_path or Paths.GOLDEN,
        predictions_path or Paths.PREDICTIONS,
        judge_path or Paths.JUDGE_SCORES,
        human_path or Paths.HUMAN_RATINGS,
    )
    dev, test = inputs.dev, inputs.test
    if not dev:
        inputs.notes.append("no dev split found; threshold taken from config/escalation.yaml")
    if any("split" not in g for g in inputs.golden):
        inputs.notes.append("some golden rows lack a split; treated as test")

    agent_rows = inputs.predictions.get("agent", {})
    dev_pairs = _aligned(dev, agent_rows)
    if dev_pairs:
        threshold = choose_threshold(
            [p for _, p in dev_pairs],
            [bool(g["gold"].get("should_escalate")) for g, _ in dev_pairs],
            min_recall=min_recall,
        )
    else:
        threshold = default_threshold()
        if agent_rows:
            inputs.notes.append("agent has no dev predictions; threshold taken from config/escalation.yaml")

    test_rows: dict[str, dict[str, dict]] = {s: dict(rows) for s, rows in inputs.predictions.items()}
    if agent_rows:
        agent_test = apply_threshold([p for _, p in _aligned(test, agent_rows)], threshold)
        test_rows["agent"] = {str(r["id"]): r for r in agent_test}

    labels = _labels(inputs.golden)
    intent = _intent_block(inputs, test_rows, labels, n_boot)
    escalation = _escalation_block(inputs, test_rows, threshold, n_boot)
    quality = _reply_quality_block(inputs, n_boot)
    agreement = judge_agreement(inputs.human, inputs.judge) if inputs.human and inputs.judge else None
    if agreement is None and inputs.human and inputs.judge:
        inputs.notes.append(
            "human ratings and judge scores share no (id, system) pairs; judge_agreement is null"
        )
    cost = _cost_block(inputs)
    dev_sweep = threshold_sweep([p for _, p in dev_pairs], [bool(g["gold"]["should_escalate"]) for g, _ in dev_pairs]) if dev_pairs else []
    eligible = [s for s in dev_sweep if s["threshold"] < 1 and s["recall"] >= min_recall]
    selection = {"rule": "recall_constraint" if eligible else ("f2_fallback" if dev_pairs else "config_default"),
                 "constraint_met": bool(eligible), "min_recall": min_recall,
                 "selected_dev": next((s for s in dev_sweep if s["threshold"] == threshold), None),
                 "dev_sweep": dev_sweep}

    summary = {
        "meta": {
            "brand": BRAND,
            "n_golden": len(inputs.golden),
            "n_dev": len(dev),
            "n_test": len(test),
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "agent_model": _model_from_rows(agent_rows, "agent"),
            "judge_model": next((str(r["rater"]) for r in inputs.judge if r.get("rater")), None)
            or _model_from_rows({}, "judge"),
            "git_sha": _git_sha(Paths.ROOT),
            "cache_hit_rate": cost["cache_hit_rate"],
            "threshold": threshold,
            "min_recall": min_recall,
            "threshold_selection": selection,
            "n_boot": n_boot,
            "systems": _ordered_systems(list(inputs.predictions)),
            "notes": inputs.notes,
        },
        "headline": _headline(intent, escalation, quality),
        "intent": intent,
        "escalation": escalation,
        "reply_quality": quality,
        "judge_agreement": agreement,
        "annotator_agreement": annotator_agreement(inputs.golden),
        "cost": cost,
    }
    summary = _sanitize(summary)
    failure_modes = _sanitize(
        mine_failure_modes(test, {"agent": list(test_rows.get("agent", {}).values())}, inputs.judge)
    )

    write_json(summary_path or Paths.EVAL_SUMMARY, summary)
    write_json(failures_path or Paths.FAILURE_MODES, failure_modes)
    if make_figures:
        from cadence.eval.figures import make_all_figures

        make_all_figures(summary, figures_dir or Paths.FIGURES)
    if not quiet:
        print_summary(summary, failure_modes)
    return summary


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------
def _fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _fmt_ci(ci: Sequence[float] | None) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "—"


def print_summary(summary: dict[str, Any], failure_modes: Sequence[dict[str, Any]]) -> None:
    """Pretty-print the headline numbers and per-system tables with rich."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    meta, head = summary["meta"], summary["headline"]
    console.rule(f"Cadence evaluation — {meta['brand']}")
    console.print(
        f"golden n={meta['n_golden']} (dev {meta['n_dev']}, test {meta['n_test']})  threshold={meta['threshold']:.2f}  "
        f"agent={meta.get('agent_model')}  judge={meta.get('judge_model')}"
    )
    headline = Table(title="Headline (agent, test split)", show_lines=False)
    headline.add_column("metric")
    headline.add_column("value", justify="right")
    headline.add_column("95% CI", justify="right")
    for key in ("intent_macro_f1", "escalation_recall", "auto_handle_rate", "judge_overall_mean"):
        headline.add_row(key, _fmt(head.get(key)), _fmt_ci(head["ci95"].get(key)))
    headline.add_row("judge_overall_mean_nn (simple)", _fmt(head.get("judge_overall_mean_nn")), "—")
    console.print(headline)

    systems = Table(title="Systems (test split)")
    for col in (
        "system",
        "intent acc",
        "macro-F1",
        "esc recall",
        "esc precision",
        "auto-handle",
        "missed",
        "judge overall",
    ):
        systems.add_column(col, justify="right" if col != "system" else "left")
    quality = (summary.get("reply_quality") or {}).get("systems", {})
    names = list(
        dict.fromkeys(
            list(summary["intent"]["systems"]) + list(summary["escalation"]["systems"]) + list(quality)
        )
    )
    for name in names:
        i = summary["intent"]["systems"].get(name, {})
        e = summary["escalation"]["systems"].get(name, {})
        q = quality.get(name, {})
        systems.add_row(
            name,
            _fmt(i.get("accuracy")),
            _fmt(i.get("macro_f1")),
            _fmt(e.get("recall")),
            _fmt(e.get("precision")),
            _fmt(e.get("auto_handle_rate")),
            _fmt(e.get("missed_escalations")),
            _fmt((q.get("mean") or {}).get("overall"), 2),
        )
    console.print(systems)

    agreement = summary.get("judge_agreement")
    if agreement:
        console.print(
            f"judge agreement: n={agreement['n']}  κw={_fmt(agreement['weighted_kappa_overall'])}  "
            f"ρ={_fmt(agreement['spearman_overall'])}  exact={_fmt(agreement['exact_agreement'])}  "
            f"within-1={_fmt(agreement['within_one'])}"
        )
    ann = summary.get("annotator_agreement") or {}
    console.print(
        f"annotators: intent κ={_fmt(ann.get('intent_kappa'))} raw={_fmt(ann.get('intent_raw'))}  "
        f"escalation κ={_fmt(ann.get('escalation_kappa'))} raw={_fmt(ann.get('escalation_raw'))}  "
        f"disagreements={ann.get('n_disagreements')}"
    )
    if failure_modes:
        fm = Table(title="Top failure modes (agent)")
        fm.add_column("#")
        fm.add_column("title")
        fm.add_column("count", justify="right")
        fm.add_column("share", justify="right")
        for mode in failure_modes:
            fm.add_row(mode["id"], mode["title"], str(mode["count"]), f"{mode['share']:.1%}")
        console.print(fm)
    for note in meta.get("notes", []):
        console.print(f"[yellow]note:[/yellow] {note}")
