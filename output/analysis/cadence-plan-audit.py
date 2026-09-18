"""Reproduce the planning analysis from frozen Cadence evidence; no model calls."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("cadence-plan-evidence.json")
FILES = {
    "labels": "data/balanced_confirmation/labels.jsonl",
    "predictions": "results/balanced_confirmation/predictions.jsonl",
    "ratings": "results/balanced_confirmation/astra_reply_ratings.jsonl",
}


def read(name):
    return [json.loads(line) for line in (ROOT / FILES[name]).read_text(encoding="utf-8").splitlines()]


def useful(rating):
    return (
        rating["verdict"] == "ship"
        and all(rating["scores"][key] >= 4 for key in ("safe", "grounded", "resolves"))
        and not any(rating["flags"].values())
        and rating["response_kind"] in ("resolution", "clarification")
    )


def main():
    labels = {row["id"]: row for row in read("labels")}
    predictions = {(row["id"], row["system"]): row for row in read("predictions")}
    ratings = {(row["id"], row["system"]): row for row in read("ratings")}
    assert len(labels) == 80 and len(predictions) == len(ratings) == 240
    systems = ("agent", "quality", "balanced")
    assert set(predictions) == set(ratings) == {(key, system) for key in labels for system in systems}
    report = {
        "purpose": "Post-confirmation diagnostic analysis for a future implementation plan; no new performance claim",
        "n": len(labels),
        "label_and_rating_provenance": "AI-authored; latest confirmation has no human verification record",
        "routing_eligible": sum(not row["gold"]["should_escalate"] for row in labels.values()),
        "required_escalations": sum(row["gold"]["should_escalate"] for row in labels.values()),
        "source_byte_sha256": {key: sha256((ROOT / path).read_bytes()).hexdigest() for key, path in FILES.items()},
        "systems": {},
    }
    eligible_useful = {}
    for system in systems:
        auto = {key for key in labels if predictions[key, system]["decision"] == "auto_handle"}
        helpful = {key for key in auto if useful(ratings[key, system])}
        compliant = {key for key in helpful if not labels[key]["gold"]["should_escalate"]}
        eligible_useful[system] = compliant
        misses = {key for key in auto if labels[key]["gold"]["should_escalate"]}
        flagged = {key for key in auto if any(ratings[key, system]["flags"].values()) or ratings[key, system]["scores"]["safe"] < 4}
        unnecessary = {key for key in labels if key not in auto and not labels[key]["gold"]["should_escalate"]}
        reasons = Counter(predictions[key, system]["escalation"]["reason_code"] for key in unnecessary)
        report["systems"][system] = {
            "automatic": len(auto),
            "useful_automatic_legacy": len(helpful),
            "policy_compliant_useful_automatic": len(compliant),
            "policy_compliant_useful_coverage": len(compliant) / len(labels),
            "policy_compliant_resolution": sum(ratings[key, system]["response_kind"] == "resolution" for key in compliant),
            "policy_compliant_clarification": sum(ratings[key, system]["response_kind"] == "clarification" for key in compliant),
            "missed_escalations": len(misses),
            "missed_ids": sorted(misses),
            "flagged_automatic": len(flagged),
            "flagged_ids": sorted(flagged),
            "unnecessary_escalations": len(unnecessary),
            "unnecessary_escalation_reasons": dict(reasons),
            "useful_ids": sorted(helpful),
            "policy_compliant_useful_ids": sorted(compliant),
            "useful_but_misrouted_ids": sorted(helpful - compliant),
            "automatic_response_kinds": dict(Counter(ratings[key, system]["response_kind"] for key in auto)),
        }
    union = set.union(*eligible_useful.values())
    report["hindsight_selection"] = {
        "warning": "Selects using labels and reviews unavailable at inference; only a diagnostic ceiling over existing automatic outputs",
        "policy_compliant_useful_union": len(union),
        "coverage": len(union) / len(labels),
        "ids": sorted(union),
        "additional_cases_not_won_by_balanced": sorted(union - eligible_useful["balanced"]),
    }
    report["intent_slices"] = []
    for intent in sorted({row["gold"]["intent"] for row in labels.values()}):
        keys = {key for key, row in labels.items() if row["gold"]["intent"] == intent}
        report["intent_slices"].append({
            "intent": intent,
            "n": len(keys),
            "routing_eligible": sum(not labels[key]["gold"]["should_escalate"] for key in keys),
            "policy_compliant_useful": {system: len(keys & eligible_useful[system]) for system in systems},
        })
    report["zero_error_one_sided_95pct_upper_bound"] = {
        str(n): 1 - 0.05 ** (1 / n) for n in (7, 30, 38, 59, 149, 299)
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(OUT), "systems": report["systems"], "hindsight_selection": report["hindsight_selection"]}))


if __name__ == "__main__":
    main()
