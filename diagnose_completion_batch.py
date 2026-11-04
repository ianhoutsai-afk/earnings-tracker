"""Read-only source diagnostics; output stays on this isolated branch."""
import json,time,threading
from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from lxml import html
from official_sync import fetch_sec,_filings,_base,_exhibit_links
from official_sources import parse_earnings_release,parse_earnings_filing,parse_inline_quarter,_local,_text
from release_metrics import parse_release_quarter_metrics
TODAY=date(2026,11,4)
lock=threading.Lock(); last=[0.]
def fetch(url):
 with lock:
  pause=.16-(time.monotonic()-last[0])
  if pause>0:time.sleep(pause)
  last[0]=time.monotonic()
 return fetch_sec(url)
mapping=json.loads(Path('sp500_mapping.json').read_text())
history=json.loads(Path('historical_data.json').read_text())
selected=['AAPL','AMD','AMZN','GOOGL','ABT','ANET','JNJ','ADP','ISRG','INTC','V','MA','JPM','ORCL','LIN','CCL','AEP','ARE','CAG','VZ','PRU','ON','MNST','USB','FICO','COIN','BAX','NTAP','FCX','AMCR','SLB','WTW','PPG','SATS','AES']
def inspect(ticker):
 cik=mapping[ticker]['cik'].zfill(10)
 result={'ticker':ticker,'stored':history[ticker][-1] if history[ticker] else None,'filings':[]}
 try:
  submissions=json.loads(fetch('https://data.sec.gov/submissions/CIK'+cik+'.json'))
  filings=_filings(submissions,TODAY)
  candidates=sorted([f for f in filings if f['form']=='8-K' and '2.02' in f['items']],key=lambda f:f['filingDate'],reverse=True)
  for event in candidates[:2]:
   base=_base(cik,event); url=base+event['primaryDocument']
   doc=fetch(url); entry={'event':event,'url':url,'exhibits':[]}
   for link in _exhibit_links(doc,base)[:2]:
    exhibit=fetch(link); tree=html.fromstring(exhibit)
    text=' '.join(_text(tree).split())
    e={'url':link,'intro':text[:1800]}
    try:
     release=parse_earnings_release(exhibit,event['reportDate'],event['filingDate'],TODAY)
     e['release']=release
    except ValueError as exc:e['releaseError']=str(exc)
    try:e['filingRelease']=parse_earnings_filing(doc,event['reportDate'],event['filingDate'],TODAY,exhibit=exhibit)
    except ValueError as exc:e['filingError']=str(exc)
    e['tables']=[]
    for table in tree.xpath('//table'):
     if table.xpath('.//table'):continue
     tabletext=' '.join(_text(table).split())
     if ('diluted' in tabletext.lower() and ('revenu' in tabletext.lower() or 'sales' in tabletext.lower()) and len(tabletext)<22000):
      prev=table.getprevious()
      prefix=' '.join(_text(prev).split())[-500:] if prev is not None else ''
      e['tables'].append({'prefix':prefix,'text':tabletext[:12000]})
    entry['exhibits'].append(e)
   tree=html.fromstring(doc); text=' '.join(_text(tree).split()); pos=text.lower().find('item 2.02')
   entry['publication']=text[pos:pos+2600]
   result['filings'].append(entry)
  # Latest stored explicit financial filing, to diagnose tagged revenue rejection.
  official=json.loads(Path('official_history.json').read_text())
  own=sorted([r for r in official if r['ticker']==ticker and r.get('secUrl')],key=lambda r:r['periodEnd'],reverse=True)
  if own:
   r=own[0];doc=fetch(r['secUrl']);tree=html.fromstring(doc)
   result['inline']={'url':r['secUrl'],'end':r['periodEnd'],'parsed':parse_inline_quarter(doc,r['periodEnd'],cik)}
   facts=[]
   for node in tree.iter():
    tag=node.get('name','').lower()
    if _local(node)=='nonfraction' and ('revenue' in tag or 'sales' in tag) and len(facts)<12:
     tables=node.xpath('ancestor::table')
     rows=node.xpath('ancestor::tr')
     table=tables[-1] if tables else None
     prev=table.getprevious() if table is not None else None
     facts.append({'tag':tag,'value':_text(node),'context':node.get('contextref'),'row':' '.join(_text(rows[-1]).split())[:350] if rows else None,'tableStart':' '.join(_text(table).split())[:650] if table is not None else None,'prefix':' '.join(_text(prev).split())[-650:] if prev is not None else None})
   result['inline']['facts']=facts
 except Exception as exc:result['error']=type(exc).__name__+':'+str(exc)
 print('Diagnosed '+ticker,flush=True)
 return result
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(inspect,selected))
Path('_diagnostics').mkdir(exist_ok=True)
Path('_diagnostics/report.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'diagnosed':len(results),'errors':[r['ticker'] for r in results if 'error' in r]}))
