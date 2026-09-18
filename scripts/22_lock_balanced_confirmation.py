"""Lock unseen confirmation cases, excluding all inspected samples and their conversation components."""
import random

from rapidfuzz import fuzz, process

from cadence.config import Paths
from cadence.eval.provenance import revision, sha256
from cadence.utils.io import read_jsonl, write_json, write_jsonl


def main():
    out = Paths.DATA / 'balanced_confirmation'
    if out.exists():
        raise ValueError('Confirmation already locked; never replace inspected cases')
    sources = [Paths.CANDIDATES, Paths.GOLDEN, Paths.ROOT / 'docs/taxonomy_calibration.jsonl',
               Paths.DATA / 'holdout/examples.jsonl', Paths.DATA / 'routing_dev/examples.jsonl', Paths.DATA / 'quality_confirmation/examples.jsonl']
    seen = [r for f in sources for r in read_jsonl(f)]
    threads = read_jsonl(Paths.THREADS)
    ids = {r['thread_id'] for r in seen}
    texts = [r['text'].casefold() for r in seen]
    tweets = {str(turn['tweet_id']) for t in threads if t['thread_id'] in ids for turn in t.get('turns', [])}
    candidates = sorted(threads, key=lambda r: r['thread_id'])
    random.Random(2026091704).shuffle(candidates)
    chosen = []
    for t in candidates:
        turns = {str(turn['tweet_id']) for turn in t.get('turns', [])}
        if t['thread_id'] in ids or t.get('language') != 'en' or not t.get('brand_replies') or turns & tweets:
            continue
        if process.extractOne(t['customer_text'].casefold(), texts, scorer=fuzz.ratio, score_cutoff=85):
            continue
        chosen.append({'id': f"b4_{len(chosen)+1:03d}", 'thread_id': t['thread_id'], 'text': t['customer_text'], 'split': 'confirmation'})
        texts.append(t['customer_text'].casefold())
        tweets.update(turns)
        if len(chosen) == 80:
            break
    if len(chosen) != 80:
        raise ValueError('Insufficient independent cases')
    write_jsonl(out / 'examples.jsonl', chosen)
    write_json(out / 'SAMPLE.lock.json', {'n': 80, 'seed': 2026091704, 'purpose': 'one-shot confirmation; AI labels before inference, never hand-labelled claim',
               'sampling': 'Seeded English brand-replied threads; exclude inspected sources, overlapping components and >=85 casefold fuzzy duplicates',
               'examples_sha256': sha256(out / 'examples.jsonl'), 'revision': revision(Paths.ROOT),
               'sources': {str(f.relative_to(Paths.ROOT)).replace('\\', '/'): sha256(f)
                           for f in [*sources, Paths.THREADS, Paths.ROOT / 'scripts/22_lock_balanced_confirmation.py']}})
    print('Locked 80 unseen messages; label independently before inference')


if __name__ == '__main__':
    main()
