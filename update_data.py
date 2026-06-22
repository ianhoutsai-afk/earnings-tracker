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


SEC_HEADERS = {
    'User-Agent': 'Earnings Dashboard admin@earnings-tracker.local',
    'Accept-Encoding': 'gzip, deflate',
}

SEC_PROXY_URL = os.environ.get('SEC_PROXY_URL', '')
SEC_PROXY_TOKEN = os.environ.get('PROXY_TOKEN', '')


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
        return requests.get(url, headers=SEC_HEADERS, timeout=timeout)

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


def fetch_sec_filing_list(cik: str) -> list:
    """
    從 SEC API 抓取該公司的 10-K/10-Q 文件列表。
    回傳 list[dict]:
        [
            {
                "form": "10-Q",
                "report_date": "2025-03-28",  # 期間結束日
                "filing_date": "2025-05-01",   # 提交日期
                "url": "https://...",
            },
            ...
        ]
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    for attempt in range(3):
        try:
            res = _sec_request(url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                break
            elif res.status_code == 429:
                time.sleep((attempt + 1) * 3)
                continue
            elif res.status_code == 403:
                return []
            else:
                if attempt < 2:
                    time.sleep(1)
                    continue
                return []
        except Exception:
            if attempt < 2:
                time.sleep(1)
                continue
            return []

    recent = data.get('filings', {}).get('recent', {})
    forms = recent.get('form', [])
    accessions = recent.get('accessionNumber', [])
    primary_docs = recent.get('primaryDocument', [])
    report_dates = recent.get('reportDate', [])
    filing_dates = recent.get('filingDate', [])
    if not forms:
        return []

    candidates = []
    for i, form in enumerate(forms):
        if form in ('10-K', '10-K/A', '10-Q', '10-Q/A'):
            report_date_str = report_dates[i] if i < len(report_dates) else ''
            filing_date_str = filing_dates[i] if i < len(filing_dates) else ''
            if not report_date_str or not filing_date_str:
                continue
            base_form = form.replace('/A', '')
            candidates.append({
                'form': base_form,
                'report_date': report_date_str,
                'filing_date': filing_date_str,
                'url': build_sec_ixbrl_url(cik, accessions[i], primary_docs[i]),
            })

    candidates.sort(key=lambda x: x['report_date'], reverse=True)
    return candidates


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


def match_filing_to_history_v2(history_item: dict, sec_filings: list) -> Optional[dict]:
    """
    精準匹配 history 項目到 SEC filing。
    回傳 dict {url, form}，或 None（找不到匹配）。

    匹配邏輯：
    1. 從 earnings release date（history.date）推估期間結束日
    2. 在 SEC filings 中尋找 report_date 完全匹配的項目
    3. 回傳時附帶 SEC 官方 form 類型（10-K 或 10-Q）

    如果 exact match 找不到，放寬到 ±3 天容差。財報分類不再依賴
    quarter label 推算，而是直接使用 SEC filing 的 form 欄位。
    """
    history_date_str = history_item.get('date', '')
    if not history_date_str:
        return None

    try:
        release_date = datetime.strptime(history_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

    # 估算期間結束日
    estimated_period_end = estimate_period_end(release_date)
    if not estimated_period_end:
        return None

    parsed_filings = []
    for filing in sec_filings:
        try:
            filing_report_date = datetime.strptime(filing['report_date'], '%Y-%m-%d').date()
        except (KeyError, ValueError):
            continue
        try:
            filing_date = datetime.strptime(filing.get('filing_date', ''), '%Y-%m-%d').date()
        except ValueError:
            filing_date = filing_report_date
        parsed_filings.append((filing, filing_report_date, filing_date))

    def result_for(filing: dict) -> dict:
        return {"url": filing['url'], "form": filing['form']}

    # 先嘗試 exact match
    exact_matches = [
        (filing, filing_date)
        for filing, filing_report_date, filing_date in parsed_filings
        if filing_report_date == estimated_period_end
    ]
    if exact_matches:
        best_filing, _ = min(
            exact_matches,
            key=lambda item: abs((item[1] - release_date).days),
        )
        return result_for(best_filing)

    # 放寬到 ±3 天
    best = None
    best_diff = None
    best_filing_diff = None
    for filing, filing_report_date, filing_date in parsed_filings:
        diff = abs((filing_report_date - estimated_period_end).days)
        if diff <= 3:
            filing_diff = abs((filing_date - release_date).days)
            if best is None or (diff, filing_diff) < (best_diff, best_filing_diff):
                best = result_for(filing)
                best_diff = diff
                best_filing_diff = filing_diff

    return best


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
    total = len(companies_to_update)

    for idx, company in enumerate(companies_to_update):
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

        filings = fetch_sec_filing_list(cik_padded)
        sec_filing_cache[ticker] = filings
        if filings:
            sec_fetch_count += 1

        if (idx + 1) % 10 == 0 or idx + 1 == total:
            print(f"    SEC: {idx+1}/{total} 家公司處理完畢（{sec_fetch_count} 家有 filing）")
        time.sleep(0.1)

    print(f"    SEC filing 抓取完成，{sec_fetch_count}/{total} 家有資料\n")

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

    for company in existing_data:
        ticker = company['ticker']
        fy_end = sec_mapping.get(ticker, {}).get('fy_end', 12)

        # 從 SEC filing cache 取得該公司的 filings
        sec_filings = sec_filing_cache.get(ticker, [])

        # 取得現有的歷史數據（從 data.json 或 historical_data.json）
        existing_history = company.get('history', [])
        archived_history = historical_data.get(ticker, [])

        if existing_history and len(existing_history) > 0:
            # 使用修正後的 quarter label 和 SEC 匹配邏輯重新處理
            corrected_history = []
            for h_item in existing_history:
                # 修正 quarter label
                try:
                    release_date = datetime.strptime(h_item['date'], '%Y-%m-%d').date()
                    period_end = estimate_period_end(release_date)
                    corrected_quarter = quarter_label_from_period_end(period_end, fy_end)
                    h_item['quarter'] = corrected_quarter
                except (ValueError, TypeError):
                    pass

                # 使用修正後的匹配邏輯配對 SEC URL 和 form 類型
                sec_match = match_filing_to_history_v2(h_item, sec_filings)
                if not sec_match and h_item.get('secUrl'):
                    sec_match = match_filing_by_sec_url(h_item['secUrl'], sec_filings)
                if sec_match:
                    h_item['secUrl'] = sec_match['url']
                    h_item['form'] = sec_match['form']  # SEC 官方分類：10-K 或 10-Q
                    sec_url_fix_count += 1
                elif 'secUrl' not in h_item:
                    # 如果舊有有 secUrl，保留它
                    pass

                corrected_history.append(h_item)

            historical_data[ticker] = corrected_history

        elif archived_history:
            # 已分離到 historical_data.json，嘗試補上缺失的 secUrl 及 form
            needs_update = False
            for h_item in archived_history:
                if rebuild_historical or 'secUrl' not in h_item or 'form' not in h_item:
                    sec_match = match_filing_to_history_v2(h_item, sec_filings)
                    if not sec_match and h_item.get('secUrl'):
                        sec_match = match_filing_by_sec_url(h_item['secUrl'], sec_filings)
                    if sec_match:
                        h_item['secUrl'] = sec_match['url']
                        h_item['form'] = sec_match['form']
                        sec_url_fix_count += 1
                        needs_update = True
            if needs_update:
                historical_data[ticker] = archived_history

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
    except Exception as e:
        print(f"❌ historical_data.json 寫入失敗: {e}")
        return False

    print(f"\n🎉 更新完成！更新成功: {updated_count} | 失敗: {failed_count}")
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
    args = parser.parse_args()

    tickers = None
    if args.ticker:
        tickers = [t.strip().upper() for t in args.ticker.split(',') if t.strip()]

    ok = update_data(
        full_mode=args.full,
        sample_mode=args.sample,
        tickers_filter=tickers,
        rebuild_historical=args.rebuild_historical,
    )
    if not ok:
        sys.exit(1)
