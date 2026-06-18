import pandas as pd
import requests
import json
import time
import sys
import os
import argparse

# SEC 官方要求 User-Agent 必須包含聯絡資訊
HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker ianhoutsai@github.com',
    'Accept-Encoding': 'gzip, deflate',
}

# Cloudflare Worker Proxy URL（用於繞過 SEC 對雲端 IP 的封鎖）
# 設定環境變數 SEC_PROXY_URL 後，所有 SEC 請求將透過此代理
SEC_PROXY_URL = os.environ.get('SEC_PROXY_URL', '')
SEC_PROXY_TOKEN = os.environ.get('PROXY_TOKEN', '')

# 樣本模式測試用的代表性公司
SAMPLE_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'WMT']


def fiscal_quarter(report_month, fy_end_month):
    """
    根據財報期末月份與公司財年結束月份反推這份 10-Q 屬於 Q1/Q2/Q3。
    fy_end=12 (12月底結算): report_month=3->Q1, 6->Q2, 9->Q3, 12->FY
    fy_end=6 (微軟): report_month=9->Q1, 12->Q2, 3->Q3, 6->FY
    """
    if not report_month or not fy_end_month:
        return None
    months_into_fy = (report_month - fy_end_month - 1) % 12 + 1
    quarter = (months_into_fy + 2) // 3
    if quarter == 4:
        return "FY"
    return f"Q{quarter}"


def build_sec_url(cik, accession_number, primary_document):
    """組裝指向特定 10-Q / 10-K 文件的精確 SEC 直連網址"""
    if not all([cik, accession_number, primary_document]):
        return None
    cik_int = str(int(cik))
    acc_no_dashes = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_document}"


def extract_filings(submissions_json, cik, fy_end_month):
    """從 SEC submissions JSON 抽出最近一份 10-K 及該財年的 Q1/Q2/Q3 10-Q。"""
    recent = submissions_json.get('filings', {}).get('recent', {})
    forms = recent.get('form', [])
    accessions = recent.get('accessionNumber', [])
    primary_docs = recent.get('primaryDocument', [])
    filing_dates = recent.get('filingDate', [])
    report_dates = recent.get('reportDate', [])

    if not forms:
        return {}

    candidates = []
    for i, form in enumerate(forms):
        if form in ('10-K', '10-K/A', '10-Q', '10-Q/A'):
            report_date = report_dates[i] if i < len(report_dates) else ''
            if not report_date:
                continue
            candidates.append({
                'form': form,
                'accession': accessions[i],
                'primary_doc': primary_docs[i],
                'filing_date': filing_dates[i],
                'report_date': report_date,
            })
    candidates.sort(key=lambda x: x['report_date'], reverse=True)

    if not candidates:
        return {}

    latest_10k = next((c for c in candidates if c['form'].startswith('10-K')), None)
    if not latest_10k:
        result = {}
        tens_q = [c for c in candidates if c['form'].startswith('10-Q')][:3]
        for c in tens_q:
            month = int(c['report_date'][5:7])
            q_label = fiscal_quarter(month, fy_end_month)
            if q_label and q_label not in result:
                result[q_label] = {
                    'form': c['form'],
                    'reportDate': c['report_date'],
                    'filingDate': c['filing_date'],
                    'url': build_sec_url(cik, c['accession'], c['primary_doc']),
                }
        return result

    later_10qs = [
        c for c in candidates
        if c['form'].startswith('10-Q') and c['report_date'] > latest_10k['report_date']
    ]

    result = {
        'FY': {
            'form': latest_10k['form'],
            'reportDate': latest_10k['report_date'],
            'filingDate': latest_10k['filing_date'],
            'url': build_sec_url(cik, latest_10k['accession'], latest_10k['primary_doc']),
        }
    }
    for c in later_10qs[:3]:
        month = int(c['report_date'][5:7])
        q_label = fiscal_quarter(month, fy_end_month)
        if q_label and q_label != 'FY' and q_label not in result:
            result[q_label] = {
                'form': c['form'],
                'reportDate': c['report_date'],
                'filingDate': c['filing_date'],
                'url': build_sec_url(cik, c['accession'], c['primary_doc']),
            }

    return result


