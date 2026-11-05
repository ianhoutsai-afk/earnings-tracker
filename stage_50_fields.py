"""One-off capped data publication; removed before merge."""
import copy,json,hashlib,re
from datetime import date,datetime,timezone
from pathlib import Path
from decimal import Decimal
from zoneinfo import ZoneInfo
today=datetime.now(ZoneInfo('America/New_York')).date()
from lxml import html
from verified_history import apply_official_records,write_json_bundle
from quarterly_policy import company_fields
from validate_quarterly_data import validate
LIMIT=50
def read(p):return json.loads(Path(p).read_text())
before={p:read(p) for p in ['data.json','historical_data.json','official_history.json','history_status.json','official_scan_state.json']}
candidates=read('audit-50/candidates.json')['selected']
mapping=read('sp500_mapping.json')
official=copy.deepcopy(before['official_history.json'])
bykey={(r['ticker'],r['periodEnd']):r for r in official}
selected=[];seen=set()
for item in candidates:
 key=(item['ticker'],item['periodEnd'])
 if key not in bykey:continue
 row=bykey[key]
 if row.get(item['field']) is not None:continue
 assert item['field']=='revenue' and key not in seen
 assert (row['fiscalYear'],row['fiscalQuarter'])==(item['fiscalYear'],item['fiscalQuarter'])
 assert row['secUrl']==item['sourceUrl'] and row['form']=='10-Q'
 e=item['evidence'];ctx=e['context']
 assert int(ctx['entity'])==int(mapping[item['ticker']]['cik'])
 assert item['sourceUrl'].startswith('https://www.sec.gov/Archives/edgar/data/')
 assert ctx['end']==row['periodEnd'] and 70<=(date.fromisoformat(ctx['end'])-date.fromisoformat(ctx['start'])).days+1<=110
 assert e['unitMeasure'].lower()=='iso4217:usd'
 assert float(Decimal(e['rawValue'])*Decimal(10)**e['scale'])==e['value']>=0
 heading=re.sub('[^a-z]','',e['statementHeading'].lower())
 assert 'consolidated' in heading or 'combined' in heading
 assert not re.search(r'(?i)non[\s-]*gaap|adjusted|pro[\s-]*forma|reconcil|\bsegment\b|\bnotes?\b',e['statementHeading'])
 assert not re.search(r'(?i)net\s+revenues?\s+less|interest\s+income|contract\s+asset', e['rowLabel'])
 row['revenue']=e['value'];row['revenueSourceUrl']=item['sourceUrl']
 row['verifiedAt']=today.isoformat()
 seen.add(key);selected.append(item)
 if len(selected)==LIMIT:break
assert len(selected)==LIMIT, f'Need exactly 50 currently missing fields, got {len(selected)}'
companies=before['data.json']
history,added=apply_official_records(companies,before['historical_data.json'],[bykey[(s['ticker'],s['periodEnd'])] for s in selected],today)
assert added==0
assert set(history)==set(before['historical_data.json'])
def identity(rows):return [(r.get('periodEnd'),r.get('date'),r.get('quarter')) for r in rows]
for t in history:
 assert identity(history[t])==identity(before['historical_data.json'][t]),t
for old,new in zip(before['official_history.json'],official):
 assert (old['ticker'],old['periodEnd'])==(new['ticker'],new['periodEnd'])
 for f in ['epsGaapDiluted','revenue']:
  if old.get(f) is not None:assert old[f]==new[f],(old['ticker'],f)
changes=[(o['ticker'],o['periodEnd'],f) for o,n in zip(before['official_history.json'],official) for f in ['epsGaapDiluted','revenue'] if o.get(f) is None and n.get(f) is not None]
assert len(changes)==50 and len(set(changes))==50
shown=[]
for t,rows in history.items():
 prev={(r.get('periodEnd'),r.get('date')):r for r in before['historical_data.json'][t]}
 for r in rows:
  old=prev[(r.get('periodEnd'),r.get('date'))]
  for f in ['eps_reported','revenue_reported']:
   if old.get(f) not in (None,'-'):assert r.get(f)==old[f],(t,f)
   if old.get(f) in (None,'-') and r.get(f) not in (None,'-'):shown.append((t,r.get('periodEnd'),f))
assert len(shown)==50 and {(t,p) for t,p,f in shown}==seen
status=copy.deepcopy(before['history_status.json'])
for t,rows in history.items():
 status[t]['recordCount']=len(rows)
 status[t]['officialQuarterCount']=sum(r.get('verificationStatus')=='official_verified' for r in rows)
 status[t]['metricsVerifiedQuarterCount']=sum(r.get('verificationStatus')=='official_verified' and r.get('epsBasis')=='GAAP diluted' and r.get('eps_reported') not in (None,'-') and r.get('revenue_reported') not in (None,'-') for r in rows)
state=copy.deepcopy(before['official_scan_state.json'])
state.update(pendingCompanies=sum(s.get('status')!='official_source_checked' or s.get('officialQuarterCount',0)<5 or s.get('metricsVerifiedQuarterCount',0)<5 for s in status.values()),
 officialQuarters=sum(s['officialQuarterCount'] for s in status.values()),
 fiveOfficialQuarterCompanies=sum(s['officialQuarterCount']==5 for s in status.values()),
 fiveCompleteMetricCompanies=sum(s['metricsVerifiedQuarterCount']==5 for s in status.values()),
 storedQuarters=sum(s['recordCount'] for s in status.values()),
 completeMetricQuarters=sum(s['metricsVerifiedQuarterCount'] for s in status.values()))
state['historyComplete']=state['fiveOfficialQuarterCompanies']==len(companies)
state['metricsComplete']=state['fiveCompleteMetricCompanies']==len(companies)
state['dataComplete']=state['historyComplete'] and state['metricsComplete']
state['healthy']=state['sourceHealthy'] and state['dataComplete']
state['dataStatus']='complete' if state['dataComplete'] else 'incomplete'
state['metricBackfill']={'date':today.isoformat(),'filledFields':50,'evidence':'docs/data-backfill-50-2026-11-05.json'}
companies=[company_fields(c,history,today) for c in companies]
report={'baselineCommit':'8a8b1cc1dac04f4f13fb793661704da16e86cd1d','collectorCommit':'13d19f3e83bd292630622f0ccdaa42d47d0c3853','methodology':'Direct dimensionless USD revenue fact in the issuer GAAP income statement for an explicit 70-110 day quarter; no annual subtraction or estimated numbers. One item is one previously null numeric field.','limit':50,'filledFields':len(changes),'revenueFields':50,'epsFields':0,'companies':len({s['ticker'] for s in selected}),'quarters':len(seen),
'retainedNonNullChanges':0,'tickerAndQuarterWindowsChanged':False,
'before':before['official_scan_state.json'],'after':state,
'selected':selected}
write_json_bundle({'official_history.json':official,'historical_data.json':history,'data.json':companies,'history_status.json':status,'official_scan_state.json':state,
'docs/data-backfill-50-2026-11-05.json':report})
print(json.dumps({'filledFields':50,'companies':report['companies'],'beforeComplete':report['before']['completeMetricQuarters'],'afterComplete':state['completeMetricQuarters'],'validation':validate()}))
