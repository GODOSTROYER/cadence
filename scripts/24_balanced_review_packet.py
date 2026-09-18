"""Blind exact confirmation replies; aliases are deterministic and scores/labels are omitted."""
import random

from cadence.config import Paths
from cadence.eval.provenance import sha256
from cadence.eval.review import RUBRIC_VERSION, reply_hash
from cadence.utils.io import read_json, read_jsonl, write_json, write_jsonl


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--experiment', required=True)
    args = p.parse_args()
    directory = Paths.ROOT / args.experiment
    predictions = read_jsonl(directory / 'predictions.jsonl')
    rows = {(r['id'], r['system']): r for r in predictions}
    manifest = read_json(directory / 'manifest.json')
    if read_json(directory / 'status.json').get('status') != 'complete':
        raise ValueError('Complete the experiment before preparing a review packet')
    if len(rows) != len(predictions) or len(rows) != manifest['frozen']['n'] * 3:
        raise ValueError('Duplicate or incomplete predictions')
    if {s for _, s in rows} != {'agent', 'quality', 'balanced'}:
        raise ValueError('Unexpected systems')
    run = 'routing_dev-' + sha256(directory / 'manifest.json')[:12]
    packet, mapping = [], []
    for identity in sorted({i for i,s in rows}):
        if not all((identity,s) in rows for s in ('agent','quality','balanced')):
            raise ValueError('Every message must have all three systems')
        systems = ['agent','quality','balanced']
        random.Random('confirmation:'+identity).shuffle(systems)
        for alias,system in zip('ABC',systems,strict=True):
            r = rows[identity,system]
            shared = {'id':identity,'alias':alias,'run_id':run,'reply_hash':reply_hash(r['reply_draft']), 'rubric_version':RUBRIC_VERSION}
            packet.append({**shared,'text':r['input_text'],'reply_draft':r['reply_draft'],'evidence':r['evidence']})
            mapping.append({**shared,'system':system})
    write_jsonl(directory / 'blind_packet.jsonl',packet)
    write_json(directory / 'blind_mapping.json',mapping)
    print(f'Prepared {len(packet)} exact replies with names, decisions, scores and gold labels hidden')


if __name__ == '__main__':
    main()
