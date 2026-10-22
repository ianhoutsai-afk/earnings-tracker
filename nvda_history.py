"""NVDA-only official-source pilot and five-quarter retention policy."""
import copy
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

from lxml import html

FEED_URL = 'https://nvidianews.nvidia.com/rss.xml'
RELEASE_PREFIX = 'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-'
QUARTERS = ('first', 'second', 'third', 'fourth')


def release_url(year, quarter):
    suffix = f'{QUARTERS[quarter - 1]}-quarter-'
    return RELEASE_PREFIX + suffix + ('and-' if quarter == 4 else '') + f'fiscal-{year}'


def _official_url(url):
    parsed = urlparse(url)
    if (parsed.scheme != 'https' or parsed.hostname != 'nvidianews.nvidia.com'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment):
        raise ValueError('Expected an official NVIDIA Newsroom URL')
    return url


def retain_nvda_history(history):
    """Scope the pilot to NVDA; only verified quarterly periods enter its window."""
    result = copy.deepcopy(history)
    periods = {}
    for row in result.get('NVDA', []):
        if (row.get('verificationStatus') == 'official_verified'
                and row.get('periodScope') == 'quarter' and row.get('periodEnd')):
            date.fromisoformat(row['periodEnd'])
            previous = periods.get(row['periodEnd'])
            if previous is None or row.get('verifiedAt', '') >= previous.get('verifiedAt', ''):
                periods[row['periodEnd']] = row
    # Do not discard legacy history until five official quarters are available.
    if len(periods) >= 5:
        result['NVDA'] = sorted(periods.values(), key=lambda row: row['periodEnd'], reverse=True)[:5]
    return result


def nvda_company_fields(company, history, today):
    result = dict(company)
    if result.get('ticker') != 'NVDA':
        return result
    # Legacy Yahoo forward estimates have no identifiable quarterly period.
    result['eps'] = '-'
    result['revenue'] = '-'
    rows = history.get('NVDA', [])
    verified = [row for row in rows if row.get('periodEnd') and row.get('verificationStatus') == 'official_verified']
    if verified:
        latest = max(verified, key=lambda row: row['periodEnd'])
        result['latestPublishedQuarter'] = latest['quarter']
        result['latestPublishedDate'] = latest['date']
    call_date = result.get('nextEarningsCallDate')
    if call_date and date.fromisoformat(call_date) < today:
        result.pop('nextEarningsCallDate', None)
        result.pop('nextEarningsCallSourceUrl', None)
    return result


def parse_release(document, url, today):
    """Parse identity/dates and the current-quarter GAAP summary only."""
    _official_url(url)
    tree = html.fromstring(document)
    title = tree.xpath('normalize-space(//h1[contains(@class,"article-title")])')
    identity = re.fullmatch(
        r'NVIDIA Announces Financial Results for (First|Second|Third|Fourth) Quarter (?:and )?Fiscal (\d{4})', title)
    if not identity:
        raise ValueError('Official quarterly release title was not found')
    quarter = QUARTERS.index(identity[1].lower()) + 1
    fiscal_year = int(identity[2])
    if url != release_url(fiscal_year, quarter):
        raise ValueError('Release URL does not match its official fiscal identity')
    published_text = tree.xpath('normalize-space(//div[contains(@class,"article-date")])')
    published = datetime.strptime(published_text, '%B %d, %Y').date()
    bodies = tree.xpath('//div[contains(@class,"article-body")]')
    if len(bodies) != 1:
        raise ValueError('Official release body was not found')
    body = bodies[0]
    narrative = ' '.join(' '.join(p.itertext()) for p in body.xpath('./p')[:3])
    end_match = re.search(r'(?i)\b' + QUARTERS[quarter - 1] + r' quarter ended ([A-Za-z]+\s+\d{1,2},\s+\d{4})', narrative)
    if not end_match:
        raise ValueError('Explicit quarter-end date was not found')
    period_end = datetime.strptime(' '.join(end_match[1].split()), '%B %d, %Y').date()
    if not period_end <= published <= today:
        raise ValueError('Release has an invalid or future date')

    revenue = eps = None
    expected_header = f'Q{quarter}FY{fiscal_year % 100:02d}'
    for table in body.xpath('.//table'):
        rows = []
        for tr in table.xpath('.//tr'):
            row = []
            for cell in tr.xpath('./th|./td'):
                span = int(cell.get('colspan', '1'))
                if not 1 <= span <= 64 or cell.get('rowspan', '1') != '1':
                    raise ValueError('Unsupported official summary table layout')
                row.extend([' '.join(' '.join(cell.itertext()).split())] * span)
            rows.append(row)
        if not rows or 'GAAP' not in rows[0]:
            continue
        header = next((row for row in rows[:3]
                       if any(cell.replace(' ', '') == expected_header for cell in row)), None)
        if header is None:
            continue
        columns = [i for i, cell in enumerate(header) if cell.replace(' ', '') == expected_header]
        if 'in millions' not in ' '.join(' '.join(row) for row in rows[:3]).lower():
            continue
        for row in rows[1:]:
            if 'Non-GAAP' in row:
                break
            if not row or row[0] not in ('Revenue', 'Diluted earnings per share'):
                continue
            # Keep empty cells and colspan positions: comparison quarters cannot slide left.
            numbers = {row[i].replace('$', '').replace(',', '').replace(' ', '')
                       for i in columns if i < len(row) and row[i] and row[i] != '$'}
            if len(numbers) != 1:
                continue
            number = numbers.pop()
            if not re.fullmatch(r'-?\d+(?:\.\d+)?', number):
                continue
            if row[0] == 'Revenue':
                revenue = int(float(number) * 1000000)
            else:
                eps = float(number)
        break
    return {
        'ticker': 'NVDA', 'date': published.isoformat(), 'periodEnd': period_end.isoformat(),
        'fiscalYear': fiscal_year, 'fiscalQuarter': quarter, 'periodScope': 'quarter',
        'epsGaapDiluted': eps, 'epsBasis': 'GAAP diluted', 'revenue': revenue, 'currency': 'USD',
        'releaseSourceUrl': url, 'metricSourceUrl': url, 'verifiedAt': today.isoformat(),
    }


