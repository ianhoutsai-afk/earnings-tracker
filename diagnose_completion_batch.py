import json,hashlib,re,time
from pathlib import Path
from lxml import html
from official_sync import fetch_sec
from official_sources import _text,_local,_contract_revenue_total,REVENUE_TAGS
report=json.loads(Path('_diagnostics/report.json').read_text())
root=Path('_diagnostics/sources');root.mkdir(exist_ok=True)
index=[]
for r in report:
 t=r['ticker']
 if t in ('SATS','AES'):continue
 f=r['filings'][0]
 sources=[('primary',f['url'])]
 if t in ('AAPL','AMD','AMZN','ANET','ABT','JNJ','ORCL','LIN','SLB','WTW','PPG','AMCR','CCL','ARE','COIN','ON','CAG','MNST','USB','FCX','FICO','BAX','PRU'):
  sources += [('release',f['exhibits'][0]['url'])] if f['exhibits'] else []
 for kind,url in sources:
  body=fetch_sec(url);name=t+'-'+kind+'.html'
  (root/name).write_bytes(body)
  index.append({'file':name,'sourceUrl':url,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body)})
 if t in ('AMZN','ADP','JNJ','ISRG','INTC','ANET') and 'inline' in r:
  body=fetch_sec(r['inline']['url']);tree=html.fromstring(body);facts=[]
  for n in tree.iter():
   if n.get('name','').lower() not in {v.lower() for v in REVENUE_TAGS}:continue
   rows=n.xpath('ancestor::tr')
   row=' '.join(_text(rows[-1]).split()) if rows else ''
   if not re.match('(?i)(?:total |net |sales to|revenu)',row):continue
   ancestors=[]
   for a in list(n.iterancestors())[:8]:
    siblings=[];prev=a.getprevious()
    for i in range(5):
     if prev is None:break
     siblings.append({'tag':str(prev.tag),'text':' '.join(_text(prev).split())[:700]})
     prev=prev.getprevious()
    ancestors.append({'tag':str(a.tag),'text':(a.text or '')[:120],'previous':siblings})
   facts.append({'tag':n.get('name'),'context':n.get('contextref'),'row':row[:400],'acceptedTotal':_contract_revenue_total(n),'ancestors':ancestors})
   if len(facts)>=2:break
  (root/(t+'-inline-diagnostic.json')).write_text(json.dumps({'sourceUrl':r['inline']['url'],'facts':facts},indent=2))
Path('_diagnostics/source-index.json').write_text(json.dumps(index,indent=2))
print(json.dumps({'files':len(index),'bytes':sum(r['bytes'] for r in index)}))
