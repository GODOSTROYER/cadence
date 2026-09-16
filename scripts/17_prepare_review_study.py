"""Reproduce the seeded, matched 50-message blind review packet from frozen predictions."""
import argparse
import random
from pathlib import Path

from cadence.eval.review import RUBRIC_VERSION, reply_hash
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def prepare(directory=Path("results/holdout_final")):
    predictions = {(r["id"], r["system"]): r for r in read_jsonl(directory / "predictions.jsonl")}
    ids = sorted({i for i, s in predictions if s == "agent"})
    selected = sorted(random.Random(20260917).sample(ids, 50))
    run = "holdout_final-" + read_json(directory / "manifest.json")["commit"][:7]
    packet, mapping = [], []
    for identity in selected:
        systems = ["agent", "simple_keyword"]
        random.Random("review:" + identity).shuffle(systems)
        for alias, system in zip("AB", systems, strict=True):
            row = predictions[identity, system]
            digest = reply_hash(row["reply_draft"])
            packet.append({"id": identity, "alias": alias, "text": row["input_text"],
                           "reply_draft": row["reply_draft"], "reply_hash": digest, "evidence": row["evidence"]})
            mapping.append({"id": identity, "alias": alias, "system": system, "reply_hash": digest,
                            "run_id": run, "rubric_version": RUBRIC_VERSION})
    return packet, mapping


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=Path("results/review_study"))
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    packet, mapping = prepare()
    if args.check:
        if packet != read_jsonl(args.out / "blind_packet.jsonl") or mapping != read_json(args.out / "mapping.json"):
            raise ValueError("Review packet or mapping differs from seeded frozen replies")
    else:
        args.out.mkdir(parents=True, exist_ok=True)
        write_jsonl(args.out / "blind_packet.jsonl", packet)
        write_json(args.out / "mapping.json", mapping)
    print("Verified 50 matched messages, 100 exact frozen replies" if args.check else "Prepared 100 blind replies")


if __name__ == "__main__":
    main()
