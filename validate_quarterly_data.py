"""Reject an inconsistent publication bundle before committing it to Pages."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from quarterly_policy import retain_history, retain_manifest
from verified_history import _validate_record
from coverage_state import company_status


def validate(root='.', today=None):
    root=Path(root)
    today=today or datetime.now(ZoneInfo('America/New_York')).date()
    companies=json.loads((root/'data.json').read_text())
    history=json.loads((root/'historical_data.json').read_text())
    status=json.loads((root/'history_status.json').read_text())
    records=json.loads((root/'official_history.json').read_text())
    mapping=json.loads((root/'sp500_mapping.json').read_text())
    summary=json.loads((root/'official_scan_state.json').read_text())
    if not isinstance(mapping,dict) or not isinstance(summary,dict):
        raise ValueError('Mapping and scan summary must be objects')
    tickers={c['ticker'] for c in companies}
    if len(tickers)!=len(companies) or set(history)!=tickers or set(status)!=tickers:
        raise ValueError('Active company/history/status sets differ')
    if history!=retain_history(history,today):
        raise ValueError('History must contain at most five distinct quarters, newest first')
    if records!=retain_manifest(records):
        raise ValueError('Official input must contain at most five distinct periods per company')
    for record in records:
        _validate_record(record,tickers,today)
    for company in companies:
        ticker=company['ticker']
        if company.get('eps')!='-' or company.get('revenue')!='-':
            raise ValueError('Unscoped next-quarter estimate found')
        raw=company.get('reportDate')
        if raw and raw<today.isoformat():
            raise ValueError('Expired next-event date')
        for row in history[ticker]:
            if row.get('verificationStatus')=='official_verified':
                if (not row.get('releaseSourceUrl') or row.get('periodScope')!='quarter'
                        or not row.get('periodEnd') or not row.get('fiscalYear') or row.get('fiscalQuarter') not in (1,2,3,4)):
                    raise ValueError('Verified release lacks period or source')
        if status[ticker].get('recordCount')!=len(history[ticker]):
            raise ValueError('Per-company record count differs from active history')
        if 'coverage' in status[ticker]:
            expected=company_status(company,history[ticker],status[ticker],summary.get('checkedAt',today.isoformat()+'T00:00:00Z'))
            if status[ticker]['coverage']!=expected['coverage']:
                raise ValueError('Field coverage differs from verified history')
            if status[ticker].get('metricsVerifiedQuarterCount')!=expected['coverage']['completeMetrics']:
                raise ValueError('Metric coverage differs from verified history')
    if summary.get('companies')!=len(companies) or summary.get('officialQuarters')!=sum(
            r.get('verificationStatus')=='official_verified' for rows in history.values() for r in rows):
        raise ValueError('Scan summary differs from active history')
    return {'companies':len(companies),'records':sum(map(len,history.values())),
            'officialQuarters':sum(r.get('verificationStatus')=='official_verified' for rows in history.values() for r in rows),
            'shortHistoryCompanies':sum(len(rows)<5 for rows in history.values())}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    args=parser.parse_args()
    print(json.dumps(validate(args.root)))
