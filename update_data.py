#!/usr/bin/env python3
"""
update_data.py — S&P 500 Earnings Tracker 數據更新腳本

兩種模式:
  1. 完整建置模式 (full): 處理所有公司，首次執行或重建時使用
  2. 增量更新模式 (incremental): 只處理未來 30 天內要發布財報的公司（預設）

用法:
  python update_data.py                        # 增量更新（預設）
  python update_data.py --full                 # 完整建置
  python update_data.py --sample               # 樣本模式（測試用）
  python update_data.py --ticker AAPL,MSFT     # 指定公司
"""

import json
import time
import sys
import os
import argparse
import urllib.request
from urllib.parse import parse_qs, unquote, urlparse
from datetime import datetime, date, timedelta
from typing import Optional

try:
    import requests
except ImportError:
    requests = None

try:
    import yfinance as yf
except ImportError:
    yf = None

try:
    import pandas as pd
except ImportError:
    pd = None


SEC_CONTACT_EMAIL = os.environ.get('SEC_CONTACT_EMAIL') or 'contact@example.com'
SEC_HEADERS = {
    'User-Agent': f'EarningsTracker audit {SEC_CONTACT_EMAIL}',
    'Accept-Encoding': 'gzip, deflate',
}

SEC_PROXY_URL = os.environ.get('SEC_PROXY_URL', '')
SEC_PROXY_TOKEN = os.environ.get('PROXY_TOKEN', '')
MAX_SEC_REPORT_LAG_DAYS = 120
SEC_FILING_GRACE_DAYS = 90
SEC_CACHE_DIR = os.environ.get('SEC_CACHE_DIR', '.sec_cache')
SEC_CACHE_TTL_SECONDS = int(os.environ.get('SEC_CACHE_TTL_SECONDS', 24 * 60 * 60))
TICKER_ALIASES = {
    'BK': 'BNY',
}
SEC_SESSION = None
if requests is not None:
    SEC_SESSION = requests.Session()
    SEC_SESSION.headers.update(SEC_HEADERS)


# ─────────────────────────────────────────────
# 工具函數
# ─────────────────────────────────────────────


def format_eps(value) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
        return f"${v:.2f}"
    except (ValueError, TypeError):
        return "-"


def format_revenue(value) -> str:
    if value is None:
        return "-"
    try:
        v = float(value)
        if v >= 1e12:
            return f"${v / 1e12:.2f}T"
        elif v >= 1e9:
            return f"${v / 1e9:.2f}B"
        elif v >= 1e6:
            return f"${v / 1e6:.2f}M"
        else:
            return f"${v:.2f}"
    except (ValueError, TypeError):
        return "-"


def migrate_ticker_aliases(existing_data: list, historical_data: dict) -> int:
    """Migrate retired ticker symbols before joining against the current SEC map."""
    migrations = 0
    current_tickers = {company.get('ticker') for company in existing_data}
    for company in existing_data:
        old_ticker = company.get('ticker')
        new_ticker = TICKER_ALIASES.get(old_ticker)
        if not new_ticker or new_ticker in current_tickers:
            continue

        company['ticker'] = new_ticker
        current_tickers.discard(old_ticker)
        current_tickers.add(new_ticker)
        if old_ticker in historical_data and new_ticker not in historical_data:
            historical_data[new_ticker] = historical_data.pop(old_ticker)
        migrations += 1
    return migrations


class _UrllibResponse:
    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    def json(self):
        return json.loads(self._body.decode('utf-8'))


def _sec_request(url: str, timeout: int = 15):
    """透過 proxy（如有設定）或直連發送 SEC 請求"""
    if SEC_PROXY_URL:
        proxy_headers = dict(SEC_HEADERS)
        if SEC_PROXY_TOKEN:
            proxy_headers['X-Proxy-Token'] = SEC_PROXY_TOKEN
        parsed = urlparse(url)
        proxy_url = SEC_PROXY_URL.rstrip('/') + parsed.path
        if parsed.query:
            proxy_url += '?' + parsed.query
        if requests is None:
            req = urllib.request.Request(proxy_url, headers=proxy_headers)
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return _UrllibResponse(res.status, res.read())
        return requests.get(proxy_url, headers=proxy_headers, timeout=timeout)

    if requests is not None:
        return SEC_SESSION.get(url, timeout=timeout)

    req = urllib.request.Request(url, headers={'User-Agent': SEC_HEADERS['User-Agent']})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return _UrllibResponse(res.status, res.read())


def build_sec_ixbrl_url(cik: str, accession_number: str, primary_document: str) -> str:
    """
    建構 SEC ixbrl 互動式檢視器 URL。
    使用 ixbrl 檢視器可以更友好地瀏覽財報內容。
    """
    cik_int = str(int(cik))
    acc_no_dashes = accession_number.replace("-", "")
    return f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_document}"


# ─────────────────────────────────────────────
# Quarter 標籤推算（使用期間結束日）
# ─────────────────────────────────────────────


def estimate_period_end(release_date: date) -> Optional[date]:
    """
    從 earnings release date 推估對應的 fiscal period end date。
    
    財報通常在公司財報期間結束後的 2-6 週發布：
    - Jan-Mar 發布 → 期間結束日為前一年 Dec 31（年報 / FY）
    - Apr-Jun 發布 → 期間結束日為今年 Mar 31（Q1）
    - Jul-Sep 發布 → 期間結束日為今年 Jun 30（Q2）
    - Oct-Dec 發布 → 期間結束日為今年 Sep 30（Q3）
    """
    if not release_date:
        return None
    m = release_date.month
    y = release_date.year
    if 1 <= m <= 3:
        return date(y - 1, 12, 31)
    elif 4 <= m <= 6:
        return date(y, 3, 31)
    elif 7 <= m <= 9:
        return date(y, 6, 30)
    elif 10 <= m <= 12:
        return date(y, 9, 30)
    return None


