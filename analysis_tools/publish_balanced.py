"""Publish the same three-arm evidence to the report and dashboard; no model calls."""
from __future__ import annotations

import argparse
import json
import sqlite3

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.utils.io import read_json

RUNS = ('balanced_dev', 'balanced_dev_v2', 'balanced_dev_v3', 'balanced_confirmation')
NAMES = {'agent': 'Reference', 'quality': 'Quality candidate', 'balanced': 'Balanced candidate'}


def execution_notes(directory, summary):
    path = directory / 'EXECUTION_NOTES.json'
    interruption_path = directory / 'INTERRUPTION.json'
    if not path.exists() and not interruption_path.exists():
        return None
    notes, interruption = read_json(path), read_json(interruption_path)
    required = {'manifest.json', 'predictions.jsonl', 'summary.json', 'INTERRUPTION.json'}
    if set(notes['input_hashes']) != required:
        raise ValueError('Execution note must bind all resumed-run inputs')
    for file, digest in notes['input_hashes'].items():
        if sha256(directory / file) != digest:
            raise ValueError('Execution note source changed: ' + file)
    total = summary['n'] * len(NAMES)
    before = interruption['completed']
    fresh = all(summary['runtime'][s]['fresh_invocations'] == summary['n'] for s in NAMES)
    if (notes.get('status') != 'completed' or interruption.get('status') != 'interrupted'
            or type(before) is not int or not 0 <= before < total
            or notes.get('saved_before_interruption') != before
            or notes.get('added_after_resume') != total - before
            or notes.get('total_predictions') != total
            or notes.get('successful_invocations_fully_fresh') is not fresh
            or notes.get('partial_invocation_cache_flags_at_interruption') != interruption['partial_invocation_cache_flags']):
        raise ValueError('Execution note differs from saved interruption or runtime')
    receipt_hash = read_json(directory / 'VERIFICATION.json')['artifacts']['calls.sqlite']
    if sha256(directory / 'calls.sqlite') != receipt_hash:
        raise ValueError('Execution receipt database changed')
    with sqlite3.connect(f"file:{(directory / 'calls.sqlite').as_posix()}?mode=ro", uri=True) as conn:
        dates = [r[0] for r in conn.execute('SELECT DISTINCT date(created_at) FROM calls ORDER BY date(created_at)')]
    if not dates or any(date is None for date in dates):
        raise ValueError('Execution receipts need valid timestamps')
    return {'receipt_dates_utc': dates, 'saved_before_interruption': before,
            'added_after_resume': total - before, 'total_predictions': total,
            'input_hashes': {'EXECUTION_NOTES.json': sha256(path), 'INTERRUPTION.json': sha256(interruption_path),
                             'calls.sqlite': receipt_hash}}


def latency_note(run):
    note = 'Latency covers successful end-to-end predictions. '
    if run['gates']['latency_observations_fully_fresh']:
        note += 'Every recorded model call for these predictions was fresh. '
    else:
        fresh = '; '.join(f"{name} {run['runtime'][system]['fresh_invocations']}/{run['n']}"
                          for system, name in NAMES.items())
        note += f'Timings include predictions with cached calls. Fully fresh predictions: {fresh}. The freshness gate failed. '
    if (execution := run.get('execution')) is not None:
        note += (f"The run stopped after {execution['saved_before_interruption']} predictions and resumed for "
                 f"{execution['added_after_resume']} more; receipt dates are "
                 + ', '.join(execution['receipt_dates_utc']) + ' (UTC). ')
    return note + 'Failed or aborted attempts and interruption time are excluded; this is not a production traffic or availability benchmark.'


def metric(value):
    return 'N/A' if value is None else f'{value:.3f}'


def publication():
    experiments = []
    for name in RUNS:
        directory = Paths.RESULTS / name
        accepted = read_json(directory / 'ACCEPTANCE.json')
        for file, digest in accepted['input_hashes'].items():
            if sha256(directory / file) != digest:
                raise ValueError('Acceptance source changed: ' + name + '/' + file)
        summary = read_json(directory / 'summary.json')
        expected_phase = 'confirmation' if name == 'balanced_confirmation' else 'development'
        if accepted.get('status') != 'completed' or summary.get('status') != 'complete':
            raise ValueError('Publication requires completed evidence: ' + name)
        if accepted.get('phase') != expected_phase or summary.get('phase') != expected_phase:
            raise ValueError('Publication phase differs from the named experiment: ' + name)
        experiments.append({'id': name, 'n': accepted['n'], 'phase': accepted['phase'],
            'classification': {'agent': summary['comparisons']['balanced']['right'],
                               'quality': summary['comparisons']['quality']['left'],
                               'balanced': summary['comparisons']['balanced']['left']},
            'counts': accepted['counts'], 'runtime': summary['runtime'], 'gates': accepted['gates'],
            'technical_gates_pass': accepted['technical_gates_pass'], 'promote': accepted['promote'],
            'decision': accepted['decision'], 'reviewer_type': accepted['reviewer_type'],
            'human_verification': accepted.get('human_verification'),
            'execution': execution_notes(directory, summary),
            'source': 'results/' + name + '/ACCEPTANCE.json'})
    human = experiments[-1]['human_verification']
    review_note = ('New labels and reply ratings are AI-authored. Arnav Bule verified the earlier 100 ratings; that verification does not cover these new outputs.'
                   if human is None else
                   f"Reply ratings were initially AI-authored, then verified unchanged by {human['reviewer']} on {human['confirmed_at']}, with the existing scores visible. This is human verification of AI-assisted scores, not an independent blind human rating pass. New routing labels retain their recorded AI provenance.")
    return {'title': 'Useful automatic coverage and escalation safety', 'experiments': experiments,
            'current': experiments[-1], 'deployed_system': 'reference',
            'review_note': review_note, 'latency_note': latency_note(experiments[-1])}


