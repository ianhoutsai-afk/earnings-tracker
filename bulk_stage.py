"""Audit and optionally publish direct official missing facts; no production parser changes."""
import copy,json,re,hashlib
from pathlib import Path
from datetime import date,datetime
from decimal import Decimal
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
from verified_history import apply_official_records,write_json_bundle
from quarterly_policy import company_fields
from validate_quarterly_data import validate
def read(p):return json.loads(Path(p).read_text())
def compact(s):return re.sub('[^a-z0-9]','',str(s).lower())
def decimal_value(raw,scale=0,sign=None,split_negative=False):
 s=re.sub(r'\s+','',str(raw)).replace(',','').replace('$','')
 negative=s.startswith('(') and s.endswith(')')
 if negative:s=s[1:-1]
 if s.startswith('.'):s='0'+s
 if not re.fullmatch(r'-?\d+(?:\.\d+)?',s):raise ValueError('Unsupported raw number')
 value=Decimal(s)*(Decimal(10)**int(scale))
 if negative or sign=='-' or split_negative:value=-abs(value)
 return float(value)
today=datetime.now(ZoneInfo('America/New_York')).date()
before={p:read(p) for p in ['data.json','official_history.json','historical_data.json','history_status.json','official_scan_state.json','sp500_mapping.json']}
mapping=before['sp500_mapping.json'];original={(r['ticker'],r['periodEnd']):r for r in before['official_history.json']}
items=read('audit-bulk/revenue.json')['selected']+read('audit-bulk/eps-selected.json')
for p in sorted(Path('audit-bulk/releases').glob('*.json')):items+=read(p)
accepted=[];rejected=[];grouped={}
for item in items:
 key=(item['ticker'],item['periodEnd'],item['field'])
 try:
  r=original.get(key[:2]);field=item['field'];e=item['evidence'];ticker=item['ticker']
  assert r and field in {'revenue','epsGaapDiluted'}
  assert mapping[ticker].get('tickerStatus') not in {'historical_alias','unconfirmed'}
  assert r.get(field) is None
  assert (r['fiscalYear'],r['fiscalQuarter'])==(item['fiscalYear'],item['fiscalQuarter'])
  u=urlparse(item['sourceUrl']);assert u.scheme=='https' and u.hostname=='www.sec.gov' and not u.username and not u.password
  assert int(u.path.split('/data/')[1].split('/')[0])==int(mapping[ticker]['cik'])
  assert len(item['sourceSha256'])==64
  heading=e['statementHeading'];h=compact(heading)
  assert not re.search(r'(?i)non[\s-]*gaap|adjusted|pro[\s-]*forma|reconcil|\bsegment\b|\bnotes?\b',heading)
  assert ('consolidated' in h or 'combined' in h or ('|' in heading and 'statement' in h))
  assert e['value']==decimal_value(e['rawValue'],e.get('scale',0),e.get('sign'),e.get('signFromSplitParentheses',False))
  if field=='revenue':assert e['value']>=0
  if item.get('sourceKind')=='explicit_quarter_release_table':
   assert item['parentReleaseUrl']==r['releaseSourceUrl']
   h=e['header'];end=date.fromisoformat(r['periodEnd'])
   assert set(re.findall(r'\b20\d{2}\b',h))=={str(end.year)}
   assert re.search(r'(?i)\b(?:three months|quarters?|(?:twelve|thirteen|fourteen) weeks)\s+ended\b',h)
   assert not re.search(r'(?i)\b(?:six|nine|twelve) months|\byears?\s+ended\b|\bfiscal year\b',h)
   assert re.search(r'(?i)\b'+end.strftime('%B')+r'\s+'+str(end.day)+r'\b',h) or re.search(r'(?i)\b'+end.strftime('%b')+r'\.?\s+'+str(end.day)+r'\b',h) or (end.month==9 and re.search(r'(?i)\bSept\.?\s+'+str(end.day)+r'\b',h))
   assert not re.search(r'(?i)\bEUR|GBP|CAD|AUD|JPY|CNY|euros?|renminbi|yen\b',e['unitCaption'])
   if mapping[ticker].get('sector')=='Utilities' and compact(mapping[ticker].get('name','')) not in compact(e['statementHeading']):
    raise ValueError('Combined utility issuer requires explicit parent identity; keep pending')
   if field=='epsGaapDiluted':
    if re.search(r'(?i)continuing|discontinued',e['rowLabel']):raise ValueError('Component EPS row')
    if re.search(r'(?i)continuing|discontinued',e['statementText']):raise ValueError('EPS component sections require separate issuer review')
    if re.search(r'(?i)non[\s-]*gaap|adjusted\s+(?:diluted|earnings|income|EPS)',e['statementText']):raise ValueError('Mixed EPS basis requires separate issuer review')
  else:
   assert item['sourceUrl']==r.get('secUrl') and r.get('form')=='10-Q'
   c=e['context'];assert int(c['entity'])==int(mapping[ticker]['cik'])
   assert c['end']==r['periodEnd'] and 70<=(date.fromisoformat(c['end'])-date.fromisoformat(c['start'])).days+1<=110
   if field=='revenue':assert e['unitMeasure'].lower()=='iso4217:usd'
   else:
    assert e['unitMeasure']=='USD/shares'
    assert e['factTag'].lower()=='us-gaap:earningspersharediluted' or (e['factTag'].lower()=='us-gaap:earningspersharebasic' and e.get('combinedBasicDilutedCaption'))
    ds=c.get('dimensions',[])
    if ds:
     assert len(ds)==1 and ds[0][0]=='us-gaap:statementclassofstockaxis'
     if e['stockClassBasis']=='exact SEC trading-symbol stock-class context':
      assert any(z['symbol']==ticker and z['dimensions']==ds for z in e['stockSymbolEvidence'])
     else:assert len({z['value'] for z in e['allPrimaryDilutedClassValues']})==1
  grouped.setdefault(key,[]).append(item)
 except Exception as exc:rejected.append({'ticker':item['ticker'],'periodEnd':item['periodEnd'],'field':item['field'],'reason':str(exc) or type(exc).__name__})
