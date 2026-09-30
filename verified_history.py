"""Publish reviewed earnings releases; use Yahoo only to discover missing quarters."""

import copy
import json
import os
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from update_data import format_eps, format_revenue


NEW_YORK = ZoneInfo('America/New_York')


def date_in_new_york(value):
    """Interpret Yahoo timestamps by the US earnings-calendar date."""
    if isinstance(value, datetime):
        return value.astimezone(NEW_YORK).date() if value.tzinfo else value.date()
    if isinstance(value, date):
        return value
    raise ValueError('Unsupported earnings date')


def _iso_date(value, label):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid {label}: {value}') from exc


def _validate_record(record, tickers, today):
    required = ('ticker', 'date', 'periodEnd', 'fiscalYear', 'fiscalQuarter',
                'periodScope', 'currency', 'releaseSourceUrl', 'verifiedAt')
    if any(key not in record for key in required):
        raise ValueError(f'Missing official record field: {record.get("ticker", "?")}')
    if record['ticker'] not in tickers:
        raise ValueError(f'Unknown ticker: {record["ticker"]}')
    release = _iso_date(record['date'], 'release date')
    period_end = _iso_date(record['periodEnd'], 'period end')
    verified = _iso_date(record['verifiedAt'], 'verification date')
    if not period_end <= release <= today or verified > today:
        raise ValueError(f'Invalid official dates for {record["ticker"]}')
    if record['periodScope'] != 'quarter' or record['fiscalQuarter'] not in (1, 2, 3, 4):
        raise ValueError('Only explicit quarterly results are accepted')
    if not isinstance(record['fiscalYear'], int) or record['fiscalYear'] < 2000:
        raise ValueError('Invalid fiscal year')
    if record['currency'] != 'USD':
        raise ValueError('Only verified USD values can use the current $ display')
    source = urlparse(record['releaseSourceUrl'])
    host = (source.hostname or '').lower()
    if source.scheme != 'https' or not host or host == 'finance.yahoo.com' or host.endswith('.yahoo.com'):
        raise ValueError('A reviewed official HTTPS release URL is required')
    metric_source = urlparse(record.get('metricSourceUrl') or record['releaseSourceUrl'])
    if metric_source.scheme != 'https' or not metric_source.hostname or metric_source.hostname.endswith('.yahoo.com'):
        raise ValueError('A reviewed official HTTPS metric URL is required')
    if record.get('epsGaapDiluted') is not None and record.get('epsBasis') != 'GAAP diluted':
        raise ValueError('EPS must explicitly be GAAP diluted, not adjusted')
    if record.get('epsGaapDiluted') is None and record.get('epsBasis') not in (None, 'GAAP diluted'):
        raise ValueError('Invalid EPS basis')
    for field in ('epsGaapDiluted', 'revenue'):
        value = record.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise ValueError(f'Invalid {field} for {record["ticker"]}')
    if record.get('revenue') is not None and record['revenue'] < 0:
        raise ValueError('Revenue cannot be negative')
    note = record.get('metricNote')
    if note is not None and (
        not isinstance(note, dict)
        or not isinstance(note.get('en'), str)
        or not isinstance(note.get('zh-TW'), str)
    ):
        raise ValueError('Metric note must have English and Traditional Chinese text')


def apply_official_records(companies, history, records, today):
    """Validate the complete batch before producing a new history object."""
    tickers = {company['ticker'] for company in companies}
    seen_manifest = set()
    for record in records:
        _validate_record(record, tickers, today)
        key = (record['ticker'], record['periodEnd'], record['periodScope'])
        if key in seen_manifest:
            raise ValueError(f'Duplicate reviewed fiscal period: {key}')
        seen_manifest.add(key)

    result = copy.deepcopy(history)
    added = 0
    for record in records:
        ticker = record['ticker']
        rows = result.setdefault(ticker, [])
        existing = next((row for row in rows if (
            row.get('date') == record['date']
            or (row.get('periodEnd') == record['periodEnd']
                and row.get('periodScope') == record['periodScope'])
        )), None)
        eps = record.get('epsGaapDiluted')
        revenue = record.get('revenue')
        official_row = {
            'date': record['date'],
            'quarter': f"{record['fiscalYear']} Q{record['fiscalQuarter']}",
            'periodEnd': record['periodEnd'],
            'periodScope': record['periodScope'],
            'eps_reported': f'-${abs(eps):.2f}' if eps is not None and eps < 0 else format_eps(eps),
            'revenue_reported': format_revenue(revenue),
            'epsBasis': 'GAAP diluted' if eps is not None else None,
            'currency': record['currency'],
            'releaseSourceUrl': record['releaseSourceUrl'],
            'metricSourceUrl': record.get('metricSourceUrl') or record['releaseSourceUrl'],
            'verifiedAt': record['verifiedAt'],
            'verificationStatus': 'official_verified',
        }
        if record.get('metricNote'):
            official_row['metricNote'] = record['metricNote']
        if existing:
            existing.update(official_row)
            continue
        rows.append(official_row)
        rows.sort(key=lambda item: item['date'])
        added += 1
    return result, added