def _sec_request(session, url, timeout=15):
    """
    向 SEC API 發送請求，支援透過 Cloudflare Worker Proxy 繞過封鎖。
    若設定 SEC_PROXY_URL 環境變數，則透過路徑式代理發送請求。

    Proxy 路徑對應：
      https://data.sec.gov/submissions/CIK... → {proxy}/submissions/CIK...
      https://www.sec.gov/Archives/edgar/...  → {proxy}/Archives/edgar/...
    """
    if SEC_PROXY_URL:
        proxy_headers = dict(HEADERS)
        if SEC_PROXY_TOKEN:
            proxy_headers['X-Proxy-Token'] = SEC_PROXY_TOKEN
        # 提取路徑部分附加到 proxy URL
        from urllib.parse import urlparse as _urlparse
        parsed = _urlparse(url)
        proxy_url = SEC_PROXY_URL.rstrip('/') + parsed.path
        if parsed.query:
            proxy_url += '?' + parsed.query
        return session.get(proxy_url, headers=proxy_headers, timeout=timeout)
    else:
        return session.get(url, timeout=timeout)


def fetch_sec_submissions(session, cik, ticker, stats):
    """
    從 SEC 抓取單一公司的 submissions JSON，含完整錯誤紀錄與重試邏輯。
    回傳 dict (成功) 或 None (失敗)。
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    for attempt in range(3):
        try:
            res = _sec_request(session, url, timeout=15)

            if res.status_code == 200:
                stats['success'] += 1
                try:
                    return res.json()
                except Exception as e:
                    stats['parse_error'] += 1
                    if stats['parse_error'] <= 3:
                        print(f"  ⚠️ {ticker}: JSON 解析失敗: {e}")
                    return None

            elif res.status_code == 429:
                wait = (attempt + 1) * 2
                print(f"  ⏳ {ticker}: 429 限速，等待 {wait}s 後重試...")
                time.sleep(wait)
                continue

            elif res.status_code == 403:
                stats['forbidden'] += 1
                # 前 3 次完整印出，之後只計數
                if stats['forbidden'] <= 3:
                    body_preview = (res.text or '')[:300].replace('\n', ' ')
                    print(f"  ❌ {ticker}: 403 Forbidden")
                    print(f"     回應內容: {body_preview!r}")
                return None

            else:
                stats['other_error'] += 1
                if stats['other_error'] <= 3:
                    body_preview = (res.text or '')[:200].replace('\n', ' ')
                    print(f"  ❌ {ticker}: HTTP {res.status_code} | body: {body_preview!r}")
                return None

        except requests.exceptions.RequestException as e:
            if attempt < 2:
                time.sleep(1)
                continue
            stats['exception'] += 1
            if stats['exception'] <= 3:
                print(f"  ❌ {ticker}: Exception: {e}")
            return None

    return None


def preflight_check(session, df):
    """執行前先測一家公司，立刻知道 SEC 是否能正常回應。"""
    if df.empty:
        return
    first_row = df.iloc[0]
    first_ticker = first_row['Symbol']
    try:
        first_cik = str(int(first_row['CIK'])).zfill(10)
    except Exception:
        first_cik = str(first_row['CIK']).zfill(10)

    print(f"🔍 預檢: 嘗試獲取 {first_ticker} (CIK={first_cik}) 的 SEC 資料...")
    test_url = f"https://data.sec.gov/submissions/CIK{first_cik}.json"
    try:
        test_res = _sec_request(session, test_url, timeout=15)
        print(f"   HTTP 狀態: {test_res.status_code}")
        print(f"   回應 headers: Content-Type={test_res.headers.get('Content-Type')}")

        if test_res.status_code != 200:
            print(f"   ❌ 預檢失敗！回應內容前 500 字元:")
            print(f"   {test_res.text[:500]}")
            print(f"\n⚠️  SEC 似乎拒絕了來自此環境的請求。常見原因：")
            print(f"   1. GitHub Actions 的 IP 範圍被 SEC 限速或封鎖（常見）")
            print(f"   2. User-Agent 格式不符合 SEC 規範")
            print(f"   3. SEC 伺服器暫時性問題")
            print(f"\n  程式仍會繼續嘗試所有 ticker，但預期會大量失敗。\n")
        else:
            print(f"   ✅ 預檢通過！\n")
    except Exception as e:
        print(f"   ❌ 預檢拋出例外: {e}\n")


def build_sp500_cache(sample_mode=False, output_file='sp500_mapping.json'):
    print("📥 正在從 DataHub 獲取 S&P 500 最新名單 (CSV)...")

    try:
        csv_url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
        df = pd.read_csv(csv_url)
        if df.empty:
            print("❌ 獲取的名單為空")
            return False
    except Exception as e:
        print(f"❌ 獲取名單失敗: {e}")
        return False

    df['Symbol'] = df['Symbol'].str.replace('.', '-', regex=False)

    if sample_mode:
        df = df[df['Symbol'].isin(SAMPLE_TICKERS)].reset_index(drop=True)
        print(f"🧪 樣本模式：只處理 {len(df)} 家代表公司")
        print(f"   → 輸出檔案: {output_file}（不會覆蓋正式檔）\n")

    companies_cache = {}
    total = len(df)

    if not sample_mode:
        print(f"✅ 成功獲取 {total} 家公司名單！\n")

    # 統計用
    stats = {
        'success': 0,
        'forbidden': 0,
        'other_error': 0,
        'exception': 0,
        'parse_error': 0,
        'with_filings': 0,
        'empty_filings_200': 0,
    }

    with requests.Session() as session:
        session.headers.update(HEADERS)

        if SEC_PROXY_URL:
            print(f"🔀 使用 SEC Proxy: {SEC_PROXY_URL}")

        # 預檢：先測一家，立刻知道 SEC 通不通
        if not sample_mode:
            preflight_check(session, df)

        print("⏳ 開始透過 SEC 官方 API 獲取財年結算月 + 最近 10-K/10-Q 文件...\n")

        for index, row in df.iterrows():
            ticker = row['Symbol']
            name = row['Security']
            try:
                cik = str(int(row['CIK'])).zfill(10)
            except Exception:
                cik = str(row['CIK']).zfill(10)

            sector = row['GICS Sector']
            fy_end = 12  # 預設
            filings = {}

            data = fetch_sec_submissions(session, cik, ticker, stats)
            if data is not None:
                fy_str = data.get("fiscalYearEnd", "1231")
                if fy_str and len(fy_str) == 4:
                    fy_end = int(fy_str[:2])
                filings = extract_filings(data, cik, fy_end)

                if filings:
                    stats['with_filings'] += 1
                else:
                    stats['empty_filings_200'] += 1

            if sample_mode:
                print(f"  ✓ {ticker:6s} ({name})")
                print(f"      fy_end={fy_end}  filings={list(filings.keys())}")
                for q_label, info in filings.items():
                    print(f"        [{q_label}] {info['form']} reportDate={info['reportDate']}")
                    print(f"             → {info['url']}")
            elif (index + 1) % 50 == 0:
                failed = stats['forbidden'] + stats['other_error'] + stats['exception']
                print(f"已處理 {index+1}/{total} 家 | 成功 filings={stats['with_filings']} | 失敗={failed}")

            companies_cache[ticker] = {
                "name": name,
                "cik": cik,
                "sector": sector,
                "fy_end": fy_end,
                "filings": filings,
            }

            time.sleep(0.15)

    # 末尾統計報告
    print(f"\n📊 處理結果統計:")
    print(f"   總公司數: {total}")
    print(f"   HTTP 200 成功: {stats['success']}")
    print(f"     ├─ 有 filings 資料: {stats['with_filings']}")
    print(f"     └─ 200 但無相關報告: {stats['empty_filings_200']}")
    print(f"   403 Forbidden: {stats['forbidden']}")
    print(f"   其他 HTTP 錯誤: {stats['other_error']}")
    print(f"   網路例外: {stats['exception']}")
    print(f"   JSON 解析錯誤: {stats['parse_error']}")

    if stats['with_filings'] == 0 and total > 0:
        print(f"\n⚠️  警告：沒有任何公司成功獲取 filings 資料！")
        print(f"   最可能原因：SEC 封鎖了當前 IP（403）或 User-Agent 不合規範。")
        print(f"   請查看上方詳細錯誤訊息確認。")

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(companies_cache, f, ensure_ascii=False, indent=4)
        print(f"\n🎉 成功寫入 {len(companies_cache)} 家公司到 {output_file}")
        return True
    except Exception as e:
        print(f"❌ 寫入檔案失敗: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build S&P 500 SEC filings cache")
    parser.add_argument(
        '--sample',
        action='store_true',
        help='樣本模式：只處理 6 家代表公司，輸出到 sp500_mapping_sample.json（不覆蓋正式檔）'
    )
    args = parser.parse_args()

    if args.sample:
        ok = build_sp500_cache(sample_mode=True, output_file='sp500_mapping_sample.json')
    else:
        ok = build_sp500_cache()

    if not ok:
        sys.exit(1)
