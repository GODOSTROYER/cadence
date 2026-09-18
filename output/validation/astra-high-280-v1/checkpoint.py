"""Persist labeling progress without displaying held-out customer text."""
import json
from datetime import UTC, datetime
from pathlib import Path

folder = Path(__file__).resolve().parent
manifest = json.loads((folder / 'MANIFEST.json').read_text(encoding='utf-8'))
progress = []
for batch in manifest['batches']:
    path = folder / 'drafts' / (batch['name'] + '.jsonl')
    count, errors = 0, []
    if path.exists():
        for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if not line.strip():
                continue
            try:
                json.loads(line)
                count += 1
            except json.JSONDecodeError:
                errors.append(line_number)
    progress.append({'batch':batch['name'], 'expected':batch['n'], 'saved_rows':count,
                     'complete_record':(folder/'drafts'/(batch['name']+'.COMPLETE.json')).exists(),
                     'invalid_json_lines':errors})
reviews = []
for name in ('confirmation_001_150.json', 'confirmation_151_200_and_challenge.json',
             'confirmation_001_150.final.json', 'confirmation_151_200_and_challenge.final.json'):
    path=folder/'reviews'/name
    if path.exists():
        item=json.loads(path.read_text(encoding='utf-8'))
        reviews.append({'file':name,'stage':'final' if '.final.' in name else 'initial',
                        'status':item.get('status'),'reviewed_count':item.get('reviewed_count'),
                        'findings':len(item.get('findings',[]))})
record = {'saved_at':datetime.now(UTC).isoformat(),'status':'AI drafts; human validation pending; inference not run',
          'progress':progress,'saved_rows':sum(row['saved_rows'] for row in progress),
          'independent_reviews':reviews,
          'consolidated_data_exists':(folder/'review_data.json').exists(),
          'workbook_exists':(folder/'Cadence-Label-Validation.xlsx').exists(),
          'acceptance_exists':(folder/'ACCEPTANCE.json').exists(),
          'resume_instructions':'Read output/analysis/ACTIVE_LABELING_STATE.md; resume incomplete batches only. Preserve source samples, original draft judgments and all human-pending fields.'}
temporary=folder/'STATE.json.tmp'
temporary.write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8',newline='\n')
temporary.replace(folder/'STATE.json')
print(json.dumps(record))
