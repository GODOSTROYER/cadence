import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def publication(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'analysis_tools' / 'publish_balanced.py'
    spec = importlib.util.spec_from_file_location('publish_balanced', path)
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    monkeypatch.setattr(publisher, 'Paths', SimpleNamespace(RESULTS=tmp_path))
    for name in publisher.RUNS:
        directory = tmp_path / name
        directory.mkdir()
        phase = 'confirmation' if name == 'balanced_confirmation' else 'development'
        summary = dict(status='complete', phase=phase, n=1,
                       runtime={s: {'fresh_invocations': 1} for s in publisher.NAMES},
                       comparisons={'balanced': {'left': {}, 'right': {}}, 'quality': {'left': {}}})
        accepted = dict(status='completed', phase=phase, n=1, counts={},
                        gates={'latency_observations_fully_fresh': True},
                        technical_gates_pass=False, promote=False,
                        decision='Not promoted', reviewer_type='ai', input_hashes={})
        save(publisher, directory, accepted, summary)
    return publisher, tmp_path


def save(publisher, directory, accepted, summary):
    (directory / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
    accepted['input_hashes']['summary.json'] = publisher.sha256(directory / 'summary.json')
    (directory / 'ACCEPTANCE.json').write_text(json.dumps(accepted), encoding='utf-8')


def test_publication_preserves_development_history_and_uses_completed_confirmation(publication):
    publisher, _ = publication
    result = publisher.publication()
    assert result['current']['id'] == 'balanced_confirmation'
    assert result['current']['phase'] == 'confirmation'
    assert all(r['phase'] == 'development' for r in result['experiments'][:-1])
    assert result['current']['reviewer_type'] == 'ai'
    assert result['current']['human_verification'] is None
    assert not result['current']['promote']
    assert 'Every recorded model call' in result['latency_note']


def test_publication_keeps_ai_authorship_and_discloses_separate_human_verification(publication):
    publisher, root = publication
    directory = root / 'balanced_confirmation'
    record = dict(status='completed', reviewer='Synthetic reviewer', reviewer_type='human',
                  confirmed_at='2026-09-17T12:00:00Z', n_reply_ratings=3, n_messages=1,
                  review_method='human_verification_of_ai_ratings',
                  blinding='existing_scores_visible', scores_changed=False)
    record_path = directory / 'HUMAN_VERIFICATION.json'
    record_path.write_text(json.dumps(record), encoding='utf-8')
    accepted = json.loads((directory / 'ACCEPTANCE.json').read_text(encoding='utf-8'))
    accepted['human_verification'] = record
    accepted['input_hashes']['HUMAN_VERIFICATION.json'] = publisher.sha256(record_path)
    (directory / 'ACCEPTANCE.json').write_text(json.dumps(accepted), encoding='utf-8')
    result = publisher.publication()
    assert result['current']['reviewer_type'] == 'ai'
    assert result['current']['human_verification'] == record
    note = result['review_note']
    assert 'Synthetic reviewer' in note and record['confirmed_at'] in note
    assert 'verified unchanged' in note and 'existing scores visible' in note
    assert 'not an independent blind human rating pass' in note
    assert 'routing labels retain their recorded AI provenance' in note


@pytest.mark.parametrize('name,accepted_update,summary_update', [
    ('balanced_confirmation', {'phase': 'development'}, {'phase': 'development'}),
    ('balanced_dev', {'phase': 'confirmation'}, {'phase': 'confirmation'}),
    ('balanced_confirmation', {}, {'phase': 'development'}),
    ('balanced_dev_v3', {'phase': 'unknown'}, {'phase': 'unknown'}),
    ('balanced_confirmation', {'status': 'pending'}, {}),
    ('balanced_dev', {}, {'status': 'partial'}),
])
def test_publication_rejects_wrong_phase_or_unfinished_evidence_even_with_valid_hashes(
        publication, name, accepted_update, summary_update):
    publisher, root = publication
    directory = root / name
    accepted = json.loads((directory / 'ACCEPTANCE.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    accepted.update(accepted_update)
    summary.update(summary_update)
    save(publisher, directory, accepted, summary)
    with pytest.raises(ValueError, match='Publication'):
        publisher.publication()


def resumed_fixture(publisher, directory):
    for name in ('manifest.json', 'predictions.jsonl'):
        (directory / name).write_text('synthetic fixture', encoding='utf-8')
    interruption = dict(status='interrupted', completed=2, partial_invocation_cache_flags=[])
    (directory / 'INTERRUPTION.json').write_text(json.dumps(interruption), encoding='utf-8')
    with sqlite3.connect(directory / 'calls.sqlite') as conn:
        conn.execute('CREATE TABLE calls (created_at TEXT)')
        conn.executemany('INSERT INTO calls VALUES (?)', [('2026-09-17T18:00:00Z',),
                                                         ('2026-09-18T06:00:00Z',)])
    verification = {'artifacts': {'calls.sqlite': publisher.sha256(directory / 'calls.sqlite')}}
    (directory / 'VERIFICATION.json').write_text(json.dumps(verification), encoding='utf-8')
    notes = dict(status='completed', saved_before_interruption=2, added_after_resume=1,
                 total_predictions=3, successful_invocations_fully_fresh=True,
                 partial_invocation_cache_flags_at_interruption=[],
                 input_hashes={name: publisher.sha256(directory / name) for name in
                               ('manifest.json', 'predictions.jsonl', 'summary.json', 'INTERRUPTION.json')})
    (directory / 'EXECUTION_NOTES.json').write_text(json.dumps(notes), encoding='utf-8')
    return notes


def test_resumed_publication_discloses_receipt_dates_without_calling_fresh_calls_one_session(publication):
    publisher, root = publication
    resumed_fixture(publisher, root / 'balanced_confirmation')
    result = publisher.publication()
    execution = result['current']['execution']
    assert execution['receipt_dates_utc'] == ['2026-09-17', '2026-09-18']
    assert execution['saved_before_interruption'] == 2 and execution['added_after_resume'] == 1
    assert 'EXECUTION_NOTES.json' in execution['input_hashes']
    assert 'Every recorded model call' in result['latency_note']
    assert 'stopped after 2 predictions and resumed for 1 more' in result['latency_note']
    assert '2026-09-17, 2026-09-18 (UTC)' in result['latency_note']
    assert 'interruption time are excluded' in result['latency_note']


@pytest.mark.parametrize('problem', ['count', 'freshness', 'receipt_changed', 'artifact_changed'])
def test_resumed_note_cannot_disagree_with_receipts_or_preserved_artifacts(publication, problem):
    publisher, root = publication
    directory = root / 'balanced_confirmation'
    notes = resumed_fixture(publisher, directory)
    if problem == 'count':
        notes['added_after_resume'] = 2
    elif problem == 'freshness':
        notes['successful_invocations_fully_fresh'] = False
    elif problem == 'receipt_changed':
        with sqlite3.connect(directory / 'calls.sqlite') as conn:
            conn.execute("UPDATE calls SET created_at = '2026-09-19T06:00:00Z'")
    else:
        (directory / 'predictions.jsonl').write_text('changed', encoding='utf-8')
    (directory / 'EXECUTION_NOTES.json').write_text(json.dumps(notes), encoding='utf-8')
    with pytest.raises(ValueError, match='Execution'):
        publisher.publication()


def test_mixed_cache_note_reports_actual_fresh_counts(publication):
    publisher, _ = publication
    run = publisher.publication()['current']
    run['gates']['latency_observations_fully_fresh'] = False
    run['runtime']['quality']['fresh_invocations'] = 0
    note = publisher.latency_note(run)
    assert 'Timings include predictions with cached calls' in note
    assert 'Quality candidate 0/1' in note and 'freshness gate failed' in note
    assert 'Every recorded model call' not in note


def test_markdown_handles_undefined_recall_without_inventing_a_score(publication):
    publisher, _ = publication
    data = publisher.publication()
    for run in data['experiments']:
        run['counts'] = {system: dict(automatic=1, useful_automatic=1, useful_resolution=1,
                                     missed_escalations=0, flagged_automatic=0) for system in publisher.NAMES}
        run['runtime'] = {system: dict(p95_ms=1000, prompt_tokens=10, output_tokens=5)
                          for system in publisher.NAMES}
        run['classification'] = {system: dict(intent_accuracy=1.0, macro_f1=1.0, escalation_recall=None)
                                 for system in publisher.NAMES}
    rendered = publisher.markdown(data)
    assert '| Reference | 1.000 | 1.000 | N/A |' in rendered
