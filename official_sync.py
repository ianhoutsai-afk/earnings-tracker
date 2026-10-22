"""Check all active issuers, publish only source-verified quarterly releases."""
import argparse
import copy
import json
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from lxml import html

from official_sources import parse_earnings_release, parse_inline_quarter
from quarterly_policy import retain_history, retain_manifest, company_fields
from verified_history import apply_official_records, write_json_bundle


def fetch_sec(url):
    from update_data import _sec_request
    response = _sec_request(url, timeout=25)
    if response.status_code != 200:
        raise OSError(f'SEC HTTP {response.status_code}')
    # Reuse existing transport, including the configured authenticated proxy.
    if hasattr(response, 'text'):
        return response.text
    return response._body.decode('utf-8')


def _filings(submissions, today):
    recent = submissions.get('filings', {}).get('recent', {})
    rows = []
    for i, form in enumerate(recent.get('form', [])):
        row = {'form':form}
        for field in ('accessionNumber','primaryDocument','filingDate','reportDate','items'):
            values = recent.get(field, [])
            row[field] = values[i] if i < len(values) else ''
        if (row['filingDate'] and date.fromisoformat(row['filingDate']) <= today
                and re.fullmatch(r'\d{10}-\d{2}-\d{6}', row['accessionNumber'])
                and re.fullmatch(r'[A-Za-z0-9_.-]+', row['primaryDocument'])):
            rows.append(row)
    return rows


def _base(cik, filing):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{filing['accessionNumber'].replace('-', '')}/"


def _exhibit_links(document, base):
    tree = html.fromstring(document)
    result = []
    for link in tree.xpath('//a[@href]'):
        label = ' '.join(link.itertext()) + ' ' + link.get('href')
        if not re.search(r'(?i)(?:99[._-]?1|earnings|press\s*release)', label):
            continue
        target = urljoin(base, link.get('href')).split('#')[0]
        parsed = urlparse(target)
        if parsed.scheme == 'https' and parsed.hostname == 'www.sec.gov' and target.startswith(base) and not parsed.query:
            result.append(target)
    return list(dict.fromkeys(result))[:4]


