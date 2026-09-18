"""Validate and assemble the additional AI-only review; never import gold labels."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import yaml

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
OLD = FOLDER.parent / 'astra-high-280-v1'
LABELS = {'intent', 'secondary_intent', 'should_escalate', 'escalation_reason_code', 'sentiment'}
FIELDS = {'id', 'review_source', 'model', 'reasoning_effort', 'reviewer', 'reviewed_at',
          'human_verified', 'disposition', 'labels', 'changed_fields', 'rationale',
          'question_resolution', 'confidence', 'requires_human_decision', 'remaining_question'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def save_new(path, content):
    if path.exists():
        require(path.read_text(encoding='utf-8') == content, f'Preserve differing existing output: {path.name}')
    else:
        path.write_text(content, encoding='utf-8', newline='\n')


def assemble():
    manifest = read(FOLDER / 'MANIFEST.json')
    prepared = datetime.fromisoformat(manifest['prepared_at'])
    for name, expected in manifest['source_bindings'].items():
        require(digest(ROOT / name) == expected, f'Source changed: {name}')
    old = read(OLD / 'review_data.json')
    flagged = {r['id']: r for partition in old.values() for r in partition if r['needs_human_attention']}
    require(len(flagged) == 55, 'Flagged scope differs')
    accepted = read(OLD / 'ACCEPTANCE.json')
    normalized = {'.md', '.json', '.jsonl', '.py', '.yaml', '.txt'}
    for key, base in [('artifact_bindings', OLD), ('source_bindings', ROOT)]:
        for name, binding in accepted[key].items():
            path = base / name
            raw = path.read_bytes()
            canonical = raw.replace(b'\r\n', b'\n') if path.suffix in normalized else raw
            require(hashlib.sha256(canonical).hexdigest() == binding['canonical_sha256'], f'Original accepted file changed: {name}')
    intents = {x['id'] for x in yaml.safe_load((ROOT / 'data/verified_confirmation/intents.snapshot.yaml').read_text(encoding='utf-8'))['intents']}
    reasons = {x['id'] for x in yaml.safe_load((ROOT / 'data/verified_confirmation/reasons.snapshot.yaml').read_text(encoding='utf-8'))['reason_codes']}
    data = {'confirmation': [], 'challenge': []}
    seen, bindings = set(), {}
    for batch in manifest['batches']:
        inp = FOLDER / batch['input']
        require(digest(inp) == batch['sha256'], f'Input changed: {batch["name"]}')
        inputs = lines(inp)
        path = FOLDER / batch['output']
        reviews = lines(path)
        require(path.with_suffix('.COMPLETE.json').is_file(), f'Incomplete batch: {batch["name"]}')
        require([r['id'] for r in inputs] == batch['ids'] == [r['id'] for r in reviews], 'Missing/reordered batch IDs')
        require(len(reviews) == batch['count'], 'Batch count differs')
        completion = read(path.with_suffix('.COMPLETE.json'))
        require(completion['reviewer'] == batch['reviewer'], 'Completion reviewer differs')
        require(completion['review_source'] == 'ai' and completion['human_verified'] is False, 'Invalid completion provenance')
        require(completion['model'] == 'gpt-6-astra' and completion['reasoning_effort'] == 'ultra', 'Completion model/effort differs')
        require(completion['reviewed_ids'] == batch['ids'] and completion['reviewed_count'] == batch['count'], 'Completion coverage differs')
        require(completion['individually_reviewed'] is True, 'Individual review not confirmed')
        completed = datetime.fromisoformat(completion['completed_at'])
        require(completed.tzinfo is not None and prepared <= completed <= datetime.now(UTC), 'Invalid completion time')
        require(all(datetime.fromisoformat(r['reviewed_at']).tzinfo is not None and datetime.fromisoformat(r['reviewed_at']) <= completed for r in reviews), 'Review timestamp after completion')
        bindings[batch['output']] = digest(path)
        bindings[path.with_suffix('.COMPLETE.json').relative_to(FOLDER).as_posix()] = digest(path.with_suffix('.COMPLETE.json'))
        for source, review in zip(inputs, reviews, strict=True):
            ident = source['id']
            require(ident not in seen and ident in flagged, f'Unexpected/duplicate ID: {ident}')
            seen.add(ident)
            prior = flagged[ident]
            require(source['text'] == prior['text'] and source['scenario_setup'] == prior['scenario_setup'], f'Source text/setup changed: {ident}')
            require(source['prior_ai_proposal'] == {k: prior[k] for k in LABELS}, f'Prior labels changed: {ident}')
            require(source['flagged_question'] == prior['validation_question'], f'Question changed: {ident}')
            require(set(review) == FIELDS, f'Invalid review fields: {ident}')
            require(review['review_source'] == 'ai' and review['human_verified'] is False, f'False human provenance: {ident}')
            require(review['model'] == 'gpt-6-astra' and review['reasoning_effort'] == 'ultra', f'Wrong model/effort: {ident}')
            require(review['reviewer'] == batch['reviewer'], f'Wrong reviewer: {ident}')
            when = datetime.fromisoformat(review['reviewed_at'])
            require(when.tzinfo is not None and prepared <= when <= datetime.now(UTC), f'Invalid timestamp: {ident}')
            labels = review['labels']
            require(set(labels) == LABELS, f'Invalid label keys: {ident}')
            require(labels['intent'] in intents, f'Invalid intent: {ident}')
            secondary = labels['secondary_intent']
            require(secondary is None or (secondary in intents and secondary != labels['intent']), f'Invalid secondary intent: {ident}')
            require(type(labels['should_escalate']) is bool, f'Invalid routing type: {ident}')
            require(labels['escalation_reason_code'] in reasons if labels['should_escalate'] else labels['escalation_reason_code'] is None, f'Route/reason mismatch: {ident}')
            require(labels['sentiment'] in {'positive', 'neutral', 'frustrated', 'angry'}, f'Invalid sentiment: {ident}')
            changes = sorted(k for k in LABELS if labels[k] != source['prior_ai_proposal'][k])
            require(isinstance(review['changed_fields'], list) and sorted(review['changed_fields']) == changes, f'Incorrect changes: {ident}')
            unresolved = review['requires_human_decision']
            require(type(unresolved) is bool, f'Invalid unresolved flag: {ident}')
            require(review['disposition'] == ('needs_discussion' if unresolved else 'revised' if changes else 'confirmed'), f'Inconsistent disposition: {ident}')
            require(isinstance(review['remaining_question'], str) and bool(review['remaining_question'].strip()) == unresolved, f'Inconsistent remaining question: {ident}')
            require(review['confidence'] in {'high', 'medium', 'low'}, f'Invalid confidence: {ident}')
            for key in ('rationale', 'question_resolution'):
                require(isinstance(review[key], str) and len(review[key].strip()) >= 15, f'Missing reasoning: {ident}')
            data[source['partition']].append({**source, 'ultra_review': review, 'human_review_status': 'Pending',
                                              'human_reviewer': '', 'human_reviewed_at': '', 'human_notes': ''})
    require(seen == set(flagged), 'Review coverage differs from all55 flagged IDs')
    require(len(data['confirmation']) == 35 and len(data['challenge']) == 20, 'Partition scope differs')
    for partition in data:
        for marker in ('LABEL_REVIEW.json', 'labels.jsonl', 'INFERENCE_STARTED.json'):
            require(not (ROOT / 'data' / f'verified_{partition}' / marker).exists(), f'Unexpected import/inference marker: {marker}')
    rows = data['confirmation'] + data['challenge']
    summary = {'total': len(rows), 'confirmation': 35, 'challenge': 20,
               'dispositions': dict(Counter(r['ultra_review']['disposition'] for r in rows)),
               'cases_with_label_changes': sum(bool(r['ultra_review']['changed_fields']) for r in rows),
               'requires_human_decision': sum(r['ultra_review']['requires_human_decision'] for r in rows)}
    metadata = {'review_source': 'ai', 'model': 'gpt-6-astra', 'reasoning_effort': 'ultra',
                'human_validation_complete': False, 'candidate_inference_run': False,
                'method': 'Additional AI review of flagged Astra-high proposals; prior labels and questions were visible.',
                'original_280_case_package_unchanged': True, 'summary': summary,
                'review_bindings': bindings}
    return {'metadata': metadata, **data}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    data = assemble()
    if args.write:
        save_new(FOLDER / 'review_data.json', json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        for partition in ('confirmation', 'challenge'):
            flat = []
            for row in data[partition]:
                r = row['ultra_review']
                flat.append({'id': row['id'], 'text': row['text'], 'scenario_setup': json.dumps(row['scenario_setup'], ensure_ascii=False, sort_keys=True),
                             **{'prior_' + k: row['prior_ai_proposal'][k] for k in sorted(LABELS)},
                             **{'ultra_' + k: r['labels'][k] for k in sorted(LABELS)},
                             'flagged_question': row['flagged_question'],
                             **{k: json.dumps(r[k]) if isinstance(r[k], list) else r[k] for k in FIELDS - {'id', 'labels'}},
                             **{k: row[k] for k in ('human_review_status', 'human_reviewer', 'human_reviewed_at', 'human_notes')}})
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=sorted(flat[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(flat)
            save_new(FOLDER / f'{partition}-ultra-review.csv', stream.getvalue())
    print(json.dumps(data['metadata']))


if __name__ == '__main__':
    main()
