"""Export results and golden data into ``ui/public/data/*.json`` for the static UI (CONTRACT.md §11).

Writes ``eval_summary.json`` (with ``results/caveats.json`` merged into ``meta.caveats`` and
``data/processed/stats.json`` summarised into ``meta.dataset``), ``failure_modes.json``,
``golden_merged.json`` (same shape as ``GET /api/golden``), ``decisions.json`` and ``health.json``. A missing source is skipped with a
warning so a partially built pipeline can still be exported; the script never crashes on absent files.

Usage: ``python scripts/07_export_ui_data.py [--out DIR]``
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cadence.api.decisions import parse_decision_log
from cadence.api.merge import merge_golden
from cadence.api.state import STATE, count_cache_entries, count_jsonl, health_payload
from cadence.config import Paths, model_name
from cadence.utils.io import read_json, read_jsonl, write_json
from cadence.utils.log import get_logger

log = get_logger("cadence.scripts.export_ui_data")


def _copy_json(source: Path, target: Path) -> bool:
    """Copy a JSON artifact verbatim; returns False (with a warning) when the source is missing."""
    if not source.exists():
        log.warning("skipping %s: %s not found", target.name, source)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    log.info("wrote %s", target)
    return True


#: Brand count in the Kaggle dump (CONTRACT §2, measured once); stats.json is Spotify-only and does not carry it.
N_BRANDS_IN_DUMP = 108
#: Months holding at least this share of openers form the "bulk" period quoted in the UI.
BULK_MONTH_SHARE = 0.05


def _bulk_period(per_month: dict[str, int]) -> tuple[str, str, float] | None:
    """(first month, last month, share) of the contiguous run of months that each hold ≥5% of openers."""
    total = sum(per_month.values())
    if total <= 0:
        return None
    months = sorted(m for m, n in per_month.items() if n / total >= BULK_MONTH_SHARE)
    if not months:
        return None
    share = sum(per_month[m] for m in months) / total
    return months[0], months[-1], round(share, 4)


def dataset_facts(stats: dict[str, Any]) -> dict[str, Any]:
    """``meta.dataset`` (ui/src/lib/types.ts ``DatasetFacts``) from ``data/processed/stats.json``."""
    n_threads = int(stats.get("n_threads") or 0)
    n_english = int(stats.get("n_openers_english") or 0)
    facts: dict[str, Any] = {
        "n_openers": n_threads,
        "n_openers_english": n_english,
        "n_brand_tweets": int(stats.get("n_brand_tweets") or 0),
        "n_rows_total": int(stats.get("n_rows_total") or 0),
        "n_brands": N_BRANDS_IN_DUMP,
        "date_from": stats.get("date_min") or "",
        "date_to": stats.get("date_max") or "",
        "share_english": round(n_english / n_threads, 4) if n_threads else 0.0,
        "share_with_link": float(stats.get("share_openers_with_link") or 0.0),
        "share_single_reply": round(1.0 - float(stats.get("share_multi_turn") or 0.0), 4),
        "n_resolved_links": int(stats.get("n_links_resolved") or 0),
    }
    bulk = _bulk_period(stats.get("openers_per_month") or {})
    if bulk:
        facts["bulk_from"], facts["bulk_to"], facts["bulk_share"] = bulk
    return facts


def export_eval_summary(target: Path) -> bool:
    """``eval_summary.json`` with ``meta.caveats`` (results/caveats.json) and ``meta.dataset`` (stats.json) merged in."""
    if not Paths.EVAL_SUMMARY.exists():
        log.warning("skipping %s: %s not found", target.name, Paths.EVAL_SUMMARY)
        return False
    summary = read_json(Paths.EVAL_SUMMARY)
    meta = summary.setdefault("meta", {})

    caveats_path = Paths.RESULTS / "caveats.json"
    if caveats_path.exists():
        caveats = read_json(caveats_path)
        if isinstance(caveats, list) and all(isinstance(c, str) for c in caveats):
            meta["caveats"] = [c.strip() for c in caveats if c.strip()]
            log.info("merged %d caveats from %s", len(meta["caveats"]), caveats_path)
        else:
            log.warning("%s is not a JSON array of strings; caveats not merged", caveats_path)
    else:
        log.warning("%s not found; the Overview callout will be empty", caveats_path)

    if Paths.STATS.exists():
        meta["dataset"] = dataset_facts(read_json(Paths.STATS))
        log.info("filled meta.dataset from %s", Paths.STATS)
    else:
        log.warning("%s not found; the UI falls back to CONTRACT §2 constants", Paths.STATS)

    write_json(target, summary)
    log.info("wrote %s", target)
    return True


def _optional_rows(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        log.warning("%s not found (%s); golden_merged.json will have no %s", path.name, path, label)
        return []
    return read_jsonl(path)


def export_golden_merged(target: Path) -> bool:
    """Golden examples merged with predictions and judge scores, exactly as ``GET /api/golden`` returns them."""
    if not Paths.GOLDEN.exists():
        log.warning("skipping %s: %s not found", target.name, Paths.GOLDEN)
        return False
    merged = merge_golden(
        read_jsonl(Paths.GOLDEN),
        _optional_rows(Paths.PREDICTIONS, "predictions"),
        _optional_rows(Paths.JUDGE_SCORES, "judge scores"),
    )
    write_json(target, merged)
    log.info("wrote %s (%d examples)", target, len(merged))
    return True


def export_decisions(target: Path) -> bool:
    if not Paths.DECISION_LOG.exists():
        log.warning("skipping %s: %s not found", target.name, Paths.DECISION_LOG)
        return False
    decisions = parse_decision_log(Paths.DECISION_LOG)
    write_json(target, decisions)
    log.info("wrote %s (%d decisions)", target, len(decisions))
    return True


def static_health() -> dict[str, Any]:
    """The ``health.json`` body: the API health payload pinned to static mode plus model and count blocks."""
    health = health_payload(STATE)
    health.update(
        {
            "static": True,
            "has_api_key": False,
            "cache_only": True,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "models": {
                "agent": model_name("agent"),
                "judge": model_name("judge"),
                "zero_shot": model_name("zero_shot"),
            },
            "counts": {
                "n_golden": count_jsonl(Paths.GOLDEN),
                "n_predictions": count_jsonl(Paths.PREDICTIONS),
                "n_judge_scores": count_jsonl(Paths.JUDGE_SCORES),
                "n_human_ratings": count_jsonl(Paths.HUMAN_RATINGS),
                "cache_entries": count_cache_entries(Paths.LLM_CACHE),
                "index_size": health["index_size"],
            },
        }
    )
    return health


def export_all(out_dir: Path) -> dict[str, bool]:
    """Write every static data file into ``out_dir``; returns ``{filename: written}``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {
        "eval_summary.json": export_eval_summary(out_dir / "eval_summary.json"),
        "failure_modes.json": _copy_json(Paths.FAILURE_MODES, out_dir / "failure_modes.json"),
        "golden_merged.json": export_golden_merged(out_dir / "golden_merged.json"),
        "decisions.json": export_decisions(out_dir / "decisions.json"),
    }
    write_json(out_dir / "health.json", static_health())
    written["health.json"] = True
    log.info("wrote %s", out_dir / "health.json")
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export results into ui/public/data for the static UI.")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: ui/public/data).")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out_dir = args.out or Paths.UI_PUBLIC_DATA
    written = export_all(out_dir)
    skipped = sorted(name for name, ok in written.items() if not ok)
    log.info("export complete: %d/%d files written to %s", len(written) - len(skipped), len(written), out_dir)
    if skipped:
        log.warning("skipped (source missing): %s", ", ".join(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
