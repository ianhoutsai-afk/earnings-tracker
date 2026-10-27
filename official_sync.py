"""Check all active issuers, publish only source-verified quarterly releases."""
import argparse
import os
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

from official_sources import parse_earnings_release, parse_earnings_filing, parse_inline_quarter, _completed_period_end, _fiscal_identity
from official_metrics import parse_companyfacts, parse_statement_metrics
from issuer_mapping import fill_missing_ciks
from quarterly_policy import retain_history, retain_manifest, company_fields, merge_manifest_record, preserve_release_provenance
from verified_history import apply_official_records, write_json_bundle
from coverage_state import company_status, PARSER_VERSION


class OfficialScanDeferred(Exception):
    """The source was not checked because this run reached its time budget."""


class SecLimiter:
    """One process-wide gate, including direct fallback and retries."""
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.next_request = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            pause = self.next_request - self.clock()
            if pause > 0:
                self.sleep(pause)
            self.next_request = self.clock() + 0.2


SEC_LIMITER = SecLimiter()


_DIRECT_SEC = False


def decode_sec_body(body):
    if body.startswith(b'\x1f\x8b'):
        return gzip.decompress(body)
    return body


def fetch_sec(url, timeout=20):
    """Try the authenticated proxy, then the same public official SEC URL directly."""
    global _DIRECT_SEC
    from update_data import _sec_request, SEC_HEADERS, SEC_PROXY_URL
    p = urlparse(url)
    if p.scheme != 'https' or p.hostname not in ('www.sec.gov','data.sec.gov') or p.username or p.password:
        raise ValueError('Only official SEC HTTPS URLs are supported')
    if not _DIRECT_SEC and SEC_PROXY_URL:
        try:
            SEC_LIMITER.wait()
            response = _sec_request(url, timeout=timeout)
            if response.status_code == 200:
                return decode_sec_body(response.content if hasattr(response,'content') else response._body)
        except (OSError, ValueError):
            pass
        except Exception:
            # requests and urllib use different transport exception types; do not leak URLs.
            pass
    try:
        SEC_LIMITER.wait()
        with urlopen(Request(url,headers={**SEC_HEADERS,'Accept-Encoding':'gzip'}),timeout=timeout) as response:
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
        if not re.search(r'(?i)(?:99[._-]?1|(?<!\d)99(?![\d.])|earnings|(?:press|news)\s*release)', label):
            continue
        target = urljoin(base, link.get('href')).split('#')[0]
        parsed = urlparse(target)
        if parsed.scheme == 'https' and parsed.hostname == 'www.sec.gov' and target.startswith(base) and not parsed.query:
            result.append(target)
    return list(dict.fromkeys(result))[:4]