def quarter_label_from_period_end(period_end: date, fy_end_month: int) -> Optional[str]:
    """
    根據期間結束日與會計年度結束月份，計算 quarter label。
    fy_end_month = 12 表示 calendar year（大部分公司）
    """
    if not period_end:
        return None
    month = period_end.month
    year = period_end.year

    # 期間結束日為 12/31 → 年報（FY）
    if month == 12 and period_end.day == 31:
        # 看 fy_end 是否也是 12
        if fy_end_month == 12:
            return f"{year} FY"
        else:
            # 非 calendar year 的公司，需要特別處理
            # 從 period_end 反推該公司在哪個會計年度
            fy_start = fy_end_month + 1
            if fy_start > 12:
                fy_start = 1
            # 如果 period_end 在 fy_start 之後，會計年度為 year+1
            # 否則為 year
            if month >= fy_start:
                fy_year = year + 1
            else:
                fy_year = year
            return f"{fy_year} FY"

    # 非年報：推算季度
    # 用期間結束日（3/31, 6/30, 9/30）推算是在會計年度的第幾季
    fy_start = fy_end_month + 1
    if fy_start > 12:
        fy_start = 1

    if month >= fy_start:
        months_into_fy = month - fy_start + 1
    else:
        months_into_fy = month + (12 - fy_start + 1)

    q = (months_into_fy - 1) // 3 + 1

    # 會計年度
    if month > fy_end_month:
        fy_year = year + 1
    else:
        fy_year = year

    return f"{fy_year} Q{q}"


# ─────────────────────────────────────────────
# SEC Filing 抓取
# ─────────────────────────────────────────────


def extract_sec_filing_data(submissions: dict, cik: str) -> dict:
    """Extract authoritative fiscal-year and filing metadata from SEC submissions."""
    recent = submissions.get('filings', {}).get('recent', {})

    fiscal_year_end = submissions.get('fiscalYearEnd', '')
    fy_end_month = None
    if isinstance(fiscal_year_end, str) and len(fiscal_year_end) == 4:
        try:
            parsed_month = int(fiscal_year_end[:2])
            if 1 <= parsed_month <= 12:
                fy_end_month = parsed_month
        except ValueError:
            pass

    candidates = []
    filing_sources = [recent, *submissions.get('_supplemental_filings', [])]
    for source in filing_sources:
        forms = source.get('form', [])
        accessions = source.get('accessionNumber', [])
        primary_docs = source.get('primaryDocument', [])
        report_dates = source.get('reportDate', [])
        filing_dates = source.get('filingDate', [])

        for i, original_form in enumerate(forms):
            base_form = original_form.replace('/A', '')
            if base_form not in ('10-K', '10-Q'):
                continue

            report_date = report_dates[i] if i < len(report_dates) else ''
            filing_date = filing_dates[i] if i < len(filing_dates) else ''
            accession = accessions[i] if i < len(accessions) else ''
            primary_doc = primary_docs[i] if i < len(primary_docs) else ''
            if not all((report_date, filing_date, accession, primary_doc)):
                continue

            candidates.append({
                'form': base_form,
                'original_form': original_form,
                'is_amendment': original_form.endswith('/A'),
                'report_date': report_date,
                'filing_date': filing_date,
                'url': build_sec_ixbrl_url(cik, accession, primary_doc),
            })

    # Prefer the original filing over amendments for the same form/reporting period.
    candidates.sort(
        key=lambda item: (
            item['report_date'],
            item['form'],
            not item['is_amendment'],
            item['filing_date'],
        ),
        reverse=True,
    )
    deduplicated = []
    seen_periods = set()
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item['report_date'],
            item['form'],
            not item['is_amendment'],
            item['filing_date'],
        ),
        reverse=True,
    ):
        period_key = (candidate['report_date'], candidate['form'])
        if period_key in seen_periods:
            continue
        seen_periods.add(period_key)
        deduplicated.append(candidate)

    deduplicated.sort(key=lambda item: item['report_date'], reverse=True)
    return {'filings': deduplicated, 'fy_end_month': fy_end_month}