def clear_past_report_dates(companies, today):
    result = copy.deepcopy(companies)
    for company in result:
        raw = company.get('reportDate')
        try:
            expected = date.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            expected = None
        if expected is None or expected < today:
            company['reportDate'] = None
            company['bmo_amc'] = None
    return result


def status_from_discovery(companies, history, candidates, errors, checked_at):
    """Public status contains no Yahoo numeric values or candidate dates."""
    result = {}
    for company in companies:
        ticker = company['ticker']
        rows = history.get(ticker, [])
        latest_stored = max((row.get('date', '') for row in rows), default='')
        latest_candidate = max(candidates.get(ticker, []), default='')
        latest_row = next((row for row in rows if row.get('date') == latest_stored), {})
        verified = latest_row.get('verificationStatus') == 'official_verified'
        if ticker in errors:
            status, reason = 'discovery_failed', errors[ticker]
        elif latest_candidate and (latest_candidate > latest_stored or not verified):
            status, reason = 'pending_official', 'newer_release_requires_official_check'
        elif latest_candidate and verified:
            status, reason = 'verified_to_latest_candidate', 'latest_yahoo_candidate_is_officially_verified'
        else:
            status, reason = 'no_new_candidate', 'no_new_release_found_in_yahoo_scan'
        result[ticker] = {
            'status': status,
            'reason': reason,
            'latestStoredDate': latest_stored or None,
            'latestStoredOfficial': verified,
            'officialSourceUrl': latest_row.get('releaseSourceUrl') if verified else None,
            'discoverySource': 'yfinance.get_earnings_dates',
            'checkedAt': checked_at,
        }
    return result


def scan_yahoo_candidates(companies, fetch, today, sleep=time.sleep):
    """Read every ticker; retain release dates only, never Yahoo EPS or revenue."""
    candidates = {}
    errors = {}
    for index, company in enumerate(companies, start=1):
        ticker = company['ticker']
        try:
            frame = fetch(ticker)
            dates = set()
            if frame is not None and not frame.empty and 'Reported EPS' in frame.columns:
                for timestamp, row in frame.iterrows():
                    eps = row.get('Reported EPS')
                    release = date_in_new_york(timestamp)
                    if eps is not None and eps == eps and release <= today:
                        dates.add(release.isoformat())
            candidates[ticker] = sorted(dates)
            if not dates:
                errors[ticker] = 'no_reported_eps_from_yahoo'
        except Exception as exc:
            error_name = type(exc).__name__.lower()
            message = str(exc).lower()
            if 'dns' in error_name or 'could not resolve host' in message:
                errors[ticker] = 'yahoo_dns_failed'
            elif 'ratelimit' in error_name or 'too many requests' in message or '429' in message:
                errors[ticker] = 'yahoo_rate_limited'
            else:
                errors[ticker] = 'yahoo_request_failed'
            candidates[ticker] = []
        if index % 25 == 0 or index == len(companies):
            print(f'Yahoo date-only discovery: {index}/{len(companies)}; failures: {len(errors)}', flush=True)
        sleep(1)
    return candidates, errors