def fetch_official(url):
    _official_url(url)
    request = Request(url, headers={'User-Agent': 'EarningsTracker NVDA official-history pilot'})
    with urlopen(request, timeout=30) as response:
        _official_url(response.url)
        return response.read().decode('utf-8')


def discover_releases(document):
    root = ElementTree.fromstring(document)
    urls = []
    for item in root.findall('.//item'):
        title = item.findtext('title') or ''
        url = (item.findtext('link') or '').strip()
        if title.startswith('NVIDIA Announces Financial Results for '):
            _official_url(url)
            if url.startswith(RELEASE_PREFIX):
                urls.append(url)
    return list(dict.fromkeys(urls))[:5]


def sync_nvda(root, today=None, fetch=fetch_official):
    """All reads/validations precede writes; other ticker rows remain identical."""
    from verified_history import apply_official_records, write_json_bundle

    root = Path(root)
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    companies = json.loads((root / 'data.json').read_text())
    if not any(company['ticker'] == 'NVDA' for company in companies):
        return {'ticker': 'NVDA', 'skipped': True}
    history = json.loads((root / 'historical_data.json').read_text())
    manifest = json.loads((root / 'official_history.json').read_text())
    status = json.loads((root / 'history_status.json').read_text())
    records = [record for record in manifest if record['ticker'] == 'NVDA']
    if not records:
        raise ValueError('NVDA official seed records are required')
    latest = max(records, key=lambda record: record['periodEnd'])
    urls = discover_releases(fetch(FEED_URL))
    urls.append(release_url(latest['fiscalYear'], latest['fiscalQuarter']))
    checked = []
    for url in dict.fromkeys(urls):
        records.append(parse_release(fetch(url), url, today))
        checked.append(url)
    # A narrowly scoped official URL probe covers releases that aged out of the RSS feed.
    next_quarter = latest['fiscalQuarter'] % 4 + 1
    next_year = latest['fiscalYear'] + (latest['fiscalQuarter'] == 4)
    next_url = release_url(next_year, next_quarter)
    if next_url not in checked:
        try:
            document = fetch(next_url)
        except HTTPError as exc:
            if exc.code != 404:
                raise
        else:
            # Newsroom returns its archive with HTTP 200 for unpublished URLs.
            page = html.fromstring(document)
            archive = (page.xpath('normalize-space(//h1)') == 'News Archive'
                       and not page.xpath('//div[contains(@class,"article-body")]'))
            if not archive:
                records.append(parse_release(document, next_url, today))
    by_period = {}
    for record in records:
        from quarterly_policy import merge_manifest_record
        previous = by_period.get(record['periodEnd'], {})
        by_period[record['periodEnd']] = merge_manifest_record(previous,record)
    records = sorted(by_period.values(), key=lambda record: record['periodEnd'], reverse=True)[:5]
    if len(records) != 5:
        raise ValueError('Expected five official NVDA quarters before replacing legacy history')
    updated_history, _ = apply_official_records(companies, history, records, today)
    updated_companies = [nvda_company_fields(company, updated_history, today) for company in companies]
    latest_row = updated_history['NVDA'][0]
    status['NVDA'] = {
        'status': 'official_source_checked', 'reason': 'nvda_newsroom_feed_and_next_quarter_checked',
        'latestStoredDate': latest_row['date'], 'latestStoredOfficial': True,
        'officialSourceUrl': latest_row['releaseSourceUrl'],
        'discoverySource': 'NVIDIA Newsroom RSS and quarterly release',
        'checkedAt': datetime.now(ZoneInfo('UTC')).isoformat().replace('+00:00', 'Z'),
    }
    updated_manifest = [record for record in manifest if record['ticker'] != 'NVDA'] + records
    write_json_bundle({root / 'data.json': updated_companies,
                       root / 'historical_data.json': updated_history,
                       root / 'official_history.json': updated_manifest,
                       root / 'history_status.json': status})
    return {'ticker': 'NVDA', 'quarters': len(updated_history['NVDA']), 'latest': latest_row['quarter']}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Refresh only NVDA from official quarterly releases')
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    try:
        print(json.dumps(sync_nvda(args.root)))
    except Exception as exc:
        raise SystemExit(f'NVDA official update failed; previous records retained: {type(exc).__name__}: {exc}')