def _load_sec_json(url: str, cache_path: str, request_label: str) -> Optional[dict]:
    """Load SEC JSON from the local TTL cache or the official endpoint."""
    try:
        cache_age = time.time() - os.path.getmtime(cache_path)
        if cache_age <= SEC_CACHE_TTL_SECONDS:
            with open(cache_path, 'r', encoding='utf-8') as cache_file:
                return json.load(cache_file)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        pass

    for attempt in range(3):
        try:
            res = _sec_request(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                try:
                    os.makedirs(SEC_CACHE_DIR, exist_ok=True)
                    temp_path = cache_path + '.tmp'
                    with open(temp_path, 'w', encoding='utf-8') as cache_file:
                        json.dump(data, cache_file)
                    os.replace(temp_path, cache_path)
                except OSError:
                    pass
                break
            elif res.status_code == 429:
                time.sleep((attempt + 1) * 3)
                continue
            elif res.status_code == 403:
                if attempt < 2:
                    time.sleep((attempt + 1) * 5)
                    continue
                print(f"  ⚠️ SEC {request_label}: HTTP 403")
                return None
            else:
                if attempt < 2:
                    time.sleep(1)
                    continue
                print(f"  ⚠️ SEC {request_label}: HTTP {res.status_code}")
                return None
        except Exception as exc:
            if attempt < 2:
                time.sleep(1)
                continue
            print(f"  ⚠️ SEC {request_label}: {type(exc).__name__}: {exc}")
            return None

    return data


def fetch_sec_filing_data(cik: str) -> Optional[dict]:
    """
    Fetch a company's authoritative 10-K/10-Q list and fiscal year-end month.
    Returns None when the SEC request fails, so callers never confuse a
    transient fetch failure with a company that has no filings.

    High-volume filers may have older filings split into supplemental SEC JSON
    files. Load only as many adjacent files as needed to cover five reports.
    """
    cache_path = os.path.join(SEC_CACHE_DIR, f'CIK{cik}.json')
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = _load_sec_json(url, cache_path, f'CIK{cik}')
    if data is None:
        return None

    filing_data = extract_sec_filing_data(data, cik)
    supplemental_filings = []
    supplemental_files = data.get('filings', {}).get('files', [])
    for file_info in supplemental_files:
        if len(filing_data['filings']) >= 5:
            break
        filename = file_info.get('name')
        if not filename:
            continue
        supplemental_url = f"https://data.sec.gov/submissions/{filename}"
        supplemental_path = os.path.join(SEC_CACHE_DIR, filename)
        supplemental = _load_sec_json(supplemental_url, supplemental_path, filename)
        if supplemental is None:
            return None
        supplemental_filings.append(supplemental)
        data['_supplemental_filings'] = supplemental_filings
        filing_data = extract_sec_filing_data(data, cik)

    return filing_data


def fetch_sec_filing_list(cik: str) -> list:
    """Backward-compatible wrapper returning only the SEC filing list."""
    result = fetch_sec_filing_data(cik)
    return result['filings'] if result else []


# ─────────────────────────────────────────────
# 改良版 History ↔ SEC Filing 匹配
# ─────────────────────────────────────────────


def _canonical_sec_doc_path(sec_url: str) -> str:
    """Normalize SEC ix viewer and direct Archives URLs to the same document path."""
    if not sec_url:
        return ''
    parsed = urlparse(sec_url)
    doc = parse_qs(parsed.query).get('doc', [''])[0]
    path = doc or parsed.path
    return unquote(path).lstrip('/')


def match_filing_by_sec_url(sec_url: str, sec_filings: list) -> Optional[dict]:
    """Use an existing SEC URL to recover the official SEC form from filing metadata."""
    target_path = _canonical_sec_doc_path(sec_url)
    if not target_path:
        return None

    for filing in sec_filings:
        filing_path = _canonical_sec_doc_path(filing.get('url', ''))
        if filing_path == target_path:
            return {"url": filing['url'], "form": filing['form']}

    return None


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _filing_result(filing: dict) -> dict:
    return {
        'url': filing['url'],
        'form': filing['form'],
        'report_date': filing['report_date'],
        'filing_date': filing['filing_date'],
    }


def match_history_to_filings(history_items: list, sec_filings: list) -> dict:
    """
    Match earnings releases to SEC filings one-to-one in chronological order.

    The authoritative SEC report date must be on or before the earnings release
    and no more than MAX_SEC_REPORT_LAG_DAYS earlier. This works for calendar and
    non-calendar fiscal years without guessing fixed quarter-end dates.

    Returns {history_index: filing_result}.
    """
    parsed_filings = []
    for filing in sec_filings:
        report_date = _parse_iso_date(filing.get('report_date'))
        filing_date = _parse_iso_date(filing.get('filing_date'))
        if not report_date or not filing_date or filing.get('form') not in ('10-K', '10-Q'):
            continue
        parsed_filings.append((filing, report_date, filing_date))

    indexed_history = []
    for index, history_item in enumerate(history_items):
        release_date = _parse_iso_date(history_item.get('date'))
        if release_date:
            indexed_history.append((index, release_date))
    indexed_history.sort(key=lambda item: item[1])

    matches = {}
    used_urls = set()
    for history_index, release_date in indexed_history:
        eligible = []
        for filing, report_date, filing_date in parsed_filings:
            if filing['url'] in used_urls:
                continue
            report_lag = (release_date - report_date).days
            if report_lag < 0 or report_lag > MAX_SEC_REPORT_LAG_DAYS:
                continue
            filing_distance = abs((filing_date - release_date).days)
            eligible.append((report_lag, filing_distance, filing))

        if not eligible:
            continue

        _, _, best_filing = min(
            eligible,
            key=lambda item: (
                item[0],
                item[1],
                item[2].get('is_amendment', False),
            ),
        )
        matches[history_index] = _filing_result(best_filing)
        used_urls.add(best_filing['url'])

    return matches


def match_filing_to_history_v2(history_item: dict, sec_filings: list) -> Optional[dict]:
    """
    Match a single history item using the same authoritative date rules as the
    batch matcher. Kept for compatibility with existing callers/tests.
    """
    return match_history_to_filings([history_item], sec_filings).get(0)


def quarter_label_from_filing(filing: dict, fy_end_month: int) -> Optional[str]:
    """Build the display quarter from the SEC form/report date."""
    report_date = _parse_iso_date(filing.get('report_date'))
    form = filing.get('form')
    if not report_date or form not in ('10-K', '10-Q'):
        return None

    if form == '10-K':
        return f"{report_date.year} FY"

    fy_end_month = fy_end_month if 1 <= (fy_end_month or 0) <= 12 else 12
    months_into_fy = (report_date.month - fy_end_month - 1) % 12 + 1
    quarter_number = (months_into_fy + 2) // 3
    if quarter_number not in (1, 2, 3):
        return None
    fiscal_year = report_date.year + 1 if report_date.month > fy_end_month else report_date.year
    return f"{fiscal_year} Q{quarter_number}"


def quarter_labels_from_match_sequence(matches: dict, fy_end_month: int) -> dict:
    """Derive fiscal-quarter labels using actual 10-K dates as year anchors."""
    parsed_matches = []
    for history_index, filing in matches.items():
        report_date = _parse_iso_date(filing.get('report_date'))
        if report_date:
            parsed_matches.append((history_index, filing, report_date))
    parsed_matches.sort(key=lambda item: item[2])

    labels = {}
    annual_positions = [
        position
        for position, (_, filing, _) in enumerate(parsed_matches)
        if filing.get('form') == '10-K'
    ]

    for position, (history_index, filing, report_date) in enumerate(parsed_matches):
        if filing.get('form') == '10-K':
            labels[history_index] = f"{report_date.year} FY"
            continue

        previous_annual = next(
            (annual_position for annual_position in reversed(annual_positions) if annual_position < position),
            None,
        )
        next_annual = next(
            (annual_position for annual_position in annual_positions if annual_position > position),
            None,
        )

        fiscal_year = None
        quarter_number = None
        if previous_annual is not None:
            anchor_date = parsed_matches[previous_annual][2]
            fiscal_year = anchor_date.year + 1
            quarter_number = round((report_date - anchor_date).days / 91.25)
        elif next_annual is not None:
            anchor_date = parsed_matches[next_annual][2]
            fiscal_year = anchor_date.year
            quarters_before_annual = round((anchor_date - report_date).days / 91.25)
            quarter_number = 4 - quarters_before_annual

        if quarter_number in (1, 2, 3):
            labels[history_index] = f"{fiscal_year} Q{quarter_number}"
            continue

        fallback = quarter_label_from_filing(filing, fy_end_month)
        if fallback:
            labels[history_index] = fallback

    return labels


def apply_sec_matches(history_items: list, sec_filings: list, fy_end_month: int) -> dict:
    """
    Replace SEC URL/form metadata atomically from authoritative SEC matches.

    Stale URLs are removed when no filing can be matched; a guessed form is
    never combined with an old URL.
    """
    matches = match_history_to_filings(history_items, sec_filings)
    quarter_labels = quarter_labels_from_match_sequence(matches, fy_end_month)
    stats = {'matched': 0, 'changed': 0, 'unmatched': 0, 'pending': 0}

    for index, history_item in enumerate(history_items):
        match = matches.get(index)
        old_pair = (history_item.get('secUrl'), history_item.get('form'))
        if not match:
            history_item.pop('secUrl', None)
            history_item.pop('form', None)
            release_date = _parse_iso_date(history_item.get('date'))
            release_age = (date.today() - release_date).days if release_date else None
            if release_age is not None and 0 <= release_age <= SEC_FILING_GRACE_DAYS:
                history_item['secStatus'] = 'pending'
                stats['pending'] += 1
            else:
                history_item.pop('secStatus', None)
            stats['unmatched'] += 1
            if old_pair != (None, None):
                stats['changed'] += 1
            continue

        history_item['secUrl'] = match['url']
        history_item['form'] = match['form']
        history_item.pop('secStatus', None)
        quarter_label = quarter_labels.get(index)
        if quarter_label:
            history_item['quarter'] = quarter_label
        stats['matched'] += 1
        if old_pair != (history_item['secUrl'], history_item['form']):
            stats['changed'] += 1

    return stats


def validate_sec_matches(history_items: list, sec_filings: list) -> list:
    """Return metadata errors for URL/form pairs not backed by SEC submissions."""
    official_by_url = {
        _canonical_sec_doc_path(filing['url']): filing
        for filing in sec_filings
        if filing.get('url')
    }
    expected_matches = match_history_to_filings(history_items, sec_filings)
    issues = []
    for index, history_item in enumerate(history_items):
        sec_url = history_item.get('secUrl')
        form = history_item.get('form')
        expected = expected_matches.get(index)
        if not sec_url:
            if expected:
                issues.append({
                    'type': 'missing_url',
                    'date': history_item.get('date'),
                    'expected_url': expected['url'],
                })
                continue
            release_date = _parse_iso_date(history_item.get('date'))
            release_age = (date.today() - release_date).days if release_date else None
            if (
                history_item.get('secStatus') == 'pending'
                and release_age is not None
                and 0 <= release_age <= SEC_FILING_GRACE_DAYS
            ):
                continue
            issues.append({'type': 'missing_url', 'date': history_item.get('date')})
            continue
        official = official_by_url.get(_canonical_sec_doc_path(sec_url))
        if not official:
            issues.append({'type': 'unknown_url', 'date': history_item.get('date'), 'url': sec_url})
        elif official['form'] != form:
            issues.append({
                'type': 'form_mismatch',
                'date': history_item.get('date'),
                'url': sec_url,
                'expected': official['form'],
                'actual': form,
            })
        elif not expected:
            issues.append({
                'type': 'unexpected_url',
                'date': history_item.get('date'),
                'url': sec_url,
            })
        elif _canonical_sec_doc_path(expected['url']) != _canonical_sec_doc_path(sec_url):
            issues.append({
                'type': 'wrong_report',
                'date': history_item.get('date'),
                'url': sec_url,
                'expected_url': expected['url'],
            })
    return issues


# ─────────────────────────────────────────────
# yfinance 數據抓取
# ─────────────────────────────────────────────


def fetch_earnings_data(ticker: str, fy_end_month: int = 12, retries: int = 2) -> Optional[dict]:
    """從 yfinance 抓取公司財報數據（不含歷史，歷史另由 build_history 處理）"""
    if yf is None:
        print(f"  ⚠️ {ticker}: 缺少 yfinance，無法抓取")
        return None

    for attempt in range(retries + 1):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            eps_est = info.get('epsForward') or info.get('earningsEstimateAvg')
            rev_est = info.get('revenueEstimateAvg') or info.get('revenueEstimate')
            eps_str = format_eps(eps_est)
            rev_str = format_revenue(rev_est)

            report_date_str = None
            bmo_amc_str = None

            try:
                earnings = stock.earnings_dates
                if earnings is not None and not earnings.empty:
                    next_date = earnings.index[0]
                    if isinstance(next_date, datetime):
                        report_date_str = next_date.strftime('%Y-%m-%d')
                        if 'Earnings Time' in earnings.columns:
                            earnings_time = earnings.iloc[0].get('Earnings Time', '')
                            if earnings_time == 'Before market open':
                                bmo_amc_str = '☀️'
                            elif earnings_time == 'After market close':
                                bmo_amc_str = '🌙'
            except Exception:
                pass

            if not report_date_str:
                next_earnings = info.get('earningsDate') or info.get('earningsTimestamp')
                if next_earnings:
                    if isinstance(next_earnings, (int, float)):
                        report_date_obj = datetime.fromtimestamp(next_earnings).date()
                        report_date_str = report_date_obj.strftime('%Y-%m-%d')

            return {
                "reportDate": report_date_str,
                "bmo_amc": bmo_amc_str,
                "eps": eps_str,
                "revenue": rev_str,
            }

        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ⚠️ {ticker}: 抓取失敗 ({e})")
            return None


def build_history_from_earnings(stock, fy_end_month: int) -> list:
    """
    從 yfinance 抓取歷史 EPS/營收，並使用修正後的 quarter 推算邏輯。

    從 earnings release date 推估期間結束日，再用期間結束日計算 quarter label。
    """
    if pd is None:
        return []

    try:
        ed = stock.earnings_dates
        if ed is None or ed.empty:
            return []
        past = ed.dropna(subset=['Reported EPS'])
        if past.empty:
            return []

        revenue_lookup = {}
        try:
            qf = stock.quarterly_income_stmt
            if qf is not None and not qf.empty and 'Total Revenue' in qf.index:
                revenues = qf.loc['Total Revenue']
                for col_date, rev_val in revenues.items():
                    if rev_val and not (isinstance(rev_val, float) and pd.isna(rev_val)):
                        date_str = col_date.strftime('%Y-%m-%d') if isinstance(col_date, pd.Timestamp) else str(col_date)[:10]
                        revenue_lookup[date_str] = rev_val
        except Exception:
            pass

        history = []
        for idx, row in past.iterrows():
            report_date = idx.date() if isinstance(idx, datetime) else idx
            eps_val = row.get('Reported EPS')
            if eps_val is None or pd.isna(eps_val):
                continue

            # 修正點：用期間結束日而非發布日來計算 quarter label
            period_end = estimate_period_end(report_date)
            quarter_label = quarter_label_from_period_end(period_end, fy_end_month) if period_end else None

            revenue_str = "-"
            date_str = report_date.strftime('%Y-%m-%d')
            for rev_date, rev_val in sorted(revenue_lookup.items(), reverse=True):
                if rev_date <= date_str:
                    revenue_str = format_revenue(rev_val)
                    break

            history.append({
                "date": date_str,
                "quarter": quarter_label,
                "eps_reported": format_eps(eps_val),
                "revenue_reported": revenue_str,
            })

        history = history[:5]
        history.reverse()
        return history

    except Exception as e:
        print(f"    抓取歷史 EPS 失敗: {e}")
        return []


# ─────────────────────────────────────────────
# 主更新邏輯
# ─────────────────────────────────────────────


def update_data(
    full_mode: bool = False,
    sample_mode: bool = False,
    tickers_filter: list = None,
    rebuild_historical: bool = False,
) -> bool:
    """
    主更新流程。

    - full_mode: 處理所有公司（首次建置或重建時使用）
    - sample_mode: 只處理樣本公司（測試用）
    - tickers_filter: 只處理指定公司
    """
    today = date.today()
    strict_sec_validation = rebuild_historical or full_mode

    # ── 載入現有 data.json ──
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        print(f"✅ 讀取現有 data.json，共 {len(existing_data)} 家公司\n")
    except FileNotFoundError:
        print("❌ data.json 不存在")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ data.json JSON 解析錯誤: {e}")
        return False

    # ── 載入現有 historical_data.json（如果存在）──
    historical_data = {}
    try:
        with open('historical_data.json', 'r', encoding='utf-8') as f:
            historical_data = json.load(f)
        print(f"✅ 讀取 historical_data.json，共 {len(historical_data)} 家\n")
    except (FileNotFoundError, json.JSONDecodeError):
        print("📄 historical_data.json 不存在或為空，將重新建立\n")

    # ── 載入 SEC mapping ──
    sec_mapping = {}
    try:
        with open('sp500_mapping.json', 'r', encoding='utf-8') as f:
            sec_mapping = json.load(f)
        print(f"✅ 讀取 sp500_mapping.json，共 {len(sec_mapping)} 家公司\n")
    except FileNotFoundError:
        print("⚠️  sp500_mapping.json 不存在")
    except json.JSONDecodeError as e:
        print(f"⚠️  sp500_mapping.json JSON 解析錯誤: {e}")

    alias_migrations = migrate_ticker_aliases(existing_data, historical_data)
    if alias_migrations:
        print(f"✅ 已遷移 {alias_migrations} 個舊股票代碼到目前代碼\n")

    # ── 決定要處理哪些公司 ──
    if rebuild_historical:
        companies_to_update = existing_data
        print(f"🔁 historical rebuild 模式：刷新全部 {len(companies_to_update)} 家公司的 SEC metadata")
    elif sample_mode:
        sample_tickers = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'WMT']
        companies_to_update = [c for c in existing_data if c['ticker'] in sample_tickers]
        print(f"🧪 樣本模式：只處理 {len(companies_to_update)} 家公司")
    elif tickers_filter:
        companies_to_update = [c for c in existing_data if c['ticker'] in tickers_filter]
        print(f"🔍 指定 ticker 模式：處理 {len(companies_to_update)} 家公司")
    elif full_mode:
        companies_to_update = existing_data
        print(f"📊 完整模式：處理全部 {len(companies_to_update)} 家公司")
    else:
        # 增量模式：只處理未來 30 天內要發布的公司
        companies_to_update = []
        for c in existing_data:
            rd = c.get('reportDate')
            if rd:
                try:
                    rd_date = datetime.strptime(rd, '%Y-%m-%d').date()
                    delta = (rd_date - today).days
                    if 0 <= delta <= 30:
                        companies_to_update.append(c)
                except ValueError:
                    pass
        # 如果完全沒有即將發布的公司，也處理過去 7 天內已發布的
        if not companies_to_update:
            for c in existing_data:
                rd = c.get('reportDate')
                if rd:
                    try:
                        rd_date = datetime.strptime(rd, '%Y-%m-%d').date()
                        delta = (today - rd_date).days
                        if 0 <= delta <= 7:
                            companies_to_update.append(c)
                    except ValueError:
                        pass
        print(f"📊 增量模式：處理 {len(companies_to_update)} 家即將發布/近期發布的公司")

        pending_tickers = {
            ticker
            for ticker, history in historical_data.items()
            if any(item.get('secStatus') == 'pending' for item in history)
        }
        selected_tickers = {company['ticker'] for company in companies_to_update}
        pending_companies = [
            company
            for company in existing_data
            if company['ticker'] in pending_tickers and company['ticker'] not in selected_tickers
        ]
        if pending_companies:
            companies_to_update.extend(pending_companies)
            print(f"   另加入 {len(pending_companies)} 家等待 SEC 申報的公司")

    if not companies_to_update:
        print("❌ 沒有符合條件的公司")
        return False

    existing_map = {c['ticker']: c for c in existing_data}

    # ── 從 SEC API 抓取 filing 列表 ──
    if SEC_PROXY_URL:
        print(f"🔀 使用 SEC Proxy: {SEC_PROXY_URL}")
    print("⏳ 從 SEC API 抓取 filing 列表...")

    sec_filing_cache = {}
    sec_fetch_count = 0
    sec_fetch_failures = 0
    sec_empty_count = 0
    total = len(companies_to_update)
    fetched_by_cik = {}
    missing_sec_mapping = [
        company['ticker']
        for company in companies_to_update
        if not sec_mapping.get(company['ticker'], {}).get('cik')
    ]
    if strict_sec_validation and missing_sec_mapping:
        print(
            "❌ 全量重建中止：以下公司缺少 SEC CIK 映射："
            + ', '.join(missing_sec_mapping)
        )
        return False

    for index, company in enumerate(companies_to_update):
        ticker = company['ticker']
        mapping_entry = sec_mapping.get(ticker, {})
        cik = mapping_entry.get('cik', '')
        if not cik:
            sec_filing_cache[ticker] = []
            continue
        try:
            cik_padded = str(int(cik)).zfill(10)
        except (ValueError, TypeError):
            sec_filing_cache[ticker] = []
            continue

        if cik_padded in fetched_by_cik:
            filing_data = fetched_by_cik[cik_padded]
        else:
            filing_data = fetch_sec_filing_data(cik_padded)
            fetched_by_cik[cik_padded] = filing_data
        if filing_data is None:
            sec_fetch_failures += 1
            if strict_sec_validation and len(fetched_by_cik) == 1:
                print("❌ SEC 預檢失敗；中止全量重建，避免連續發送無效請求")
                return False
        else:
            filings = filing_data['filings']
            sec_filing_cache[ticker] = filings
            official_fy_end = filing_data.get('fy_end_month')
            if official_fy_end:
                mapping_entry['fy_end'] = official_fy_end
            if filings:
                sec_fetch_count += 1
            else:
                sec_empty_count += 1

        if (index + 1) % 10 == 0 or index + 1 == total:
            print(
                f"    SEC: {index + 1}/{total} 家公司處理完畢"
                f"（{sec_fetch_count} 家有 filing；{sec_fetch_failures} 家失敗"
                f"；{sec_empty_count} 家無 10-K/10-Q）"
            )
        time.sleep(0.12)

    print(
        f"    SEC filing 抓取完成，{sec_fetch_count}/{total} 家有資料"
        f"；{sec_fetch_failures} 家請求失敗；{sec_empty_count} 家無 10-K/10-Q\n"
    )
    if strict_sec_validation and (sec_fetch_failures or sec_empty_count):
        print("❌ 全量重建中止：SEC 官方資料未完整取得，現有資料檔案不會被覆寫")
        return False

    # ── 更新每家公司數據 ──
    updated_count = 0
    failed_count = 0

    if rebuild_historical:
        print("⏭️  rebuild-historical 模式：略過 yfinance 未來財報估值更新")

    for idx, company in enumerate(companies_to_update):
        ticker = company['ticker']
        print(f"  [{idx+1}/{total}] 處理 {ticker}...", end=" ")

        fy_end = 12
        if ticker in sec_mapping:
            fy_end = sec_mapping[ticker].get('fy_end', 12)

        if rebuild_historical:
            print("⏭️")
            continue

        result = fetch_earnings_data(ticker, fy_end_month=fy_end)

        if result:
            existing = existing_map.get(ticker, {})
            existing['reportDate'] = result['reportDate'] or existing.get('reportDate')
            existing['bmo_amc'] = result['bmo_amc'] or existing.get('bmo_amc')
            existing['eps'] = result['eps'] if result['eps'] != '-' else existing.get('eps', '-')
            existing['revenue'] = result['revenue'] if result['revenue'] != '-' else existing.get('revenue', '-')
            existing['ticker'] = ticker
            existing_map[ticker] = existing
            updated_count += 1
            print(f"✅ (報告日: {result.get('reportDate', '-')})")
        else:
            print("❌ (保留現有數據)")
            failed_count += 1

        if (idx + 1) % 10 == 0 and idx + 1 < total:
            print(f"  ⏳ 已處理 {idx+1}/{total}，暫停 1 秒...")
            time.sleep(1)
        else:
            time.sleep(0.2)

    # ── 合併歷史數據 ──
    #   對於 data.json 中已不再包含 history 的公司（因為已分離出去），
    #   從 historical_data.json 中保留。
    print("\n🔄 建立/更新 historical_data.json...")
    sec_url_fix_count = 0
    sec_unmatched_count = 0
    sec_pending_count = 0
    validation_issues = []
    validated_company_count = 0

    for company in existing_data:
        ticker = company['ticker']
        fy_end = sec_mapping.get(ticker, {}).get('fy_end', 12)

        # 從 SEC filing cache 取得該公司的 filings
        sec_filings = sec_filing_cache.get(ticker, [])

        # 取得現有的歷史數據（從 data.json 或 historical_data.json）
        existing_history = company.get('history', [])
        archived_history = historical_data.get(ticker, [])

        target_history = existing_history if existing_history else archived_history
        if not target_history or ticker not in sec_filing_cache or not sec_filings:
            continue

        match_stats = apply_sec_matches(target_history, sec_filings, fy_end)
        sec_url_fix_count += match_stats['changed']
        sec_unmatched_count += match_stats['unmatched']
        sec_pending_count += match_stats['pending']
        historical_data[ticker] = target_history

        ticker_issues = validate_sec_matches(target_history, sec_filings)
        validated_company_count += 1
        validation_issues.extend(
            {'ticker': ticker, **issue}
            for issue in ticker_issues
        )

    if validation_issues:
        print(f"⚠️  SEC metadata 驗證仍有 {len(validation_issues)} 個問題")
        for issue in validation_issues[:20]:
            print(f"   {issue}")
    elif validated_company_count:
        print(
            f"✅ {validated_company_count} 家已處理公司的 SEC URL 與 "
            "10-K/10-Q 標籤全部通過官方 metadata 驗證"
        )
    else:
        print("⚠️  沒有公司取得 SEC 官方 metadata，因此未執行連結驗證")

    if strict_sec_validation and validation_issues:
        print("❌ 全量重建中止：仍有未匹配或標籤錯配，現有資料檔案不會被覆寫")
        return False

    # ── 寫入 data.json（不含 history）──
    final_data = []
    for company in existing_data:
        ticker = company['ticker']
        entry = {
            "ticker": ticker,
            "name": company.get('name', ticker),
        }
        updated = existing_map.get(ticker, {})
        entry['reportDate'] = updated.get('reportDate') or company.get('reportDate')
        entry['bmo_amc'] = updated.get('bmo_amc') or company.get('bmo_amc')
        entry['eps'] = updated.get('eps') or company.get('eps', '-')
        entry['revenue'] = updated.get('revenue') or company.get('revenue', '-')
        final_data.append(entry)

    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print(f"✅ data.json 寫入完成！共 {len(final_data)} 家公司")
    except Exception as e:
        print(f"❌ data.json 寫入失敗: {e}")
        return False

    # ── 寫入 historical_data.json ──
    try:
        with open('historical_data.json', 'w', encoding='utf-8') as f:
            json.dump(historical_data, f, ensure_ascii=False, indent=2)
        print(f"✅ historical_data.json 寫入完成！共 {len(historical_data)} 家公司的歷史資料")

        # 統計 secUrl 覆蓋率
        total_hist_items = sum(len(v) for v in historical_data.values())
        total_with_sec = sum(sum(1 for h in v if 'secUrl' in h) for v in historical_data.values())
        total_with_form = sum(sum(1 for h in v if 'form' in h) for v in historical_data.values())
        print(f"   歷史財報總筆數: {total_hist_items}")
        if total_hist_items:
            print(f"   有 SEC URL: {total_with_sec} ({total_with_sec/total_hist_items*100:.1f}%)")
            print(f"   有 SEC form: {total_with_form} ({total_with_form/total_hist_items*100:.1f}%)")
        if sec_url_fix_count > 0:
            print(f"   本次修復/新增: {sec_url_fix_count} 個 SEC metadata")
        if sec_unmatched_count > 0:
            print(f"   無法匹配並已移除舊連結: {sec_unmatched_count} 個")
        if sec_pending_count > 0:
            print(f"   等待 SEC 尚未提交文件: {sec_pending_count} 個")

        if sec_mapping:
            with open('sp500_mapping.json', 'w', encoding='utf-8') as f:
                json.dump(sec_mapping, f, ensure_ascii=False, indent=4)
            print("✅ sp500_mapping.json 已同步 SEC 官方財年結束月份")
    except Exception as e:
        print(f"❌ historical_data.json 寫入失敗: {e}")
        return False

    print(f"\n🎉 更新完成！更新成功: {updated_count} | 失敗: {failed_count}")
    return True


