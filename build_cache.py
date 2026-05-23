import pandas as pd
import requests
import json
import time
import sys
import argparse

# SEC 官方要求 User-Agent 必須包含聯絡資訊
HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)',
}

# 樣本模式測試用的代表性公司
# 故意挑選不同財年結束月份，方便驗證 fiscal_quarter() 邏輯：
#   AAPL fy_end=9 (蘋果財年9月底)
#   MSFT fy_end=6 (微軟財年6月底)
#   NVDA fy_end=1 (輝達財年1月底)
#   AMZN / GOOGL / WMT fy_end=12 (一般曆年制)
SAMPLE_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'WMT']


def fiscal_quarter(report_month, fy_end_month):
    """
    根據財報期末月份 (report_month) 與公司財年結束月份 (fy_end_month)
    反推這份 10-Q 屬於該財年的 Q1 / Q2 / Q3。

    例如 fy_end=12 (12月底結算):
        report_month=3  -> Q1
        report_month=6  -> Q2
        report_month=9  -> Q3
        report_month=12 -> FY (10-K)

    例如 fy_end=6 (6月底結算，如微軟):
        report_month=9  -> Q1 (FY 開始於 7 月)
        report_month=12 -> Q2
        report_month=3  -> Q3
        report_month=6  -> FY
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
    cik_int = str(int(cik))  # 移除前導 0
    acc_no_dashes = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dashes}/{primary_document}"


def extract_filings(submissions_json, cik, fy_end_month):
    """
    從 SEC submissions JSON 抽出最近一份 10-K 及該財年的 Q1/Q2/Q3 10-Q。
    回傳格式: { "Q1": {...}, "Q2": {...}, "Q3": {...}, "FY": {...} }
    """
    recent = submissions_json.get('filings', {}).get('recent', {})
    forms = recent.get('form', [])
    accessions = recent.get('accessionNumber', [])
    primary_docs = recent.get('primaryDocument', [])
    filing_dates = recent.get('filingDate', [])
    report_dates = recent.get('reportDate', [])

    if not forms:
        return {}

    # 收集所有 10-K / 10-K/A 與 10-Q / 10-Q/A，按 reportDate 由新到舊
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

    # 找最新一份 10-K 作為錨點
    latest_10k = next((c for c in candidates if c['form'].startswith('10-K')), None)
    if not latest_10k:
        # 沒有 10-K 的話只回傳最近 3 份 10-Q
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

    # 找該 10-K 之後 (時間更近) 的 10-Q
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
    for c in later_10qs[:3]:  # 最多三份 Q1/Q2/Q3
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

    # 樣本模式：只保留代表公司
    if sample_mode:
        df = df[df['Symbol'].isin(SAMPLE_TICKERS)].reset_index(drop=True)
        print(f"🧪 樣本模式啟用：只處理 {len(df)} 家代表性公司")
        print(f"   → 輸出檔案: {output_file}（不會覆蓋正式檔）\n")

    companies_cache = {}
    total = len(df)
    if not sample_mode:
        print(f"✅ 成功獲取 {total} 家公司名單！")

    print("⏳ 開始透過 SEC 官方 API 獲取財年結算月 + 最近 10-K/10-Q 文件...\n")

    with requests.Session() as session:
        session.headers.update(HEADERS)

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

            try:
                url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                res = session.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    fy_str = data.get("fiscalYearEnd", "1231")
                    if fy_str and len(fy_str) == 4:
                        fy_end = int(fy_str[:2])
                    filings = extract_filings(data, cik, fy_end)

                if sample_mode:
                    # 樣本模式下，每家公司結果都印出來方便人工檢查
                    print(f"  ✓ {ticker:6s} ({name})")
                    print(f"      fy_end={fy_end}  filings={list(filings.keys())}")
                    for q_label, info in filings.items():
                        print(f"        [{q_label}] {info['form']} reportDate={info['reportDate']}")
                        print(f"             → {info['url']}")
                elif (index + 1) % 50 == 0:
                    print(f"已處理 {index+1}/{total} 家公司...")

            except Exception as e:
                print(f"  ⚠️ {ticker} 獲取失敗: {e}")

            companies_cache[ticker] = {
                "name": name,
                "cik": cik,
                "sector": sector,
                "fy_end": fy_end,
                "filings": filings,
            }

            # SEC 嚴格限制每秒 10 次請求
            time.sleep(0.15)

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
