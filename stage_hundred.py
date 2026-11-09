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
def quarter_columns(grid,boundary,end,year,quarter):
    headers=grid[:boundary]
    columns={}
    months={end.strftime('%B'),end.strftime('%b')}
    if end.month==9:
        months.add('Sept')
    date_pattern=r'(?i)(?:\b(?:'+'|'.join(months)+r')\.?\s+'+str(end.day)+r'\b|\b0?'+str(end.month)+r'/0?'+str(end.day)+r'/'+str(end.year)+r'\b)'
    ordinal=('first','second','third','fourth')[quarter-1]
    explicit=r'(?i)\b(?:'+ordinal+r'[\s-]+quarter|'+str(quarter)+r'(?:st|nd|rd|th)[\s-]+quarter|q'+str(quarter)+r'|'+str(quarter)+r'q)\b'
    for index in range(1,max(map(len,grid),default=0)):
        label=' '.join(dict.fromkeys(r[index] for r in headers if index<len(r) and r[index]))
        label=re.sub(r'(?i)\bFY\s*(\d{2})\b',r'20\1',label)
        if re.search(r'(?i)(?:six|nine|twelve)\s+months|years?\s+ended|full[\s-]*year|annual|percent\s+change',label):
            continue
        years=set(re.findall(r'\b20\d{2}\b',label))
        date_match=(years=={str(end.year)} and re.search(date_pattern,label)
                    and re.search(r'(?i)\b(?:(?:three|3)[\s-]+months|quarters?|(?:twelve|thirteen|fourteen|12|13|14)[\s-]+weeks)\s+ended\b',label))
        ordinal_match=years=={str(year)} and re.search(explicit,label)
        other_ordinals=('first','second','third','fourth')
        if ordinal_match and any(re.search(r'(?i)\b'+x+r'\s+quarter\b',label) for x in other_ordinals if x!=ordinal):
            ordinal_match=False
        if date_match or ordinal_match:
            columns[index]=(label,'explicit-date' if date_match else 'fiscal-quarter-column')
    return columns

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
items=read('selected-hundred.json')['selected']
accepted=[]
seen=set()
for item in items:
 key=(item['ticker'],item['periodEnd'])
 row=original[key]
 field=item['field']
 e=item['evidence']
 ticker=item['ticker']
 source=urlparse(item['sourceUrl'])
 assert field in ('epsGaapDiluted','revenue') and row.get(field) is None,(ticker,item['periodEnd'],field,row.get(field))
 assert (row['fiscalYear'],row['fiscalQuarter'])==(item['fiscalYear'],item['fiscalQuarter'])
 assert mapping[ticker].get('tickerStatus') not in ('historical_alias','unconfirmed')
 assert source.scheme=='https' and source.hostname=='www.sec.gov' and not source.username and not source.password
 assert int(source.path.split('/data/')[1].split('/')[0])==int(mapping[ticker]['cik'])==e['entity']
 assert e['unitMeasure']==('USD/shares' if field=='epsGaapDiluted' else 'USD')
 assert re.fullmatch(r'[a-f0-9]{64}',e['sourceSha256'])
 if item.get('sourceKind') in ('explicit_release_eps','explicit_release_revenue','narrative_release_revenue'):
  assert item['sourceKind'] in (('explicit_release_eps',) if field=='epsGaapDiluted' else ('explicit_release_revenue','narrative_release_revenue'))
  assert item['parentReleaseUrl']==row['releaseSourceUrl']
  assert item['sourceUrl'].rsplit('/',1)[0]==item['parentReleaseUrl'].rsplit('/',1)[0]
  identity=e['releaseIdentity']
  assert identity['date']==row['date'] and identity['periodEnd'] in (None,row['periodEnd'])
  if identity['fiscalYear'] is not None:
   assert (identity['fiscalYear'],identity['fiscalQuarter'])==(row['fiscalYear'],row['fiscalQuarter'])
  assert e['headerBasis'] in ('explicit-date','fiscal-quarter-column','explicit-quarter-paragraph')
  if e['headerBasis']=='explicit-date':
   assert quarter_columns([['',e['header']]],1,date.fromisoformat(row['periodEnd']),row['fiscalYear'],row['fiscalQuarter']).get(1,(None,None))[1]=='explicit-date'
  else:
   assert identity['periodEnd']==row['periodEnd']
   if e['headerBasis']=='fiscal-quarter-column':
    assert quarter_columns([['',e['header']]],1,date.fromisoformat(row['periodEnd']),row['fiscalYear'],row['fiscalQuarter']).get(1,(None,None))[1]=='fiscal-quarter-column'
  signed_raw=e.get('signedRawValue',e['rawValue'])
  normalized=e['rawValue'].replace('−','-')
  if signed_raw!=normalized:
   assert normalized.startswith(('(','$(')) and signed_raw==normalized+')'
   assert e['rowCells'][e['columnIndex']+1]==')'
  signed_raw=signed_raw.replace('−','-')
  assert item['value']==decimal_value(signed_raw,e['scale'],split_negative=e.get('signFromLossWording',False) or e.get('signFromSplitParentheses',False))
  if item['sourceKind']=='narrative_release_revenue':
   assert field=='revenue' and e['headerBasis']=='explicit-quarter-paragraph' and e['scale']=={'thousand':3,'million':6,'billion':9}[e['sourcePrecisionUnit'].lower()]
   assert e['matchedText'] in e['paragraph'] and e['quarterAnchor']
   assert re.search(r'(?i)revenues?|sales',e['rowLabel'])
  elif field=='revenue':
   assert e['headerBasis'] in ('explicit-date','fiscal-quarter-column') and e['scale'] in (3,6,9) and e['statementHeading'] and e['unitCaption']
   assert e['rowCells'][e['columnIndex']]==e['rawValue']
  elif e['headerBasis']=='explicit-quarter-paragraph':
   assert e['scale']==0 and e['matchedText'] and e['paragraph'] and 'diluted' in e['matchedText'].lower()
  else:
   assert e['scale']==0 and e['rowCells'][e['columnIndex']]==e['rawValue']
   assert e['sectionRows'] or re.search(r'(?i)dilut(?:ed|ion)',e['rowLabel'])
 elif item.get('sourceKind') in ('inline_statement_revenue','inline_statement_eps'):
  assert item['sourceKind']==('inline_statement_revenue' if field=='revenue' else 'inline_statement_eps')
  assert item['sourceUrl']==row['secUrl'] and e['filingForm']==row['form']
  assert field!='epsGaapDiluted' or e['factTag'].lower()=='us-gaap:earningspersharediluted'
  assert e['end']==row['periodEnd'] and 70<=(date.fromisoformat(e['end'])-date.fromisoformat(e['start'])).days+1<=110
  assert e['context']['end']==e['end'] and e['context']['start']==e['start'] and int(e['context']['entity'])==e['entity']
  assert e['statementHeading'] and e['rowLabel'] and e['contextHtml'] and e['unitHtml']
  assert item['value']==decimal_value(e['rawValue'],e['scale'],e.get('sign'))
 else:
  assert e['end']==row['periodEnd'] and 70<=(date.fromisoformat(e['end'])-date.fromisoformat(e['start'])).days+1<=110
  fact=e['companyfactsFact']
  assert (fact['start'],fact['end'],fact['val'])==(e['start'],e['end'],item['value'])
  assert source.path.split('/')[5]==fact['accn'].replace('-','')
  assert item['value']==decimal_value(e['rawValue'],e['scale'],e['sign'])
  assert field!='epsGaapDiluted' or e['factTag']=='us-gaap:EarningsPerShareDiluted'
 assert field!='revenue' or item['value']>=0
 assert (*key,field) not in seen
 seen.add((*key,field))
 item['evidence']['value']=item['value']
 accepted.append(item)
