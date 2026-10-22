"""One-time auditable migration; no source requests and no invented quarters."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from quarterly_policy import retain_manifest, company_fields
from verified_history import apply_official_records, write_json_bundle
from validate_quarterly_data import validate


def migrate(root='.',today=None):
    root=Path(root)
    today=today or datetime.now(ZoneInfo('America/New_York')).date()
    companies=json.loads((root/'data.json').read_text())
    before=json.loads((root/'historical_data.json').read_text())
    manifest=retain_manifest(json.loads((root/'official_history.json').read_text()))
    status=json.loads((root/'history_status.json').read_text())
    history,_=apply_official_records(companies,before,manifest,today)
    report={'date':today.isoformat(),'companies':len(companies),'beforeRecords':sum(map(len,before.values())),
            'afterRecords':sum(map(len,history.values())),'companyChanges':[]}
    for company in companies:
        ticker=company['ticker'];rows=history[ticker]
        latest=rows[0] if rows else {}
        verified=sum(r.get('verificationStatus')=='official_verified' for r in rows)
        current=status.get(ticker,{})
        if ticker!='NVDA':
            current.update(status='pending_official',reason='all_company_official_migration_pending')
        elif current.get('checkedAt'):
            current['officialCheckedAt']=current['checkedAt']
        status[ticker]={**current,'recordCount':len(rows),'officialQuarterCount':verified,
                        'latestStoredDate':latest.get('date'),'latestStoredOfficial':latest.get('verificationStatus')=='official_verified',
                        'officialSourceUrl':latest.get('releaseSourceUrl')}
        retained_dates={r['date'] for r in rows}
        report['companyChanges'].append({'ticker':ticker,'beforeCount':len(before[ticker]),'afterCount':len(rows),
                'officialQuarters':verified,'missingQuarters':max(0,5-len(rows)),
                'removedDates':[r['date'] for r in before[ticker] if r['date'] not in retained_dates]})
    companies=[company_fields(c,history,today) for c in companies]
    report['scope']='All active companies; legacy values retained in storage but hidden until their quarterly GAAP basis is verified.'
    write_json_bundle({root/'data.json':companies,root/'historical_data.json':history,
                       root/'official_history.json':manifest,root/'history_status.json':status})
    summary=validate(root,today)
    report['validation']=summary
    output=root/'docs'/'all-company-quarterly-migration.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':print(json.dumps(migrate()))
