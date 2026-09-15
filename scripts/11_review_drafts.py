"""Recover pre-guard drafts from experiment receipts, judge both orders, prepare blind human worksheet.

This isolates draft quality from the citation-required release guard. Default: no network.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import numpy as np

from cadence.agent.models import EvidenceItem, LLMDecision
from cadence.agent.prompts import build_user_prompt
from cadence.agent.rules import apply_rules
from cadence.config import Paths, model_name
from cadence.eval.blind_judge import judge_pair, normalize_candidate
from cadence.llm.cache import schema_json
from cadence.llm.gemini import GeminiClient
from cadence.utils.io import read_jsonl, write_json, write_jsonl


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--experiment", type=Path, default=Paths.RESULTS / "dev_experiment")
    p.add_argument("--live-free-tier", action="store_true")
    p.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)
    os.environ["CADENCE_CACHE_ONLY"] = "0" if args.live_free_tier else "1"
    predictions = read_jsonl(args.experiment / "predictions.jsonl")
    golden = [g for g in read_jsonl(Paths.GOLDEN) if g["split"] == "dev"][: args.limit]
    client = GeminiClient(model_name("judge"), cache_path=args.experiment / "calls.sqlite", deadline_s=55)
    with client.cache._lock:
        receipts = client.cache._conn.execute(
            "SELECT * FROM calls WHERE model=?", (model_name("agent"),)
        ).fetchall()
    lookup = {r["prompt"]: dict(r) for r in receipts}
    raw = []
    for row in predictions:
        prompt = build_user_prompt(
            row["input_text"],
            [EvidenceItem.model_validate(e) for e in row["evidence"]],
            apply_rules(row["input_text"]),
        )
        receipt = lookup[prompt]
        if receipt["schema_json"] != schema_json(LLMDecision):
            raise ValueError("Receipt schema changed")
        output = json.loads(receipt["response_json"])
        raw.append(
            {
                **row,
                "reply_draft": output["reply_draft"],
                "citations": output["citations"],
                "decision": output["decision"],
                "release_decision": row["decision"],
                "release_reply": row["reply_draft"],
                "receipt_key": receipt["key"],
            }
        )
    write_jsonl(args.experiment / "drafts_before_guard.jsonl", raw)
    by_key = {(r["id"], r["system"]): r for r in raw}
    scores_path = args.experiment / "draft_judge_orders.jsonl"
    scores = read_jsonl(scores_path)
    for g in golden:
        if sum(r["id"] == g["id"] for r in scores) == 4:
            continue
        new = judge_pair(g, by_key[(g["id"], "agent")], by_key[(g["id"], "agent_no_evidence")], client)
        write_jsonl(scores_path, new, append=True)
        scores.extend(new)
        print(f"draft judge saved {g['id']}", flush=True)
    deltas = []
    for g in golden:
        deltas.append(
            [
                next(
                    r["scores"]["overall"]
                    for r in scores
                    if r["id"] == g["id"] and r["system"] == "agent" and r["order_id"] == o
                )
                - next(
                    r["scores"]["overall"]
                    for r in scores
                    if r["id"] == g["id"] and r["system"] == "agent_no_evidence" and r["order_id"] == o
                )
                for o in (0, 1)
            ]
        )
    means = np.mean(deltas, axis=1)
    rng = np.random.default_rng(2026)
    write_json(
        args.experiment / "draft_judge_comparison.json",
        {
            "n": len(golden),
            "kind": "pre-guard drafts; normalized equally; two orders",
            "human_agreement": None,
            "mean_overall_delta": float(means.mean()),
            "ci95": np.percentile(
                [np.mean(rng.choice(means, len(means))) for _ in range(2000)], [2.5, 97.5]
            ).tolist(),
            "preference_order_consistency": float(np.mean([np.sign(a) == np.sign(b) for a, b in deltas])),
            "position_means": {
                str(pos): float(np.mean([r["scores"]["overall"] for r in scores if r["position"] == pos]))
                for pos in (1, 2)
            },
        },
    )
    worksheet = args.experiment / "blind_human_preferences.csv"
    if not worksheet.exists():
        import random

        with worksheet.open("w", newline="", encoding="utf-8") as f:
            fields = ["id", "text", "reply_A", "reply_B", "preferred", "annotator", "rationale"]
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            mapping = []
            for g in golden:
                order = ["agent", "agent_no_evidence"]
                random.Random("human:" + g["id"]).shuffle(order)
                writer.writerow(
                    {
                        "id": g["id"],
                        "text": g["text"],
                        "reply_A": normalize_candidate(by_key[(g["id"], order[0])]["reply_draft"]),
                        "reply_B": normalize_candidate(by_key[(g["id"], order[1])]["reply_draft"]),
                    }
                )
                mapping.append({"id": g["id"], "A": order[0], "B": order[1]})
            write_json(args.experiment / "human_preference_mapping.json", mapping)


if __name__ == "__main__":
    main()