companies={x['ticker'] for x in accepted}
assert len(companies)==len({int(mapping[t]['cik']) for t in companies})==100
assert not ({int(mapping[t]['cik']) for t in companies} & set([773840,51434,1034054,1393818,217346,16732,65984,75362,72903,1037540,906345,1755672,1297996,1501585,77360,2041610,1063761,1393052,1097149,64803,1093557,1352010,1324424,1035983,882095,1652044,1543151,796343,6281,47217,857005,814547,910606,1014473,711404,21076,943819,320187,5272,1374310,895126,97210,1113169,86312,1555280,1094285,72741,1123360,1571949,865752,76334,91419,922224,769397,1327811,29534,1751008,9389,1701605,1324404,1091667,849395,1792789,1561550,927066,1065088,33185,33213,1551182,1099800,798354,1609711,1932393,1474735,4281,1373715,726728,1781335,945841,101829,1121788,1645590,1601046,72331,882184,898293,1375365,745732,1403568,1262039,879169,860731,1792044,1327567,4127,40533,1048695,1687229,900075,100885]))
audit={'baselineCommit':'e5ace5ce36c80da7ed1abf6b77511d2242f3d148','companies':len(companies),'quarters':len({(x['ticker'],x['periodEnd']) for x in accepted}),
       'epsFields':sum(x['field']=='epsGaapDiluted' for x in accepted),'revenueFields':sum(x['field']=='revenue' for x in accepted),
       'collectionPasses':read('selected-hundred.json')['collectionPasses']}