def check_issuer(cik, submissions, fetch, today):
    filings = _filings(submissions, today)
    releases = [r for r in filings if r['form'] in ('8-K','8-K/A') and '2.02' in re.split(r'[,;\s]+', r['items'])
                and r['reportDate'] and (today-date.fromisoformat(r['filingDate'])).days <= 550]
    releases.sort(key=lambda r:r['filingDate'], reverse=True)
    records, pending, failures = {}, 0, 0
    for event in releases[:12]:
        base = _base(cik, event)
        try:
            links = _exhibit_links(fetch(base + event['primaryDocument']), base)
        except (OSError, TimeoutError):
            failures += 1
            continue
        except (ValueError, html.etree.ParserError):
            pending += 1
            continue
        accepted = False
        for url in links:
            try:
                release_doc = fetch(url)
                release = parse_earnings_release(release_doc, event['reportDate'], event['filingDate'], today)
            except (OSError, TimeoutError):
                failures += 1
                continue
            except (ValueError, html.etree.ParserError):
                continue
            matches = [r for r in filings if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') and r['reportDate'] == release['periodEnd']]
            matches.sort(key=lambda r:r['filingDate'], reverse=True)
            metrics = None
            metric_url = url
            matched_filing = None
            for candidate in matches[:2]:
                candidate_url = _base(cik, candidate) + candidate['primaryDocument']
                try:
                    parsed = parse_inline_quarter(fetch(candidate_url), release['periodEnd'])
                except (ValueError, OSError, TimeoutError, html.etree.ParserError):
                    continue
                if (release.get('fiscalYear') is not None and
                        (release['fiscalYear'], release['fiscalQuarter']) != (parsed['fiscalYear'], parsed['fiscalQuarter'])):
                    continue
                metrics, metric_url, matched_filing = parsed, candidate_url, candidate
                break
            if metrics is None:
                # A published quarter may be admitted before its 10-Q, but only with explicit fiscal identity.
                if not release.get('fiscalYear') or not release.get('fiscalQuarter'):
                    continue
                metrics = {'epsGaapDiluted':None, 'revenue':None, 'epsBasis':None, 'currency':'USD', 'periodScope':'quarter'}
            record = {**release, **metrics, 'releaseSourceUrl':url, 'metricSourceUrl':metric_url,
                      'verifiedAt':today.isoformat(), 'releaseFilingDate':event['filingDate'],
                      'releaseAccession':event['accessionNumber']}
            if matched_filing:
                record.update(secUrl=metric_url, form=matched_filing['form'].replace('/A',''),
                              filingDate=matched_filing['filingDate'], accessionNumber=matched_filing['accessionNumber'])
            prior = records.get(record['periodEnd'])
            if prior is None:
                records[record['periodEnd']] = record
            elif record['date'] < prior['date']:
                # Keep newest revision metrics and earliest confirmed original release/date source.
                prior['date'] = record['date']
                prior['releaseSourceUrl'] = record['releaseSourceUrl']
            accepted = True
            break
        if not accepted:
            pending += 1
    rows = sorted(records.values(), key=lambda r:r['periodEnd'], reverse=True)[:5]
    return rows, {'releaseCandidates':len(releases[:12]), 'parsedQuarters':len(rows), 'parsePending':pending, 'requestFailures':failures}


def _now(today):
    current = datetime.now(timezone.utc)
    # Deterministic historic test date without a future official check timestamp.
    return current if current.date() == today else datetime.combine(today, datetime.min.time(), timezone.utc)


def _due(company, status, today, full):
    if full:
        return True
    checked = status.get('officialCheckedAt')
    if not checked or checked[:10] < today.isoformat():
        return True
    raw = company.get('reportDate')
    try:
        return raw is not None and -10 <= (date.fromisoformat(raw)-today).days <= 21
    except ValueError:
        return True


def sync_all(root, today=None, fetch=None, full=False, nvda_sync=None):
    root = Path(root)
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    checked = _now(today).isoformat().replace('+00:00','Z')
    companies = json.loads((root/'data.json').read_text())
    history = json.loads((root/'historical_data.json').read_text())
    manifest = json.loads((root/'official_history.json').read_text())
    status = json.loads((root/'history_status.json').read_text())
    mapping = json.loads((root/'sp500_mapping.json').read_text())
    tickers = {c['ticker'] for c in companies}
    if set(history) != tickers:
        raise ValueError('Company/history ticker set mismatch; no publication')
    history, _ = apply_official_records(companies, history, manifest, today)
    groups = {}
    for company in companies:
        ticker = company['ticker']
        if ticker == 'NVDA' or not _due(company, status.get(ticker, {}), today, full):
            continue
        cik = mapping.get(ticker, {}).get('cik')
        if not isinstance(cik, str) or not re.fullmatch(r'\d{1,10}', cik):
            status[ticker] = {**status.get(ticker,{}), 'status':'official_mapping_missing', 'reason':'sec_cik_mapping_missing', 'officialCheckedAt':checked}
            continue
        groups.setdefault(cik.zfill(10), []).append(ticker)
    source_failures, parsed_count = 0, 0
    sec_preflight_failed = False
    real_fetch = fetch is None
    transport = fetch or fetch_sec
    last_request = [0.0]
    def paced(url):
        if real_fetch:
            pause = 0.3 - (time.monotonic()-last_request[0])
            if pause > 0:
                time.sleep(pause)
        last_request[0] = time.monotonic()
        return transport(url)
    for index, (cik, aliases) in enumerate(groups.items(), 1):
        try:
            if sec_preflight_failed:
                raise OSError('SEC preflight unavailable')
            submissions = json.loads(paced(f'https://data.sec.gov/submissions/CIK{cik}.json'))
            records, details = check_issuer(cik, submissions, paced, today)
            source_failures += bool(details['requestFailures'])
            state = 'official_source_failed' if details['requestFailures'] else 'official_parse_pending' if details['parsePending'] else 'official_source_checked'
            for ticker in aliases:
                incoming = [{**r,'ticker':ticker} for r in records]
                # Keep original verified figures when this run only confirms the release.
                by_period = {(r['ticker'],r['periodEnd']):r for r in manifest}
                for r in incoming:
                    prior = by_period.get((ticker,r['periodEnd']))
                    if prior:
                        for field in ('epsGaapDiluted','revenue'):
                            if r.get(field) is None and prior.get(field) is not None:
                                r[field] = prior[field]
                                r['metricSourceUrl'] = prior.get('metricSourceUrl') or prior['releaseSourceUrl']
                                if field == 'epsGaapDiluted':r['epsBasis'] = 'GAAP diluted'
                        r['date'],r['releaseSourceUrl'] = prior['date'],prior['releaseSourceUrl']
                history, added = apply_official_records(companies, history, incoming, today)
                parsed_count += added
                manifest = retain_manifest(manifest + incoming)
                status[ticker] = {**status.get(ticker,{}), **details, 'status':state, 'reason':'sec_earnings_exhibits_checked' if state=='official_source_checked' else 'sec_release_or_metric_check_pending',
                    'discoverySource':'SEC submissions and earnings exhibits', 'officialCheckedAt':checked, 'checkedAt':checked, 'cik':cik}
        except Exception as exc:
            source_failures += 1
            if index == 1:
                # Avoid hammering 500 issuers when shared infrastructure is unavailable.
                sec_preflight_failed = True
            for ticker in aliases:
                status[ticker] = {**status.get(ticker,{}), 'status':'official_source_failed', 'reason':'sec_request_or_configuration_failed', 'officialCheckedAt':checked, 'checkedAt':checked, 'cik':cik}
        if index % 50 == 0 or index == len(groups):
            print(f'Official SEC issuer checks: {index}/{len(groups)}; failures: {source_failures}', flush=True)
    # NVIDIA stays on its independently tested, earlier-than-10-Q newsroom source.
    if 'NVDA' in tickers:
        from nvda_history import sync_nvda
        try:
            with tempfile.TemporaryDirectory() as temp:
                stage = Path(temp)
                for name, value in [('data.json',companies),('historical_data.json',history),('official_history.json',manifest),('history_status.json',status)]:
                    (stage/name).write_text(json.dumps(value))
                (nvda_sync or sync_nvda)(stage, today=today)
                history['NVDA'] = json.loads((stage/'historical_data.json').read_text())['NVDA']
                manifest = [r for r in manifest if r['ticker']!='NVDA'] + [r for r in json.loads((stage/'official_history.json').read_text()) if r['ticker']=='NVDA']
                status['NVDA'] = json.loads((stage/'history_status.json').read_text())['NVDA']
                status['NVDA']['officialCheckedAt'] = checked
        except Exception:
            source_failures += 1
            status['NVDA'] = {**status.get('NVDA',{}),'status':'official_source_failed','reason':'nvda_newsroom_request_or_parse_failed','officialCheckedAt':checked,'checkedAt':checked}
    history = retain_history(history, today)
    companies = [company_fields(c,history,today) for c in companies]
    for company in companies:
        ticker = company['ticker']
        rows = history[ticker]
        latest = rows[0] if rows else {}
        status[ticker] = {**status.get(ticker,{}), 'recordCount':len(rows), 'officialQuarterCount':sum(r.get('verificationStatus')=='official_verified' for r in rows),
                         'latestStoredDate':latest.get('date'), 'latestStoredOfficial':latest.get('verificationStatus')=='official_verified',
                         'officialSourceUrl':latest.get('releaseSourceUrl') if latest.get('verificationStatus')=='official_verified' else None}
    summary = {'companies':len(companies), 'issuersChecked':len(groups), 'newRecords':parsed_count,
               'sourceFailures':source_failures, 'pendingCompanies':sum(s.get('status') in ('official_parse_pending','official_mapping_missing') for s in status.values()),
               'checkedAt':checked, 'healthy':source_failures==0}
    write_json_bundle({root/'data.json':companies,root/'historical_data.json':history,
        root/'official_history.json':retain_manifest(manifest),root/'history_status.json':status,
        root/'official_scan_state.json':summary})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    summary=sync_all(args.root,full=args.full)
    print(json.dumps(summary))
    if not summary['healthy']:
        raise SystemExit('Official source checks failed; prior history preserved and failure status saved')
