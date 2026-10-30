"""Audit branch-only updates and verify replay without production writes."""
import json, subprocess, tempfile, shutil
from pathlib import Path
from official_sync import sync_all
from validate_quarterly_data import validate
def read(name):
 return json.loads(Path(name).read_text())
def metrics(row):
 return row.get('verificationStatus')=='official_verified' and row.get('epsBasis')=='GAAP diluted' and all(row.get(k) not in (None,'-') for k in ('eps_reported','revenue_reported'))
before={name:read(name) for name in ('historical_data.json','history_status.json','official_history.json')}
summary=sync_all('.',full=True)
assert summary['sourceHealthy'], 'Source failure; branch data stays unpublished'
validate()
after=read('historical_data.json')
assert set(before['historical_data.json'])==set(after)
changes=[]
for ticker,rows in after.items():
 old=before['historical_data.json'][ticker]
 if rows!=old:
  changes.append({'ticker':ticker,'beforeComplete':sum(map(metrics,old)),'afterComplete':sum(map(metrics,rows)), 'beforeLatest':old[0].get('periodEnd') if old else None,'afterLatest':rows[0].get('periodEnd') if rows else None})
 for prior in old:
  current=next((r for r in rows if r.get('periodEnd') and r.get('periodEnd')==prior.get('periodEnd')),None)
  if current:
   for field in ('eps_reported','revenue_reported'):
    if prior.get('verificationStatus')=='official_verified' and prior.get(field) not in (None,'-'):
     assert current.get(field)==prior[field], (ticker,prior.get('periodEnd'),field,'Existing verified value changed; review required')
  elif prior.get('verificationStatus')=='official_verified':
   assert len(rows)==5 and all(r.get('periodEnd','')>prior.get('periodEnd','') for r in rows), (ticker,'Unexpected lost quarter')
for ticker,period_end in [('TSLA','2025-12-31'),('SYK','2026-09-30')]:
 row=next(r for r in after[ticker] if r.get('periodEnd')==period_end)
 assert metrics(row), ticker+' reviewed target remains incomplete'
# A second sync of critical issuers must not alter any history object.
tickers={'TSLA','SYK','META','MSFT'}
with tempfile.TemporaryDirectory() as tmp:
 stage=Path(tmp)
 for name in ('data.json','historical_data.json','official_history.json','history_status.json','sp500_mapping.json'):
  value=read(name)
  selected=[r for r in value if r['ticker'] in tickers] if isinstance(value,list) else {k:v for k,v in value.items() if k in tickers}
  (stage/name).write_text(json.dumps(selected))
 result=sync_all(stage,full=True)
 assert result['sourceHealthy']
 assert read('historical_data.json')==after
 replay=json.loads((stage/'historical_data.json').read_text())
 assert replay=={k:v for k,v in after.items() if k in tickers}, 'Critical replay changed histories'
 validate(stage)
Path('docs/reviewed-metric-results-2026-10-30.json').write_text(json.dumps({'summary':summary,'changes':changes,'replay':{'tickers':sorted(tickers),'idempotent':True}},indent=2)+'\n')
print('REVIEWED_BACKFILL',json.dumps({'summary':summary,'changes':changes,'replayIdempotent':True}),flush=True)