def _parse_events(cik, filings, fetch, today):
    records, pending, failures, metric_pending = {}, 0, 0, 0
    source_errors=[]
    facts_payload = None
    releases = [r for r in filings if r['form'] in ('8-K','8-K/A') and '2.02' in re.split(r'[,;\s]+', r['items'])
                and r['reportDate']]
    releases.sort(key=lambda r:r['filingDate'], reverse=True)
    for event in releases:
        base = _base(cik, event)
        try:
            primary_doc=fetch(base + event['primaryDocument'])
            links = [link for link in _exhibit_links(primary_doc, base) if link != base+event['primaryDocument']]
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
        first_exhibit_url=None
        for url in links+[base+event['primaryDocument']]:
            try:
                if url==base+event['primaryDocument']:
                    if event_conflict:continue
                    release=parse_earnings_filing(primary_doc,event['reportDate'],event['filingDate'],today,exhibit=first_exhibit)
                else:
                    release_doc = fetch(url)
                    if first_exhibit is None:
                        first_exhibit,first_exhibit_url=release_doc,url
                    release = parse_earnings_release(release_doc, event['reportDate'], event['filingDate'], today)
            except (OSError, TimeoutError) as exc:
                failures += 1
                source_errors.append({'stage':'earnings_release','sourceUrl':url,'errorType':type(exc).__name__})
                continue
            except (ValueError, html.etree.ParserError):
                continue
            matches = [r for r in filings if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') and r['reportDate']
                       and r['reportDate'] <= r['filingDate']
                       and -45 <= (date.fromisoformat(r['filingDate'])-date.fromisoformat(release['date'])).days <= 45
                       and (r['reportDate'] == release['periodEnd'] if release['periodEnd'] else
                            -7 <= (date.fromisoformat(r['filingDate'])-date.fromisoformat(release['date'])).days
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
                # These two releases explicitly name FY2026; their original
                # 10-Q DEI focus says 2025, while the issuer's year-end 10-K
                # confirms the same fiscal year. Never generalize this exception.
                reviewed_workday = {
                    '2025-07-31': (2, '000132781125000181/wday-07312025x991.htm', '000132781125000184/wday-20250731.htm'),
                    '2025-10-31': (3, '000132781125000196/wday-10312025x991.htm', '000132781125000198/wday-20251031.htm'),
                }.get(parsed['periodEnd'])
                wday_base='https://www.sec.gov/Archives/edgar/data/1327811/'
                if (str(cik).lstrip('0') == '1327811' and reviewed_workday
                        and (release.get('fiscalYear'),release.get('fiscalQuarter')) == (2026,reviewed_workday[0])
                        and (parsed['fiscalYear'],parsed['fiscalQuarter']) == (2025,reviewed_workday[0])
                        and url == wday_base+reviewed_workday[1] and candidate_url == wday_base+reviewed_workday[2]):
                    parsed['fiscalYear']=2026
                    parsed['fiscalIdentityCorrectionEvidence']={
                        'reason':'issuer_release_and_year_end_filing_confirm_fiscal_2026',
                        'filingFiscalYear':2025,'releaseFiscalYear':2026,
                        'releaseSourceUrl':url,'filingSourceUrl':candidate_url,
                        'supportingAnnualUrl':wday_base+'000132781126000014/wday-20260131.htm'}
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
            # Fill missing fields only, preserving independent per-field provenance.
            # A valid inline context establishes USD; otherwise an explicit USD
            # statement is required before reading untagged financial tables.
            document = primary_doc if url == base+event['primaryDocument'] else release_doc
            statement_url = url
            if matched_filing and url == base+event['primaryDocument'] and first_exhibit is not None:
                headline = ' '.join(' '.join(html.fromstring(first_exhibit).itertext()).split())[:1200]
                exhibit_end = _completed_period_end(headline,date.fromisoformat(release['date']))
                exhibit_identity = _fiscal_identity(headline)
                if (re.search(r'(?i)\b(?:reports?|announces?)\b.{0,180}\b(?:results|earnings)\b',headline)
                        and ((exhibit_end is not None and exhibit_end.isoformat() == metrics['periodEnd'])
                             or (exhibit_end is None and exhibit_identity == (metrics['fiscalYear'],metrics['fiscalQuarter'])))):
                    document,statement_url=first_exhibit,first_exhibit_url
            text = ' '.join(html.fromstring(document).itertext())
            currency = metrics.get('currency') if matched_filing else ('USD' if re.search(r'(?i)U\.S\. dollars|USD|United States dollars', text) else None)
            statement = parse_statement_metrics(document, metrics.get('periodEnd') or release['periodEnd'],
                currency=currency, fiscal_year=metrics.get('fiscalYear') or release.get('fiscalYear'),
                fiscal_quarter=metrics.get('fiscalQuarter') or release.get('fiscalQuarter'))
            for field, state_field, source_field in [('epsGaapDiluted','epsVerificationStatus','epsSourceUrl'), ('revenue','revenueVerificationStatus','revenueSourceUrl')]:
                if metrics.get(field) is not None:
                    metrics[state_field] = 'verified'
                    metrics[source_field] = metric_url
                    statement_value = statement.get(field)
                    precision = float(statement.get('metricLocators',{}).get(field,{}).get('precision','0'))
                    if statement[state_field] == 'conflict' or (statement_value is not None
                            and abs(metrics[field]-statement_value) > precision/2 + 1e-9):
                        metrics[state_field] = 'conflict'
                        evidence = statement.get('metricConflicts',{}).get(field,[])
                        metrics.setdefault('metricConflicts',{})[field] = [
                            {'value':metrics[field],'sourceUrl':metric_url}] + (
                            [{**e,'sourceUrl':statement_url} for e in evidence] if evidence else
                            [{'value':statement_value,'sourceUrl':statement_url,'locator':statement['metricLocators'].get(field)}])
                elif statement.get(field) is not None:
                    metrics[field], metrics[state_field], metrics[source_field] = statement[field], 'verified', statement_url
                    metrics.setdefault('metricLocators', {})[field] = statement['metricLocators'][field]
                else:
                    metrics[state_field] = statement.get(state_field, 'pending')
                    if metrics[state_field] == 'conflict':
                        metrics.setdefault('metricConflicts',{})[field] = [
                            {**e,'sourceUrl':statement_url} for e in statement['metricConflicts'][field]]
            if matched_filing and (metrics.get('epsGaapDiluted') is None or metrics.get('revenue') is None):
                facts_url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{str(cik).zfill(10)}.json'
                try:
                    if facts_payload is None:
                        facts_payload = json.loads(fetch(facts_url))
                    facts = parse_companyfacts(facts_payload, cik=cik, period_end=metrics['periodEnd'],
                        accessions={matched_filing['accessionNumber']}, today=today)
                    for field, state_field, source_field in [('epsGaapDiluted','epsVerificationStatus','epsSourceUrl'), ('revenue','revenueVerificationStatus','revenueSourceUrl')]:
                        if metrics.get(field) is None and facts.get(field) is not None and metrics[state_field] != 'conflict':
                            metrics[field], metrics[state_field], metrics[source_field] = facts[field], 'verified', facts_url
                            metrics.setdefault('metricLocators', {})[field] = facts['metricLocators'][field]
                        elif metrics.get(field) is None and facts[state_field] == 'conflict':
                            metrics[state_field] = 'conflict'
                            metrics.setdefault('metricConflicts',{}).setdefault(field,[]).extend(
                                {**e,'sourceUrl':facts_url} for e in facts['metricConflicts'][field])
                except (OSError, TimeoutError) as exc:
                    failures += 1
                    source_errors.append({'stage':'companyfacts','sourceUrl':facts_url,'errorType':type(exc).__name__})
                except (ValueError, TypeError):
                    pass
            if metrics.get('epsGaapDiluted') is not None:
                metrics['epsBasis'] = 'GAAP diluted'
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
    return rows, {'releaseCandidates':len(releases), 'parsedQuarters':len(rows), 'parsePending':pending, 'metricPending':metric_pending, 'requestFailures':failures,'sourceErrors':source_errors}


def check_issuer(cik, submissions, fetch, today, *, depth=5, progress=None, known_records=None):
    """Resume a versioned source cursor; never call a partial check complete."""
    if submissions.get('cik') is not None and str(submissions['cik']).zfill(10) != str(cik).zfill(10):
        raise ValueError('Submission issuer mismatch')
    progress = copy.deepcopy(progress or {})
    same_parser = progress.get('parserVersion') == PARSER_VERSION
    completed = set(progress.get('completedAccessions', [])) if same_parser else set()
    records = {r['periodEnd']:copy.deepcopy(r) for r in (known_records or [])}
    candidates = {c['key']:c for c in progress.get('candidates', [])} if same_parser else {}
    filings = {r['accessionNumber']:r for r in progress.get('filings', [])}
    recent = {r['accessionNumber']:r for r in _filings(submissions, today)
              if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') or (r['form'] in ('8-K','8-K/A') and '2.02' in re.split(r'[,;\s]+',r['items']))}
    if any(r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') and a not in filings for a,r in recent.items()):
        # An announcement rejected before its report arrived must be revisited.
        completed.difference_update(c.get('accession') for c in candidates.values())
        completed.difference_update(r.get('releaseAccession') for r in records.values())
    filings.update(recent)
    loaded = set(progress.get('loadedSubmissionFiles', []))
    source_errors, attempted, was_deferred = [], 0, False
    # Freeze the campaign date, while always including the current submissions response.
    audit_as_of = progress.get('auditAsOf') or _now(today).isoformat().replace('+00:00','Z')
    files = [e for e in submissions.get('filings', {}).get('files', [])
             if re.fullmatch(r'CIK'+str(cik).zfill(10)+r'-submissions-\d+\.json', e.get('name',''))
             and e.get('filingFrom','') <= today.isoformat()]
    files.sort(key=lambda e:e.get('filingTo',''), reverse=True)
    latest_floor = max((r['reportDate'] for r in recent.values()
        if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') and r['reportDate']),
        default=(today-timedelta(days=200)).isoformat())
    # Load every relevant chunk, not a fixed file count. With fewer than five
    # known periods, later iterations extend backwards until five or exhaustion.
    # Query beyond the required five-quarter span, but do not backfill decades
    # of unrelated accepted Q1s to disguise an unresolved current quarter.
    required_since = (date.fromisoformat(latest_floor)-timedelta(days=550)).isoformat()
    floor = max(required_since,min(records)) if len(records)>=5 else required_since
    def load_file(entry):
        name = entry['name']; url = 'https://data.sec.gov/submissions/'+name
        if name in loaded:
            return
        try:
            payload = json.loads(fetch(url))
            if not isinstance(payload, dict):
                raise ValueError('Invalid submissions history')
            filings.update({r['accessionNumber']:r for r in _filings({'filings':{'recent':payload}},today)
                if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A') or (r['form'] in ('8-K','8-K/A') and '2.02' in re.split(r'[,;\s]+',r['items']))})
            loaded.add(name)
        except (OSError, TimeoutError, ValueError, TypeError) as exc:
            source_errors.append({'stage':'submission_history','sourceUrl':url,'errorType':type(exc).__name__})
    def release_events():
        return sorted((r for r in filings.values() if r['form'] in ('8-K','8-K/A')
            and '2.02' in re.split(r'[,;\s]+',r['items']) and r['reportDate']
            and r['filingDate'] >= (latest_floor if depth==1 else floor)),
            key=lambda r:(r['filingDate'],r['accessionNumber']), reverse=True)
    try:
        if depth == 5:
            for entry in files:
                if entry.get('filingTo','') >= floor:
                    load_file(entry)
        elif not release_events():
            for entry in files:
                if entry.get('filingTo','') < latest_floor:
                    break
                load_file(entry)
                if release_events():
                    break
        while True:
            accepted_periods = set()
            for event in release_events():
                accession = event['accessionNumber']
                existing = next((r for r in records.values() if r.get('releaseAccession') == accession), None)
                if accession in completed:
                    if existing:
                        accepted_periods.add(existing['periodEnd'])
                    if len(accepted_periods) >= depth:
                        break
                    continue
                url = _base(cik,event)+event['primaryDocument']
                key = f'{str(cik).zfill(10)}:{accession}:{url}'
                candidate = {'key':key,'accession':accession,'filingDate':event['filingDate'],
                    'sourceUrl':url,'reason':'quarter_identity_unconfirmed','attemptedAt':_now(today).isoformat()}
                # The single event plus all exact-period reports; no competing event can hide a failure.
                companions = [r for r in filings.values() if r['form'] in ('10-Q','10-Q/A','10-K','10-K/A')]
                try:
                    parsed, details = _parse_events(cik, [event]+companions, fetch, today)
                except OfficialScanDeferred:
                    candidate['reason'] = 'source_check_deferred'
                    candidates[key] = candidate
                    raise
                attempted += 1
                source_errors.extend(details['sourceErrors'])
                if parsed:
                    for record in parsed:
                        old = records.get(record['periodEnd'], {})
                        records[record['periodEnd']] = merge_manifest_record(old,record)
                        accepted_periods.add(record['periodEnd'])
                    candidates.pop(key,None)
                else:
                    candidate['reason'] = 'official_source_unavailable' if details['requestFailures'] else 'release_date_or_quarter_format_unsupported'
                    candidates[key] = candidate
                # Transport failures remain eligible on the next pass.
                if not details['requestFailures']:
                    completed.add(accession)
                if len(accepted_periods) >= depth:
                    break
            if len(accepted_periods) >= depth or depth == 1:
                break
            next_file = next((e for e in files if e['name'] not in loaded
                and e.get('filingTo','') >= floor
                and not any(e['name'] in error['sourceUrl'] for error in source_errors)),None)
            if next_file is None:
                break
            load_file(next_file)
    except OfficialScanDeferred:
        was_deferred = True
    rows = sorted(records.values(),key=lambda r:r['periodEnd'],reverse=True)[:5]
    pending = sum(c['reason'] != 'source_check_deferred' for c in candidates.values())
    cursor = {'parserVersion':PARSER_VERSION,'auditAsOf':audit_as_of,'completedAccessions':sorted(completed),
        'loadedSubmissionFiles':sorted(loaded),'filings':sorted(filings.values(),key=lambda r:r['accessionNumber']),
        'candidates':list(candidates.values()),'phase':'latest' if depth==1 else 'five_quarters',
        'state':'deferred' if was_deferred else 'source_failed' if source_errors else 'scanned',
        'historyExhausted':all(e['name'] in loaded for e in files) and len(rows)<depth}
    return rows, {'releaseCandidates':len(release_events()),'parsedQuarters':len(rows),
        'parsePending':pending,'metricPending':sum(r.get('epsGaapDiluted') is None or r.get('revenue') is None for r in rows),
        'requestFailures':len(source_errors),'sourceErrors':source_errors,'candidates':list(candidates.values()),
        'deferred':was_deferred,'discoveryComplete':not was_deferred and not source_errors,'backfillProgress':cursor,
        'attemptedAnnouncements':attempted}


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
    live_date = today is None
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    checked = _now(today).isoformat().replace('+00:00','Z')
    load = lambda name:json.loads((root/name).read_text())
    companies, history, manifest = load('data.json'), load('historical_data.json'), load('official_history.json')
    status, mapping = load('history_status.json'), load('sp500_mapping.json')
    tickers = {c['ticker'] for c in companies}
    if set(history) != tickers:
        raise ValueError('Company/history ticker set mismatch; no publication')
    history, _ = apply_official_records(companies, history, manifest, today)
    deadline = time.monotonic()+budget_seconds
    cache_root = root/'.sec_cache'/'official'
    transport, real_fetch = fetch or fetch_sec, fetch is None
    memory_cache = {}
    def paced(url):
        if time.monotonic() >= deadline:
            raise OfficialScanDeferred('Official scan time budget exhausted')
        if url in memory_cache:
            return memory_cache[url]
        cache_file = cache_root/(hashlib.sha256(url.encode()).hexdigest()+'.body') if real_fetch and '/Archives/' in url else None
        if cache_file is not None and cache_file.exists():
            return decode_sec_body(cache_file.read_bytes())
        for attempt in range(3):
            try:
                if real_fetch and deadline-time.monotonic() < 25:
                    raise OfficialScanDeferred('Saving progress before the source deadline')
                body = transport(url)
                break
            except (OSError, TimeoutError):
                if attempt == 2 or time.monotonic()+2**attempt >= deadline:
                    raise
                time.sleep(2**attempt)
        if cache_file is not None:
            cache_root.mkdir(parents=True,exist_ok=True)
            payload = body.encode('utf-8') if isinstance(body,str) else body
            # Only immutable originals are persisted; live submissions/facts are per-run.
            cache_file.write_bytes(gzip.compress(payload,compresslevel=1))
        else:
            memory_cache[url] = body
        return body
    mapping = fill_missing_ciks(companies,history,mapping,paced)
    groups = {}
    for company in companies:
        ticker = company['ticker']
        if ticker == 'NVDA' or not _due(company,status.get(ticker,{}),today,full):
            continue
        cik = mapping.get(ticker,{}).get('cik')
        if not isinstance(cik,str) or not re.fullmatch(r'\d{1,10}',cik):
            status[ticker] = {**status.get(ticker,{}),'status':'official_mapping_missing','reason':'sec_cik_mapping_missing',
                'sourceCheck':{**status.get(ticker,{}).get('sourceCheck',{}),'state':'identity_pending','lastAttemptAt':checked}}
            continue
        groups.setdefault(cik.zfill(10),[]).append(ticker)
    # Oldest successful discovery first, then no verified quarter/latest unverified.
    groups = dict(sorted(groups.items(),key=lambda pair:(
        min(status.get(t,{}).get('sourceCheck',{}).get('lastSuccessfulDiscoveryAt','') for t in pair[1]),
        not any(not status.get(t,{}).get('latestStoredOfficial') for t in pair[1]))))
    checked_issuers, failed_issuers, deferred_tickers = set(), set(), set()
    parsed_count = 0
    submissions_cache = {}
    def inspect(cik, depth):
        aliases = groups[cik]
        if cik not in submissions_cache:
            print(f'Checking official issuer: {",".join(aliases)}',flush=True)
            submissions_cache[cik] = json.loads(paced(f'https://data.sec.gov/submissions/CIK{cik}.json'))
        prior = status.get(aliases[0],{})
        return check_issuer(cik,submissions_cache[cik],paced,today,depth=depth,
            progress=prior.get('backfillProgress'),known_records=[r for r in manifest if r['ticker']==aliases[0]])
    def merge_result(cik, depth, result=None, error=None):
        nonlocal history, manifest, parsed_count
        aliases = groups[cik]
        url = f'https://data.sec.gov/submissions/CIK{cik}.json'
        if isinstance(error,OfficialScanDeferred):
            deferred_tickers.update(aliases)
            for ticker in aliases:
                prior = status.get(ticker,{})
                status[ticker] = {**prior,'status':'official_check_deferred','reason':'official_scan_time_budget_exhausted','queuedAt':checked,
                    'sourceCheck':{**prior.get('sourceCheck',{}),'state':'deferred','lastAttemptAt':checked,'sourceUrl':url}}
            return
        checked_issuers.add(cik)
        if error is not None:
            failed_issuers.add(cik)
            print(f'Official issuer check failed: {",".join(aliases)}; error type: {type(error).__name__}',flush=True)
            for ticker in aliases:
                prior = status.get(ticker,{})
                status[ticker] = {**prior,'status':'official_source_failed','reason':'official_validation_failed' if isinstance(error,ValueError) else 'sec_request_or_configuration_failed',
                    'errorType':type(error).__name__,'officialCheckedAt':checked,'checkedAt':checked,'cik':cik,
                    'sourceCheck':{**prior.get('sourceCheck',{}),'state':'failed','lastAttemptAt':checked,'sourceUrl':url}}
            return
        records, details = result
        if details['requestFailures']:
            failed_issuers.add(cik)
        if details.get('deferred'):
            deferred_tickers.update(aliases)
        state = ('official_check_deferred' if details.get('deferred') else 'official_source_failed' if details['requestFailures']
                 else 'official_parse_pending' if details['parsePending'] or details['metricPending'] else 'official_source_checked')
        for ticker in aliases:
            by_period = {(r['ticker'],r['periodEnd']):r for r in manifest}
            incoming = [merge_manifest_record(by_period.get((ticker,r['periodEnd']),{}),{**r,'ticker':ticker}) for r in records]
            history, added = apply_official_records(companies,history,incoming,today)
            parsed_count += added
            manifest = retain_manifest(manifest+incoming)
            prior = {k:v for k,v in status.get(ticker,{}).items() if k not in ('errorType','queuedAt')}
            source = {**prior.get('sourceCheck',{}),'lastAttemptAt':checked,'sourceUrl':url,
                      'state':'deferred' if details.get('deferred') else 'failed' if details['requestFailures'] else 'checked'}
            if depth == 1 and details.get('discoveryComplete'):
                source['lastSuccessfulDiscoveryAt'] = checked
            progress = details.get('backfillProgress',{})
            progress.setdefault('auditAsOf',prior.get('backfillProgress',{}).get('auditAsOf') or checked)
            status[ticker] = {**prior,**details,'backfillProgress':progress,'status':state,
                'reason':'sec_earnings_exhibits_checked' if state=='official_source_checked' else 'sec_release_or_metric_check_pending',
                'sourceCheck':source,'discoverySource':'SEC submissions and earnings exhibits','officialCheckedAt':checked,'checkedAt':checked,'cik':cik}
    def run_phase(depth, selected=None):
        selected = list(groups) if selected is None else selected
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {cik:pool.submit(inspect,cik,depth) for cik in selected}
            for index,cik in enumerate(selected,1):
                try:
                    result = futures[cik].result()
                except Exception as exc:
                    merge_result(cik,depth,error=exc)
                else:
                    merge_result(cik,depth,result=result)
                if index%50==0 or index==len(selected):
                    print(f'Official phase {depth}: {index}/{len(selected)}; source failures: {len(failed_issuers)}',flush=True)
    run_phase(1)
    # NVIDIA's independent, tested newsroom discovery also precedes historical work.
    if 'NVDA' in tickers:
        from nvda_history import sync_nvda
        prior = status.get('NVDA',{})
        try:
            if time.monotonic() >= deadline:
                raise OfficialScanDeferred()
            with tempfile.TemporaryDirectory() as temp:
                stage = Path(temp)
                for name,value in [('data.json',companies),('historical_data.json',history),('official_history.json',manifest),('history_status.json',status)]:
                    (stage/name).write_text(json.dumps(value))
                if nvda_sync:
                    nvda_sync(stage,today=today)
                else:
                    from nvda_history import fetch_official
                    def newsroom(url):
                        for attempt in range(3):
                            if deadline-time.monotonic() < 35:
                                raise OfficialScanDeferred('Saving progress before the source deadline')
                            try:
                                return fetch_official(url)
                            except HTTPError as exc:
                                if exc.code != 429 and exc.code < 500:
                                    raise
                                if attempt == 2:raise
                            except (OSError,TimeoutError):
                                if attempt == 2:raise
                            pause=2**attempt
                            if deadline-time.monotonic() < pause+35:
                                raise OfficialScanDeferred('Saving progress before the source deadline')
                            time.sleep(pause)
                    sync_nvda(stage,today=today,fetch=newsroom)
                history['NVDA'] = json.loads((stage/'historical_data.json').read_text())['NVDA']
                manifest = [r for r in manifest if r['ticker']!='NVDA']+[r for r in json.loads((stage/'official_history.json').read_text()) if r['ticker']=='NVDA']
                status['NVDA'] = {**prior,**json.loads((stage/'history_status.json').read_text())['NVDA'],'officialCheckedAt':checked,
                    'sourceCheck':{'state':'checked','lastAttemptAt':checked,'lastSuccessfulDiscoveryAt':checked,
                                   'sourceUrl':'https://nvidianews.nvidia.com/news'}}
        except Exception as exc:
            is_deferred = isinstance(exc,OfficialScanDeferred)
            (deferred_tickers if is_deferred else failed_issuers).add('NVDA')
            status['NVDA'] = {**prior,'status':'official_check_deferred' if is_deferred else 'official_source_failed',
                'reason':'official_scan_time_budget_exhausted' if is_deferred else 'nvda_newsroom_request_or_parse_failed',
                'sourceCheck':{**prior.get('sourceCheck',{}),'state':'deferred' if is_deferred else 'failed','lastAttemptAt':checked}}
    # Never spend the remaining budget on old quarters before every due latest check finishes.
    if not deferred_tickers:
        run_phase(5,[cik for cik in groups if cik not in failed_issuers])
    final_today = max(today, datetime.now(ZoneInfo('America/New_York')).date()) if live_date else today
    history = retain_history(history,final_today)
    enriched = []
    for company in companies:
        entry = dict(company); issuer = mapping.get(entry['ticker'],{})
        if issuer.get('tickerStatus') in ('historical_alias','unconfirmed'):
            entry['tickerIdentityStatus'] = issuer['tickerStatus']
            entry['officialCurrentTickers'] = issuer.get('officialTickers',[])
        entry = company_fields(entry,history,final_today)
        enriched.append(entry)
        status[entry['ticker']] = company_status(entry,history[entry['ticker']],status.get(entry['ticker'],{}),checked)
    companies = enriched
    summary = {'companies':len(companies),'issuersChecked':len(checked_issuers),'issuerTargets':len(groups),
        'deferredCompanies':len(deferred_tickers),'newRecords':parsed_count,'sourceFailures':len(failed_issuers),
        'pendingCompanies':sum(bool(s['gaps']) for s in status.values()),
        'officialQuarters':sum(s['officialQuarterCount'] for s in status.values()),
        'fiveOfficialQuarterCompanies':sum(s['coverage']['verifiedQuarters']==5 for s in status.values()),
        'fiveCompleteMetricCompanies':sum(s['metricsVerifiedQuarterCount']==5 for s in status.values()),
        'latestIdentifiedCompanies':sum(s['latestQuarter']['state']=='identified' for s in status.values()),
        'latestCompleteMetricCompanies':sum(s['latestQuarter']['metricsComplete'] for s in status.values()),
        'sourceStaleCompanies':sum(s['sourceCheck']['stale'] for s in status.values()),
        'sourceFailedCompanies':sum(s['sourceCheck']['state']=='failed' for s in status.values()),
        'checkedAt':checked,'healthy':not failed_issuers and not deferred_tickers}
    write_json_bundle({root/'data.json':companies,root/'historical_data.json':history,root/'official_history.json':retain_manifest(manifest),
        root/'history_status.json':status,root/'official_scan_state.json':summary,root/'sp500_mapping.json':mapping})
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default='.')
    parser.add_argument('--full',action='store_true')
    parser.add_argument('--mapping-only',action='store_true')
    parser.add_argument('--budget-seconds',type=float,default=float(os.environ.get('OFFICIAL_SOURCE_BUDGET_SECONDS','2400')))
    args=parser.parse_args()
    if args.mapping_only:
        root=Path(args.root)
        mapping=fill_missing_ciks(json.loads((root/'data.json').read_text()),
            json.loads((root/'historical_data.json').read_text()),
            json.loads((root/'sp500_mapping.json').read_text()),fetch_sec)
        write_json_bundle({root/'sp500_mapping.json':mapping})
        print(json.dumps({'mappingUpdated':True,'companies':len(mapping)}))
        raise SystemExit(0)
    summary=sync_all(args.root,full=args.full,budget_seconds=args.budget_seconds)
    print(json.dumps(summary))
    if not summary['healthy']:
        raise SystemExit('Official checks incomplete; prior history preserved and per-company status saved')
