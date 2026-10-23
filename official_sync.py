"""Check all active issuers, publish only source-verified quarterly releases."""
import argparse
import hashlib
import gzip
import copy
import json
import re
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from lxml import html

from official_sources import parse_earnings_release, parse_earnings_filing, parse_inline_quarter
from issuer_mapping import fill_missing_ciks
from quarterly_policy import retain_history, retain_manifest, company_fields, merge_manifest_record, preserve_release_provenance
from verified_history import apply_official_records, write_json_bundle


class OfficialScanDeferred(Exception):
    """The source was not checked because this run reached its time budget."""


_DIRECT_SEC = False


def decode_sec_body(body):
    if body.startswith(b'\x1f\x8b'):
        return gzip.decompress(body)
    return body


def fetch_sec(url):
    """Try the authenticated proxy, then the same public official SEC URL directly."""
    global _DIRECT_SEC
    from update_data import _sec_request, SEC_HEADERS, SEC_PROXY_URL
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in ('www.sec.gov','data.sec.gov') or p.username or p.password:
        raise ValueError('Only official SEC HTTPS URLs are supported')
    if not _DIRECT_SEC and SEC_PROXY_URL:
        try:
            response = _sec_request(url, timeout=20)
            if response.status_code == 200:
                return decode_sec_body(response.content if hasattr(response,'content') else response._body)
        except (OSError, ValueError):
            pass
        except Exception:
            # requests and urllib use different transport exception types; do not leak URLs.
            pass
    try:
        with urlopen(Request(url,headers={**SEC_HEADERS,'Accept-Encoding':'gzip'}),timeout=20) as response:
            body=response.read()
        _DIRECT_SEC = True
        return decode_sec_body(body)
    except HTTPError as exc:
        raise OSError(f'Official SEC HTTP {exc.code}') from None
    except Exception:
        raise OSError('Official SEC connection unavailable') from None


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
    tree = html.fromstring(document.encode('utf-8') if isinstance(document, str) else document)
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
    records, pending, failures, metric_pending = {}, 0, 0, 0
    source_errors=[]
    # Main SEC submissions may cover only weeks for high-volume debt issuers.
    cutoff=today-timedelta(days=550)
    if filings and min(date.fromisoformat(r['filingDate']) for r in filings)>cutoff:
        supplements=submissions.get('filings',{}).get('files',[])
        for entry in sorted(supplements,key=lambda r:r.get('filingTo',''),reverse=True)[:5]:
            name=entry.get('name','')
            if not re.fullmatch(r'CIK'+str(cik).zfill(10)+r'-submissions-\d+\.json',name):continue
            if entry.get('filingTo','')<cutoff.isoformat() or entry.get('filingFrom','')>today.isoformat():continue
            url='https://data.sec.gov/submissions/'+name
            try:
                payload=json.loads(fetch(url))
                filings += _filings({'filings':{'recent':payload}},today)
            except (OSError,TimeoutError) as exc:
                failures+=1
                source_errors.append({'stage':'submission_history','sourceUrl':url,'errorType':type(exc).__name__})
            except (ValueError,TypeError):
                pending+=1
        filings=list({r['accessionNumber']:r for r in filings}.values())
    releases = [r for r in filings if r['form'] in ('8-K','8-K/A') and '2.02' in re.split(r'[,;\s]+', r['items'])
                and r['reportDate'] and (today-date.fromisoformat(r['filingDate'])).days <= 550]
    releases.sort(key=lambda r:r['filingDate'], reverse=True)
    for event in releases[:12]:
        base = _base(cik, event)
        try:
            primary_doc=fetch(base + event['primaryDocument'])
            links = _exhibit_links(primary_doc, base)
        except (OSError, TimeoutError) as exc:
            failures += 1
            source_errors.append({'stage':'announcement_filing','sourceUrl':base+event['primaryDocument'],'errorType':type(exc).__name__})
            continue
        except (ValueError, html.etree.ParserError):
            pending += 1
            continue
        accepted = False
        event_conflict=False
        first_exhibit=None
        for url in links+[base+event['primaryDocument']]:
            try:
                if url==base+event['primaryDocument']:
                    if event_conflict:continue
                    release=parse_earnings_filing(primary_doc,event['reportDate'],event['filingDate'],today,exhibit=first_exhibit)
                else:
                    release_doc = fetch(url)
                    if first_exhibit is None:first_exhibit=release_doc
                    release = parse_earnings_release(release_doc, event['reportDate'], event['filingDate'], today)
            except (OSError, TimeoutError) as exc:
                failures += 1
                source_errors.append({'stage':'earnings_release','sourceUrl':url,'errorType':type(exc).__name__})
                continue
            except (ValueError, html.etree.ParserError):
                continue
            matches = [r for r in filings if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') and r['reportDate'] and
                       (r['reportDate'] == release['periodEnd'] if release['periodEnd'] else
                        -7 <= (date.fromisoformat(r['filingDate'])-date.fromisoformat(release['date'])).days <= 45
                        and 0 < (date.fromisoformat(release['date'])-date.fromisoformat(r['reportDate'])).days <= 180)]
            matches.sort(key=lambda r:r['filingDate'], reverse=True)
            metrics = None
            metric_url = url
            matched_filing = None
            identity_conflict = False
            for candidate in matches[:2]:
                candidate_url = _base(cik, candidate) + candidate['primaryDocument']
                try:
                    parsed = parse_inline_quarter(fetch(candidate_url), release['periodEnd'] or candidate['reportDate'],cik=cik)
                except (OSError, TimeoutError) as exc:
                    failures += 1
                    metric_pending += 1
                    source_errors.append({'stage':'metrics','sourceUrl':candidate_url,'errorType':type(exc).__name__})
                    continue
                except (ValueError, html.etree.ParserError):
                    metric_pending += 1
                    continue
                if (release.get('fiscalYear') is not None and
                        (release['fiscalYear'], release['fiscalQuarter']) != (parsed['fiscalYear'], parsed['fiscalQuarter'])):
                    identity_conflict = True
                    event_conflict = True
                    metric_pending += 1
                    continue
                metrics, metric_url, matched_filing = parsed, candidate_url, candidate
                break
            if metrics is None and identity_conflict:
                pending += 1
                continue
            if metrics is None:
                # A published quarter may be admitted before its 10-Q, but only with explicit fiscal identity.
                if not release.get('periodEnd') or not release.get('fiscalYear') or not release.get('fiscalQuarter'):
                    continue
                metrics = {'epsGaapDiluted':None, 'revenue':None, 'epsBasis':None, 'currency':'USD', 'periodScope':'quarter'}
            if metrics.get('epsGaapDiluted') is None or metrics.get('revenue') is None:
                metric_pending += 1
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
                preserve_release_provenance(prior,record)
            accepted = True
            break
        if not accepted:
            pending += 1
    rows = sorted(records.values(), key=lambda r:r['periodEnd'], reverse=True)[:5]
    return rows, {'releaseCandidates':len(releases[:12]), 'parsedQuarters':len(rows), 'parsePending':pending, 'metricPending':metric_pending, 'requestFailures':failures,'sourceErrors':source_errors[:20]}


