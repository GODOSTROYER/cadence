"""Report figures (matplotlib, Agg backend, white background, 150 dpi, one muted palette).

Every ``plot_*`` function takes plain data (as stored in ``eval_summary.json``) and a target path and
returns the written path. ``make_all_figures`` renders every chart the summary supports and skips the
ones whose data is absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402  (backend must be selected before pyplot import)
import numpy as np  # noqa: E402

from cadence.config import JUDGED_SYSTEMS, Paths  # noqa: E402
from cadence.utils.log import get_logger  # noqa: E402

log = get_logger(__name__)

PALETTE: tuple[str, ...] = ("#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860", "#64B5CD")
"""Muted categorical palette used by every figure."""
SCORE_PALETTE: tuple[str, ...] = ("#C44E52", "#DD8452", "#CCB974", "#8AB07D", "#55A868")
"""1 → 5 colours for stacked score distributions."""
DPI = 150
GRID_COLOR = "#DDDDDD"


def _new_figure(width: float, height: float) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(width, height), facecolor="white")
    ax.set_facecolor("white")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return fig, ax


def _save(fig: plt.Figure, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


def _short(label: str) -> str:
    return label.replace("_or_", "/").replace("_", " ")


def plot_confusion_matrix(labels: Sequence[str], matrix: Sequence[Sequence[int]], path: Path) -> Path:
    """Row-normalised confusion heat-map with raw counts annotated."""
    m = np.asarray(matrix, dtype=float)
    row_sums = m.sum(axis=1, keepdims=True)
    norm = np.divide(m, np.where(row_sums == 0, 1, row_sums))
    size = max(5.0, 0.55 * len(labels) + 1.5)
    fig, ax = _new_figure(size, size)
    ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels([_short(lab) for lab in labels], rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([_short(lab) for lab in labels], fontsize=8)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if m[i, j]:
                ax.text(
                    j,
                    i,
                    f"{int(m[i, j])}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if norm[i, j] > 0.5 else "#222222",
                )
    ax.set_xlabel("Predicted intent")
    ax.set_ylabel("Gold intent")
    ax.set_title("Agent intent confusion (test split)")
    for spine in ax.spines.values():
        spine.set_visible(False)
    return _save(fig, path)


def plot_per_intent_f1(
    per_class: dict[str, dict[str, Any]],
    ci: dict[str, Sequence[float]] | None,
    path: Path,
) -> Path:
    """Horizontal bars of per-intent F1 with 95% CI whiskers and support annotations."""
    labels = list(per_class)
    f1 = np.array([per_class[lab]["f1"] for lab in labels])
    fig, ax = _new_figure(7.5, max(3.5, 0.4 * len(labels) + 1))
    y = np.arange(len(labels))
    ax.barh(y, f1, color=PALETTE[0], height=0.6)
    if ci:
        lo = np.array([ci.get(lab, (f, f))[0] for lab, f in zip(labels, f1, strict=True)])
        hi = np.array([ci.get(lab, (f, f))[1] for lab, f in zip(labels, f1, strict=True)])
        ax.errorbar(
            f1,
            y,
            xerr=[np.clip(f1 - lo, 0, None), np.clip(hi - f1, 0, None)],
            fmt="none",
            ecolor="#333333",
            elinewidth=1,
            capsize=3,
        )
    for i, lab in enumerate(labels):
        ax.text(1.02, i, f"n={per_class[lab]['support']}", va="center", fontsize=8, color="#555555")
    ax.set_yticks(y)
    ax.set_yticklabels([_short(lab) for lab in labels], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.15)
    ax.set_xlabel("F1 (95% bootstrap CI)")
    ax.set_title("Per-intent F1 — agent")
    ax.grid(axis="x", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    return _save(fig, path)


def plot_threshold_sweep(sweep: Sequence[dict[str, Any]], chosen: float | None, path: Path) -> Path:
    """Escalation recall / precision / auto-handle rate as a function of the confidence threshold."""
    t = [s["threshold"] for s in sweep]
    fig, ax = _new_figure(7, 4.2)
    for key, color, label in (
        ("recall", PALETTE[3], "Escalation recall"),
        ("precision", PALETTE[0], "Escalation precision"),
        ("auto_handle_rate", PALETTE[2], "Auto-handle rate"),
    ):
        ax.plot(
            t, [s[key] for s in sweep], marker="o", markersize=3.5, color=color, label=label, linewidth=1.6
        )
    if chosen is not None:
        ax.axvline(chosen, color="#555555", linestyle="--", linewidth=1)
        ax.text(chosen, 1.02, f"chosen {chosen:.2f}", ha="center", fontsize=8, color="#555555")
    ax.set_ylim(0, 1.08)
    ax.set_xlabel("Intent-confidence threshold (below → escalate)")
    ax.set_ylabel("Rate")
    ax.set_title("Threshold sweep (agent, no new LLM calls)")
    ax.grid(color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    return _save(fig, path)


def plot_judge_scores(systems: dict[str, dict[str, Any]], path: Path) -> Path:
    """Stacked distribution of the judge's ``overall`` score (1–5) per system."""
    names = [s for s in JUDGED_SYSTEMS if s in systems] + sorted(set(systems) - set(JUDGED_SYSTEMS))
    fig, ax = _new_figure(7, 3.6)
    left = np.zeros(len(names))
    for score in range(1, 6):
        counts = np.array([systems[n].get("dist_overall", [0] * 5)[score - 1] for n in names], dtype=float)
        totals = np.array([max(1, sum(systems[n].get("dist_overall", [0] * 5))) for n in names], dtype=float)
        share = counts / totals
        ax.barh(names, share, left=left, color=SCORE_PALETTE[score - 1], label=str(score), height=0.55)
        for i, (c, s) in enumerate(zip(counts, share, strict=True)):
            if s > 0.06:
                ax.text(left[i] + s / 2, i, f"{int(c)}", ha="center", va="center", fontsize=8, color="white")
        left += share
    ax.set_xlim(0, 1)
    ax.set_xlabel("Share of test examples")
    ax.set_title("Judge overall score distribution per system")
    ax.legend(
        title="overall",
        ncol=5,
        frameon=False,
        fontsize=8,
        title_fontsize=8,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
    )
    ax.invert_yaxis()
    return _save(fig, path)