conflicts=[]
for key,values in grouped.items():
 if len({v['evidence']['value'] for v in values})!=1:
  conflicts.append({'key':key,'values':[{'value':v['evidence']['value'],'source':v['sourceUrl']} for v in values]});continue
 values.sort(key=lambda x:(x.get('sourceKind')=='explicit_quarter_release_table',x['sourceUrl']))
 accepted.append(values[0])
accepted.sort(key=lambda x:(x['ticker'],x['periodEnd'],x['field']))
audit={'baselineCommit':'b166038b3fce74e7350472613a0755ea5f58f35a','inputFields':len(items),'acceptedFields':len(accepted),'revenueFields':sum(x['field']=='revenue' for x in accepted),'epsFields':sum(x['field']=='epsGaapDiluted' for x in accepted),'companies':len({x['ticker'] for x in accepted}),'quarters':len({(x['ticker'],x['periodEnd']) for x in accepted}),'conflicts':conflicts,'rejected':rejected,'selected':accepted}
Path('audit-bulk/accepted.json').write_text(json.dumps(audit,indent=2)+'\n')
print(json.dumps({k:v for k,v in audit.items() if k not in {'selected','rejected','conflicts'}}|{'conflicts':len(conflicts),'rejected':len(rejected)}))
if '--apply' not in __import__('sys').argv:raise SystemExit(0)
assert accepted
official=copy.deepcopy(before['official_history.json']);bykey={(r['ticker'],r['periodEnd']):r for r in official};changed_records={}
for item in accepted:
 r=bykey[(item['ticker'],item['periodEnd'])];field=item['field'];r[field]=item['evidence']['value']
 r['revenueSourceUrl' if field=='revenue' else 'epsSourceUrl']=item['sourceUrl'];r['verifiedAt']=today.isoformat()
 if field=='epsGaapDiluted':
  r['epsBasis']='GAAP diluted'
  e=item['evidence'];ds=e.get('context',{}).get('dimensions',[])
  if ds and len({x['value'] for x in e.get('allPrimaryDilutedClassValues',[])})>1:
   member=ds[0][1];m=re.search(r'CommonClass([A-Z0-9]+)Member',member)
   name='Class '+m[1]+' common shares' if m else 'listed common shares'
   note={'en':'GAAP diluted EPS is for '+name+' associated with '+item['ticker']+'.','zh-TW':'GAAP 稀釋 EPS 為 '+item['ticker']+' 對應的'+(' Class '+m[1]+' 普通股' if m else '上市普通股')+'數值。'}
   old=r.get('metricNote')
   if old:note={k:old[k]+' '+note[k] for k in note}
   r['metricNote']=note
 changed_records[(r['ticker'],r['periodEnd'])]=r