def _now(today):
    current = datetime.now(timezone.utc)
    # Deterministic historic test date without a future official check timestamp.
    return current if current.astimezone(ZoneInfo('America/New_York')).date() == today else datetime.combine(today, datetime.min.time(), timezone.utc)


def _due(company, status, today, full):
    if full:
        return True
    checked = status.get('officialCheckedAt')
    if status.get('status') in ('official_source_failed','official_check_deferred'):
        return True
    if not checked:
        return True
    try:
        if _now(today) - datetime.fromisoformat(checked.replace('Z','+00:00')) >= timedelta(hours=24):
            return True
    except (ValueError,TypeError):
        return True
    try:
        report_date = company.get('reportDate')
        latest_release = company.get('latestPublishedDate')
        return bool((report_date and -10 <= (date.fromisoformat(report_date)-today).days <= 21)
                    or (latest_release and -14 <= (date.fromisoformat(latest_release)-today).days <= 0))
    except (ValueError, TypeError):
        return True


def sync_all(root, today=None, fetch=None, full=False, nvda_sync=None, budget_seconds=2400):
    root = Path(root)
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    checked = _now(today).isoformat().replace('+00:00','Z')
    companies = json.loads((root/'data.json').read_text())
    history = json.loads((root/'historical_data.json').read_text())
    manifest = json.loads((root/'official_history.json').read_text())
    status = json.loads((root/'history_status.json').read_text())
    mapping = json.loads((root/'sp500_mapping.json').read_text())
    mapping=fill_missing_ciks(companies,history,mapping,fetch or fetch_sec)
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
    groups=dict(sorted(groups.items(),key=lambda pair:(not any(status.get(t,{}).get('status') in ('official_source_failed','official_check_deferred') for t in pair[1]),min(status.get(t,{}).get('officialCheckedAt') or '' for t in pair[1]))))
    source_failures, parsed_count, issuers_checked, deferred = 0, 0, 0, 0
    real_fetch = fetch is None
    transport = fetch or fetch_sec
    last_request = [0.0]
    request_lock = threading.Lock()
    deadline = time.monotonic()+budget_seconds
    cache_root = root/'.sec_cache'/'official'
    def paced(url):
        cache_file = cache_root/(hashlib.sha256(url.encode()).hexdigest()+'.body') if real_fetch and '/Archives/' in url else None
        if cache_file is not None and cache_file.exists():
            return decode_sec_body(cache_file.read_bytes())
        if time.monotonic()>deadline:
            raise OfficialScanDeferred('Official scan time budget exhausted')
        if real_fetch:
            with request_lock:
                pause = 0.15 - (time.monotonic()-last_request[0])
                if pause > 0:
                    time.sleep(pause)
                last_request[0] = time.monotonic()
        body = transport(url)
        if cache_file is not None:
            cache_root.mkdir(parents=True,exist_ok=True)
            payload=body.encode('utf-8') if isinstance(body,str) else body
            cache_file.write_bytes(gzip.compress(payload,compresslevel=1))
        return body
    def inspect(cik):
        print(f'Checking official issuer: {",".join(groups[cik])}',flush=True)
        submissions = json.loads(paced(f'https://data.sec.gov/submissions/CIK{cik}.json'))
        return check_issuer(cik,submissions,paced,today)
    # Network work is concurrent; validated data merges and publication remain serial.
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {cik:pool.submit(inspect,cik) for cik in groups}
        for index, (cik, aliases) in enumerate(groups.items(), 1):
            counted=False
            try:
                records, details = futures[cik].result()
                issuers_checked += 1
                counted=True
                source_failures += bool(details['requestFailures'])
                state = 'official_source_failed' if details['requestFailures'] else 'official_parse_pending' if details['parsePending'] or details['metricPending'] else 'official_source_checked'
                for ticker in aliases:
                    incoming = [{**r,'ticker':ticker} for r in records]
                    # Keep original verified figures when this run only confirms the release.
                    by_period = {(r['ticker'],r['periodEnd']):r for r in manifest}
                    incoming=[merge_manifest_record(by_period.get((ticker,r['periodEnd']),{}),r) for r in incoming]
                    history, added = apply_official_records(companies, history, incoming, today)
                    parsed_count += added
                    manifest = retain_manifest(manifest + incoming)
                    prior_status={k:v for k,v in status.get(ticker,{}).items() if k not in ('errorType','queuedAt')}
                    status[ticker] = {**prior_status, **details, 'status':state, 'reason':'sec_earnings_exhibits_checked' if state=='official_source_checked' else 'sec_release_or_metric_check_pending',
                        'discoverySource':'SEC submissions and earnings exhibits', 'officialCheckedAt':checked, 'checkedAt':checked, 'cik':cik}
            except OfficialScanDeferred:
                deferred += len(aliases)
                for ticker in aliases:
                    status[ticker]={**status.get(ticker,{}),'status':'official_check_deferred','reason':'official_scan_time_budget_exhausted','queuedAt':checked}
            except Exception as exc:
                source_failures += 1
                if not counted:issuers_checked += 1
                print(f'Official issuer check failed: {",".join(aliases)}; error type: {type(exc).__name__}',flush=True)
                for ticker in aliases:
                    status[ticker] = {**status.get(ticker,{}), 'status':'official_source_failed', 'reason':'official_validation_failed' if isinstance(exc,ValueError) else 'sec_request_or_configuration_failed', 'errorType':type(exc).__name__, 'officialCheckedAt':checked, 'checkedAt':checked, 'cik':cik}
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
    enriched=[]
    for company in companies:
        entry=dict(company)
        issuer=mapping.get(entry['ticker'],{})
        if issuer.get('tickerStatus') in ('historical_alias','unconfirmed'):
            entry['tickerIdentityStatus']=issuer['tickerStatus']
            entry['officialCurrentTickers']=issuer.get('officialTickers',[])
            if entry.get('reportDateSource')!='official':
                entry['reportDate']=None
                entry['reportDateSource']=None
                entry['reportDateSourceUrl']=None
        enriched.append(company_fields(entry,history,today))
    companies=enriched
    for company in companies:
        ticker = company['ticker']
        rows = history[ticker]
        latest = rows[0] if rows else {}
        status[ticker] = {**status.get(ticker,{}), 'recordCount':len(rows), 'officialQuarterCount':sum(r.get('verificationStatus')=='official_verified' for r in rows),
                         'latestStoredDate':latest.get('date'), 'latestStoredOfficial':latest.get('verificationStatus')=='official_verified',
                         'officialSourceUrl':latest.get('releaseSourceUrl') if latest.get('verificationStatus')=='official_verified' else None,
                         'metricsVerifiedQuarterCount':sum(r.get('verificationStatus')=='official_verified' and r.get('epsBasis')=='GAAP diluted' and r.get('eps_reported') not in (None,'-') and r.get('revenue_reported') not in (None,'-') for r in rows)}
    summary = {'companies':len(companies), 'issuersChecked':issuers_checked,'issuerTargets':len(groups),'deferredCompanies':deferred, 'newRecords':parsed_count,
               'sourceFailures':source_failures, 'pendingCompanies':sum(s.get('status')!='official_source_checked' or s.get('officialQuarterCount',0)<5 or s.get('metricsVerifiedQuarterCount',0)<5 for s in status.values()),
               'officialQuarters':sum(s.get('officialQuarterCount',0) for s in status.values()),
               'fiveOfficialQuarterCompanies':sum(s.get('officialQuarterCount',0)==5 for s in status.values()),
               'fiveCompleteMetricCompanies':sum(s.get('metricsVerifiedQuarterCount',0)==5 for s in status.values()),
               'sourceFailedCompanies':sum(s.get('status')=='official_source_failed' for s in status.values()),
               'checkedAt':checked, 'healthy':source_failures==0 and deferred==0}
    write_json_bundle({root/'data.json':companies,root/'historical_data.json':history,
        root/'official_history.json':retain_manifest(manifest),root/'history_status.json':status,
        root/'official_scan_state.json':summary,root/'sp500_mapping.json':mapping})
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    summary=sync_all(args.root,full=args.full)
    print(json.dumps(summary))
    if not summary['healthy']:
        raise SystemExit('Official checks incomplete; prior history preserved and per-company status saved')
