"""Offline revised-benchmark report. Never calls a model or presents partial coverage as a headline."""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

import numpy as np

from cadence.config import Paths, intent_ids
from cadence.eval.metrics import intent_metrics, macro_f1
from cadence.eval.paired import compare
from cadence.eval.provenance import sha256
from cadence.llm.cache import LLMCache
from cadence.utils.io import read_json, read_jsonl, write_json


def interval(values):
    valid = [v for v in values if v is not None]
    return np.quantile(valid, [0.025, 0.975]).tolist() if valid else None


def summarize(golden, rows, n_boot=2000):
    by_id = {r['id']: r for r in rows}
    if len(by_id) != len(rows) or set(by_id) != {g['id'] for g in golden}:
        raise ValueError('Predictions must cover every label exactly once')
    rows = [by_id[g['id']] for g in golden]
    truth = np.array([g['gold']['intent'] for g in golden])
    pred = np.array([r['intent'] for r in rows])
    required = np.array([g['gold']['should_escalate'] for g in golden])
    escalated = np.array([r['decision'] == 'escalate' for r in rows])

    def stats(ix):
        g, p = required[ix], escalated[ix]
        return {
            'accuracy': float(np.mean(truth[ix] == pred[ix])),
            'macro_f1': macro_f1(truth[ix], pred[ix], labels=intent_ids()),
            'escalation_recall': float(np.mean(p[g])) if g.any() else None,
            'escalation_precision': float(np.mean(g[p])) if p.any() else None,
            'auto_handle_rate': float(np.mean(~p)),
            'unsafe_auto_rate': float(np.mean(g[~p])) if (~p).any() else None,
        }

    point = stats(np.arange(len(rows)))
    rng = np.random.default_rng(2026)
    boot = [stats(rng.integers(len(rows), size=len(rows))) for _ in range(n_boot)]
    live = [r['latency_ms'] for r in rows if not r.get('cached') and r.get('model', '').startswith('gemini')]
    return {
        'n': len(rows), 'seed': 2026, 'bootstrap_resamples': n_boot,
        'metrics': {k: {'estimate': v, 'ci95': interval([b[k] for b in boot])} for k, v in point.items()},
        'intent_detail': intent_metrics(truth.tolist(), pred.tolist(), intent_ids()),
        'missed_escalation_ids': [r['id'] for r, g, p in zip(rows, required, escalated, strict=True) if g and not p],
        'wrong_intent_ids': [r['id'] for r, g, p in zip(rows, truth, pred, strict=True) if g != p],
        'integrity_blocked': sum(bool(r.get('trace', {}).get('integrity_blocked')) for r in rows),
        'live_successful_prediction_latency': {'n': len(live), 'p50_ms': float(np.median(live)) if live else None,
                                             'p95_ms': float(np.quantile(live, .95)) if live else None},
        'cached_predictions': sum(bool(r.get('cached')) for r in rows),
    }


