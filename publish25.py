import copy
import json
import math
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from validate_quarterly_data import validate
from verified_history import apply_official_records, write_json_bundle

project=Path.cwd()
seed=project.parent/'seed'
audit_file=Path('docs/complete-25-issuer-financials-2026-11-14.json')
review_file='docs/complete-25-issuer-financials-2026-11-09.json'
today=datetime.now(ZoneInfo('America/New_York')).date()
names=['data.json','historical_data.json','official_history.json','history_status.json','official_scan_state.json','sp500_mapping.json']
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))
before={name:read(name) for name in names}
validate(today=today)
history=before['historical_data.json']
records=copy.deepcopy(before['official_history.json'])
review=read(seed/review_file)
by_key={(r['ticker'],r['periodEnd']):r for r in records}
items=[]
proofs={}
updates=[]
for v in review['selected']:
    key=(v['ticker'],v['periodEnd'])
    row=by_key[key]
    proof_path=Path(v['evidenceFile'])
    full=read(seed/proof_path)
    e=full['evidence']
    issuer=int(before['sp500_mapping.json'][key[0]]['cik'])
    assert (row['fiscalYear'],row['fiscalQuarter'])==(v['fiscalYear'],v['fiscalQuarter'])
    assert v['parentReleaseUrl']==row['releaseSourceUrl']==full['parentReleaseUrl']
    assert v['sourceUrl']==full['sourceUrl']==e['independentCheckUrl']
    p=urlsplit(v['sourceUrl'])
    assert p.scheme=='https' and p.netloc=='www.sec.gov'
    assert p.path.startswith(f'/Archives/edgar/data/{issuer}/')
    assert v['sourceUrl'].rsplit('/',1)[0]==row['releaseSourceUrl'].rsplit('/',1)[0]
    assert e['entity']==issuer and e['reviewedQuarter']==key[1] and e['unitMeasure']=='USD/shares'
    assert re.fullmatch(r'[a-f0-9]{64}',e['sourceSha256'])
    assert v['field']==full['field']=='epsGaapDiluted' and all(k not in v['rowLabel'].lower() for k in ('adjusted','non-gaap','guidance'))
    assert row['epsGaapDiluted'] is None
    h=next(r for r in history[key[0]] if r.get('periodEnd')==key[1])
    assert h.get('eps_reported') in (None,'-') and h['verificationStatus']=='official_verified'
    assert e['rowCells'][e['columnIndex']]==e['rawValue']
    raw=e['signedRawValue'].replace(',','').replace('$','').strip()
    raw=re.sub(r'\s+','',raw).replace('−','-')
    num=-float(raw[1:-1]) if raw.startswith('(') and raw.endswith(')') else float(raw)
    if e.get('signFromSplitParentheses'):
        num=-abs(num)
    assert math.isfinite(num) and num==v['value']==full['value']==e['value'] and e['scale']==0
    row.update(epsGaapDiluted=num,epsBasis='GAAP diluted',epsSourceUrl=v['sourceUrl'],verifiedAt=today.isoformat())
    updates.append(row)
    items.append(v)
    proofs[proof_path]=full
assert len(items)==len({(x['ticker'],x['periodEnd']) for x in items})==len({proof['evidence']['entity'] for proof in proofs.values()})==25
after_history,added=apply_official_records(before['data.json'],history,updates,today)
assert added==0
changed={(x['ticker'],x['periodEnd']) for x in items}
for ticker,rows in history.items():
    assert len(rows)==len(after_history[ticker])
    for old,new in zip(rows,after_history[ticker]):
        if (ticker,old.get('periodEnd')) in changed:
            assert new['eps_reported'] not in (None,'-') and new['epsBasis']=='GAAP diluted'
            assert {k for k in set(old)|set(new) if old.get(k)!=new.get(k)} <= {'eps_reported','epsBasis','epsSourceUrl','verifiedAt'}
        else:
            assert old==new
status=copy.deepcopy(before['history_status.json'])
for ticker,rows in after_history.items():
    status[ticker]['metricsVerifiedQuarterCount']=sum(r.get('verificationStatus')=='official_verified' and r.get('epsBasis')=='GAAP diluted'
        and r.get('eps_reported') not in (None,'-') and r.get('revenue_reported') not in (None,'-') for r in rows)
state=copy.deepcopy(before['official_scan_state.json'])
state['completeMetricQuarters']=sum(r['metricsVerifiedQuarterCount'] for r in status.values())
state['fiveCompleteMetricCompanies']=sum(r['metricsVerifiedQuarterCount']==5 for r in status.values())
state['pendingCompanies']=sum(r.get('status')!='official_source_checked' or r['officialQuarterCount']<5 or r['metricsVerifiedQuarterCount']<5 for r in status.values())
state['metricBackfill']={'date':today.isoformat(),'filledFields':len(items),'evidence':str(audit_file)}
assert state['completeMetricQuarters']-before['official_scan_state.json']['completeMetricQuarters']==25
result={**review,'baselineCommit':'0b57f5808be0e487edc9c55187e9eaa4668ab841','sourceReviewCommit':'ad0235d7cf2402155c3e5ae4725b5fb94b8ef909','before':before['official_scan_state.json'],'after':state,'selected':items}
proof_dir=Path(next(iter(proofs))).parent
proof_dir.mkdir(exist_ok=True)
docs={**proofs,audit_file:result,'official_history.json':records,'historical_data.json':after_history,'history_status.json':status,'official_scan_state.json':state}
write_json_bundle(docs)
print(json.dumps({'changed':len(items),'validation':validate(today=today),'old':result['before'],'new':state},ensure_ascii=False))
