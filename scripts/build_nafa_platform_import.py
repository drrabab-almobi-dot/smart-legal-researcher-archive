#!/usr/bin/env python3
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('.')
SRC = ROOT / 'indices' / 'nafa' / 'documents.ndjson'
TEXT_ROOT = ROOT / 'extracted' / 'nafa'
OUT = ROOT / 'indices' / 'nafa' / 'platform-import.ndjson'
BATCH_DIR = ROOT / 'platform-import' / 'nafa'
MAN = ROOT / 'manifests' / 'nafa'
MAN.mkdir(parents=True, exist_ok=True)

DIAC = re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]')
BIDI = re.compile(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]')
TRANS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')

def norm(s: str) -> str:
    s = unicodedata.normalize('NFKC', str(s or '')).translate(TRANS)
    s = BIDI.sub('', s)
    s = DIAC.sub('', s).replace('ـ','')
    return re.sub(r'\s+', ' ', s).strip()

def sha_text(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def first(patterns, text):
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            return norm(m.group(1))
    return ''

def verified_type(o, text):
    typ = norm(o.get('documentType'))
    if typ and typ != 'وثيقة قانونية':
        return typ
    t = text
    if re.search(r'رقم\s*(?:الصك|الحكم|القضية|الدعوى)', t): return 'حكم قضائي'
    if re.search(r'تعميم\s*(?:رقم)?', t): return 'تعميم'
    if re.search(r'قرار\s*(?:رقم)?', t): return 'قرار'
    if 'مبدأ قضائي' in t or 'المبادئ القضائية' in t: return 'مبدأ قضائي'
    if 'سابقة قضائية' in t or 'السوابق القضائية' in t: return 'سابقة قضائية'
    if 'لائحة' in t or re.search(r'\bنظام\b', t): return 'نظام أو لائحة'
    if 'بحث' in t or 'دراسة' in t: return 'بحث قانوني'
    return typ or 'مرجع قانوني'

records=[]
failures=[]
if not SRC.exists():
    raise SystemExit('missing indices/nafa/documents.ndjson')

for line_no, line in enumerate(SRC.open(encoding='utf-8'), 1):
    if not line.strip():
        continue
    try:
        o=json.loads(line)
        file_path = o.get('file') or o.get('sourceFile')
        p = ROOT / file_path if file_path else None
        extracted = ''
        if p and p.exists() and p.is_file():
            extracted = p.read_text(encoding='utf-8', errors='ignore')
        if not norm(extracted):
            failures.append({'line':line_no,'id':o.get('id'),'reason':'missing_extractedText','file':file_path})
            continue
        nt=norm(extracted)
        deed=norm(o.get('deedNumber')) or first([r'رقم\s*الصك\s*[:：\-]?\s*([0-9/\-]{3,30})'],nt)
        judgment=norm(o.get('judgmentNumber')) or first([r'رقم\s*الحكم\s*[:：\-]?\s*([0-9/\-]{3,30})'],nt)
        case=norm(o.get('lawsuitNumber') or o.get('caseNumber')) or first([r'رقم\s*(?:القضية|الدعوى)\s*[:：\-]?\s*([0-9/\-]{3,30})'],nt)
        circular=norm(o.get('circularNumber')) or first([r'تعميم\s*(?:رقم)?\s*[:：\-]?\s*([0-9/\-]{2,30})'],nt)
        decision=norm(o.get('decisionNumber')) or first([r'قرار\s*(?:رقم)?\s*[:：\-]?\s*([0-9/\-]{2,30})'],nt)
        court=norm(o.get('court')) or first([r'((?:المحكمة|محكمة)\s+[^\n،؛]{3,120})'],nt)
        circuit=norm(o.get('circuit')) or first([r'(الدائرة\s+[^\n،؛]{2,100})'],nt)
        date=norm(o.get('date')) or first([
            r'(1[34][0-9]{2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2})',
            r'([0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*1[34][0-9]{2})'
        ],nt)
        year=norm(o.get('year')) or first([r'\b(1[34][0-9]{2})\b'],date+' '+nt[:1000])
        rec={
            'id':o.get('id'),
            'documentType':verified_type(o,nt),
            'title':norm(o.get('title')) or nt[:220],
            'extractedText':extracted,
            'textChecksum':sha_text(nt),
            'sourceChecksum':norm(o.get('sourceChecksum')),
            'sourceUrl':o.get('sourceUrl') or '',
            'sourceFile':file_path or '',
            'deedNumber':deed,
            'judgmentNumber':judgment,
            'lawsuitNumber':case,
            'caseNumber':case,
            'circularNumber':circular,
            'decisionNumber':decision,
            'court':court,
            'circuit':circuit,
            'date':date,
            'year':year,
        }
        if not rec['id'] or not rec['title'] or not rec['sourceChecksum'] or not (rec['sourceUrl'] or rec['sourceFile']):
            failures.append({'line':line_no,'id':o.get('id'),'reason':'missing_required_metadata'})
            continue
        records.append(rec)
    except Exception as e:
        failures.append({'line':line_no,'reason':'parse_error','detail':str(e)[:300]})

# Confirmed duplicates: exact normalized text, exact source checksum, or confirmed deed/judgment number.
# Case number alone is review-only and never removes a record.
seen_text={}; seen_source={}; seen_deed={}; seen_judgment={}; seen_case={}
accepted=[]; confirmed=[]; candidates=[]
for r in records:
    hit=None; method=None
    if r['textChecksum'] in seen_text:
        hit=seen_text[r['textChecksum']]; method='exact_normalized_text'
    elif r['sourceChecksum'] and r['sourceChecksum'] in seen_source:
        hit=seen_source[r['sourceChecksum']]; method='exact_source_checksum'
    elif r['deedNumber'] and r['deedNumber'] in seen_deed:
        hit=seen_deed[r['deedNumber']]; method='confirmed_deed_number'
    elif r['judgmentNumber'] and r['judgmentNumber'] in seen_judgment:
        hit=seen_judgment[r['judgmentNumber']]; method='confirmed_judgment_number'
    if hit:
        confirmed.append({'duplicate':r['id'],'canonical':hit['id'],'method':method})
        continue
    if r['lawsuitNumber'] and r['lawsuitNumber'] in seen_case:
        candidates.append({'record_id':r['id'],'possible_canonical':seen_case[r['lawsuitNumber']]['id'],'reason':'case_number_only','value':r['lawsuitNumber'],'disposition':'kept_pending_review'})
    accepted.append(r)
    seen_text[r['textChecksum']]=r
    if r['sourceChecksum']: seen_source.setdefault(r['sourceChecksum'],r)
    if r['deedNumber']: seen_deed.setdefault(r['deedNumber'],r)
    if r['judgmentNumber']: seen_judgment.setdefault(r['judgmentNumber'],r)
    if r['lawsuitNumber']: seen_case.setdefault(r['lawsuitNumber'],r)

OUT.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in accepted),encoding='utf-8')
with (MAN/'duplicate-candidates.csv').open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['record_id','possible_canonical','reason','value','disposition']); w.writeheader(); w.writerows(candidates)
(MAN/'duplicates-confirmed.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in confirmed),encoding='utf-8')
(MAN/'platform-import-failures.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in failures),encoding='utf-8')

if BATCH_DIR.exists(): shutil.rmtree(BATCH_DIR)
BATCH_DIR.mkdir(parents=True,exist_ok=True)
for i in range(0,len(accepted),100):
    with gzip.open(BATCH_DIR/f'nafa-batch-{i//100+1:03d}.json.gz','wt',encoding='utf-8',compresslevel=9) as f:
        json.dump(accepted[i:i+100],f,ensure_ascii=False,separators=(',',':'))

counts=Counter(r['documentType'] for r in accepted)
summary={
    'sources_expected':804,
    'input_records_with_text':len(records),
    'import_records':len(accepted),
    'records_with_full_text':sum(1 for r in accepted if norm(r['extractedText'])),
    'records_without_text_excluded':sum(1 for x in failures if x.get('reason')=='missing_extractedText'),
    'confirmed_duplicates':len(confirmed),
    'duplicate_candidates_review':len(candidates),
    'failures':len(failures),
    'by_type':dict(sorted(counts.items())),
    'batches':(len(accepted)+99)//100,
}
(MAN/'platform-import-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

# Hard validation: every importable record must contain real extractedText and matching checksum.
errors=[]
for n,r in enumerate(accepted,1):
    if not norm(r.get('extractedText')): errors.append({'line':n,'id':r.get('id'),'reason':'empty extractedText'})
    elif sha_text(norm(r['extractedText'])) != r.get('textChecksum'): errors.append({'line':n,'id':r.get('id'),'reason':'textChecksum mismatch'})
    if r.get('documentType')=='وثيقة قانونية': errors.append({'line':n,'id':r.get('id'),'reason':'generic document type'})
    if not r.get('sourceChecksum'): errors.append({'line':n,'id':r.get('id'),'reason':'missing sourceChecksum'})
    if not (r.get('sourceUrl') or r.get('sourceFile')): errors.append({'line':n,'id':r.get('id'),'reason':'missing source reference'})
validation={'valid':not errors,'records':len(accepted),'errors':errors[:500]}
(MAN/'platform-import-validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
if errors:
    raise SystemExit(f'validation failed: {len(errors)} errors')
