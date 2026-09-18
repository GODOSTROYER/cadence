"""Persist compact progress without changing review decisions."""
import json
from datetime import UTC, datetime
from pathlib import Path

folder = Path(__file__).resolve().parent
manifest = json.loads((folder / 'MANIFEST.json').read_text(encoding='utf-8'))
progress = []
for batch in manifest['batches']:
    path = folder / batch['output']
    saved = 0
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                json.loads(line)
                saved += 1
    progress.append({'batch': batch['name'], 'expected': batch['count'], 'saved': saved,
                     'complete': path.with_suffix('.COMPLETE.json').exists()})
state = {'saved_at': datetime.now(UTC).isoformat(), 'review_source': 'ai',
         'model': 'gpt-6-astra', 'reasoning_effort': 'ultra',
         'human_validation_complete': False, 'candidate_inference_run': False,
         'progress': progress, 'saved_rows': sum(r['saved'] for r in progress),
         'consolidated': (folder / 'review_data.json').exists(),
         'workbook': (folder / 'Cadence-Astra-Ultra-Review.xlsx').exists(),
         'acceptance': (folder / 'ACCEPTANCE.json').exists(),
         'resume': 'Read STATE.md and output/analysis/ACTIVE_LABELING_STATE.md. Preserve existing review rows and original 280-case packet.'}
temp = folder / 'STATE.json.tmp'
temp.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8', newline='\n')
temp.replace(folder / 'STATE.json')
print(json.dumps(state))