rejected=[]
official=copy.deepcopy(before['official_history.json']);bykey={(r['ticker'],r['periodEnd']):r for r in official};changed_records={}
for item in accepted:
 r=bykey[(item['ticker'],item['periodEnd'])];field=item['field'];r[field]=item['evidence']['value']
 r['revenueSourceUrl' if field=='revenue' else 'epsSourceUrl']=item['sourceUrl'];r['verifiedAt']=today.isoformat()
 if item['sourceKind']=='narrative_release_revenue':
  note={'en':'Revenue is shown at the precision stated in the official earnings release.','zh-TW':'營收採用官方財報公告所列精度。'}
  old=r.get('metricNote')
  if old:note={k:old[k]+' '+note[k] for k in note}
  r['metricNote']=note
 if field=='epsGaapDiluted':
  r['epsBasis']='GAAP diluted'
  e=item['evidence'];ds=e.get('context',{}).get('dimensions',[])
  if e.get('splitBasis'):
   split=e['splitBasis']
   assert ticker=='KLAC' and split['ratio']=='10-for-1' and split['effectiveDate']=='2026-06-11' and split['quote']
   note={'en':'Reported diluted EPS reflects the 10-for-1 stock split effective June 11, 2026.','zh-TW':'本季公告稀釋 EPS 已反映 2026 年 6 月 11 日生效的 1 拆 10。'}
   old=r.get('metricNote')
   if old:note={k:old[k]+' '+note[k] for k in note}
   r['metricNote']=note
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
state['metricBackfill']={'date':today.isoformat(),'filledFields':len(accepted),'evidence':'docs/hundred-company-backfill-2026-11-09.json'}
folder=Path('docs/evidence-hundred-companies-2026-11-09');folder.mkdir(exist_ok=True)
documents={};light=[]
for item in accepted:
 path=folder/(item['ticker']+'-'+item['periodEnd']+'-'+item['field']+'.json');documents[path]=item
 e=item['evidence'];light.append({k:v for k,v in item.items() if k!='evidence'}|{'value':e['value'],'factTag':e.get('factTag'),'rowLabel':e.get('rowLabel'),'evidenceFile':str(path)})
report={k:v for k,v in audit.items() if k not in {'selected','rejected'}}
report.update(filledFields=len(accepted),retainedNonNullChanges=0,unchangedTickerAndQuarterWindows=True,before=before['official_scan_state.json'],after=state,rejectionCount=len(rejected),selected=light)
documents.update({'official_history.json':official,'historical_data.json':history,'data.json':[company_fields(c,history,today) for c in before['data.json']],'history_status.json':status,'official_scan_state.json':state,'docs/hundred-company-backfill-2026-11-09.json':report})
write_json_bundle(documents)
print(json.dumps({'filledFields':len(accepted),'companies':report['companies'],'completeBefore':report['before']['completeMetricQuarters'],'completeAfter':state['completeMetricQuarters'],'validation':validate()}))
