"""Replay consumed benchmark receipts through repaired guards; never a fresh evaluation."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from reproduce_benchmark import summarize

from cadence.agent.pipeline import SupportAgent
from cadence.config import Paths, model_name
from cadence.eval.provenance import revision, sha256
from cadence.llm.gemini import GeminiClient
from cadence.retrieval.index import Retriever
from cadence.utils.io import read_jsonl, write_json, write_jsonl


def main():
    os.environ['CADENCE_CACHE_ONLY'] = '1'
    source = Paths.RESULTS / 'holdout_final'
    output = Paths.RESULTS / 'post_audit_regression'
    golden = read_jsonl(Paths.DATA / 'holdout/ai_reviewed_set.jsonl')
    excluded = {g['thread_id'] for g in golden}
    retriever = Retriever.build([t for t in read_jsonl(Paths.THREADS) if t['thread_id'] not in excluded])
    before = {r['id']: r for r in read_jsonl(source / 'predictions.jsonl') if r['system'] == 'agent'}
    with tempfile.TemporaryDirectory(prefix='cadence-regression-') as directory:
        cache_path = Path(directory) / 'calls.sqlite'
        with closing(sqlite3.connect((source / 'calls.sqlite').resolve().as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(cache_path)) as dst:
                src.backup(dst)
        client = GeminiClient(model_name('agent'), cache_path=cache_path)
        agent = SupportAgent(client, retriever, k=6, threshold=.9)
        try:
            rows = [agent.handle(g['text'], id=g['id'], exclude_thread_ids=excluded).model_dump() for g in golden]
            if not all(r['cached'] for r in rows):
                raise ValueError('Regression must use only frozen receipts')
        finally:
            client.close()
    write_jsonl(output / 'predictions.jsonl', rows)
    report = {
        'kind': 'Post-audit regression on consumed benchmark, NOT fresh generalization evidence',
        'model_calls': 0, 'cached_predictions': len(rows), 'revision': revision(Paths.ROOT),
        'source_manifest_sha256': sha256(source / 'manifest.json'),
        'labels_sha256': sha256(Paths.DATA / 'holdout/ai_reviewed_set.jsonl'),
        'guard_hashes': {name: sha256(Paths.ROOT / name) for name in (
            'src/cadence/agent/integrity.py', 'src/cadence/agent/pipeline.py')},
        'changed_ids': [r['id'] for r in rows if (r['decision'], r['reply_draft']) !=
                        (before[r['id']]['decision'], before[r['id']]['reply_draft'])],
        'newly_escalated_ids': [r['id'] for r in rows if r['decision'] == 'escalate' and
                               before[r['id']]['decision'] == 'auto_handle'],
        'metrics': summarize(golden, rows),
        'judge': None,
        'judge_note': 'Frozen judge scores do not score the changed replies.',
    }
    write_json(output / 'summary.json', report)
    print({'cached': len(rows), 'model_calls': 0, 'changed': report['changed_ids'],
           'newly_escalated': report['newly_escalated_ids']})


if __name__ == '__main__':
    main()