history,added=apply_official_records(before['data.json'],before['historical_data.json'],list(changed_records.values()),today)
assert added==0 and set(history)==set(before['historical_data.json'])
def window(rows):return [(r.get('periodEnd'),r.get('date'),r.get('quarter')) for r in rows]
for t in history:assert window(history[t])==window(before['historical_data.json'][t]),t
raw_changes=[]
for a,b in zip(before['official_history.json'],official):
 assert (a['ticker'],a['periodEnd'])==(b['ticker'],b['periodEnd'])
 for f in ['revenue','epsGaapDiluted']:
  if a.get(f) is not None:assert a[f]==b[f]
  elif b.get(f) is not None:raw_changes.append((a['ticker'],a['periodEnd'],f))
 for f in ['date','releaseSourceUrl','releaseFilingDate','releaseAccession','fiscalYear','fiscalQuarter']:
  assert a.get(f)==b.get(f),(a['ticker'],f)
assert set(raw_changes)=={(x['ticker'],x['periodEnd'],x['field']) for x in accepted}
display_changes=[]
for t,rows in history.items():
 for a,b in zip(before['historical_data.json'][t],rows):
  for raw,shown in [('revenue','revenue_reported'),('epsGaapDiluted','eps_reported')]:
   if a.get(shown) not in (None,'-'):assert a[shown]==b[shown]
   elif b.get(shown) not in (None,'-'):display_changes.append((t,b['periodEnd'],raw))
assert set(display_changes)==set(raw_changes)
status=copy.deepcopy(before['history_status.json'])
for t,rows in history.items():
 status[t]['recordCount']=len(rows)
 status[t]['officialQuarterCount']=sum(r.get('verificationStatus')=='official_verified' for r in rows)
 status[t]['metricsVerifiedQuarterCount']=sum(r.get('verificationStatus')=='official_verified' and r.get('epsBasis')=='GAAP diluted' and r.get('eps_reported') not in (None,'-') and r.get('revenue_reported') not in (None,'-') for r in rows)
state=copy.deepcopy(before['official_scan_state.json'])
state.update(pendingCompanies=sum(s.get('status')!='official_source_checked' or s.get('officialQuarterCount',0)<5 or s.get('metricsVerifiedQuarterCount',0)<5 for s in status.values()),officialQuarters=sum(s['officialQuarterCount'] for s in status.values()),fiveOfficialQuarterCompanies=sum(s['officialQuarterCount']==5 for s in status.values()),fiveCompleteMetricCompanies=sum(s['metricsVerifiedQuarterCount']==5 for s in status.values()),storedQuarters=sum(s['recordCount'] for s in status.values()),completeMetricQuarters=sum(s['metricsVerifiedQuarterCount'] for s in status.values()))
state['historyComplete']=state['fiveOfficialQuarterCompanies']==len(before['data.json']);state['metricsComplete']=state['fiveCompleteMetricCompanies']==len(before['data.json']);state['dataComplete']=state['historyComplete'] and state['metricsComplete'];state['healthy']=state['sourceHealthy'] and state['dataComplete'];state['dataStatus']='complete' if state['dataComplete'] else 'incomplete'
state['metricBackfill']={'date':today.isoformat(),'filledFields':len(accepted),'evidence':'docs/data-backfill-2026-11-07.json'}
folder=Path('docs/evidence-2026-11-07');folder.mkdir(exist_ok=True)
documents={};light=[]
for item in accepted:
 path=folder/(item['ticker']+'-'+item['periodEnd']+'-'+item['field']+'.json');documents[path]=item
 e=item['evidence'];light.append({k:v for k,v in item.items() if k!='evidence'}|{'value':e['value'],'rowLabel':e['rowLabel'],'statementHeading':e['statementHeading'],'evidenceFile':str(path)})
report={k:v for k,v in audit.items() if k not in {'selected','rejected'}}
report.update(filledFields=len(accepted),retainedNonNullChanges=0,unchangedTickerAndQuarterWindows=True,before=before['official_scan_state.json'],after=state,rejectionCount=len(rejected),selected=light)
documents.update({'official_history.json':official,'historical_data.json':history,'data.json':[company_fields(c,history,today) for c in before['data.json']],'history_status.json':status,'official_scan_state.json':state,'docs/data-backfill-2026-11-07.json':report})
write_json_bundle(documents)
print(json.dumps({'filledFields':len(accepted),'companies':report['companies'],'completeBefore':report['before']['completeMetricQuarters'],'completeAfter':state['completeMetricQuarters'],'validation':validate()}))
