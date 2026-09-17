"""Content-bound supplemental review; AI and human ratings are never conflated."""
from __future__ import annotations

import hashlib
from collections import Counter

from cadence.config import JUDGE_DIMENSIONS, JUDGE_FLAGS
from cadence.eval.agreement import judge_agreement

RUBRIC_VERSION = "support-review-v1"


def reply_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_reviews(rows, mapping):
    by_key = {(r["id"], r["alias"]): r for r in mapping}
    if len(by_key) != len(mapping):
        raise ValueError("Duplicate mapping")
    result, seen = [], set()
    for row in rows:
        target = by_key.get((row["id"], row["alias"]))
        if not target or any(row.get(f) != target[f] for f in ("reply_hash", "run_id", "rubric_version")):
            raise ValueError("Unknown reply or mismatched review identity")
        if row.get("reviewer_type") not in ("human", "ai") or not row.get("reviewer_id"):
            raise ValueError("Explicit reviewer identity and type required")
        if not row.get("rated_at") or (row.get("verdict") != "ship" and not row.get("rationale", "").strip()):
            raise ValueError("Timestamp required; edit/reject require a rationale")
        if any(type(row.get("scores", {}).get(d)) is not int or not 1 <= row["scores"][d] <= 5 for d in JUDGE_DIMENSIONS):
            raise ValueError("All rubric scores must be integers 1–5")
        if any(type(row.get("flags", {}).get(f)) is not bool for f in JUDGE_FLAGS):
            raise ValueError("All rubric flags are required booleans")
        if row.get("verdict") not in ("ship", "edit", "reject") or row.get("response_kind") not in ("resolution", "clarification", "handoff", "other"):
            raise ValueError("Invalid verdict or response kind")
        k = (row["id"], row["alias"], row["reviewer_id"], row["rated_at"])
        if k in seen:
            raise ValueError("Duplicate reviewer revision")
        seen.add(k)
        result.append({**row, "system": target["system"]})
    return result


def review_report(rows, mapping, judge_rows):
    reviews = validate_reviews(rows, mapping)
    bound = {(r["id"], r["system"]): r for r in mapping}
    judged = [{**r, **{f: bound[r["id"], r["system"]][f] for f in ("run_id", "reply_hash", "rubric_version")}}
              for r in judge_rows if (r["id"], r["system"]) in bound]
    # Rubric identity describes the comparison rubric. Frozen judge prompts remain separately hashed by the study manifest.
    output = {"rubric_version": RUBRIC_VERSION, "n_expected_replies": len(mapping), "reviewers": {}}
    for rid in sorted({r["reviewer_id"] for r in reviews}):
        ratings = [r for r in reviews if r["reviewer_id"] == rid]
        types = {r["reviewer_type"] for r in ratings}
        if len(types) != 1:
            raise ValueError("Reviewer type changed within study")
        latest = {}
        for r in sorted(ratings, key=lambda r: r["rated_at"]):
            latest[r["id"], r["system"]] = r
        ratings = list(latest.values())
        output["reviewers"][rid] = {
            "reviewer_type": next(iter(types)), "status": "complete" if len(ratings) == len(mapping) else "partial",
            "n": len(ratings), "verdicts": dict(Counter(r["verdict"] for r in ratings)),
            "agreement_kind": "human_vs_judge" if types == {"human"} else "ai_vs_judge",
            "agreement": judge_agreement(ratings, judged, strict=True),
            "systems": {s: {"n": len(rs), "mean_overall": sum(r["scores"]["overall"] for r in rs) / len(rs),
                             "ship": sum(r["verdict"] == "ship" for r in rs)}
                        for s in sorted({r["system"] for r in ratings})
                        if (rs := [r for r in ratings if r["system"] == s])},
        }
    humans = [r for r in reviews if r["reviewer_type"] == "human"]
    output["human_agreement"] = judge_agreement(humans, judged, strict=True) if humans else None
    return output
