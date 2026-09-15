"""Join actual blind human preferences to the two-order draft judge. Never fills missing ratings."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score

from cadence.config import Paths
from cadence.utils.io import read_json, read_jsonl, write_json


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", type=Path, default=Paths.RESULTS / "dev_experiment")
    p.add_argument(
        "--ratings",
        type=Path,
        required=True,
        help="Completed copy of blind_human_preferences.csv; do not read mapping before rating",
    )
    args = p.parse_args(argv)
    with args.ratings.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    mapping = {r["id"]: r for r in read_json(args.experiment / "human_preference_mapping.json")}
    scores = read_jsonl(args.experiment / "draft_judge_orders.jsonl")
    pairs = []
    seen = set()
    for r in rows:
        if not r["preferred"]:
            continue
        if (
            r["id"] not in mapping
            or r["preferred"] not in {"A", "B", "tie"}
            or not r["annotator"].strip()
            or not r["rationale"].strip()
        ):
            raise ValueError("Every completed rating needs a valid id, A/B/tie, annotator and rationale")
        key = (r["id"], r["annotator"])
        if key in seen:
            raise ValueError("Duplicate (id, annotator) rating")
        seen.add(key)
        human = "tie" if r["preferred"] == "tie" else mapping[r["id"]][r["preferred"]]
        averages = {
            s: np.mean([j["scores"]["overall"] for j in scores if j["id"] == r["id"] and j["system"] == s])
            for s in ("agent", "agent_no_evidence")
        }
        if not all(np.isfinite(v) for v in averages.values()):
            raise ValueError("Missing judge pair")
        judge = (
            "tie" if averages["agent"] == averages["agent_no_evidence"] else max(averages, key=averages.get)
        )
        pairs.append({"id": r["id"], "annotator": r["annotator"], "human": human, "judge": judge})
    if not pairs:
        raise ValueError("No actual human ratings: agreement remains unavailable")
    report = {
        "n": len(pairs),
        "kind": "human pairwise preference vs mean two-order judge score",
        "raters": {},
    }
    for rater in sorted({r["annotator"] for r in pairs}):
        rs = [r for r in pairs if r["annotator"] == rater]
        k = cohen_kappa_score(
            [r["human"] for r in rs], [r["judge"] for r in rs], labels=["agent", "agent_no_evidence", "tie"]
        )
        report["raters"][rater] = {
            "n": len(rs),
            "kappa": float(k) if np.isfinite(k) else None,
            "exact_agreement": float(np.mean([r["human"] == r["judge"] for r in rs])),
        }
    write_json(args.experiment / "human_preference_agreement.json", report)
    print(report)


if __name__ == "__main__":
    main()
