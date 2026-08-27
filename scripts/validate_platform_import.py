#!/usr/bin/env python3
import json,re
from pathlib import Path
from collections import Counter

ROOT=Path('.')
SRC=ROOT/'indices/platform-import.ndjson'
REP=ROOT/'manifests/platform-import'
REP.mkdir(parents=True,exist_ok=True)

ALLOWED={
 'حكم قضائي','حكم قضائي دولي','تعميم','قرار','مبدأ قضائي','سابقة قضائية',
 'نظام أو لائحة','مرجع قانوني','بحث قانوني','وثيقة قانونية'
}

def nonempty(o,k):
    return bool(str(o.get(k,'')).strip())

def any_nonempty(o,ks):
    return any(nonempty(o,k) for k in ks)

errors=[]
warnings=[]
counts=Counter()
ids=set(); text_hashes=set()
records=0

if not SRC.exists() or SRC.stat().st_size==0:
    raise SystemExit('missing or empty indices/platform-import.ndjson')

for n,line in enumerate(SRC.open(encoding='utf-8'),1):
    line=line.strip()
    if not line:
        errors.append({'line':n,'reason':'blank line'})
        continue
    try:
        o=json.loads(line)
    except Exception as e:
        errors.append({'line':n,'reason':'invalid json','detail':str(e)})
        continue
    records+=1
    typ=str(o.get('documentType','')).strip()
    counts[typ or 'غير مصنف']+=1
    for k in ('id','documentType','title','textChecksum'):
        if not nonempty(o,k): errors.append({'line':n,'id':o.get('id'),'reason':f'missing {k}'})
    if typ not in ALLOWED:
        warnings.append({'line':n,'id':o.get('id'),'reason':'unrecognized documentType','value':typ})
    oid=o.get('id')
    if oid in ids: errors.append({'line':n,'id':oid,'reason':'duplicate id'})
    ids.add(oid)
    th=o.get('textChecksum')
    if th and not re.fullmatch(r'[0-9a-f]{64}',str(th)):
        errors.append({'line':n,'id':oid,'reason':'invalid textChecksum'})
    if th in text_hashes:
        warnings.append({'line':n,'id':oid,'reason':'textChecksum collision remained after dedup'})
    if th: text_hashes.add(th)

    if typ in ('حكم قضائي','حكم قضائي دولي'):
        if not any_nonempty(o,('deedNumber','judgmentNumber','lawsuitNumber')):
            warnings.append({'line':n,'id':oid,'reason':'judgment has no deed/judgment/lawsuit number'})
        if not any_nonempty(o,('sourceFile','sourceUrl')):
            errors.append({'line':n,'id':oid,'reason':'judgment has no source reference'})
    elif typ=='تعميم':
        if not any_nonempty(o,('circularNumber','sourceUrl','sourceFile')):
            errors.append({'line':n,'id':oid,'reason':'circular lacks number and source'})
    elif typ=='قرار':
        if not any_nonempty(o,('decisionNumber','sourceUrl','sourceFile')):
            warnings.append({'line':n,'id':oid,'reason':'decision lacks decision number/source'})
    elif typ in ('مبدأ قضائي','سابقة قضائية'):
        if not any_nonempty(o,('reference','sourceFile','sourceUrl')):
            errors.append({'line':n,'id':oid,'reason':'principle/precedent has no source reference'})

report={
 'valid':not errors,
 'records':records,
 'typeCounts':dict(sorted(counts.items())),
 'errorsCount':len(errors),
 'warningsCount':len(warnings),
 'errors':errors[:500],
 'warnings':warnings[:500]
}
(REP/'compatibility-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(REP/'compatibility-review.ndjson').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in warnings),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('errors','warnings')},ensure_ascii=False))
if errors:
    raise SystemExit(f'compatibility validation failed with {len(errors)} errors')
