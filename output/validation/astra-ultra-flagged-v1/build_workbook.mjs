import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createRequire } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

// Resolve only the bundled Artifact Tool through the task's temporary junction.
const runtimeDir = path.join(os.tmpdir(), 'cadence-astra-ultra-flagged-workbook');
const require = createRequire(path.join(runtimeDir, 'bootstrap.mjs'));
const { Workbook, SpreadsheetFile, FileBlob } = await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const outputDir = path.dirname(fileURLToPath(import.meta.url));
const outputPath = path.join(outputDir, 'Cadence-Astra-Ultra-Review.xlsx');
const sourcePath = path.join(outputDir, 'review_data.json');
const checkpoint = async (status, detail) => fs.writeFile(path.join(outputDir,'WORKBOOK_STATE.md'),
  `# Workbook state\n\nUpdated: ${new Date().toISOString()}\n\nStatus: ${status}\n\n${detail}\n\nThe artifact operation marker ran successfully exactly once before authoring. Do not run it again.\n`, 'utf8');
const raw = JSON.parse(await fs.readFile(sourcePath,'utf8'));
const schemas = [['Confirmation','confirmation',35],['Challenge','challenge',20]];
const labelKeys = ['intent','secondary_intent','should_escalate','escalation_reason_code','sentiment'];
const headers = ['Case ID','Source text','Scenario setup','AI disposition','Changed label fields','Human review status','Prior intent','Ultra intent','Prior secondary intent','Ultra secondary intent','Prior should escalate','Ultra should escalate','Prior escalation reason','Ultra escalation reason','Prior sentiment','Ultra sentiment','Ultra rationale','Question resolution','Remaining question','Requires human decision','Ultra confidence','Flagged question','Human reviewer','Human reviewed at','Human notes','Prior rationale','Prior confidence','Acceptance review findings','Review source','Model','Reasoning effort','AI reviewer','AI reviewed at (UTC)','Human verified'];
const widths = [17,68,43,22,27,24,31,31,31,31,20,20,29,29,18,18,85,85,70,23,18,90,26,27,60,75,19,120,18,25,20,38,39,19];
const statuses = ['Pending','Approved','Corrected','Needs discussion'];
const C = {charcoal:'#26322E',green:'#267747',deepGreen:'#245B3C',paleGreen:'#EDF5EF',amber:'#FFF4CE',ink:'#26322E',muted:'#58665F',line:'#DDE5DF',light:'#F5F7F5',white:'#FFFFFF'};
const col = i => {let value=i+1,result='';while(value){value--;result=String.fromCharCode(65+value%26)+result;value=Math.floor(value/26);}return result;};
const textJSON = value => value === null || value === undefined ? '' : typeof value === 'object' ? (Object.keys(value).length ? JSON.stringify(value,null,2) : '') : String(value);
const findingsJSON = value => Array.isArray(value) && value.length ? JSON.stringify(value) : '';
const literal = value => typeof value==='string' && value.startsWith('=') ? `'${value}` : value ?? '';
const ids = new Set();
if(raw.metadata.review_source!=='ai'||raw.metadata.model!=='gpt-6-astra'||raw.metadata.reasoning_effort!=='ultra'||raw.metadata.human_validation_complete!==false||raw.metadata.candidate_inference_run!==false) throw new Error('Invalid packet provenance');
for(const [,key,count] of schemas){
  if(raw[key]?.length!==count) throw new Error(`Expected ${count} ${key} rows`);
  for(const r of raw[key]){
    if(ids.has(r.id)) throw new Error(`Duplicate ID ${r.id}`); ids.add(r.id);
    const u=r.ultra_review;
    if(!u||u.id!==r.id||u.review_source!=='ai'||u.model!=='gpt-6-astra'||u.reasoning_effort!=='ultra'||u.human_verified!==false) throw new Error(`Invalid AI provenance for ${r.id}`);
    if(r.partition!==key||r.human_review_status!=='Pending'||r.human_reviewer!==''||r.human_reviewed_at!==''||r.human_notes!=='') throw new Error(`Invalid human/source fields ${r.id}`);
    if(!['confirmed','revised','needs_discussion'].includes(u.disposition)||!['high','medium','low'].includes(u.confidence)||typeof u.requires_human_decision!=='boolean') throw new Error(`Invalid AI decision ${r.id}`);
    const actualChanges=labelKeys.filter(k=>r.prior_ai_proposal[k]!==u.labels[k]);
    if(JSON.stringify([...actualChanges].sort())!==JSON.stringify([...u.changed_fields].sort())) throw new Error(`Changed fields mismatch ${r.id}`);
    if(u.requires_human_decision ? !u.remaining_question : u.remaining_question!=='') throw new Error(`Question status mismatch ${r.id}`);
    if(Number.isNaN(Date.parse(u.reviewed_at))||!/(Z|\+00:00)$/.test(u.reviewed_at)) throw new Error(`Invalid actual UTC review time ${r.id}`);
  }
}
const matrixFor = rows => rows.map(r=>{
  const p=r.prior_ai_proposal,u=r.ultra_review,l=u.labels;
  return [r.id,r.text,textJSON(r.scenario_setup),u.disposition,u.changed_fields.join(', '),r.human_review_status,p.intent,l.intent,p.secondary_intent,l.secondary_intent,p.should_escalate,l.should_escalate,p.escalation_reason_code,l.escalation_reason_code,p.sentiment,l.sentiment,u.rationale,u.question_resolution,u.remaining_question,u.requires_human_decision,u.confidence,r.flagged_question,r.human_reviewer,r.human_reviewed_at,r.human_notes,r.prior_rationale,r.prior_confidence,findingsJSON(r.acceptance_review_findings),u.review_source,u.model,u.reasoning_effort,u.reviewer,`'${u.reviewed_at}`,u.human_verified].map(literal);
});
const estimateLines=(value,width)=>String(value??'').split(/\r?\n/).reduce((n,line)=>n+Math.max(1,Math.ceil(line.length/Math.max(10,Math.floor(width*.94)))),0);
const workbook=Workbook.create();
const layout=[];
for(const [name,key,count] of schemas){
  const sheet=workbook.worksheets.add(name),first=9,last=first+count-1;
  sheet.tabColor=C.green; sheet.showGridLines=false;
  sheet.getRange(`A1:AH${last}`).format={font:{name:'Arial',size:11,color:C.ink},verticalAlignment:'center'};
  widths.forEach((width,i)=>{sheet.getRange(`${col(i)}1:${col(i)}${last}`).format.columnWidth=width;});
  sheet.getRange('A1:AH1').format.rowHeight=10;
  sheet.getRange('A2').values=[[`Cadence Astra Ultra review — ${name}`]];
  sheet.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:C.charcoal};
  sheet.getRange('A2:AH2').format.rowHeight=27;
  sheet.getRange('A2:AH2').format.borders={bottom:{style:'thin',color:C.green}};
  sheet.getRange('A3').values=[['AI review only. GPT-6 Astra (gpt-6-astra), reasoning effort: ultra. Human validation remains Pending.']];
  sheet.getRange('A4').values=[['Prior and Ultra proposals are recorded separately. Amber cells record human review; put any label corrections in Human notes.']];
  sheet.getRange('A5').values=[['Complete human review only after checking labels, recording the reviewer and review time, and explaining corrections or unresolved questions.']];
  sheet.getRange('A6').values=[[`Source: review_data.json (${key}) and inputs/${key==='confirmation'?'confirmation_01.jsonl + confirmation_02.jsonl':'challenge_01.jsonl'}. ${count} flagged cases.`]];
  sheet.getRange('A3:AH6').format={font:{name:'Arial',size:11,color:C.muted},rowHeight:21,wrapText:false};
  sheet.getRange('A7:AH7').format.rowHeight=9;
  sheet.getRange('A8:AH8').values=[headers];
  const matrix=matrixFor(raw[key]);
  sheet.getRange(`A${first}:AH${last}`).values=matrix;
  const table=sheet.tables.add(`A8:AH${last}`,true,`${name}UltraReview`);
  table.showFilterButton=true;table.style='TableStyleLight1';
  sheet.getRange(`A${first}:AH${last}`).format={wrapText:true,verticalAlignment:'top',horizontalAlignment:'left'};
  // Text formatting and an escaped ISO string prevent the runtime from rounding provenance timestamps.
  for(const column of ['A','B','C','AG']) sheet.getRange(`${column}${first}:${column}${last}`).setNumberFormat('@');
  sheet.getRange(`A${first}:A${last}`).format.font={name:'Arial',size:11,bold:true,color:C.charcoal};
  sheet.getRange(`D${first}:E${last}`).format.fill=C.paleGreen;
  for(const column of ['H','J','L','N','P']) sheet.getRange(`${column}${first}:${column}${last}`).format.fill=C.paleGreen;
  sheet.getRange(`Q${first}:U${last}`).format.fill=C.paleGreen;
  sheet.getRange(`F${first}:F${last}`).format.fill=C.amber;
  sheet.getRange(`W${first}:Y${last}`).format.fill=C.amber;
  sheet.getRange(`Z${first}:AH${last}`).format.fill=C.light;
  sheet.getRange(`X${first}:X${last}`).setNumberFormat('yyyy-mm-dd hh:mm');
  for(const column of ['C','F','P','V','Y','AB']) sheet.getRange(`${column}${first}:${column}${last}`).format.borders={right:{style:'thin',color:C.line}};
  sheet.getRange('A8:AH8').format={fill:C.charcoal,font:{name:'Arial',size:11,bold:true,color:C.white},wrapText:true,horizontalAlignment:'center',verticalAlignment:'center',rowHeight:45,borders:{insideVertical:{style:'thin',color:C.white}}};
  for(const range of ['D8:E8','H8','J8','L8','N8','P8:U8']) sheet.getRange(range).format.fill=C.deepGreen;
  for(const range of ['F8','W8:Y8']) sheet.getRange(range).format.fill=C.green;
  sheet.getRange(`F${first}:F${last}`).dataValidation={rule:{type:'list',values:statuses}};
  const statusRange=sheet.getRange(`F${first}:F${last}`);
  for(const status of ['Approved','Corrected']) statusRange.conditionalFormats.add('containsText',{text:status,format:{fill:'#DDEFE2',font:{color:'#1B6134'}}});
  statusRange.conditionalFormats.add('containsText',{text:'Needs discussion',format:{fill:'#FBE4DD',font:{color:'#913D27',bold:true}}});
  sheet.getRange(`D${first}:D${last}`).conditionalFormats.add('containsText',{text:'needs_discussion',format:{fill:'#FBE4DD',font:{color:'#913D27',bold:true}}});
  sheet.getRange(`D${first}:D${last}`).conditionalFormats.add('containsText',{text:'revised',format:{fill:'#E4EEDD',font:{color:'#245B3C',bold:true}}});
  let maxRowHeight=0;
  for(let i=0;i<matrix.length;i++){
    const lines=Math.max(...matrix[i].map((v,j)=>estimateLines(v,widths[j])));
    const height=Math.max(96,lines*15+18);
    if(height>409) throw new Error(`${matrix[i][0]} needs ${height}pt; enlarge long-text column widths`);
    sheet.getRange(`A${first+i}:AH${first+i}`).format.rowHeight=height;maxRowHeight=Math.max(maxRowHeight,height);
  }
  sheet.freezePanes.freezeRows(8);sheet.freezePanes.freezeColumns(1);
  layout.push({sheet:name,partition:key,count,table:`A8:AH${last}`,first,last,freeze:'B9',maxRowHeight,columns:headers.map((header,i)=>({column:col(i),header,width:widths[i]}))});
}
await checkpoint('Built in memory','55 exact consolidated records populated. Recalculation, Artifact Tool inspection, export, timestamp fidelity verification, renders and independent saved-file QA remain.');
workbook.recalculate();
const inspections=[];
for(const [name] of schemas) inspections.push((await workbook.inspect({kind:'table',range:`${name}!A8:F10`,include:'values,formulas',tableMaxRows:3,tableMaxCols:6,maxChars:5000})).ndjson);
const errors=await workbook.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:20},summary:'Final formula error scan',maxChars:2500});
await fs.writeFile(path.join(outputDir,'workbook_inspection.txt'),inspections.join('\n')+'\n'+errors.ndjson,'utf8');
await (await SpreadsheetFile.exportXlsx(workbook)).save(outputPath);
// Public Artifact Tool text export retains the protective apostrophe for ISO strings.
// Repair only that known serialization defect, leaving every other ZIP member unchanged.
const timestampFix=spawnSync('C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',['-c',String.raw`
import json, os, re, sys, zipfile
from xml.sax.saxutils import escape, unescape
target, source = sys.argv[1:]
with open(source, encoding='utf-8') as stream: data=json.load(stream)
parts={'xl/worksheets/sheet1.xml':data['confirmation'],'xl/worksheets/sheet2.xml':data['challenge']}
patched=0
temporary=target+'.tmp'
with zipfile.ZipFile(target,'r') as original,zipfile.ZipFile(temporary,'w') as result:
 for item in original.infolist():
  payload=original.read(item.filename)
  if item.filename in parts:
   xml=payload.decode('utf-8')
   for row,record in enumerate(parts[item.filename],9):
    address='AG'+str(row)
    pattern=r'(<(?:\w+:)?c\b[^>]*\br="'+address+r'"[^>]*>)(.*?)(</(?:\w+:)?c>)'
    match=re.search(pattern,xml,re.DOTALL)
    if not match or 't="str"' not in match.group(1): raise RuntimeError('Expected string '+address)
    value=re.search(r'<(?:\w+:)?v>(.*?)</(?:\w+:)?v>',match.group(2),re.DOTALL)
    stamp=record['ultra_review']['reviewed_at']
    if not value or unescape(value.group(1))!="'"+stamp: raise RuntimeError('Unexpected provenance '+address)
    body=match.group(2)
    replacement=match.group(1)+body[:value.start(1)]+escape(stamp)+body[value.end(1):]+match.group(3)
    xml=xml[:match.start()]+replacement+xml[match.end():]
    patched+=1
   payload=xml.encode('utf-8')
  result.writestr(item,payload)
if patched!=55: raise RuntimeError('Expected 55 exact timestamps')
os.replace(temporary,target)
print(json.dumps({'literal_timestamp_cells_preserved':patched}))
`,outputPath,sourcePath],{encoding:'utf8'});
if(timestampFix.status!==0) throw new Error(`Timestamp fidelity repair failed: ${timestampFix.stderr}`);
await fs.writeFile(path.join(outputDir,'workbook_timestamp_fidelity.json'),timestampFix.stdout,'utf8');
await fs.writeFile(path.join(outputDir,'workbook_layout.json'),JSON.stringify({sheets:layout,total:ids.size,headers},null,2)+'\n');
await checkpoint('Exported','Cadence-Astra-Ultra-Review.xlsx exported. Exact UTC timestamp strings preserved. Artifact Tool source/label/review/human-field renders and independent saved-file QA remain.');
const reopened=await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
await fs.writeFile(path.join(outputDir,'workbook_reopen.txt'),(await reopened.inspect({kind:'workbook,sheet,table',maxChars:4500,tableMaxRows:2,tableMaxCols:3})).ndjson,'utf8');
for(const [name] of schemas){
  for(const [suffix,range] of [['source','A1:F10'],['labels','G8:P10'],['reasoning','Q8:V10'],['human','W8:Y10'],['provenance','AC8:AH10']]){
    const preview=await reopened.render({sheetName:name,range,scale:1,format:'png'});
    await fs.writeFile(path.join(outputDir,`workbook_${name.toLowerCase()}_${suffix}.png`),new Uint8Array(await preview.arrayBuffer()));
  }
}
await checkpoint('Artifact checks complete','Workbook exported and reopened through Artifact Tool. Both sheets rendered in source, label, reasoning, human, and provenance views. Independent saved-file QA and visual image inspection remain. Native Excel interaction has not been tested.');
console.log(JSON.stringify({output:outputPath,rows:ids.size,sheets:layout.map(({sheet,count,table,freeze,maxRowHeight})=>({sheet,count,table,freeze,maxRowHeight})),checks:'Artifact Tool inspect, error scan, export, reimport, 10 rendered views'}));
