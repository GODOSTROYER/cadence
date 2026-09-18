"""Recompute three-arm results and acceptance from saved receipts and exact reviews."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime

import numpy as np
from reproduce_quality import verified_reviews

from cadence.config import Paths
from cadence.eval.paired import compare
from cadence.eval.provenance import sha256
from cadence.eval.review import RUBRIC_VERSION, reply_hash, validate_reviews
from cadence.llm.cache import LLMCache
from cadence.utils.io import read_json, read_jsonl, write_json

SYSTEMS = ('agent', 'quality', 'balanced')
HUMAN_BOUND_FILES = ('manifest.json', 'predictions.jsonl', 'blind_packet.jsonl', 'blind_mapping.json',
                     'blind_astra_ratings.jsonl', 'astra_reply_ratings.jsonl')


def human_verification(directory, ratings):
    """Validate a later, explicit human attestation without changing the initial AI ratings."""
    path = directory / 'HUMAN_VERIFICATION.json'
    if not path.exists():
        return None
    record = read_json(path)
    if any(not isinstance(record.get(key), str) or not record[key].strip()
           for key in ('reviewer', 'confirmation', 'confirmed_at')):
        raise ValueError('Human identity, attestation and timestamp must be nonempty strings')
    confirmed_at = datetime.fromisoformat(record['confirmed_at'].replace('Z', '+00:00'))
    if confirmed_at.tzinfo is None:
        raise ValueError('Human confirmation timestamp must include its timezone')
    if (record.get('status') != 'completed' or record.get('reviewer_type') != 'human'
            or not str(record.get('reviewer', '')).strip() or not record.get('confirmed_at')
            or not str(record.get('confirmation', '')).strip()
            or record.get('review_method') != 'human_verification_of_ai_ratings'
            or record.get('blinding') != 'existing_scores_visible' or record.get('scores_changed') is not False
            or type(record.get('n_reply_ratings')) is not int or type(record.get('n_messages')) is not int
            or record.get('n_reply_ratings') != len(ratings)
            or record.get('n_messages') != len({r['id'] for r in ratings})):
        raise ValueError('Incomplete or unsupported human verification')
    expected = {file: sha256(directory / file) for file in HUMAN_BOUND_FILES}
    if record.get('artifacts') != expected:
        raise ValueError('Human verification does not bind the exact new review artifacts')
    return record


def verify_review_metadata(ratings, coverage, run_id):
    identities = {(r['reviewer_id'], r['reviewer_type'], r['run_id']) for r in ratings}
    if identities != {(coverage.get('reviewer_id'), coverage.get('reviewer_type'), run_id)} or coverage.get('run_id') != run_id:
        raise ValueError('Coverage reviewer identity, provenance or run differs from exact ratings')


def validate_run_state(manifest, summary, status, n):
    phase = manifest['frozen']['phase']
    if phase not in ('development', 'confirmation') or summary.get('phase') != phase:
        raise ValueError('Run phase differs from frozen manifest')
    if (n <= 0 or manifest['frozen']['n'] != n or summary.get('n') != n
            or summary.get('status') != 'complete' or status.get('status') != 'complete'
            or status.get('completed') != n * len(SYSTEMS)
            or status.get('expected') != n * len(SYSTEMS)):
        raise ValueError('Run is not a complete matched comparison')


def verify_blind_packet(predictions, mapping, packet, run_id):
    """Bind the entire reviewed context, not only its reply text, to each source output."""
    source = {(r['id'], r['system']): r for r in predictions}
    identities = {(r['id'], r['alias']): r for r in mapping}
    reviewed = {(r['id'], r['alias']): r for r in packet}
    mapped_sources = {(r['id'], r['system']) for r in mapping}
    if (not predictions or len(source) != len(predictions)
            or len(identities) != len(mapping) or len(reviewed) != len(packet)
            or len(mapping) != len(source) or len(packet) != len(source)
            or len(mapped_sources) != len(mapping) or mapped_sources != set(source)
            or set(reviewed) != set(identities)):
        raise ValueError('Blind packet and mapping must cover every prediction exactly once')
    for identity, item in identities.items():
        if item['alias'] not in ('A', 'B', 'C') or item['system'] not in SYSTEMS:
            raise ValueError('Unknown blind alias or system')
        row = source[item['id'], item['system']]
        shared = {'id': row['id'], 'alias': item['alias'], 'run_id': run_id,
                  'reply_hash': reply_hash(row['reply_draft']), 'rubric_version': RUBRIC_VERSION}
        if item != {**shared, 'system': row['system']}:
            raise ValueError('Blind mapping does not match the exact source identity')
        expected = {**shared, 'text': row['input_text'], 'reply_draft': row['reply_draft'],
                    'evidence': row['evidence']}
        if reviewed[identity] != expected:
            raise ValueError('Blind review customer, reply, evidence or identity differs from its source')


def acceptance(directory, labels, rows, ratings, coverage, summary, rules):
    if summary['phase'] not in ('development', 'confirmation'):
        raise ValueError('Unknown acceptance phase')
    truth = {r['id']: r['gold']['should_escalate'] for r in labels}
    reviews = {(r['id'], r['system']): r for r in ratings}
    counts = {}
    for system in SYSTEMS:
        auto = [r for r in rows if r['system'] == system and r['decision'] == 'auto_handle']
        counts[system] = {**coverage['systems'][system],
            'missed_escalations': sum(truth[r['id']] for r in auto),
            'flagged_automatic': sum(any(reviews[r['id'], system]['flags'].values())
                 or reviews[r['id'], system]['scores']['safe'] < 4 for r in auto)}
    ref, quality, candidate = (counts[s] for s in SYSTEMS)
    n = len(labels)
    human = human_verification(directory, ratings)
    gates = {
        'no_more_misses_than_either': candidate['missed_escalations'] <= min(ref['missed_escalations'], quality['missed_escalations']),
        'strictly_better_useful_coverage_than_both': candidate['useful_automatic'] > max(ref['useful_automatic'], quality['useful_automatic']),
        'minimum_automatic_coverage': candidate['automatic'] / n >= rules['min_auto_coverage'],
        'bounded_coverage_loss_vs_reference': (ref['automatic'] - candidate['automatic']) / n <= rules['max_auto_coverage_loss_vs_reference'],
        'no_fewer_useful_resolutions_than_reference': candidate['useful_resolution'] >= ref['useful_resolution'],
        'no_reviewer_flagged_unsafe_automatic': candidate['flagged_automatic'] == 0,
        'latency_within_frozen_limit': summary['runtime']['balanced']['p95_ms'] <= rules['max_candidate_p95_ms'],
        'latency_observations_fully_fresh': all(summary['runtime'][s]['fresh_invocations'] == n for s in SYSTEMS),
        'new_reply_reviews_verified_by_human': human is not None or all(r['reviewer_type'] == 'human' for r in ratings),
    }
    promote = summary['phase'] == 'confirmation' and all(gates.values())
    decision = ('Development assessment only; fresh confirmation is required before promotion.'
                if summary['phase'] == 'development' else
                'All gates passed.' if promote else
                'Keep the deployed reference; not all promotion gates are met.')
    result = {'status': 'completed', 'phase': summary['phase'], 'n': n, 'counts': counts,
        'gates': gates, 'technical_gates_pass': all(v for k, v in gates.items() if k != 'new_reply_reviews_verified_by_human'),
        'promote': promote, 'reviewer_type': coverage['reviewer_type'], 'decision': decision,
        'input_hashes': {f: sha256(directory / f) for f in ('manifest.json', 'summary.json', 'predictions.jsonl',
            'blind_packet.jsonl', 'blind_mapping.json', 'blind_astra_ratings.jsonl',
            'astra_reply_ratings.jsonl', 'astra_coverage.json')}}
    if human is not None:
        result['human_verification'] = human
        result['input_hashes']['HUMAN_VERIFICATION.json'] = sha256(directory / 'HUMAN_VERIFICATION.json')
    return result


def verify(name, write=False):
    directory = Paths.ROOT / name
    manifest = read_json(directory / 'manifest.json')
    for f, digest in read_json(directory / 'VERIFICATION.json')['artifacts'].items():
        if sha256(directory / f) != digest:
            raise ValueError('Frozen output changed: ' + f)
    for f, digest in manifest['frozen']['inputs'].items():
        file = directory / 'source_snapshot' / f if f.endswith('.py') else Paths.ROOT / f
        if sha256(file) != digest:
            raise ValueError('Frozen input changed: ' + f)
    label_file = next(f for f in manifest['frozen']['inputs'] if f.endswith('/labels.jsonl'))
    labels = read_jsonl(Paths.ROOT / label_file)
    rows = read_jsonl(directory / 'predictions.jsonl')
    keys = {(r['id'], r['system']) for r in rows}
    if len(keys) != len(rows) or keys != {(r['id'], s) for r in labels for s in SYSTEMS}:
        raise ValueError('Incomplete or duplicate paired predictions')
    grouped = {s: [r for r in rows if r['system'] == s] for s in SYSTEMS}
    summary = read_json(directory / 'summary.json')
    validate_run_state(manifest, summary, read_json(directory / 'status.json'), len(labels))
    for system in ('quality', 'balanced'):
        if compare(labels, grouped[system], grouped['agent']) != summary['comparisons'][system]:
            raise ValueError('Paired comparison differs: ' + system)
    if compare(labels, grouped['balanced'], grouped['quality']) != summary['balanced_vs_quality']:
        raise ValueError('Quality comparison differs')
    for system, rs in grouped.items():
        runtime = {'n': len(rs), 'p50_ms': float(np.median([r['latency_ms'] for r in rs])),
            'p95_ms': float(np.percentile([r['latency_ms'] for r in rs], 95)),
            **{k: sum(r['trace'][k] for r in rs) for k in ('model_calls', 'prompt_tokens', 'output_tokens')},
            'cached': sum(r['cached'] for r in rs),
            'fresh_invocations': sum(r['measurement']['fully_fresh_invocation'] for r in rs)}
        for r in rs:
            flags = r['measurement']['per_call_cached']
            if len(flags) != r['trace']['model_calls'] or any(type(f) is not bool for f in flags):
                raise ValueError('Incomplete call cache observations')
            if r['measurement']['fully_fresh_invocation'] != (not any(flags)):
                raise ValueError('Fresh latency marker differs from call observations')
        if runtime != summary['runtime'][system]:
            raise ValueError('Runtime differs: ' + system)
    with sqlite3.connect(f"file:{(directory / 'calls.sqlite').as_posix()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        receipts = [dict(r) for r in conn.execute('select * from calls')]
    for r in receipts:
        if r['key'] != LLMCache.key(r['model'], r['system'], r['prompt'], r['schema_json'], r['temperature']):
            raise ValueError('Receipt key mismatch')
        json.loads(r['response_json'])
    if sum(r['trace']['model_calls'] for r in rows) != len(receipts):
        raise ValueError('Call counts differ from saved receipts')
    for k in ('prompt_tokens', 'output_tokens'):
        if sum(r['trace'][k] for r in rows) != sum(r[k] for r in receipts):
            raise ValueError('Token counts differ from saved receipts')
    mapping = read_json(directory / 'blind_mapping.json')
    verify_blind_packet(rows, mapping, read_jsonl(directory / 'blind_packet.jsonl'),
                        'routing_dev-' + sha256(directory / 'manifest.json')[:12])
    ratings, coverage = verified_reviews(directory, rows)
    verify_review_metadata(ratings, coverage, 'routing_dev-' + sha256(directory / 'manifest.json')[:12])
    mapped = validate_reviews(read_jsonl(directory / 'blind_astra_ratings.jsonl'), mapping)
    for r in mapped:
        r['blind_alias'], r['alias'] = r['alias'], r['system']
    def sort(r):
        return r['id'], r['system']
    if sorted(mapped, key=sort) != sorted(ratings, key=sort):
        raise ValueError('Blind scores changed during mapping')
    result = acceptance(directory, labels, rows, ratings, coverage, summary, manifest['frozen']['acceptance'])
    if write:
        write_json(directory / 'ACCEPTANCE.json', result)
    elif result != read_json(directory / 'ACCEPTANCE.json'):
        raise ValueError('Acceptance differs from evidence')
    print({'experiment': name, 'predictions': len(rows), 'receipts': len(receipts),
        'technical_gates_pass': result['technical_gates_pass'], 'new_model_calls': 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', action='append', help='Repeat to verify multiple runs; defaults to the latest confirmation')
    parser.add_argument('--write-acceptance', action='store_true')
    args = parser.parse_args()
    for name in args.experiment or ['results/balanced_confirmation']:
        verify(name, args.write_acceptance)


if __name__ == '__main__':
    main()
