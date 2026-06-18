#!/usr/bin/env python3
"""
update_data.py — S&P 500 Earnings Tracker 數據更新腳本

功能：
1. 從 data.json 讀取現有公司資料
2. 從 sp500_mapping.json 讀取財年結算月份（fy_end）與 CIK
3. 用 yfinance 抓取即時財報日期、EPS 預估、營收預估
4. 從 yfinance earnings_dates 抓取真實歷史 EPS（Reported EPS）
5. 根據日期 + fy_end 推算季度/年度標籤
6. 從 SEC API 即時抓取 10-K/10-Q filing URL，根據 filingDate 配對到各季度
7. 產生 5 筆歷史資料（含精確 SEC 直連網址）
8. 動態計算 countdown（離財報發布日天數）
9. 判斷 BMO/AMC 標示
10. 合併後寫回 data.json

用法：
    python update_data.py              # 完整更新全部公司
    python update_data.py --sample     # 樣本模式（只處理 AAPL, MSFT, NVDA, AMZN, GOOGL, WMT）
    python update_data.py --ticker AAPL,MSFT  # 只處理指定公司，用逗號分隔
"""

import yfinance as yf
import json
import time
import sys
import argparse
import requests
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd


# SEC API 請求標頭（需包含聯絡資訊）
SEC_HEADERS = {
    'User-Agent': 'Earnings Dashboard admin@earnings-tracker.local',
    'Accept-Encoding': 'gzip, deflate',
}


def fiscal_quarter_from_date(report_date: date, fy_end_month: int) -> Optional[str]:
    """
    根據財報發布日期與公司財年結束月份，推算此財報屬於哪個季度/年度。

    例如：
    - Apple (fy_end=9): 10-12月→Q1, 1-3月→Q2, 4-6月→Q3, 7-9月→FY
    - Microsoft (fy_end=6): 7-9月→Q1, 10-12月→Q2, 1-3月→Q3, 4-6月→FY
    - 標準 12月結算: 1-3月→Q1, 4-6月→Q2, 7-9月→Q3, 10-12月→FY

    回傳格式: "2025 Q1", "2025 Q2", "2025 Q3", "2025 FY", "2026 Q1"
    """
    if not report_date or not fy_end_month:
        return None

    month = report_date.month
    year = report_date.year

    # 財年 = fy_end_month 的後一個月開始
    fy_start_month = fy_end_month + 1
    if fy_start_month > 12:
        fy_start_month = 1

    # 計算這是財年的第幾個月
    if month >= fy_start_month:
        months_into_fy = month - fy_start_month + 1
    else:
        months_into_fy = month + (12 - fy_start_month + 1)

    quarter = (months_into_fy - 1) // 3 + 1

    # 財年年份：報告月份 > fy_end_month 表示進入下個財年
    if month > fy_end_month:
        fy_year = year + 1
    else:
        fy_year = year

    if quarter == 4:
        return f"{fy_year} FY"
    else:
        return f"{fy_year} Q{quarter}"


def format_eps(value) -> str:
    """格式化 EPS 值"""
    if value is None:
        return "-"
    try:
        v = float(value)
        return f"${v:.2f}"
    except (ValueError, TypeError):
        return "-"


def format_revenue(value) -> str:
    """格式化營收值"""
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


def build_sec_url(cik: str, accession_number: str, primary_document: str) -> Optional[str]:
    """組裝指向特定 10-Q / 10-K 文件的精確 SEC 直連網址"""
    if not all([cik, accession_number, primary_document]):
        return None
    cik_int = str(int(cik))
    acc_no_dashes = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_document}"


