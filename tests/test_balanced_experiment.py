import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


def module(name, folder='scripts'):
    path = Path(__file__).resolve().parents[1] / folder / name
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize('problem', ['partial_status', 'missing_arm', 'duplicate', 'unknown_system'])
def test_blind_packet_refuses_biased_or_incomplete_comparisons(tmp_path, monkeypatch, problem):
    rows = [dict(id='x', system=s, input_text='customer', reply_draft='reply', evidence=[])
            for s in ('agent', 'quality', 'balanced')]
    if problem == 'missing_arm':
        rows.pop()
    if problem == 'duplicate':
        rows[-1] = rows[0].copy()
    if problem == 'unknown_system':
        rows[-1]['system'] = 'unexpected'
    (tmp_path / 'predictions.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    (tmp_path / 'manifest.json').write_text(json.dumps({'frozen': {'n': 1}}))
    (tmp_path / 'status.json').write_text(json.dumps({'status': 'partial' if problem == 'partial_status' else 'complete'}))
    monkeypatch.setattr(sys, 'argv', ['packet', '--experiment', str(tmp_path)])
    with pytest.raises(ValueError):
        module('24_balanced_review_packet.py').main()
    assert not (tmp_path / 'blind_packet.jsonl').exists()


def test_mixed_cache_invocation_is_explicit_not_mistaken_for_fresh_latency():
    flags = iter([True, False])

    class Client:
        def generate_json(self, *args, **kwargs):
            return 'result', SimpleNamespace(cached=next(flags))

    measured = module('23_balanced_experiment.py').InvocationClient(Client())
    measured.generate_json('first', object)
    measured.generate_json('second', object)
    assert measured.cached == [True, False]
    assert any(measured.cached)


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'analysis_tools'))
    return module('reproduce_balanced.py', 'analysis_tools')


def blind_context(verifier):
    rows, mapping, packet = [], [], []
    for alias, system in zip('ABC', verifier.SYSTEMS, strict=True):
        row = dict(id='x', system=system, input_text='My music stopped playing',
                   reply_draft=f'Approved {system} reply /AI',
                   evidence=[{'thread_id': 'current:playback', 'brand_reply': 'Restart the app.'}])
        shared = dict(id='x', alias=alias, run_id='test-run',
                      reply_hash=verifier.reply_hash(row['reply_draft']), rubric_version=verifier.RUBRIC_VERSION)
        rows.append(row)
        mapping.append({**shared, 'system': system})
        packet.append({**shared, 'text': row['input_text'], 'reply_draft': row['reply_draft'],
                       'evidence': deepcopy(row['evidence'])})
    return rows, mapping, packet


@pytest.mark.parametrize('field,value', [('reviewer_type', 'human'), ('reviewer_id', 'someone-else'), ('run_id', 'old-run')])
def test_coverage_metadata_cannot_relabel_ai_reviews(verifier, field, value):
    rating = {'reviewer_id': 'astra', 'reviewer_type': 'ai', 'run_id': 'current-run'}
    verifier.verify_review_metadata([rating], rating.copy(), 'current-run')
    changed = {**rating, field: value}
    with pytest.raises(ValueError):
        verifier.verify_review_metadata([rating], changed, 'current-run')


def human_record(verifier, directory):
    for file in verifier.HUMAN_BOUND_FILES:
        (directory / file).write_text('synthetic test fixture', encoding='utf-8')
    return dict(status='completed', reviewer='Test reviewer', reviewer_type='human',
                confirmed_at='2026-09-17T00:00:00Z', confirmation='Synthetic test attestation',
                review_method='human_verification_of_ai_ratings', blinding='existing_scores_visible',
                scores_changed=False, n_reply_ratings=3, n_messages=1,
                artifacts={file: verifier.sha256(directory / file) for file in verifier.HUMAN_BOUND_FILES})


def test_human_verification_is_separate_and_never_rewrites_ai_provenance(verifier, tmp_path):
    ratings = [{'id': 'x', 'reviewer_type': 'ai'} for _ in range(3)]
    assert verifier.human_verification(tmp_path, ratings) is None
    record = human_record(verifier, tmp_path)
    (tmp_path / 'HUMAN_VERIFICATION.json').write_text(json.dumps(record), encoding='utf-8')
    before = (tmp_path / 'blind_astra_ratings.jsonl').read_bytes()
    assert verifier.human_verification(tmp_path, ratings) == record
    assert all(r['reviewer_type'] == 'ai' for r in ratings)
    assert (tmp_path / 'blind_astra_ratings.jsonl').read_bytes() == before


@pytest.mark.parametrize('problem', ['old_hash', 'wrong_count', 'ai_reviewer', 'partial', 'scores_changed', 'missing_artifact'])
def test_human_confirmation_cannot_transfer_to_other_or_unfinished_reviews(verifier, tmp_path, problem):
    record = human_record(verifier, tmp_path)
    if problem == 'old_hash':
        record['artifacts']['blind_astra_ratings.jsonl'] = 'old'
    elif problem == 'wrong_count':
        record['n_reply_ratings'] = 100
    elif problem == 'ai_reviewer':
        record['reviewer_type'] = 'ai'
    elif problem == 'partial':
        record['status'] = 'pending'
    elif problem == 'scores_changed':
        record['scores_changed'] = True
    else:
        record['artifacts'].pop('blind_packet.jsonl')
    (tmp_path / 'HUMAN_VERIFICATION.json').write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError):
        verifier.human_verification(tmp_path, [{'id': 'x'} for _ in range(3)])


