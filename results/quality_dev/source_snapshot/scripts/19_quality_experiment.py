"""Paired current/candidate inference with immutable inputs, receipts and no implicit promotion."""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np
from rapidfuzz import fuzz, process

from cadence.agent.pipeline import SupportAgent
from cadence.agent.quality import QualityAgent
from cadence.config import Paths, model_name
from cadence.eval.paired import compare
from cadence.eval.provenance import revision, sha256
from cadence.llm.gemini import GeminiClient
from cadence.retrieval.index import Retriever
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--phase", choices=["development", "confirmation"], required=True)
    p.add_argument("--live-free-tier", action="store_true")
    p.add_argument("--freeze-only", action="store_true")
    args = p.parse_args()
    labels = read_jsonl(args.labels)
    if not labels or len({r['id'] for r in labels}) != len(labels) or any(not r.get('gold') for r in labels):
        raise ValueError("Complete unique labels required before prediction")
    if args.phase == "confirmation":
        lock = read_json(args.labels.parent / "SAMPLE.lock.json")
        if sha256(args.labels.parent / "examples.jsonl") != lock['examples_sha256']:
            raise ValueError("Confirmation sample changed")
        examples = read_jsonl(args.labels.parent / "examples.jsonl")
        if [{k: r[k] for k in ('id', 'thread_id', 'text', 'split')} for r in labels] != examples:
            raise ValueError("Labels differ from locked sample")
    watched = sorted([*Paths.ROOT.glob('src/cadence/**/*.py'), *Paths.CONFIG.glob('*.yaml'),
                      *Paths.CONFIG.glob('*.json'), Path(__file__), args.labels, Paths.THREADS])
    if args.phase == 'confirmation':
        watched += [args.labels.parent / 'SAMPLE.lock.json', args.labels.parent / 'LABEL_REVIEW.json']
    frozen = {"inputs": {str(f.resolve().relative_to(Paths.ROOT)).replace('\\', '/'): sha256(f) for f in watched},
              "threshold": .9, "model": model_name('agent'), "n": len(labels), "phase": args.phase,
              "systems": ["agent", "quality"], "label_sources": sorted({r['label_source'] for r in labels}),
              "acceptance": {"no_more_missed_escalations": True, "strictly_better_useful_coverage": True,
                             "no_reviewer_flagged_unsafe_automatic": True, "max_candidate_p95_ms": 15000,
                             "human_approval_needed_for_new_ai_reviewed_outputs": True}}
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / 'manifest.json'
    if manifest.exists() and read_json(manifest)['frozen'] != frozen:
        raise ValueError("Frozen source/data changed; use a new experiment")
    if not manifest.exists():
        write_json(manifest, {'frozen': frozen, 'revision': revision(Paths.ROOT)})
    if args.freeze_only:
        print('Frozen source, labels and acceptance rules; no model calls')
        return
    os.environ['CADENCE_CACHE_ONLY'] = '0' if args.live_free_tier else '1'
    threads = read_jsonl(Paths.THREADS)
    texts = [t['customer_text'].casefold() for t in threads]
    excluded = {r['thread_id'] for r in labels}
    # Exclude complete overlapping conversation components and fuzzy opener duplicates.
    tweets = {str(turn['tweet_id']) for t in threads if t['thread_id'] in excluded for turn in t.get('turns', [])}
    excluded.update(t['thread_id'] for t in threads if any(str(turn['tweet_id']) in tweets for turn in t.get('turns', [])))
    for row in labels:
        excluded.update(threads[i]['thread_id'] for _, _, i in process.extract(row['text'].casefold(), texts, scorer=fuzz.ratio, score_cutoff=85, limit=None))
    retriever = Retriever.build([t for t in threads if t['thread_id'] not in excluded])
    client = GeminiClient(model_name('agent'), cache_path=args.out / 'calls.sqlite', deadline_s=55)
    agents = {'agent': SupportAgent(client, retriever, threshold=.9),
              'quality': QualityAgent(client, retriever, threshold=.9, system_name='quality')}
    rows = read_jsonl(args.out / 'predictions.jsonl')
    done = {(r['id'], r['system']) for r in rows}
    expected = {(r['id'], s) for r in labels for s in agents}
    if len(done) != len(rows) or not done <= expected:
        raise ValueError('Unexpected or duplicate predictions')
    try:
        for i, label in enumerate(labels):
            order = list(agents) if i % 2 == 0 else list(reversed(agents))
            for system in order:
                if (label['id'], system) in done:
                    continue
                row = agents[system].handle(label['text'], id=label['id'], exclude_thread_ids=excluded).model_dump()
                write_jsonl(args.out / 'predictions.jsonl', [row], append=True)
                rows.append(row)
                write_json(args.out / 'status.json', {'status': 'partial', 'completed': len(rows), 'expected': len(expected)})
                print(f"saved {label['id']} {system} calls={row['trace']['model_calls']}", flush=True)
    finally:
        client.close()
    grouped = {s: [r for r in rows if r['system'] == s] for s in agents}
    summary = {'status': 'complete', 'phase': args.phase, 'n': len(labels), 'label_sources': frozen['label_sources'],
               'comparisons': {'quality': compare(labels, grouped['quality'], grouped['agent'])},
               'runtime': {s: {'n': len(rs), 'p50_ms': float(np.median([r['latency_ms'] for r in rs])),
                               'p95_ms': float(np.percentile([r['latency_ms'] for r in rs], 95)),
                               **{key: sum(r['trace'][key] for r in rs) for key in ('model_calls', 'prompt_tokens', 'output_tokens')},
                               'cached': sum(r['cached'] for r in rs)} for s, rs in grouped.items()},
               'excluded_retrieval_threads': len(excluded), 'promotion': 'Requires separate acceptance decision; no automatic promotion'}
    write_json(args.out / 'summary.json', summary)
    write_json(args.out / 'status.json', {'status': 'complete', 'completed': len(rows), 'expected': len(expected)})
    if not (args.out / 'retrieval_review.csv').exists():
        with (args.out / 'retrieval_review.csv').open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['id', 'system', 'thread_id', 'customer', 'evidence_customer', 'evidence_reply', 'relevant', 'supports_next_step', 'current_advice', 'reviewer_id', 'reviewer_type', 'rationale'])
            writer.writeheader()
            for row in rows:
                for e in row['evidence']:
                    writer.writerow({'id': row['id'], 'system': row['system'], 'thread_id': e['thread_id'], 'customer': row['input_text'], 'evidence_customer': e['customer_text'], 'evidence_reply': e['brand_reply']})
    write_json(args.out / 'VERIFICATION.json', {'status': 'complete', 'execution': revision(Paths.ROOT),
               'artifacts': {f: sha256(args.out / f) for f in ('manifest.json', 'predictions.jsonl', 'summary.json', 'status.json', 'calls.sqlite')}})
    print('Completed paired experiment with immutable artifact hashes')


if __name__ == '__main__':
    main()
