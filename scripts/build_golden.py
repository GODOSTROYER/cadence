"""Merge two annotation passes + adjudication into the final golden set (CONTRACT.md §7).

Inputs (data/golden/work/):
  chunk_{i}.jsonl               candidates to label (from make_label_chunks.py)
  annotations_a_chunk_{i}.jsonl pass A labels   {id, intent, secondary_intent, should_escalate,
  annotations_b_chunk_{i}.jsonl pass B labels    escalation_reason_code, sentiment, media_only, notes, unusable?}
  adjudication_chunk_{i}.jsonl  {id, final: {...same label fields...}, disagreements: [field,...], rationale}

Outputs (data/golden/):
  golden_set.jsonl, annotations_a.jsonl, annotations_b.jsonl, adjudication.jsonl, golden_stats.json

Split: stratified by (gold intent, should_escalate) into dev (--dev, default 50) and test (rest), SEED-seeded.
Rows flagged `unusable` by the adjudicator (or by both annotators) are dropped and listed in golden_stats.json.

Usage: python scripts/build_golden.py [--dev 50]
"""

from __future__ import annotations

import argparse
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from cadence import SEED
from cadence.config import Paths, intent_ids, reason_codes
from cadence.utils.io import read_jsonl, write_json, write_jsonl
from cadence.utils.log import get_logger

log = get_logger(__name__)
WORK = Paths.GOLDEN_DIR / "work"
LABEL_FIELDS = ("intent", "secondary_intent", "should_escalate", "escalation_reason_code", "sentiment", "media_only", "notes")
SENTIMENTS = {"positive", "neutral", "frustrated", "angry"}


def _chunk_index(path: Path) -> int:
    m = re.search(r"chunk_(\d+)\.jsonl$", path.name)
    return int(m.group(1)) if m else 0


def _normalise(label: dict, valid_intents: set[str], valid_reasons: set[str]) -> dict:
    """Coerce one annotation into the canonical label shape; invalid values fall back to safe defaults."""
    intent = label.get("intent")
    if intent not in valid_intents:
        log.warning("invalid intent %r for %s -> other", intent, label.get("id"))
        intent = "other"
    secondary = label.get("secondary_intent")
    if secondary not in valid_intents:
        secondary = None
    esc = bool(label.get("should_escalate", False))
    reason = label.get("escalation_reason_code")
    if not esc:
        reason = None
    elif reason not in valid_reasons:
        log.warning("invalid reason %r for %s -> needs_account_lookup", reason, label.get("id"))
        reason = "needs_account_lookup"
    sentiment = label.get("sentiment") if label.get("sentiment") in SENTIMENTS else "neutral"
    return {
        "intent": intent,
        "secondary_intent": secondary,
        "should_escalate": esc,
        "escalation_reason_code": reason,
        "sentiment": sentiment,
        "media_only": bool(label.get("media_only", False)),
        "notes": (label.get("notes") or "").strip(),
    }