@pytest.mark.parametrize('field,value', [('reviewer', None), ('reviewer', False), ('confirmation', None),
                                       ('confirmation', 123), ('confirmed_at', 'not a timestamp'),
                                       ('confirmed_at', '2026-09-17T00:00:00'), ('n_messages', True)])
def test_invalid_human_identity_and_timestamp_cannot_open_gate(verifier, tmp_path, field, value):
    record = {**human_record(verifier, tmp_path), field: value}
    (tmp_path / 'HUMAN_VERIFICATION.json').write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError):
        verifier.human_verification(tmp_path, [{'id': 'x'} for _ in range(3)])


def test_blind_context_accepts_complete_exact_mapping(verifier):
    verifier.verify_blind_packet(*blind_context(verifier), 'test-run')


@pytest.mark.parametrize('problem', ['customer', 'evidence', 'reply', 'missing', 'duplicate',
                                    'leaked_system', 'mapping_system', 'stale_run'])
def test_review_context_tampering_cannot_pass_with_a_valid_reply_hash(verifier, problem):
    rows, mapping, packet = blind_context(verifier)
    if problem == 'customer':
        packet[0]['text'] = 'An unrelated customer issue'
    elif problem == 'evidence':
        packet[0]['evidence'][0]['brand_reply'] = 'Unrelated evidence'
    elif problem == 'reply':
        packet[0]['reply_draft'] = 'Different reply /AI'
    elif problem == 'missing':
        packet.pop()
    elif problem == 'duplicate':
        packet[-1] = deepcopy(packet[0])
    elif problem == 'leaked_system':
        packet[0]['system'] = 'agent'
    elif problem == 'mapping_system':
        mapping[0]['system'] = 'quality'
    elif problem == 'stale_run':
        mapping[0]['run_id'] = packet[0]['run_id'] = 'old-run'
    with pytest.raises(ValueError):
        verifier.verify_blind_packet(rows, mapping, packet, 'test-run')


@pytest.mark.parametrize('problem', ['phase', 'unknown_phase', 'summary_status', 'status',
                                    'summary_count', 'frozen_count', 'completed', 'expected'])
def test_acceptance_requires_complete_run_and_matching_phase(verifier, problem):
    manifest = {'frozen': {'phase': 'confirmation', 'n': 2}}
    summary = {'phase': 'confirmation', 'status': 'complete', 'n': 2}
    status = {'status': 'complete', 'completed': 6, 'expected': 6}
    verifier.validate_run_state(manifest, summary, status, 2)
    if problem == 'phase':
        summary['phase'] = 'development'
    elif problem == 'unknown_phase':
        manifest['frozen']['phase'] = summary['phase'] = 'unknown'
    elif problem == 'summary_status':
        summary['status'] = 'partial'
    elif problem == 'status':
        status['status'] = 'partial'
    elif problem == 'summary_count':
        summary['n'] = 1
    elif problem == 'frozen_count':
        manifest['frozen']['n'] = 1
    else:
        status[problem] = 5
    with pytest.raises(ValueError):
        verifier.validate_run_state(manifest, summary, status, 2)


@pytest.mark.parametrize('phase,promote', [('development', False), ('confirmation', True)])
def test_passing_development_gates_never_authorize_promotion(verifier, monkeypatch, phase, promote):
    monkeypatch.setattr(verifier, 'sha256', lambda _: 'test-hash')
    labels = [{'id': str(i), 'gold': {'should_escalate': False}} for i in range(10)]
    totals = {'agent': 2, 'quality': 1, 'balanced': 3}
    rows = [{'id': str(i), 'system': system, 'decision': 'auto_handle' if i < count else 'escalate'}
            for system, count in totals.items() for i in range(10)]
    ratings = [{**row, 'flags': {}, 'scores': {'safe': 5}, 'reviewer_type': 'human'} for row in rows]
    coverage = {'reviewer_type': 'human', 'systems': {system: {
        'automatic': count, 'useful_automatic': count, 'useful_resolution': count}
        for system, count in totals.items()}}
    summary = {'phase': phase, 'runtime': {system: {'p95_ms': 1000, 'fresh_invocations': 10}
                                         for system in totals}}
    rules = {'min_auto_coverage': .2, 'max_auto_coverage_loss_vs_reference': .1,
             'max_candidate_p95_ms': 7500}
    result = verifier.acceptance(Path('.'), labels, rows, ratings, coverage, summary, rules)
    assert all(result['gates'].values()) and result['technical_gates_pass']
    assert result['promote'] is promote
    assert 'blind_packet.jsonl' in result['input_hashes']
    if phase == 'development':
        assert 'fresh confirmation is required' in result['decision']
