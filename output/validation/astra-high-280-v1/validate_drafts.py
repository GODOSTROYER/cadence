"""Verify AI draft identity/provenance and assemble the human validation packet."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from cadence.eval.provenance import sha256

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
FIELDS = {'id', 'intent', 'secondary_intent', 'should_escalate', 'escalation_reason_code',
          'sentiment', 'notes', 'confidence', 'needs_human_attention', 'validation_question',
          'annotator', 'label_source', 'model', 'reasoning_effort', 'labeled_at'}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_annotation(row, batch, prepared, intents, reasons):
    ident = row['id']
    require(set(row) == FIELDS, 'Unexpected fields: ' + ident)
    require(row['intent'] in intents, 'Invalid intent: ' + ident)
    require(row['secondary_intent'] is None or (row['secondary_intent'] in intents and row['secondary_intent'] != row['intent']), 'Invalid secondary intent: ' + ident)
    require(type(row['should_escalate']) is bool and type(row['needs_human_attention']) is bool, 'Boolean required: ' + ident)
    require(row['escalation_reason_code'] in reasons if row['should_escalate'] else row['escalation_reason_code'] is None, 'Route/reason disagree: ' + ident)
    require(row['sentiment'] in {'positive', 'neutral', 'frustrated', 'angry'}, 'Invalid sentiment: ' + ident)
    require(row['confidence'] in {'high', 'medium', 'low'}, 'Invalid confidence: ' + ident)
    require(isinstance(row['notes'], str) and len(row['notes'].strip()) >= 10, 'Missing rationale: ' + ident)
    require(isinstance(row['validation_question'], str), 'Invalid validation question: ' + ident)
    require(not row['needs_human_attention'] or bool(row['validation_question'].strip()), 'Missing human question: ' + ident)
    require(row['label_source'] == 'ai' and row['model'] == 'gpt-6-astra' and row['reasoning_effort'] == 'high', 'Wrong AI provenance: ' + ident)
    require(row['annotator'] == '/root/label_' + batch['name'], 'Unexpected annotator identity: ' + ident)
    labeled = datetime.fromisoformat(row['labeled_at'])
    require(labeled.tzinfo is not None and prepared <= labeled <= datetime.now(UTC), 'Invalid label timestamp: ' + ident)


def verify():
    manifest = read_json(FOLDER / 'MANIFEST.json')
    prepared = datetime.fromisoformat(manifest['prepared_at'])
    require(sha256(FOLDER / 'ANNOTATION_GUIDE.md') == manifest['guide_sha256'], 'Annotation guide changed')
    raw_mismatches = []
    for name, digests in manifest['sources'].items():
        path = ROOT / name
        require(sha256(path) == digests['sha256'], 'Source changed: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digests['raw_sha256']:
            raw_mismatches.append(name)
    intents = {r['id'] for r in yaml.safe_load((ROOT / 'data/verified_confirmation/intents.snapshot.yaml').read_text(encoding='utf-8'))['intents']}
    reasons = {r['id'] for r in yaml.safe_load((ROOT / 'data/verified_confirmation/reasons.snapshot.yaml').read_text(encoding='utf-8'))['reason_codes']}
    sources = {}
    for partition in ('confirmation', 'challenge'):
        directory = ROOT / 'data' / ('verified_' + partition)
        for name in ('LABEL_REVIEW.json', 'labels.jsonl', 'INFERENCE_STARTED.json'):
            require(not (directory / name).exists(), 'Unexpected human import/inference artifact: ' + name)
        sources[partition] = {row['id']: row for row in read_lines(directory / 'examples.jsonl')}
    output, counts, bindings = {'confirmation': [], 'challenge': []}, [], {}
    revisions = []
    for batch in manifest['batches']:
        path = ROOT / batch['output']
        inputs = ROOT / batch['input']
        require(sha256(inputs) == batch['input_sha256'], 'Batch input changed: ' + batch['name'])
        require(path.exists(), 'Missing draft: ' + batch['name'])
        require(path.with_suffix('.COMPLETE.json').exists(), 'Draft not complete: ' + batch['name'])
        rows = read_lines(path)
        expected = read_lines(inputs)
        require(len(rows) == batch['n'], 'Wrong batch size: ' + batch['name'])
        require([r['id'] for r in rows] == [r['id'] for r in expected], 'IDs missing, duplicated, or reordered: ' + batch['name'])
        effective_rows = []
        for original in rows:
            validate_annotation(original, batch, prepared, intents, reasons)
            row = original
            ident = row['id']
            revision_path = FOLDER / 'drafts' / (ident + '.revision_01.json')
            revision_metadata = {}
            if revision_path.exists():
                row = read_json(revision_path)
                require(row['id'] == ident, 'Revision identity changed')
                validate_annotation(row, batch, prepared, intents, reasons)
                require(datetime.fromisoformat(row['labeled_at']) > datetime.fromisoformat(original['labeled_at']), 'Revision must follow original label')
                changed = [key for key in sorted(FIELDS) if row[key] != original[key]]
                relative = revision_path.relative_to(ROOT).as_posix()
                revision_metadata = {'original_ai_annotation': original, 'ai_revision_path': relative, 'ai_revision_changed_fields': changed}
                revisions.append({'id': ident, 'path': relative, 'sha256': sha256(revision_path), 'changed_fields': changed})
                bindings[relative] = sha256(revision_path)
            source = sources[batch['partition']][ident]
            source_input = next(item for item in expected if item['id'] == ident)
            require(source_input['text'] == source['text'], 'Input/source text differs: ' + ident)
            if batch['partition'] == 'challenge':
                require(source_input['scenario_setup'] == source.get('setup', {}), 'Scenario setup differs: ' + ident)
            output[batch['partition']].append({**row, **revision_metadata, 'text': source['text'], 'scenario_setup': source.get('setup', {}),
                                                'review_status': 'Pending', 'reviewer': '', 'reviewed_at': '', 'human_notes': ''})
            effective_rows.append(row)
        counts.append({'batch': batch['name'], 'n': len(rows), 'escalate': sum(r['should_escalate'] for r in effective_rows),
                       'initial_escalate': sum(r['should_escalate'] for r in rows),
                       'needs_human_attention': sum(r['needs_human_attention'] for r in effective_rows)})
        bindings[batch['output']] = sha256(path)
        bindings[path.with_suffix('.COMPLETE.json').relative_to(ROOT).as_posix()] = sha256(path.with_suffix('.COMPLETE.json'))
    require(len(output['confirmation']) == 200 and len(output['challenge']) == 80, 'Partition counts do not match')
    return output, {'verified_at': datetime.now(UTC).isoformat(), 'status': 'AI drafts verified for human validation',
                    'counts': counts, 'draft_bindings': bindings, 'ai_revisions': revisions, 'source_files_unchanged': True,
                    'raw_source_byte_differences': raw_mismatches,
                    'human_validation_complete': False, 'independent_human_labeling': False, 'candidate_inference_run': False}


def attach_acceptance_questions(data):
    """Preserve original proposals and surface independent review suggestions."""
    by_id = {row['id']: row for rows in data.values() for row in rows}
    reviewed_ids, review_bindings, total_findings = [], {}, 0
    for name in ('confirmation_001_150.final.json', 'confirmation_151_200_and_challenge.final.json'):
        path = FOLDER / 'reviews' / name
        require(path.exists(), 'Missing independent acceptance review: ' + name)
        review = read_json(path)
        require(review['reviewer_model'] == 'gpt-6-astra' and review['reasoning_effort'] == 'xhigh' and review['reviewer_type'] == 'ai', 'Invalid review provenance')
        require(review['status'] == 'accepted_for_human_validation', 'Review requires rework: ' + name)
        require(review['reviewed_count'] == len(review['reviewed_ids']), 'Review coverage count differs')
        for source, digest in review['input_hashes'].items():
            candidate = ROOT / source
            if not candidate.exists():
                candidate = FOLDER / source
            require(candidate.is_file() and sha256(candidate) == digest, 'Reviewed input changed: ' + source)
        reviewed_ids.extend(review['reviewed_ids'])
        for finding in review['findings']:
            require(finding['id'] in review['reviewed_ids'], 'Finding outside assigned review')
            row = by_id[finding['id']]
            row.setdefault('original_validation_question', row['validation_question'])
            row.setdefault('acceptance_review_findings', []).append(finding)
            row['needs_human_attention'] = True
            proposed = json.dumps(finding['proposed_value'], ensure_ascii=False)
            if finding['severity'] == 'correction' and row.get('ai_revision_path'):
                suggestion = f"The original Astra-high annotator revised this proposal after acceptance review ({finding['field']}). The original draft is preserved. {finding['question_for_human']}"
            else:
                suggestion = f"Acceptance review suggests {finding['field']} = {proposed}. {finding['rationale']} {finding['question_for_human']}"
            row['validation_question'] = (row['validation_question'] + '\n' + suggestion).strip()
            total_findings += 1
        review_bindings[path.relative_to(ROOT).as_posix()] = sha256(path)
    require(len(reviewed_ids) == len(set(reviewed_ids)) == 280 and set(reviewed_ids) == set(by_id), 'Independent review coverage is incomplete')
    return {'independently_reviewed_rows': 280, 'acceptance_review_findings': total_findings,
            'rows_requiring_human_attention': sum(row['needs_human_attention'] for row in by_id.values()),
            'review_bindings': review_bindings,
            'original_draft_files_unchanged': True,
            'method': 'Named, reviewed Astra-high revisions applied explicitly; original draft rows preserved in revision metadata. Acceptance questions remain visible; human approval pending.'}


def write_new(path, content):
    if path.exists():
        require(path.read_text(encoding='utf-8') == content, 'Existing output differs; preserve it and choose a new revision: ' + path.name)
    else:
        path.write_text(content, encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assemble', action='store_true')
    args = parser.parse_args()
    data, record = verify()
    if args.assemble:
        record['acceptance_review'] = attach_acceptance_questions(data)
        write_new(FOLDER / 'review_data.json', json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        fields = ['id', 'text', 'scenario_setup', 'intent', 'secondary_intent', 'should_escalate',
                  'escalation_reason_code', 'sentiment', 'notes', 'confidence', 'needs_human_attention',
                  'validation_question', 'review_status', 'reviewer', 'reviewed_at', 'human_notes', 'label_source']
        for partition, rows in data.items():
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
            writer.writeheader()
            for row in rows:
                item = {k: row[k] for k in fields}
                item['scenario_setup'] = json.dumps(item['scenario_setup'], ensure_ascii=False, sort_keys=True) if item['scenario_setup'] else ''
                for key in ('should_escalate', 'needs_human_attention'):
                    item[key] = str(item[key]).lower()
                writer.writerow(item)
            write_new(FOLDER / (partition + '-validation.csv'), stream.getvalue())
        (FOLDER / 'DRAFT_VALIDATION.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps({k: v for k, v in record.items() if k != 'draft_bindings'}))


if __name__ == '__main__':
    main()