def _stratified_split(rows: list[dict], n_dev: int, seed: int) -> None:
    """Assign row['split'] in place: ~n_dev dev examples stratified by (intent, should_escalate)."""
    rng = random.Random(seed)
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["gold"]["intent"], r["gold"]["should_escalate"])].append(r)
    total = len(rows)
    for r in rows:
        r["split"] = "test"
    assigned = 0
    # proportional allocation with at least one dev example for any group of size >= 4
    alloc = {}
    for key, members in groups.items():
        rng.shuffle(members)
        alloc[key] = round(n_dev * len(members) / total)
        if len(members) >= 4:
            alloc[key] = max(1, alloc[key])
        alloc[key] = min(alloc[key], max(0, len(members) - 2))  # keep >= 2 in test per group
    for key, members in groups.items():
        for r in members[: alloc[key]]:
            r["split"] = "dev"
            assigned += 1
    # fix rounding drift
    keys = sorted(groups, key=lambda k: -len(groups[k]))
    i = 0
    while assigned < n_dev and keys:
        members = groups[keys[i % len(keys)]]
        cand = [r for r in members if r["split"] == "test"]
        if len(cand) > 2:
            cand[0]["split"] = "dev"
            assigned += 1
        i += 1
        if i > 10 * len(keys):
            break


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev", type=int, default=50)
    args = ap.parse_args(argv)

    valid_intents, valid_reasons = set(intent_ids()), set(reason_codes())
    chunks = sorted(WORK.glob("chunk_*.jsonl"), key=_chunk_index)
    if not chunks:
        raise SystemExit(f"no chunks in {WORK}; run scripts/make_label_chunks.py first")
    selected = {r["id"]: r for r in read_jsonl(WORK / "selected.jsonl")} if (WORK / "selected.jsonl").exists() else {}

    golden, all_a, all_b, all_adj, dropped = [], [], [], [], []
    for chunk_path in chunks:
        i = _chunk_index(chunk_path)
        cands = {r["id"]: r for r in read_jsonl(chunk_path)}
        a = {r["id"]: r for r in read_jsonl(WORK / f"annotations_a_chunk_{i}.jsonl")}
        b = {r["id"]: r for r in read_jsonl(WORK / f"annotations_b_chunk_{i}.jsonl")}
        adj = {r["id"]: r for r in read_jsonl(WORK / f"adjudication_chunk_{i}.jsonl")}
        missing = [cid for cid in cands if cid not in a or cid not in b]
        if missing:
            log.warning("chunk %d: %d candidates lack a label in one pass (skipped): %s", i, len(missing), missing[:5])
        for cid, cand in cands.items():
            if cid in missing:
                dropped.append({"id": cid, "reason": "missing annotation"})
                continue
            la, lb = _normalise(a[cid], valid_intents, valid_reasons), _normalise(b[cid], valid_intents, valid_reasons)
            all_a.append({"id": cid, **la})
            all_b.append({"id": cid, **lb})
            agreement = {"intent": la["intent"] == lb["intent"], "should_escalate": la["should_escalate"] == lb["should_escalate"]}
            adj_row = adj.get(cid)
            if adj_row and adj_row.get("unusable") or (a[cid].get("unusable") and b[cid].get("unusable")):
                dropped.append({"id": cid, "reason": (adj_row or {}).get("rationale") or "both annotators marked unusable"})
                continue
            if adj_row and adj_row.get("final"):
                gold = _normalise(adj_row["final"], valid_intents, valid_reasons)
                adjudicated = True
                all_adj.append({"id": cid, "chunk": i, "a": la, "b": lb, "final": gold,
                                "disagreements": adj_row.get("disagreements", []), "rationale": adj_row.get("rationale", "")})
            elif agreement["intent"] and agreement["should_escalate"]:
                gold = la if la["escalation_reason_code"] == lb["escalation_reason_code"] else {**la, "notes": f"{la['notes']} | b: {lb['notes']}".strip(" |")}
                adjudicated = False
            else:
                log.warning("%s: disagreement without adjudication; taking pass A", cid)
                gold = la
                adjudicated = False
            src = selected.get(cid, {})
            golden.append({
                "id": None,  # assigned below
                "candidate_id": cid,
                "thread_id": cand["thread_id"],
                "split": "test",
                "text": cand["text"],
                "text_raw": src.get("text_raw", cand["text"]),
                "created_at": cand.get("created_at"),
                "historical_brand_reply": cand.get("historical_brand_reply", ""),
                "historical_thread": cand.get("historical_thread", []),
                "gold": gold,
                "annotations": {"a": la, "b": lb},
                "agreement": agreement,
                "adjudicated": adjudicated,
                "sampling_bucket": src.get("sampling_bucket", "unknown"),
            })

    golden.sort(key=lambda r: r["candidate_id"])
    for n, r in enumerate(golden, 1):
        r["id"] = f"g_{n:03d}"
    _stratified_split(golden, args.dev, SEED)

    write_jsonl(Paths.GOLDEN, golden)
    write_jsonl(Paths.ANNOTATIONS_A, all_a)
    write_jsonl(Paths.ANNOTATIONS_B, all_b)
    write_jsonl(Paths.ADJUDICATION, all_adj)

    n = len(golden)
    stats = {
        "n_golden": n,
        "n_dev": sum(r["split"] == "dev" for r in golden),
        "n_test": sum(r["split"] == "test" for r in golden),
        "n_dropped": len(dropped),
        "dropped": dropped,
        "n_adjudicated": sum(r["adjudicated"] for r in golden),
        "intent_agreement_raw": sum(r["agreement"]["intent"] for r in golden) / n if n else None,
        "escalation_agreement_raw": sum(r["agreement"]["should_escalate"] for r in golden) / n if n else None,
        "intent_distribution": dict(Counter(r["gold"]["intent"] for r in golden).most_common()),
        "escalate_share": sum(r["gold"]["should_escalate"] for r in golden) / n if n else None,
        "reason_code_distribution": dict(Counter(r["gold"]["escalation_reason_code"] for r in golden if r["gold"]["should_escalate"]).most_common()),
        "sentiment_distribution": dict(Counter(r["gold"]["sentiment"] for r in golden).most_common()),
        "media_only": sum(r["gold"]["media_only"] for r in golden),
    }
    write_json(Paths.GOLDEN_DIR / "golden_stats.json", stats)
    log.info("golden set: %d rows (%d dev / %d test), %d adjudicated, %d dropped", n, stats["n_dev"], stats["n_test"], stats["n_adjudicated"], len(dropped))
    log.info("raw agreement: intent %.3f, escalation %.3f", stats["intent_agreement_raw"] or 0, stats["escalation_agreement_raw"] or 0)
    log.info("intent distribution: %s", stats["intent_distribution"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