def markdown(data):
    run = data['current']
    lines = ['# Balanced candidate: measured coverage and safety', '',
        'The previous quality candidate reduced missed escalations but sacrificed automatic coverage. This follow-up compares the unchanged reference, QualityAgent and BalancedAgent on the same messages.', '',
        '## Fresh confirmation', '',
        f"{run['n']} new messages, labelled by an independent GPT-6 Astra extra-high reviewer before inference. All three replies per message received a separate, blinded Astra review. These are AI assessments; small samples do not establish general safety.", '',
        '| System | Automatic | Useful automatic | Resolution-style replies | Missed escalations | Flagged auto | p95 | Tokens |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for system, name in NAMES.items():
        c, t = run['counts'][system], run['runtime'][system]
        lines.append(f"| {name} | {c['automatic']}/{run['n']} | {c['useful_automatic']}/{run['n']} | {c['useful_resolution']} | {c['missed_escalations']} | {c['flagged_automatic']} | {t['p95_ms']/1000:.2f} s | {t['prompt_tokens']+t['output_tokens']:,} |")
    lines += ['', '**Useful automatic** requires ship, grounding/safety/next-step scores of at least 4, no review flags, and a resolution or necessary clarification. Handoffs and social acknowledgments are excluded. Reviewer-rated resolution-style replies are reported separately from clarifications; these are not observed ticket closures. Missed escalations are measured against the independently frozen routing labels, even if the reply itself looks harmless.', '',
        data['latency_note'] + ' Tokens include every recorded successful model call.', '',
        '| System | Intent accuracy | Intent macro-F1 | Escalation recall |', '|---|---:|---:|---:|']
    for system, name in NAMES.items():
        metrics = run['classification'][system]
        lines.append(f"| {name} | {metric(metrics['intent_accuracy'])} | {metric(metrics['macro_f1'])} | {metric(metrics['escalation_recall'])} |")
    lines += ['', 'Paired bootstrap intervals and disagreement tests for routing/classification are retained in the full `summary.json`. Counts and point estimates here are descriptive, not proof of a population-wide gain.', '',
        '## Fixed acceptance gates', '', '| Gate | Result |', '|---|---|']
    lines += [f"| {name.replace('_', ' ')} | {'PASS' if passed else 'FAIL'} |" for name, passed in run['gates'].items()]
    lines += ['', run['decision'], '', data['review_note'], '',
        '## Development history', '', '| Run | Reference auto / useful / misses | Quality auto / useful / misses | Balanced auto / useful / misses | Technical gates |', '|---|---|---|---|---|']
    for experiment in data['experiments'][:-1]:
        cells = [f"{experiment['counts'][s]['automatic']} / {experiment['counts'][s]['useful_automatic']} / {experiment['counts'][s]['missed_escalations']}" for s in NAMES]
        lines.append(f"| {experiment['id']} (n={experiment['n']}) | " + ' | '.join(cells) + f" | {'PASS' if experiment['technical_gates_pass'] else 'FAIL'} |")
    lines += ['', 'Development examples were inspected and used to revise the candidate. Their scores are regression evidence. The confirmation sample excluded previous sampled cases, overlapping conversations and near-duplicates; the chosen code was frozen before confirmation inference. No tuning follows those results.', '',
        'See [design and current-source references](BALANCED_DESIGN.md), the exact [confirmation acceptance](../results/balanced_confirmation/ACCEPTANCE.json), and [prior quality experiment](QUALITY_ACCEPTANCE.md).', '',
        '## Reproduce without API calls', '', '```bash']
    lines += [f'python analysis_tools/reproduce_balanced.py --experiment results/{name}' for name in RUNS]
    lines += ['python analysis_tools/publish_balanced.py --check', '```', '',
        'The verifier binds source snapshots, labels, receipts, paired metrics, runtime, complete blind review context, scores and acceptance gates. Offline verification makes zero model calls.', '']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    data = publication()
    serialized = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    for name, content in [('results/published/balanced.json', serialized),
                          ('ui/public/data/balanced.json', serialized),
                          ('docs/BALANCED_ACCEPTANCE.md', markdown(data))]:
        path = Paths.ROOT / name
        if args.check:
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                raise ValueError('Stale balanced publication: ' + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8', newline='\n')
    print('Balanced report and dashboard publication match the accepted evidence')


if __name__ == '__main__':
    main()