def audit_sec_dataset() -> bool:
    """Independently audit stored links against cached/current SEC submissions."""
    try:
        with open('data.json', 'r', encoding='utf-8') as file:
            companies = json.load(file)
        with open('historical_data.json', 'r', encoding='utf-8') as file:
            historical_data = json.load(file)
        with open('sp500_mapping.json', 'r', encoding='utf-8') as file:
            sec_mapping = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        print(f"❌ 無法讀取稽核資料: {exc}")
        return False

    issues = []
    company_tickers = {company.get('ticker') for company in companies}
    history_tickers = set(historical_data)
    mapping_tickers = set(sec_mapping)
    if company_tickers != history_tickers:
        issues.append({
            'type': 'company_history_ticker_mismatch',
            'missing_history': sorted(company_tickers - history_tickers),
            'extra_history': sorted(history_tickers - company_tickers),
        })
    if company_tickers != mapping_tickers:
        issues.append({
            'type': 'company_mapping_ticker_mismatch',
            'missing_mapping': sorted(company_tickers - mapping_tickers),
            'extra_mapping': sorted(mapping_tickers - company_tickers),
        })

    total_records = 0
    linked_records = 0
    pending_records = 0
    for company in companies:
        ticker = company.get('ticker')
        mapping_entry = sec_mapping.get(ticker, {})
        cik = mapping_entry.get('cik')
        history = historical_data.get(ticker, [])
        total_records += len(history)
        if not cik:
            issues.append({'ticker': ticker, 'type': 'missing_cik'})
            continue

        try:
            cik_padded = str(int(cik)).zfill(10)
            expected_cik = str(int(cik))
        except (TypeError, ValueError):
            issues.append({'ticker': ticker, 'type': 'invalid_cik', 'cik': cik})
            continue

        filing_data = fetch_sec_filing_data(cik_padded)
        if not filing_data or not filing_data['filings']:
            issues.append({'ticker': ticker, 'type': 'missing_sec_metadata'})
            continue

        for issue in validate_sec_matches(history, filing_data['filings']):
            issues.append({'ticker': ticker, **issue})

        seen_paths = set()
        for history_item in history:
            sec_url = history_item.get('secUrl')
            if not sec_url:
                if history_item.get('secStatus') == 'pending':
                    pending_records += 1
                continue
            linked_records += 1
            parsed = urlparse(sec_url)
            path = _canonical_sec_doc_path(sec_url)
            path_parts = path.split('/')
            if parsed.scheme != 'https' or parsed.hostname != 'www.sec.gov':
                issues.append({'ticker': ticker, 'type': 'non_sec_url', 'url': sec_url})
            if len(path_parts) < 6 or path_parts[:3] != ['Archives', 'edgar', 'data']:
                issues.append({'ticker': ticker, 'type': 'invalid_sec_path', 'url': sec_url})
            elif path_parts[3] != expected_cik:
                issues.append({
                    'ticker': ticker,
                    'type': 'cik_mismatch',
                    'expected': expected_cik,
                    'actual': path_parts[3],
                    'url': sec_url,
                })
            if path in seen_paths:
                issues.append({'ticker': ticker, 'type': 'duplicate_report', 'url': sec_url})
            seen_paths.add(path)

            form = history_item.get('form')
            quarter = history_item.get('quarter', '')
            if form == '10-K' and 'FY' not in quarter:
                issues.append({
                    'ticker': ticker,
                    'type': 'annual_quarter_label_mismatch',
                    'date': history_item.get('date'),
                    'quarter': quarter,
                })
            if form == '10-Q' and 'FY' in quarter:
                issues.append({
                    'ticker': ticker,
                    'type': 'quarterly_quarter_label_mismatch',
                    'date': history_item.get('date'),
                    'quarter': quarter,
                })

    print(
        f"SEC 稽核: {len(companies)} 家公司；{total_records} 筆財報；"
        f"{linked_records} 筆官方連結；{pending_records} 筆等待申報"
    )
    if issues:
        print(f"❌ 發現 {len(issues)} 個問題")
        for issue in issues[:50]:
            print(f"   {issue}")
        return False

    print("✅ 所有已存在連結的公司、期間、CIK 與 10-K/10-Q 標籤均通過 SEC 官方資料驗證")
    return True


# ─────────────────────────────────────────────
# 入口
# ─────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S&P 500 Earnings Tracker 數據更新腳本")
    parser.add_argument('--full', action='store_true', help='完整模式（處理所有公司）')
    parser.add_argument('--sample', action='store_true', help='樣本模式')
    parser.add_argument('--ticker', type=str, help='指定 ticker（逗號分隔）')
    parser.add_argument('--rebuild-historical', action='store_true', help='重建 historical_data.json 的 SEC URL/form metadata')
    parser.add_argument('--validate-sec', action='store_true', help='以 SEC 官方 metadata 稽核現有連結與標籤')
    args = parser.parse_args()

    tickers = None
    if args.ticker:
        tickers = [t.strip().upper() for t in args.ticker.split(',') if t.strip()]

    if args.validate_sec:
        ok = audit_sec_dataset()
    else:
        ok = update_data(
            full_mode=args.full,
            sample_mode=args.sample,
            tickers_filter=tickers,
            rebuild_historical=args.rebuild_historical,
        )
    if not ok:
        sys.exit(1)