def plot_judge_agreement(
    pairs: Sequence[dict[str, Any]], path: Path, stats: dict[str, Any] | None = None
) -> Path:
    """Jittered human-vs-judge scatter on ``overall`` with the identity line."""
    rng = np.random.default_rng(0)
    human = np.array([p["human"] for p in pairs], dtype=float)
    judge = np.array([p["judge"] for p in pairs], dtype=float)
    fig, ax = _new_figure(4.8, 4.8)
    ax.plot([0.5, 5.5], [0.5, 5.5], color="#888888", linestyle="--", linewidth=1, label="identity")
    ax.scatter(
        human + rng.uniform(-0.18, 0.18, human.size),
        judge + rng.uniform(-0.18, 0.18, judge.size),
        s=28,
        alpha=0.65,
        color=PALETTE[0],
        edgecolor="white",
        linewidth=0.5,
    )
    ax.set_xlim(0.5, 5.5)
    ax.set_ylim(0.5, 5.5)
    ax.set_xticks(range(1, 6))
    ax.set_yticks(range(1, 6))
    ax.set_xlabel("Human overall")
    ax.set_ylabel("Judge overall")
    title = f"Human vs judge (n={len(pairs)})"
    if stats and stats.get("weighted_kappa_overall") is not None:
        title += f"  κw={stats['weighted_kappa_overall']:.2f}"
    if stats and stats.get("spearman_overall") is not None:
        title += f"  ρ={stats['spearman_overall']:.2f}"
    ax.set_title(title, fontsize=10)
    ax.grid(color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    return _save(fig, path)


def plot_baselines(summary: dict[str, Any], path: Path) -> Path:
    """Grouped bars: intent macro-F1, escalation recall and judge overall (scaled to 0–1) per system."""
    intent = summary.get("intent", {}).get("systems", {})
    esc = summary.get("escalation", {}).get("systems", {})
    quality = summary.get("reply_quality", {}).get("systems", {})
    names = sorted(set(intent) | set(esc) | set(quality), key=lambda n: (n != "agent", n))
    metrics = (
        ("Intent macro-F1", [intent.get(n, {}).get("macro_f1") for n in names], PALETTE[0]),
        ("Escalation recall", [esc.get(n, {}).get("recall") for n in names], PALETTE[3]),
        (
            "Judge overall / 5",
            [
                (quality[n]["mean"]["overall"] / 5) if n in quality and quality[n].get("mean") else None
                for n in names
            ],
            PALETTE[2],
        ),
    )
    fig, ax = _new_figure(max(6.5, 1.3 * len(names) + 2), 4)
    x = np.arange(len(names))
    width = 0.26
    for k, (label, values, color) in enumerate(metrics):
        vals = np.array([np.nan if v is None else float(v) for v in values])
        bars = ax.bar(x + (k - 1) * width, np.nan_to_num(vals), width, color=color, label=label)
        for bar, v in zip(bars, vals, strict=True):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels([_short(n) for n in names], fontsize=9)
    ax.set_ylim(0, 1.1)
    ax.set_title("Systems compared (test split)")
    ax.grid(axis="y", color=GRID_COLOR, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    return _save(fig, path)


def make_all_figures(summary: dict[str, Any], out_dir: Path | None = None) -> list[Path]:
    """Render every figure the summary has data for into ``out_dir`` (default ``results/figures``)."""
    out = Path(out_dir) if out_dir is not None else Paths.FIGURES
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    agent_intent = summary.get("intent", {}).get("systems", {}).get("agent")
    if agent_intent:
        conf = agent_intent["confusion"]
        written.append(plot_confusion_matrix(conf["labels"], conf["matrix"], out / "confusion_matrix.png"))
        written.append(
            plot_per_intent_f1(
                agent_intent["per_class"],
                agent_intent.get("ci95", {}).get("per_class_f1"),
                out / "per_intent_f1.png",
            )
        )
    sweep = summary.get("escalation", {}).get("threshold_sweep")
    if sweep:
        written.append(
            plot_threshold_sweep(sweep, summary.get("meta", {}).get("threshold"), out / "threshold_sweep.png")
        )
    quality = summary.get("reply_quality", {}).get("systems")
    if quality:
        written.append(plot_judge_scores(quality, out / "judge_scores.png"))
    agreement = summary.get("judge_agreement")
    if agreement and agreement.get("pairs"):
        written.append(plot_judge_agreement(agreement["pairs"], out / "judge_agreement.png", agreement))
    if summary.get("intent", {}).get("systems") or summary.get("escalation", {}).get("systems"):
        written.append(plot_baselines(summary, out / "baselines.png"))
    log.info("wrote %d figures to %s", len(written), out)
    return written
