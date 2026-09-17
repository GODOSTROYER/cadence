"""Generate/check the public benchmark and report table from the same frozen artifact."""
from __future__ import annotations

import argparse
import json

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json, read_jsonl

NAMES = {"trivial": "Majority / always escalate", "simple_keyword": "Keyword / rules / nearest reply",
         "agent_no_evidence": "Same-prompt agent, k0", "agent": "Retrieval agent, k6"}


def publication(root=Paths.ROOT):
    directory = root / "results/holdout_final"
    summary = read_json(directory / "summary.json")
    manifest = read_json(directory / "manifest.json")
    if summary["execution_commit"] != manifest["commit"] or summary["input_hashes"]["ai_reviewed_set.jsonl"] != manifest["labels"]:
        raise ValueError("Benchmark identity mismatch")
    for name, digest in read_json(directory / "run_status.json")["artifacts"].items():
        if sha256(directory / name) != digest:
            raise ValueError(f"Frozen artifact changed: {name}")
    predictions = read_jsonl(directory / "predictions.jsonl")
    models = sorted({r["model"] for r in predictions if r["system"] == "agent"})
    systems = [{"id": key, "name": name, "n": summary["systems"][key]["n"],
                "metrics": summary["systems"][key]["metrics"],
                "misses": len(summary["systems"][key]["missed_escalation_ids"])} for key, name in NAMES.items()]
    replay = read_json(root / "results/post_audit_regression/summary.json")
    review = read_json(root / "data/holdout/HUMAN_REVIEW.json")
    verified = read_json(root / "results/review_study/arnav_verified_summary.json")
    for name, digest in verified["input_hashes"].items():
        if sha256(root / name.replace("\\", "/")) != digest:
            raise ValueError(f"Human review source changed: {name}")
    human = verified["reviewers"]["Arnav Bule"]
    agreement = verified["human_agreement"]
    experiment = read_json(root / "results/routing_dev/summary.json")
    comparison = experiment["comparisons"]["selective"]
    return {"run_id": "holdout_final-" + manifest["commit"][:7], "execution_commit": manifest["commit"],
            "dataset_hash": manifest["labels"], "summary_hash": sha256(directory / "summary.json"),
            "prompt_version": manifest["files"]["src/cadence/agent/prompts.py"],
            "policy_version": manifest["files"]["config/escalation.yaml"], "models": models,
            "evaluation_mode": "frozen recorded benchmark", "n": summary["n_labels"],
            "review": {k: review[k] for k in ("reviewer", "status", "n_examples", "review_outcome")},
            "systems": systems, "judge": summary["judge"],
            "supplemental_review": {"status": human["status"], "reviewer": "Arnav Bule", "initial_reviewer": "GPT-6 Astra", "initial_reasoning_effort": "xhigh",
                                    "n_messages": agreement["n_examples"], "n_ratings": human["n"], "scores_changed": False,
                                    "method": "AI-assisted ratings verified unchanged by the human reviewer; not an independent blind human pass",
                                    "weighted_kappa": agreement["weighted_kappa_overall"], "exact_agreement": agreement["exact_agreement"], "within_one": agreement["within_one"],
                                    "verdicts": human["verdicts"], "source": "results/review_study/arnav_verified_summary.json"},
            "routing_experiment": {"status": experiment["status"], "n": experiment["n"], "label_sources": experiment["label_sources"],
                                   "current": comparison["right"], "selective": comparison["left"], "promotion": experiment["promotion"],
                                   "source": "results/routing_dev/summary.json"},
            "replay": {"mode": "retrospective regression; not fresh inference", "changed_ids": replay["changed_ids"],
                       "metrics": {"metrics": replay["metrics"]["metrics"]}, "judge_note": replay["judge_note"]},
            "source": "results/holdout_final/summary.json"}


def table(data):
    lines = ["| System | Intent accuracy | Macro-F1 | Escalation recall | Auto-handles | Misses among auto |",
             "|---|---:|---:|---:|---:|---:|"]
    for s in data["systems"]:
        m = s["metrics"]
        auto = round(m["auto_handle_rate"]["estimate"] * s["n"])
        lines.append(f"| {s['name']} | {m['accuracy']['estimate']:.3f} | {m['macro_f1']['estimate']:.3f} | {m['escalation_recall']['estimate']:.3f} | {auto}/{s['n']} | {str(s['misses']) + '/' + str(auto) if auto else 'N/A'} |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = publication()
    content = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    paths = [Paths.ROOT / "ui/public/data/benchmark.json", Paths.RESULTS / "published/benchmark.json"]
    for path in paths:
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise ValueError(f"Stale benchmark export: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    report_path = Paths.ROOT / "REPORT.md"
    report = report_path.read_text(encoding="utf-8")
    begin, end = "<!-- benchmark-table:start -->", "<!-- benchmark-table:end -->"
    if begin not in report:
        start = report.index("| System | Intent accuracy")
        stop = report.index("\n\n", start)
        report = report[:start] + begin + "\n" + report[start:stop] + "\n" + end + report[stop:]
    expected = report[:report.index(begin)+len(begin)] + "\n" + table(data) + "\n" + report[report.index(end):]
    if args.check:
        if expected != report_path.read_text(encoding="utf-8"):
            raise ValueError("Report table is not generated from the published benchmark")
    else:
        report_path.write_text(expected, encoding="utf-8")
    print(f"{'Verified' if args.check else 'Published'} {data['run_id']}: report and public metrics match")


if __name__ == "__main__":
    main()
