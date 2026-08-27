#!/usr/bin/env python3
import json,re,hashlib,unicodedata,csv
from pathlib import Path
from collections import Counter,defaultdict
ROOT=Path('.')
OUT=ROOT/'indices/platform-import.ndjson'; REP=ROOT/'manifests/platform-import'; REP.mkdir(parents=True,exist_ok=True)
DIAC=re.compile(r'[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]'); BIDI=re.compile(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069]')
TRANS=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
def norm(s):
 s=unicodedata.normalize('NFKC',str(s or '')).translate(TRANS); s=BIDI.sub('',s); s=DIAC.sub('',s).replace('ـ',' '); return re.sub(r'\s+',' ',s).strip()
def sha(s): return hashlib.sha256(s.encode('utf-8')).hexdigest()
def first(pats,s):
 for p in pats:
  m=re.search(p,s,re.I)
  if m:return norm(m.group(1))
 return ''
def enrich(o,text=''):
 t=norm(text or o.get('text') or o.get('title') or '')
 o['documentType']=o.get('documentType') or o.get('type') or 'وثيقة قانونية'; o['title']=norm(o.get('title') or t[:180] or o.get('id'))
 o['deedNumber']=norm(o.get('deedNumber') or first([r'رقم\s*الصك\s*[:：]?\s*([0-9/\-]+)'],t))
 o['judgmentNumber']=norm(o.get('judgmentNumber') or first([r'رقم\s*الحكم\s*[:：]?\s*([0-9/\-]+)'],t))
 o['lawsuitNumber']=norm(o.get('lawsuitNumber') or o.get('caseNumber') or first([r'رقم\s*(?:القضية|الدعوى)\s*[:：]?\s*([0-9/\-]+)'],t))
 o['court']=norm(o.get('court') or first([r'((?:المحكمة|محكمة)\s+[^\n،؛]{3,100})'],t))
 o['circuit']=norm(o.get('circuit') or first([r'(الدائرة\s+[^\n،؛]{2,80})'],t))
 o['date']=norm(o.get('date') or first([r'(1[34][0-9]{2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2})',r'([0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*1[34][0-9]{2})'],t))
 o['year']=norm(o.get('year') or first([r'\b(1[34][0-9]{2})\b'],o['date']+' '+t[:500]))
 o['textChecksum']=sha(t); return o,t
records=[]; failures=[]
# Canonical existing registers: avoid collector mirror when base register exists.
for p in [ROOT/'indices/case-register.ndjson',ROOT/'indices/specialized-case-register.ndjson',ROOT/'indices/principle-precedent-register.ndjson',ROOT/'indices/nafa/documents.ndjson']:
 if not p.exists(): continue
 try:
  for n,line in enumerate(p.open(encoding='utf-8'),1):
   if not line.strip():continue
   try:o=json.loads(line); o['_register']=str(p); records.append(enrich(o)[0])
   except Exception as e: failures.append({'source':str(p),'line':n,'reason':str(e)})
 except Exception as e: failures.append({'source':str(p),'reason':str(e)})
# Extracted independent text files not already represented.
for p in sorted((ROOT/'extracted').rglob('*.txt')) if (ROOT/'extracted').exists() else []:
 try:
  text=p.read_text(encoding='utf-8',errors='ignore'); nt=norm(text)
  if len(nt)<40: continue
  typ='حكم قضائي' if ('حكم' in nt or 'قضية' in nt) else ('تعميم' if 'تعميم' in nt else ('قرار' if 'قرار' in nt else 'وثيقة قانونية'))
  o={'id':'text-'+sha(str(p))[:20],'documentType':typ,'title':nt[:180],'sourceFile':str(p),'sourceChecksum':sha(p.read_bytes().hex())}
  records.append(enrich(o,text)[0])
 except Exception as e: failures.append({'source':str(p),'reason':str(e)})
# MOJ circular register metadata, if generated.
cp=ROOT/'manifests/collector/circular-register.csv'
if cp.exists():
 try:
  for r in csv.DictReader(cp.open(encoding='utf-8')):
   o={'id':'moj-circular-'+r.get('portal_id',''),'documentType':'تعميم','title':r.get('subject',''),'sourceUrl':r.get('source_page',''),'sourceFile':r.get('file',''),'sourceChecksum':r.get('sha256',''),'circularNumber':norm(r.get('circular_number','')),'date':norm(r.get('circular_date',''))}; records.append(enrich(o)[0])
 except Exception as e: failures.append({'source':str(cp),'reason':str(e)})
# Dedup: confirmed only on exact strong keys; ambiguous collisions go to review.
seen=defaultdict(dict); accepted=[]; confirmed=[]; review=[]
for o in records:
 keys=[]
 for k in ['sourceUrl','sourceChecksum','textChecksum','deedNumber','judgmentNumber','lawsuitNumber','circularNumber','decisionNumber']:
  v=norm(o.get(k,''));
  if v: keys.append((k,v))
 hits=[]
 for k,v in keys:
  if v in seen[k]: hits.append((k,v,seen[k][v]))
 strong=[h for h in hits if h[0] in ('sourceUrl','sourceChecksum','textChecksum')]
 ids=[h for h in hits if h[0] not in ('sourceUrl','sourceChecksum','textChecksum')]
 if strong:
  confirmed.append({'duplicate':o.get('id'),'canonical':strong[0][2].get('id'),'matches':[x[0] for x in strong]}); continue
 if ids:
  review.append({'candidate':o.get('id'),'possibleCanonical':ids[0][2].get('id'),'matches':[x[0] for x in ids]})
 accepted.append(o)
 for k,v in keys: seen[k].setdefault(v,o)
OUT.parent.mkdir(parents=True,exist_ok=True)
with OUT.open('w',encoding='utf-8') as f:
 for o in accepted:
  o.pop('_register',None); f.write(json.dumps(o,ensure_ascii=False,separators=(',',':'))+'\n')
(REP/'duplicates-confirmed.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in confirmed),encoding='utf-8')
(REP/'review-candidates.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in review),encoding='utf-8')
(REP/'failures.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in failures),encoding='utf-8')
by=Counter(o.get('documentType','غير مصنف') for o in accepted)
summary={'input_records':len(records),'import_records':len(accepted),'by_type':dict(sorted(by.items())),'confirmed_duplicates':len(confirmed),'review_candidates':len(review),'failures':len(failures)}
(REP/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
# Importability tests
bad=[]; ids=set()
for n,line in enumerate(OUT.open(encoding='utf-8'),1):
 try:
  o=json.loads(line); assert o.get('id') and o.get('documentType') and o.get('title') and o.get('textChecksum');
  if o['id'] in ids: bad.append({'line':n,'reason':'duplicate id'})
  ids.add(o['id'])
 except Exception as e: bad.append({'line':n,'reason':str(e)})
(REP/'validation.json').write_text(json.dumps({'valid':not bad,'records':len(ids),'errors':bad[:100]},ensure_ascii=False,indent=2),encoding='utf-8')
if bad: raise SystemExit('platform import validation failed')
print(json.dumps(summary,ensure_ascii=False))
