"""Reconcile reviewed quarterly history with concurrent automated main updates."""
import json, subprocess
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from quarterly_policy import retain_history, retain_manifest, company_fields, merge_manifest_record
from verified_history import apply_official_records, write_json_bundle
from validate_quarterly_data import validate

def read(ref,name):
    return json.loads(subprocess.check_output(['git','show',ref+':'+name],text=True))
today=datetime.now(ZoneInfo('America/New_York')).date()
main='origin/main'; branch='HEAD'
companies=read(main,'data.json')
branch_companies={r['ticker']:r for r in read(branch,'data.json')}
assert {r['ticker'] for r in companies}==set(branch_companies), 'Concurrent company-universe change needs separate review'
mh,bh=read(main,'historical_data.json'),read(branch,'historical_data.json')
records={}
for record in read(branch,'official_history.json')+read(main,'official_history.json'):
    key=(record['ticker'],record['periodEnd'])
    records[key]=merge_manifest_record(records.get(key,{}),record)
manifest=retain_manifest(list(records.values()))
history=retain_history({k:mh[k]+bh[k] for k in branch_companies},today)
history,_=apply_official_records(companies,history,manifest,today)
status=read(branch,'history_status.json')
main_status=read(main,'history_status.json')
for company in companies:
    ticker=company['ticker']; reviewed=branch_companies[ticker]
    if reviewed.get('reportDateSource')=='official' and (reviewed.get('reportDate') or '')>=today.isoformat():
        for name in ('reportDate','reportDateSource','reportDateSourceUrl','bmo_amc'):
            company[name]=reviewed.get(name)
    if ticker=='XYZ' and company.get('reportDateSourceUrl')=='https://www.sec.gov/Archives/edgar/data/1512673/000119312526335117/d91486dex991.htm' and company.get('reportDate')=='2026-11-03':
        company['bmo_amc']='AMC'
        if status[ticker].get('nextEarningsEvent'):
            status[ticker]['nextEarningsEvent']['bmo_amc']='AMC'
    rows=history[ticker]
    # Preserve a later main ingestion, while retaining corrected parser status elsewhere.
    if (main_status[ticker].get('latestStoredDate') or '')>(status[ticker].get('latestStoredDate') or ''):
        status[ticker]=main_status[ticker]
    latest=rows[0] if rows else {}
    status[ticker].update(recordCount=len(rows),officialQuarterCount=sum(r.get('verificationStatus')=='official_verified' for r in rows),metricsVerifiedQuarterCount=sum(r.get('verificationStatus')=='official_verified' and r.get('epsBasis')=='GAAP diluted' and r.get('eps_reported') not in (None,'-') and r.get('revenue_reported') not in (None,'-') for r in rows),latestStoredDate=latest.get('date'),latestStoredOfficial=latest.get('verificationStatus')=='official_verified',officialSourceUrl=latest.get('releaseSourceUrl'))
    for old in (mh[ticker],bh[ticker]):
        old_end=max((r.get('periodEnd','') for r in old if r.get('verificationStatus')=='official_verified'),default='')
        assert max((r.get('periodEnd','') for r in rows),default='')>=old_end, ticker+' latest official quarter regressed'
companies=[company_fields(c,history,today) for c in companies]
summary=read(branch,'official_scan_state.json')
summary.update(companies=len(companies),officialQuarters=sum(s['officialQuarterCount'] for s in status.values()),storedQuarters=sum(s['recordCount'] for s in status.values()),completeMetricQuarters=sum(s['metricsVerifiedQuarterCount'] for s in status.values()),fiveOfficialQuarterCompanies=sum(s['officialQuarterCount']==5 for s in status.values()),fiveCompleteMetricCompanies=sum(s['metricsVerifiedQuarterCount']==5 for s in status.values()),pendingCompanies=sum(s.get('status')!='official_source_checked' or s['officialQuarterCount']<5 or s['metricsVerifiedQuarterCount']<5 for s in status.values()),reconciledMainCommit=subprocess.check_output(['git','rev-parse',main],text=True).strip(),dataMergedAt=datetime.now(timezone.utc).isoformat())
summary['historyComplete']=summary['fiveOfficialQuarterCompanies']==len(companies)
summary['metricsComplete']=summary['fiveCompleteMetricCompanies']==len(companies)
summary['dataComplete']=summary['historyComplete'] and summary['metricsComplete']
summary['healthy']=summary['sourceHealthy'] and summary['dataComplete']
summary['dataStatus']='complete' if summary['dataComplete'] else 'incomplete'
write_json_bundle({Path('data.json'):companies,Path('historical_data.json'):history,Path('official_history.json'):manifest,Path('history_status.json'):status,Path('official_scan_state.json'):summary})
print('RECONCILIATION',json.dumps(summary))
print('VALIDATION',json.dumps(validate()))