def fetch_sec_filing_list(cik: str) -> list:
    """
    從 SEC API 抓取該公司的 10-K/10-Q 文件列表。

    回傳 list[dict]:
        [
            {"filingDate": "2025-05-01", "form": "10-Q", "url": "https://...", "reportDate": "2025-03-28"},
            ...
        ]
    若失敗則回傳空 list。
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        res = requests.get(url, headers=SEC_HEADERS, timeout=15)
        if res.status_code != 200:
            return []
        data = res.json()
    except Exception:
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
            # 標準化 form 名稱（移除 /A 後綴）
            base_form = form.replace('/A', '')
            candidates.append({
                'form': base_form,
                'accession': accessions[i],
                'primary_doc': primary_docs[i],
                'report_date': report_date_str,
                'filing_date': filing_date_str,
                'url': build_sec_url(cik, accessions[i], primary_docs[i]),
            })
    # 按 filingDate 降序排列（最新的在前）
    candidates.sort(key=lambda x: x['filing_date'], reverse=True)
    return candidates


def match_filing_to_history(history_item: dict, sec_filings: list) -> Optional[str]:
    """
    將一筆歷史財報資料（含 date 和 quarter label）配對到最合適的 SEC filing URL。

    配對規則：
    1. 從 SEC filings 中找到 filingDate 最接近 history.date 的 filing
       （優先找 filingDate 剛好在 history.date 之後 0-3 天內的 filing）
    2. 驗證 form 類型：
       - FY → 必須是 10-K
       - Q1/Q2/Q3 → 必須是 10-Q
    3. 若找不到符合條件的，回傳 None
    """
    history_date_str = history_item.get('date', '')
    quarter_label = history_item.get('quarter', '')

    if not history_date_str or not quarter_label:
        return None

    # 解析 quarter label：提取 Q1/Q2/Q3 或 FY
    q_key = quarter_label.split()[-1] if ' ' in quarter_label else quarter_label
    is_fy = (q_key == 'FY')
    expected_form = '10-K' if is_fy else '10-Q'

    try:
        hist_date = datetime.strptime(history_date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

    best_url = None
    best_diff = None

    for filing in sec_filings:
        if filing['form'] != expected_form:
            continue

        try:
            filing_dt = datetime.strptime(filing['filing_date'], '%Y-%m-%d').date()
        except ValueError:
            continue

        diff = (filing_dt - hist_date).days

        # 只考慮 filingDate 在 history date 之後 0-10 天內，或之前最多 3 天
        if diff < -3 or diff > 10:
            continue

        # 找 filingDate 最接近 history date 的（優先選擇之後的）
        if best_url is None:
            best_url = filing['url']
            best_diff = diff
        elif diff >= 0 and (best_diff < 0 or diff < best_diff):
            # 優先選擇 diff >= 0（之後）且 diff 最小的
            best_url = filing['url']
            best_diff = diff
        elif diff < 0 and best_diff < 0 and diff > best_diff:
            # 如果都是負的，選最接近的（diff 最大的負數）
            best_url = filing['url']
            best_diff = diff

    return best_url


def fetch_earnings_data(ticker: str, fy_end_month: int = 12, retries: int = 2) -> Optional[dict]:
    """
    用 yfinance 抓取單一股票的財報資訊。
    回傳 dict：
        {
            "reportDate": "2026-07-21" | None,
            "bmo_amc": "☀️" | "🌙" | None,
            "countdown": 59 | None,
            "eps": "$9.46" | "-",
            "revenue": "$25.02B" | "-",
            "history": [ ... ]  # 5 筆真實歷史 EPS
        }
    若完全失敗則回傳 None。
    """
    for attempt in range(retries + 1):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            # --- 從 info 取得預估 EPS 與營收 ---
            eps_est = info.get('epsForward') or info.get('earningsEstimateAvg')
            rev_est = info.get('revenueEstimateAvg') or info.get('revenueEstimate')

            eps_str = format_eps(eps_est)
            rev_str = format_revenue(rev_est)

            # --- 從 earnings_dates 取得財報日期與 BMO/AMC ---
            report_date_str = None
            bmo_amc_str = None
            countdown_val = None

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

                        today = date.today()
                        report_date_obj = next_date.date() if isinstance(next_date, datetime) else next_date
                        delta = (report_date_obj - today).days
                        countdown_val = delta if delta >= 0 else None
            except Exception:
                pass

            if not report_date_str:
                next_earnings = info.get('earningsDate') or info.get('earningsTimestamp')
                if next_earnings:
                    if isinstance(next_earnings, (int, float)):
                        report_date_obj = datetime.fromtimestamp(next_earnings).date()
                        report_date_str = report_date_obj.strftime('%Y-%m-%d')
                        today = date.today()
                        delta = (report_date_obj - today).days
                        countdown_val = delta if delta >= 0 else None

            # --- 從 earnings_dates 抓取歷史 EPS ---
            history = build_history_from_earnings(stock, fy_end_month)

            return {
                "reportDate": report_date_str,
                "bmo_amc": bmo_amc_str,
                "countdown": countdown_val,
                "eps": eps_str,
                "revenue": rev_str,
                "history": history,
            }

        except Exception as e:
            if attempt < retries:
                time.sleep(1)
                continue
            print(f"  ⚠️ {ticker}: 抓取失敗 ({e})")
            return None


def build_history_from_earnings(stock, fy_end_month: int) -> list:
    """
    從 yfinance earnings_dates 抓取已發布的歷史 EPS，
    從 quarterly_income_stmt 抓取歷史營收，
    根據日期推算季度/年度標籤，回傳最近 5 筆（3Q + FY + 1Q）。

    回傳格式：
    [
        {"date": "2025-01-30", "quarter": "2025 Q1", "eps_reported": "$2.34", "revenue_reported": "$95.36B"},
        ...
    ]
    """
    try:
        ed = stock.earnings_dates
        if ed is None or ed.empty:
            return []

        # 只取有 Reported EPS 的（已發布的）
        past = ed.dropna(subset=['Reported EPS'])

        if past.empty:
            return []

        # --- 從 quarterly_income_stmt 建立營收查找表 ---
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

            quarter_label = fiscal_quarter_from_date(report_date, fy_end_month)

            # 匹配最近的營收日期
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

        # 取最近 5 筆（已按日期倒序排列）
        history = history[:5]

        # 反轉為時間順序（最早的在前）
        history.reverse()

        return history

    except Exception as e:
        print(f"    抓取歷史 EPS 失敗: {e}")
        return []


def update_data(sample_mode: bool = False, tickers_filter: list = None) -> bool:
    """
    主流程：
    1. 讀取現有 data.json
    2. 從 sp500_mapping.json 讀取 fy_end、CIK
    3. 從 SEC API 即時抓取各公司 filing list
    4. 用 yfinance 更新即時財報數據 + 歷史 EPS
    5. 將 SEC URL 根據 filingDate 配對到各季度 history 項目
    6. 寫回 data.json
    """
    # 1. 讀取現有 data.json
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            existing_data = json.load(f)
        print(f"✅ 讀取現有 data.json，共 {len(existing_data)} 家公司\n")
    except FileNotFoundError:
        print("❌ data.json 不存在，請先確認專案目錄")
        return False
    except json.JSONDecodeError as e:
        print(f"❌ data.json JSON 解析錯誤: {e}")
        return False

    # 2. 讀取 sp500_mapping.json（取得 fy_end、CIK）
    sec_mapping = {}
    try:
        with open('sp500_mapping.json', 'r', encoding='utf-8') as f:
            sec_mapping = json.load(f)
        print(f"✅ 讀取 sp500_mapping.json，共 {len(sec_mapping)} 家公司\n")
    except FileNotFoundError:
        print("⚠️  sp500_mapping.json 不存在，將使用預設 fy_end=12，且無 SEC 連結")
    except json.JSONDecodeError as e:
        print(f"⚠️  sp500_mapping.json JSON 解析錯誤: {e}")

    # 3. 決定要處理的公司
    if sample_mode:
        sample_tickers = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'WMT']
        companies_to_update = [c for c in existing_data if c['ticker'] in sample_tickers]
        print(f"🧪 樣本模式：只處理 {len(companies_to_update)} 家公司")
    elif tickers_filter:
        companies_to_update = [c for c in existing_data if c['ticker'] in tickers_filter]
        print(f"🔍 指定 ticker 模式：處理 {len(companies_to_update)} 家公司")
    else:
        companies_to_update = existing_data
        print(f"📊 完整模式：更新全部 {len(companies_to_update)} 家公司")

    if not companies_to_update:
        print("❌ 沒有符合條件的公司")
        return False

    existing_map = {c['ticker']: c for c in existing_data}

    # 4. 預先從 SEC API 抓取所有相關公司的 filing list
    print("⏳ 從 SEC API 抓取 filing 列表...")
    sec_filing_cache = {}  # { ticker: [{"filingDate":..., "form":..., "url":...}, ...] }
    sec_fetch_count = 0
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

        if (idx + 1) % 10 == 0 or idx + 1 == len(companies_to_update):
            print(f"    SEC: {idx+1}/{len(companies_to_update)} 家公司處理完畢（{sec_fetch_count} 家有 filing）")
        time.sleep(0.1)

    print(f"    SEC filing 抓取完成，{sec_fetch_count}/{len(companies_to_update)} 家有資料\n")

    # 5. 逐家抓取 yfinance 數據
    updated_count = 0
    failed_count = 0
    total = len(companies_to_update)

    for idx, company in enumerate(companies_to_update):
        ticker = company['ticker']
        print(f"  [{idx+1}/{total}] 處理 {ticker}...", end=" ")

        # 從 sp500_mapping 取得 fy_end
        fy_end = 12
        if ticker in sec_mapping:
            fy_end = sec_mapping[ticker].get('fy_end', 12)

        result = fetch_earnings_data(ticker, fy_end_month=fy_end)

        if result:
            existing = existing_map.get(ticker, {})
            existing['reportDate'] = result['reportDate'] or existing.get('reportDate')
            existing['bmo_amc'] = result['bmo_amc'] or existing.get('bmo_amc')
            existing['countdown'] = result['countdown'] if result['countdown'] is not None else existing.get('countdown')
            existing['eps'] = result['eps'] if result['eps'] != '-' else existing.get('eps', '-')
            existing['revenue'] = result['revenue'] if result['revenue'] != '-' else existing.get('revenue', '-')
            existing['ticker'] = ticker

            # 更新歷史 EPS 數據並配對 SEC URL
            if result.get('history') and len(result['history']) > 0:
                enriched_history = result['history']
                # 從 SEC filing cache 取得該公司的 filing 列表
                sec_filings = sec_filing_cache.get(ticker, [])
                if sec_filings:
                    for h_item in enriched_history:
                        sec_url = match_filing_to_history(h_item, sec_filings)
                        if sec_url:
                            h_item['secUrl'] = sec_url
                existing['history'] = enriched_history

            existing_map[ticker] = existing
            updated_count += 1
            print(f"✅ ({len(result.get('history', []))} 筆歷史)")
        else:
            failed_count += 1
            print("❌")

        if (idx + 1) % 10 == 0 and idx + 1 < total:
            print(f"  ⏳ 已處理 {idx+1}/{total}，暫停 1 秒...")
            time.sleep(1)
        else:
            time.sleep(0.2)

    # 6. 重建完整列表（保留原始順序）
    final_data = []
    for company in existing_data:
        ticker = company['ticker']
        if ticker in existing_map:
            final_data.append(existing_map[ticker])
        else:
            final_data.append(company)

    # 7. 寫入 data.json
    try:
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        print(f"\n🎉 寫入完成！共 {len(final_data)} 家公司")
        print(f"   更新成功: {updated_count} | 失敗: {failed_count}")
        return True
    except Exception as e:
        print(f"\n❌ 寫入檔案失敗: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="S&P 500 Earnings Tracker 數據更新腳本")
    parser.add_argument('--sample', action='store_true', help='樣本模式：只處理 6 家代表公司')
    parser.add_argument('--ticker', type=str, help='指定 ticker（逗號分隔），例如 --ticker AAPL,MSFT')
    args = parser.parse_args()

    tickers = None
    if args.ticker:
        tickers = [t.strip().upper() for t in args.ticker.split(',') if t.strip()]

    ok = update_data(sample_mode=args.sample, tickers_filter=tickers)
    if not ok:
        sys.exit(1)