"""Read-only diagnosis of missing quarterly revenue; no publication mutations."""
import json,hashlib,time
from pathlib import Path
from lxml import html
from official_sync import fetch_sec,decode_sec_body
from official_sources import parse_inline_quarter,_local,_text,_desc,_unique_text,_contract_revenue_total
records=json.loads(Path('official_history.json').read_text())
mapping=json.loads(Path('sp500_mapping.json').read_text())
targets=sorted([r for r in records if r.get('revenue') is None and r.get('epsGaapDiluted') is not None and r.get('secUrl')],key=lambda r:(r['periodEnd'],r['date']),reverse=True)
chosen=[];seen=set()
for r in targets:
 if r['ticker'] in seen:continue
 seen.add(r['ticker']);chosen.append(r)
 if len(chosen)==35:break
reports=[]
for r in chosen:
 url=r['secUrl'];cache=Path('.sec_cache/official')/(hashlib.sha256(url.encode()).hexdigest()+'.body')
 if cache.exists():body=decode_sec_body(cache.read_bytes())
 else:body=fetch_sec(url);time.sleep(.2)
 tree=html.fromstring(body)
 contexts={}
 for c in [n for n in tree.iter() if _local(n)=='context']:
  start=_unique_text(_desc(c,'startdate'));end=_unique_text(_desc(c,'enddate'))
  if start and end==r['periodEnd'] and not _desc(c,'segment') and not _desc(c,'scenario'):contexts[c.get('id')]={'start':start,'end':end,'entity':_unique_text(_desc(c,'identifier'))}
 item={'ticker':r['ticker'],'periodEnd':r['periodEnd'],'sourceUrl':url,'parsed':parse_inline_quarter(body,r['periodEnd'],mapping[r['ticker']]['cik']),'facts':[]}
 for n in tree.iter():
  if _local(n)!='nonfraction' or n.get('contextref') not in contexts:continue
  tag=n.get('name','').lower()
  if not ('revenue' in tag or 'salesrevenu' in tag):continue
  rows=n.xpath('ancestor::tr');tables=n.xpath('ancestor::table')
  if not rows or not tables:continue
  row=rows[-1];table=tables[-1]
  before=[]
  for cell in row.xpath('./td|./th'):
   if n is cell or any(c is n for c in cell.iter()):break
   before.append(_text(cell))
  prefixes=[];current=table
  for depth in range(3):
   prev=current.getprevious()
   for j in range(8):
    if prev is None:break
    text=' '.join(_text(prev).split())
    if text:prefixes.append({'tag':str(prev.tag),'text':text[:700]})
    if _local(prev)=='table':break
    prev=prev.getprevious()
   current=current.getparent()
   if current is None or _local(current) in ('body','html'):break
  item['facts'].append({'tag':n.get('name'),'value':_text(n),'scale':n.get('scale'),'sign':n.get('sign'),'format':n.get('format'),'unit':n.get('unitref'),'context':contexts[n.get('contextref')],'label':' '.join(' '.join(before).split()).strip(' :$'),'row':' '.join(_text(row).split())[:400],'tableStart':' '.join(_text(table).split())[:600],'prefixes':prefixes,'acceptedTotal':_contract_revenue_total(n)})
  if len(item['facts'])>=10:break
 reports.append(item)
 print('Inspected '+r['ticker'],flush=True)
Path('audit-150').mkdir(exist_ok=True)
Path('audit-150/diagnostic.json').write_text(json.dumps(reports,indent=2))
print(json.dumps({'issuers':len(reports)}))
