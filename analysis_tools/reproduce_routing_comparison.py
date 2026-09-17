"""Verify saved development predictions, receipt integrity and paired comparisons offline."""
import json
import sqlite3

from cadence.config import Paths
from cadence.eval.paired import compare
from cadence.eval.provenance import sha256
from cadence.llm.cache import LLMCache
from cadence.utils.io import read_json, read_jsonl


def main():
    directory = Paths.RESULTS / "routing_dev"
    verification = read_json(directory / "VERIFICATION.json")
    for name, digest in verification["artifacts"].items():
        if sha256(directory / name) != digest:
            raise ValueError(f"Development artifact changed: {name}")
    rows = read_jsonl(directory / "predictions.jsonl")
    truth = read_jsonl(Paths.DATA / "routing_dev/labels.jsonl")
    manifest = read_json(directory / "manifest.json")
    if sha256(Paths.DATA / "routing_dev/labels.jsonl") != manifest["frozen"]["inputs"]["data/routing_dev/labels.jsonl"]:
        raise ValueError("Development labels changed")
    grouped = {s: [r for r in rows if r["system"] == s] for s in manifest["frozen"]["systems"]}
    summary = read_json(directory / "summary.json")
    for system in ("selective", "trained_tfidf_lr"):
        if compare(truth, grouped[system], grouped["agent"]) != summary["comparisons"][system]:
            raise ValueError(f"Paired comparison differs: {system}")
    with sqlite3.connect(f"file:{(directory / 'calls.sqlite').as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        receipts = [dict(r) for r in conn.execute("SELECT * FROM calls")]
    for r in receipts:
        if r["key"] != LLMCache.key(r["model"], r["system"], r["prompt"], r["schema_json"], r["temperature"]):
            raise ValueError("Receipt key mismatch")
        json.loads(r["response_json"])
    live = [r for r in rows if r["system"] != "trained_tfidf_lr"]
    if len(receipts) != sum(r["trace"]["model_calls"] for r in live):
        raise ValueError("Receipt count differs from model-call traces")
    for key in ("prompt_tokens", "output_tokens"):
        if sum(r[key] for r in receipts) != sum(r["trace"][key] for r in live):
            raise ValueError("Receipt and prediction token totals differ")
    print({"status": "verified", "messages": len(truth), "predictions": len(rows), "receipts": len(receipts), "new_model_calls": 0})


if __name__ == "__main__":
    main()
