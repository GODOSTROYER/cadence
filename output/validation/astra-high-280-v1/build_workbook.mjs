import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

// Resolve only the bundled Artifact Tool through a temporary junction.
const runtimeDir = path.join(os.tmpdir(), 'cadence-astra-high-280-workbook');
const require = createRequire(path.join(runtimeDir, 'bootstrap.mjs'));
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const outputDir = path.dirname(fileURLToPath(import.meta.url));
const outputPath = path.join(outputDir, 'Cadence-Label-Validation.xlsx');
const statePath = path.join(outputDir, 'WORKBOOK_STATE.md');
const checkpoint = async (status, detail) => fs.writeFile(statePath,
  `# Workbook state\n\nUpdated: ${new Date().toISOString()}\n\nStatus: ${status}\n\n${detail}\n\nThe artifact operation marker ran successfully exactly once before authoring. Do not run it again.\n`, 'utf8');
const raw = JSON.parse(await fs.readFile(path.join(outputDir, 'review_data.json'), 'utf8'));
const schemas = [ ['Confirmation', 'confirmation', 200], ['Challenge', 'challenge', 80] ];
const intents = ['non_english','account_hacked_or_security','billing_or_charge','login_or_password','download_or_offline','metadata_or_artist_issue','playlist_or_library','content_or_availability','playback_or_app_bug','subscription_or_plan','feature_request_or_feedback','other'];
const reasons = ['billing_dispute','account_security','needs_account_lookup','high_frustration_or_churn','legal_or_safety','ambiguous_or_media_only','low_confidence','out_of_scope'];
const statuses = ['Pending','Approved','Corrected','Needs discussion'];
const headers = ['Case ID','Source text','Scenario setup','Review status','Intent','Secondary intent','Should escalate','Escalation reason code','Sentiment','Human notes','Astra rationale','Validation question','Confidence','Needs human attention','Annotator','Model','Reasoning effort','Labeled at (UTC)'];
const widths = [19,70,45,23,30,30,19,29,18,45,75,65,17,23,24,24,19,25];
const C = { charcoal:'#26322E', green:'#267747', deepGreen:'#245B3C', paleGreen:'#EDF5EF', amber:'#FFF4CE', ink:'#26322E', muted:'#58665F', line:'#DDE5DF', light:'#F5F7F5', white:'#FFFFFF' };
const ids = new Set();
for (const [,key,expected] of schemas) {
  if (!Array.isArray(raw[key]) || raw[key].length !== expected) throw new Error(`${key}: expected ${expected} rows`);
  for (const r of raw[key]) {
    for (const field of ['id','text','scenario_setup','intent','secondary_intent','should_escalate','escalation_reason_code','sentiment','notes','confidence','needs_human_attention','validation_question','annotator','model','reasoning_effort','labeled_at']) {
      if (!(field in r)) throw new Error(`${r.id}: missing ${field}`);
    }
    if (ids.has(r.id)) throw new Error(`Duplicate case ID ${r.id}`);
    ids.add(r.id);
    if (!intents.includes(r.intent)) throw new Error(`${r.id}: invalid intent`);
    if (r.secondary_intent && !intents.includes(r.secondary_intent)) throw new Error(`${r.id}: invalid secondary_intent`);
    if (r.escalation_reason_code && !reasons.includes(r.escalation_reason_code)) throw new Error(`${r.id}: invalid reason`);
    if (!['positive','neutral','frustrated','angry'].includes(r.sentiment)) throw new Error(`${r.id}: invalid sentiment`);
    if (!['high','medium','low'].includes(r.confidence)) throw new Error(`${r.id}: invalid confidence`);
    for (const field of ['should_escalate','needs_human_attention']) if (typeof r[field] !== 'boolean') throw new Error(`${r.id}: ${field} is not boolean`);
    if (Number.isNaN(Date.parse(r.labeled_at))) throw new Error(`${r.id}: invalid labeled_at`);
  }
}

