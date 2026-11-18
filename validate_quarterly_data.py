"""Reject an inconsistent publication bundle before committing it to Pages."""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from quarterly_policy import all_release_dates_verified, filing_dated_quarters, official_source_url, retain_history, retain_manifest, pending_history_companies, history_continuity_issues
from verified_history import _validate_record


def validate(root='.', today=None):
    root=Path(root)
    today=today or datetime.now(ZoneInfo('America/New_York')).date()
    companies=json.loads((root/'data.json').read_text())
    history=json.loads((root/'historical_data.json').read_text())
    status=json.loads((root/'history_status.json').read_text())
    records=json.loads((root/'official_history.json').read_text())
    tickers={c['ticker'] for c in companies}
    if len(tickers)!=len(companies) or set(history)!=tickers or set(status)!=tickers:
        raise ValueError('Active company/history/status sets differ')
    if history!=retain_history(history,today):
        raise ValueError('History must contain at most five distinct quarters, newest first')
    if records!=retain_manifest(records):
        raise ValueError('Official input must contain at most five distinct periods per company')
    by_period = {(r['ticker'], r['periodEnd']): r for r in records}
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
                if (not official_source_url(row) or row.get('periodScope')!='quarter'
                        or not row.get('periodEnd') or not row.get('fiscalYear') or row.get('fiscalQuarter') not in (1,2,3,4)):
                    raise ValueError('Verified quarter lacks period or source')
                if row.get('dateSource') == 'sec_filing':
                    record = by_period.get((ticker, row['periodEnd']))
                    if not record or any(row.get(field)!=record.get(field) for field in
                                         ('date','dateSource','filingDate','form','secUrl','accessionNumber','releaseSourceUrl')):
                        raise ValueError('Displayed filing provenance differs from the official record')
                if row.get('dateSource') == 'recast':
                    record = by_period.get((ticker, row['periodEnd']))
                    if not record or any(row.get(field)!=record.get(field) for field in
                                         ('date','dateSource','releaseFilingDate','releaseSourceUrl','releaseAccession')):
                        raise ValueError('Displayed recast provenance differs from the official record')
        if status[ticker].get('recordCount')!=len(history[ticker]):
            raise ValueError('Per-company record count differs from active history')
    state_path = root/'official_scan_state.json'
    if state_path.exists():
        state = json.loads(state_path.read_text())
        continuity = history_continuity_issues(history)
        consecutive = sum(len(rows) == 5 and ticker not in continuity
                          and all(row.get('verificationStatus') == 'official_verified' for row in rows)
                          for ticker, rows in history.items())
        if state.get('historyComplete') and consecutive != len(companies):
            raise ValueError('History marked complete without five consecutive verified quarters')
        if state.get('dataComplete') and (consecutive != len(companies) or state.get('historyComplete') is False):
            raise ValueError('Data marked complete without five consecutive verified quarters')
        if 'historyContinuityPendingCompanies' in state and state['historyContinuityPendingCompanies'] != len(continuity):
            raise ValueError('Quarter-continuity count differs from the published quarters')
        if 'fiveConsecutiveQuarterCompanies' in state and state['fiveConsecutiveQuarterCompanies'] != consecutive:
            raise ValueError('Consecutive-quarter count differs from the published quarters')
        if 'scanPendingCompanies' in state:
            if state.get('pendingCompanies') != pending_history_companies(history):
                raise ValueError('Pending-data count differs from the published quarters')
            if state['scanPendingCompanies'] != sum(row.get('status') != 'official_source_checked' for row in status.values()):
                raise ValueError('Pending-scan count differs from the last source review')
        if 'filingDatedQuarters' in state:
            filing_count = filing_dated_quarters(history)
            all_releases = all_release_dates_verified(history)
            if state['filingDatedQuarters'] != filing_count or state.get('releaseDatesComplete') != all_releases:
                raise ValueError('Release-date coverage differs from the published quarters')
            if not all_releases and state.get('dataComplete'):
                raise ValueError('Data marked complete while earnings-release dates are unverified')
    return {'companies':len(companies),'records':sum(map(len,history.values())),
            'officialQuarters':sum(r.get('verificationStatus')=='official_verified' for rows in history.values() for r in rows),
            'shortHistoryCompanies':sum(len(rows)<5 for rows in history.values())}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    args=parser.parse_args()
    print(json.dumps(validate(args.root)))