def write_json_bundle(documents):
    """Stage every file, then restore earlier files if a replacement fails."""
    staged = {}
    originals = {}
    replaced = []
    try:
        for target, value in documents.items():
            target = Path(target)
            originals[target] = target.read_bytes() if target.exists() else None
            with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=target.parent,
                                             prefix=f'.{target.name}.', delete=False) as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.write('\n')
                staged[target] = Path(handle.name)
        for target, source in staged.items():
            os.replace(source, target)
            replaced.append(target)
    except Exception:
        for target in reversed(replaced):
            prior = originals[target]
            if prior is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(prior)
        raise
    finally:
        for source in staged.values():
            source.unlink(missing_ok=True)


def _fetch_yahoo_earnings(ticker):
    import yfinance as yf

    last_error = None
    for attempt in range(2):
        try:
            return yf.Ticker(ticker).get_earnings_dates(limit=12)
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(2)
    raise last_error


def refresh_site_data(root, today=None, scan=False, fetch=None, sleep=time.sleep):
    """Apply reviewed releases and maintain a per-company discovery status."""
    root = Path(root)
    today = today or datetime.now(NEW_YORK).date()
    companies = json.loads((root / 'data.json').read_text(encoding='utf-8'))
    history = json.loads((root / 'historical_data.json').read_text(encoding='utf-8'))
    reviewed = json.loads((root / 'official_history.json').read_text(encoding='utf-8'))
    updated_history, added = apply_official_records(companies, history, reviewed, today)
    updated_companies = clear_past_report_dates(companies, today)
    if scan:
        candidates, errors = scan_yahoo_candidates(companies, fetch or _fetch_yahoo_earnings, today, sleep=sleep)
        checked_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        status = status_from_discovery(companies, updated_history, candidates, errors, checked_at)
    else:
        checked_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        status_path = root / 'history_status.json'
        existing_status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
        status = {}
        for company in companies:
            ticker = company['ticker']
            rows = updated_history.get(ticker, [])
            latest = max((row.get('date', '') for row in rows), default='')
            latest_row = next((row for row in rows if row.get('date') == latest), {})
            verified = latest_row.get('verificationStatus') == 'official_verified'
            prior = existing_status.get(ticker)
            if prior and prior.get('latestStoredDate') == (latest or None):
                status[ticker] = {
                    **prior,
                    'latestStoredOfficial': verified,
                    'officialSourceUrl': latest_row.get('releaseSourceUrl') if verified else None,
                }
                if verified and prior.get('status') == 'pending_official':
                    status[ticker].update({
                        'status': 'official_verified_scan_pending',
                        'reason': 'official_release_added; next_discovery_scan_pending',
                        'checkedAt': checked_at,
                    })
            elif verified:
                status[ticker] = {
                    'status': 'official_verified_scan_pending',
                    'reason': 'official_release_added; next_discovery_scan_pending',
                    'latestStoredDate': latest,
                    'latestStoredOfficial': True,
                    'officialSourceUrl': latest_row.get('releaseSourceUrl'),
                    'discoverySource': None,
                    'checkedAt': checked_at,
                }
            else:
                status[ticker] = prior or {
                    'status': 'not_scanned',
                    'reason': 'no_yahoo_discovery_scan_yet',
                    'latestStoredDate': latest or None,
                    'latestStoredOfficial': False,
                    'officialSourceUrl': None,
                    'discoverySource': None,
                    'checkedAt': checked_at,
                }
    write_json_bundle({
        root / 'data.json': updated_companies,
        root / 'historical_data.json': updated_history,
        root / 'history_status.json': status,
    })
    return {
        'companies': len(companies),
        'added': added,
        'pending_official': sum(item['status'] == 'pending_official' for item in status.values()),
        'discovery_failed': sum(item['status'] == 'discovery_failed' for item in status.values()),
        'official_verified': sum(item.get('latestStoredOfficial', False) for item in status.values()),
    }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Refresh officially reviewed earnings history')
    parser.add_argument('--scan', action='store_true', help='Scan all companies with Yahoo for date-only candidates')
    parser.add_argument('--root', default='.', help='Website data directory')
    args = parser.parse_args()
    summary = refresh_site_data(args.root, scan=args.scan)
    print(json.dumps(summary, ensure_ascii=False))
    if args.scan and summary['discovery_failed'] == summary['companies']:
        raise SystemExit('All Yahoo discovery requests lacked usable reported EPS')