// Artifact Tool treats = as a formula unless escaped. Other formula-like prefixes
// remain typed strings. The exported ZIP check verifies source equality and types.
const literal = v => typeof v === 'string' && v.startsWith('=') ? `'${v}` : (v ?? '');
const scenarioText = value => {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return Object.keys(value).length ? JSON.stringify(value,null,2) : '';
  return String(value);
};
const col = n => String.fromCharCode(65+n);
const estimateLines = (value, width) => {
  const capacity = Math.max(10, Math.floor(width * 1.1));
  return String(value ?? '').split(/\r?\n/).reduce((count, line) => count + Math.max(1, Math.ceil(line.length / capacity)), 0);
};
const workbook = Workbook.create();
const layout = [];
for (const [name,key,count] of schemas) {
  const sheet = workbook.worksheets.add(name);
  const last = 10 + count;
  sheet.tabColor = C.green;
  sheet.showGridLines = false;
  sheet.getRange(`A1:R${last}`).format = { font:{name:'Arial',size:11,color:C.ink}, verticalAlignment:'center' };
  for(let i=0;i<widths.length;i++) sheet.getRange(`${col(i)}1:${col(i)}${last}`).format.columnWidth = widths[i];
  if (name === 'Confirmation') sheet.getRange(`C1:C${last}`).format.columnWidth = 20;
  sheet.getRange('A1:R1').format.rowHeight = 10;
  sheet.getRange('A2').values = [[`Cadence label validation — ${name}`]];
  sheet.getRange('A2:R2').format.rowHeight = 27;
  sheet.getRange('A2').format.font = {name:'Arial',size:16,bold:true,color:C.charcoal};
  sheet.getRange('A2:R2').format.borders = {bottom:{style:'thin',color:C.green}};
  sheet.getRange('A3').values = [['AI drafts awaiting human validation. Read each source message and scenario, then confirm or correct the labels.']];
  sheet.getRange('A4').values = [['Set Review status to Approved, Corrected or Needs discussion. Use Human notes to explain changes or unresolved questions.']];
  sheet.getRange('A5').values = [['Enter Reviewer and Reviewed at before completing review. Edited labels stay here; original AI labels remain in drafts/.']];
  sheet.getRange('A3:R5').format.rowHeight = 20;
  sheet.getRange('A3:R5').format.font = {name:'Arial',size:11,color:C.muted};
  sheet.getRange('A3:R5').format.wrapText = false;
  sheet.getRange('A6:R6').format.rowHeight = 9;
  sheet.getRange('A7').values = [['Reviewer']];
  sheet.getRange('C7').values = [['Reviewed at']];
  sheet.getRange('B7').values = [['']];
  sheet.getRange('D7').values = [['']];
  sheet.getRange('B7').format.fill = C.amber;
  sheet.getRange('D7').format.fill = C.amber;
  sheet.getRange('D7').setNumberFormat('yyyy-mm-dd hh:mm');
  sheet.getRange('A7:R7').format.rowHeight = 25;
  sheet.getRange('A7').format.font.bold = true;
  sheet.getRange('C7').format.font.bold = true;
  sheet.getRange('A8').values = [[`${count} source cases`]];
  sheet.getRange('B8').values = [['Yellow cells are editable. Blank secondary intent means none.']];
  sheet.getRange('C8').values = [['Blank reason means no escalation.']];
  sheet.getRange('A8:R8').format.rowHeight = 23;
  sheet.getRange('A8:R8').format.font = {name:'Arial',size:11,color:C.muted};
  sheet.getRange('A9:R9').format.rowHeight = 8;
  sheet.getRange('A10:R10').values = [headers];
  const matrix = raw[key].map(r => [
    r.id,r.text,scenarioText(r.scenario_setup),'Pending',r.intent,r.secondary_intent,
    String(r.should_escalate),r.escalation_reason_code,r.sentiment,'',
    r.notes,r.validation_question,r.confidence,String(r.needs_human_attention),
    r.annotator,r.model,r.reasoning_effort,`'${r.labeled_at}`
  ].map(literal));
  sheet.getRange(`A11:R${last}`).values = matrix;
  const table = sheet.tables.add(`A10:R${last}`,true,`${name}Review`);
  table.showFilterButton = true;
  table.style = 'TableStyleLight1';
  sheet.getRange(`A11:R${last}`).format.wrapText = true;
  sheet.getRange(`A11:R${last}`).format.verticalAlignment = 'top';
  sheet.getRange(`A11:R${last}`).format.horizontalAlignment = 'left';
  // Preserve the original ISO timestamp's sub-millisecond provenance exactly.
  sheet.getRange(`A11:R${last}`).setNumberFormat('@');
  sheet.getRange(`D11:J${last}`).format.fill = C.amber;
  sheet.getRange(`K11:L${last}`).format.fill = C.paleGreen;
  sheet.getRange(`M11:R${last}`).format.fill = C.light;
  sheet.getRange(`A11:A${last}`).format.font = {name:'Arial',size:11,bold:true,color:C.charcoal};
  sheet.getRange(`A11:C${last}`).format.borders = {right:{style:'thin',color:C.line}};
  sheet.getRange(`J11:J${last}`).format.borders = {right:{style:'thin',color:C.line}};
  sheet.getRange(`L11:L${last}`).format.borders = {right:{style:'thin',color:C.line}};
  sheet.getRange('A10:R10').format = {
    fill:C.charcoal,font:{name:'Arial',size:11,bold:true,color:C.white},
    wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:35,
    borders:{insideVertical:{style:'thin',color:C.white}}
  };
  sheet.getRange('D10:J10').format.fill = C.green;
  sheet.getRange('K10:L10').format.fill = C.deepGreen;
  // Excel limits inline validation lists to 255 characters. Keep the complete
  // canonical choices in a compact reference block below each review table.
  const choicesHeader = last+4;
  const choicesFirst = last+5;
  sheet.getRange(`A${choicesHeader}:E${choicesHeader}`).values = [['Correction choices','Intent / secondary intent','Escalation reason code','Review status','Sentiment']];
  sheet.getRange(`A${choicesHeader}:E${choicesHeader}`).format = {font:{name:'Arial',size:11,bold:true,color:C.white},fill:C.charcoal,rowHeight:30,wrapText:true};
  const choiceRows = Array.from({length:13},(_,i)=>['',intents[i]??'',reasons[i]??'',statuses[i]??'',(['positive','neutral','frustrated','angry'][i])??'']);
  sheet.getRange(`A${choicesFirst}:E${choicesFirst+12}`).values = choiceRows;
  sheet.getRange(`A${choicesFirst}:E${choicesFirst+12}`).format = {font:{name:'Arial',size:11,color:C.muted},rowHeight:21,verticalAlignment:'center'};
  if (name === 'Confirmation') {
    sheet.getRange(`C${choicesFirst}:C${choicesFirst+12}`).format.wrapText = true;
    sheet.getRange(`A${choicesFirst}:E${choicesFirst+12}`).format.rowHeight = 36;
  }
  const validations = {
    D:{type:'list',values:statuses},
    E:{type:'list',formula1:`$B$${choicesFirst}:$B$${choicesFirst+11}`},
    F:{type:'list',formula1:`$B$${choicesFirst}:$B$${choicesFirst+12}`},
    G:{type:'list',values:['true','false']},
    H:{type:'list',formula1:`$C$${choicesFirst}:$C$${choicesFirst+8}`},
    I:{type:'list',values:['positive','neutral','frustrated','angry']}
  };
  for(const [letter,rule] of Object.entries(validations)) sheet.getRange(`${letter}11:${letter}${last}`).dataValidation = {rule};
  const statusRange = sheet.getRange(`D11:D${last}`);
  statusRange.conditionalFormats.add('containsText',{text:'Approved',format:{fill:'#DDEFE2',font:{color:'#1B6134'}}});
  statusRange.conditionalFormats.add('containsText',{text:'Corrected',format:{fill:'#DDEFE2',font:{color:'#1B6134'}}});
  statusRange.conditionalFormats.add('containsText',{text:'Needs discussion',format:{fill:'#FBE4DD',font:{color:'#913D27',bold:true}}});
  sheet.getRange(`N11:N${last}`).conditionalFormats.add('containsText',{text:'true',format:{font:{color:'#913D27',bold:true}}});
  let maxRowHeight = 0;
  for(let i=0;i<matrix.length;i++) {
    const lines = Math.max(...matrix[i].map((v,j)=> j === 17 ? 2 : estimateLines(v,widths[j])));
    const height = Math.max(84,lines*15+18);
    if(height>409) throw new Error(`${matrix[i][0]} needs ${height}pt row height. Increase the constrained text column width.`);
    sheet.getRange(`A${i+11}:R${i+11}`).format.rowHeight = height;
    maxRowHeight = Math.max(maxRowHeight,height);
  }
  sheet.freezePanes.freezeRows(10);
  sheet.freezePanes.freezeColumns(2);
  layout.push({sheet:name,count,table:`A10:R${last}`,freeze:'C11',maxRowHeight});
}
await checkpoint('Workbook built in memory', 'All 280 rows populated from review_data.json. Recalculation, visual renders, export, and independent ZIP/XML QA remain. Builder can be rerun from its saved file.');
workbook.recalculate();
const inspections = [];
for(const [name] of schemas) {
  inspections.push((await workbook.inspect({kind:'table',range:`${name}!A10:R12`,include:'values,formulas',tableMaxRows:3,tableMaxCols:18,maxChars:9000})).ndjson);
}
const errors = await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},summary:'Final formula error scan',maxChars:3000});
await fs.writeFile(path.join(outputDir,'workbook_inspection.txt'),inspections.join('\n')+'\n'+errors.ndjson,'utf8');
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
// The runtime auto-parses unescaped ISO strings, but retains the apostrophe in
// escaped strings on export. No exact-text setter is exposed by public help.
// Keep all workbook authoring in Artifact Tool; repair only this serialization
// defect in the 280 provenance cells, preserving their string type and precision.
const timestampFix = spawnSync('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe', ['-c', String.raw`
import json, os, re, sys, zipfile
from xml.sax.saxutils import escape, unescape
target, source = sys.argv[1:]
with open(source, encoding='utf-8') as stream:
    data = json.load(stream)
parts = {'xl/worksheets/sheet1.xml': data['confirmation'], 'xl/worksheets/sheet2.xml': data['challenge']}
patched = 0
temporary = target + '.tmp'
with zipfile.ZipFile(target, 'r') as original, zipfile.ZipFile(temporary, 'w') as result:
    for item in original.infolist():
        payload = original.read(item.filename)
        if item.filename in parts:
            xml = payload.decode('utf-8')
            for row, record in enumerate(parts[item.filename], 11):
                address = 'R' + str(row)
                pattern = r'(<(?:\w+:)?c\b[^>]*\br="' + address + r'"[^>]*>)(.*?)(</(?:\w+:)?c>)'
                match = re.search(pattern, xml, re.DOTALL)
                if not match or 't="str"' not in match.group(1):
                    raise RuntimeError('Expected literal string cell ' + address)
                value = re.search(r'<(?:\w+:)?v>(.*?)</(?:\w+:)?v>', match.group(2), re.DOTALL)
                if not value or unescape(value.group(1)) != "'" + record['labeled_at']:
                    raise RuntimeError('Unexpected timestamp before patch at ' + address)
                body = match.group(2)
                replacement = match.group(1) + body[:value.start(1)] + escape(record['labeled_at']) + body[value.end(1):] + match.group(3)
                xml = xml[:match.start()] + replacement + xml[match.end():]
                patched += 1
            payload = xml.encode('utf-8')
        result.writestr(item, payload)
if patched != 280:
    raise RuntimeError('Expected 280 repaired timestamp cells')
os.replace(temporary, target)
print(json.dumps({'literal_timestamp_cells_preserved': patched}))
`, outputPath, path.join(outputDir,'review_data.json')], {encoding:'utf8'});
if (timestampFix.status !== 0) throw new Error(`Timestamp serialization repair failed: ${timestampFix.stderr}`);
await fs.writeFile(path.join(outputDir,'workbook_timestamp_fidelity.json'),timestampFix.stdout,'utf8');
await fs.writeFile(path.join(outputDir,'workbook_layout.json'),JSON.stringify({sheets:layout,total:ids.size,headers},null,2)+'\n');
await checkpoint('Workbook exported', 'Cadence-Label-Validation.xlsx exported. All 280 rows populated; table inspections and formula-error scan saved. Representative renders and independent ZIP/XML QA remain.');
for(const [name] of schemas) {
  for(const [suffix,range] of [['source','A1:D13'],['review','D10:L12']]) {
    const preview = await workbook.render({sheetName:name,range,scale:1,format:'png'});
    await fs.writeFile(path.join(outputDir,`workbook_${name.toLowerCase()}_${suffix}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
}
// Read the saved export back through Artifact Tool in addition to ZIP/XML QA.
const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const reopenedSummary = await reopened.inspect({kind:'workbook,sheet,table',maxChars:5000,tableMaxRows:2,tableMaxCols:3});
await fs.writeFile(path.join(outputDir,'workbook_reopen.txt'),reopenedSummary.ndjson,'utf8');
await checkpoint('Export and Artifact Tool checks complete', 'Cadence-Label-Validation.xlsx exported and reopened successfully. Both sheets rendered in source and review regions. Independent ZIP/XML QA and visual image inspection remain.');
console.log(JSON.stringify({output:outputPath,rows:ids.size,sheets:layout,checks:'Artifact Tool inspect, error scan, export, reimport, four representative renders'}));