def judge_summary(scores, ids):
    if not scores:
        return {'status': 'not_run', 'human_agreement': None}
    indexed = {(r['id'], r['system'], r['order_id']): r for r in scores}
    systems = sorted({r['system'] for r in scores})
    if len(indexed) != len(scores) or len(systems) != 2 or 'agent' not in systems:
        raise ValueError('Duplicate judge records or incorrect system count')
    if any(r['id'] not in ids or r['order_id'] not in (0, 1) for r in scores):
        raise ValueError('Unexpected judge ID or order')
    if any((i, s, o) not in indexed for i in ids for s in systems for o in (0, 1)):
        return {'status': 'incomplete', 'records': len(scores), 'expected': len(ids)*4, 'human_agreement': None}
    left, right = 'agent', next(s for s in systems if s != 'agent')
    differences, consistency = [], []
    for i in ids:
        differences.append(np.mean([indexed[i, left, o]['scores']['overall'] - indexed[i, right, o]['scores']['overall'] for o in (0, 1)]))
        preferences = [np.sign(indexed[i, left, o]['rank'] - indexed[i, right, o]['rank']) for o in (0, 1)]
        consistency.append(preferences[0] == preferences[1])
    rng = np.random.default_rng(2026)
    boot = [float(np.mean(rng.choice(differences, size=len(ids)))) for _ in range(2000)]
    return {'status': 'complete', 'n_pairs': len(ids), 'human_agreement': None,
            'direction': f'{left} minus {right}', 'mean_overall_delta': float(np.mean(differences)),
            'ci95': interval(boot), 'preference_order_consistency': float(np.mean(consistency)),
            'system_means': {s: float(np.mean([r['scores']['overall'] for r in scores if r['system'] == s])) for s in systems},
            'both_orders_ship_rate': {s: float(np.mean([all(indexed[i, s, o]['verdict'] == 'ship' for o in (0, 1)) for i in ids])) for s in systems},
            'flagged_in_either_order_rate': {s: float(np.mean([any(any(indexed[i, s, o]['flags'].values()) for o in (0, 1)) for i in ids])) for s in systems},
            'position_means': {str(p): float(np.mean([r['scores']['overall'] for r in scores if r['position'] == p])) for p in (1, 2)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, default=Paths.RESULTS / 'holdout_final')
    parser.add_argument('--golden', type=Path, default=Paths.DATA / 'holdout/ai_reviewed_set.jsonl')
    parser.add_argument('--out', type=Path, default=Paths.RESULTS / 'reproduced/benchmark_summary.json')
    args = parser.parse_args()
    status_path = args.directory / 'run_status.json'
    if status_path.exists():
        for name, digest in read_json(status_path).get('artifacts', {}).items():
            if name != 'summary.json' and sha256(args.directory / name) != digest:
                raise ValueError(f'Frozen artifact changed: {name}')
    golden, rows = read_jsonl(args.golden), read_jsonl(args.directory / 'predictions.jsonl')
    manifest = read_json(args.directory / 'manifest.json')
    if sha256(args.golden) != manifest['labels']:
        raise ValueError('Label hash differs from frozen experiment')
    counts = Counter(r['system'] for r in rows)
    expected = {'agent', 'agent_no_evidence', 'trivial', 'simple_keyword'}
    complete = set(counts) == expected and all(n == len(golden) for n in counts.values())
    report = {'kind': 'AI-reviewed benchmark; no human ground truth', 'model_calls': 0,
              'execution_commit': manifest['commit'], 'status': 'complete' if complete else 'incomplete',
              'n_labels': len(golden), 'prediction_counts': dict(counts), 'human_agreement': None,
              'input_hashes': {p.name: sha256(p) for p in (args.golden, args.directory / 'predictions.jsonl', args.directory / 'manifest.json')}}
    if complete:
        grouped = {s: [r for r in rows if r['system'] == s] for s in sorted(expected)}
        report['systems'] = {s: summarize(golden, rs) for s, rs in grouped.items()}
        report['paired'] = {s: compare(golden, grouped['agent'], rs) for s, rs in grouped.items() if s != 'agent'}
        raw = {s: [{**r, 'decision': r['trace']['llm_decision']} for r in grouped[s]]
               for s in ('agent', 'agent_no_evidence')}
        report['raw_decision_ablation'] = compare(golden, raw['agent'], raw['agent_no_evidence'])
        agent_metrics = report['systems']['agent']['metrics']
        report['safety_gate'] = {
            'target_recall': .9, 'target_recall_ci95_lower': .88,
            'recall_constraint_met': agent_metrics['escalation_recall']['estimate'] >= .9,
            'recall_lower_bound_met': agent_metrics['escalation_recall']['ci95'][0] >= .88,
            'semantic_grounding_verified': False,
            'interpretation': 'Necessary recall criteria only; AI labels and surface guards cannot certify release safety.',
        }
    report['judge'] = judge_summary(read_jsonl(args.directory / 'judge_orders.jsonl'), [g['id'] for g in golden])
    with sqlite3.connect((args.directory / 'calls.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        calls = conn.execute('SELECT * FROM calls').fetchall()
        for row in calls:
            if LLMCache.key(row['model'], row['system'], row['prompt'], row['schema_json'], row['temperature']) != row['key']:
                raise ValueError('Call receipt key mismatch')
            json.loads(row['response_json'])
        report['successful_call_receipts'] = len(calls)
        report['usage'] = {m: {'calls': sum(r['model'] == m for r in calls),
                               'input_tokens': sum(r['prompt_tokens'] for r in calls if r['model'] == m),
                               'output_tokens': sum(r['output_tokens'] for r in calls if r['model'] == m)}
                           for m in sorted({r['model'] for r in calls})}
        for model, usage in report['usage'].items():
            matching = [r for r in calls if r['model'] == model]
            times = sorted(datetime.fromisoformat(r['created_at']) for r in matching)
            span = (times[-1] - times[0]).total_seconds()
            latencies = [r['latency_ms'] for r in matching]
            usage.update({'receipt_latency_p50_ms': float(np.median(latencies)),
                          'receipt_latency_p95_ms': float(np.quantile(latencies, .95)),
                          'first_to_last_receipt_seconds': span,
                          'completed_intervals_per_second': (len(times)-1)/span if span else None,
                          'throughput_scope': 'Local two-worker run, first-to-last successful receipt; excludes startup and is not sustained server capacity.'})
            rates = {'gemini-3.5-flash-lite': (.30, 2.50), 'gemini-3.1-flash-lite': (.25, 1.50)}
            if model in rates:
                inp, out = rates[model]
                usage['paid_tier_counterfactual_usd'] = (usage['input_tokens']*inp + usage['output_tokens']*out)/1_000_000
        report['cost_scope'] = 'Configured free tier, not billing verification. Paid-tier counterfactual uses published standard rates; failed-call token usage is unavailable.'
    write_json(args.out, report)
    print(json.dumps({'status': report['status'], 'counts': dict(counts), 'judge': report['judge']['status'], 'output': str(args.out), 'model_calls': 0}, indent=2))


if __name__ == '__main__':
    main()
