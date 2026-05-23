import pandas as pd
import requests
import json
import time
import sys

# SEC 官方要求 User-Agent 必須包含聯絡資訊
HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)',
}


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
    # 距離財年起始月份 (fy_end_month + 1) 過了幾個月
    months_into_fy = (report_month - fy_end_month - 1) % 12 + 1
    quarter = (months_into_fy + 2) // 3  # 1-3月->Q1, 4-6月->Q2, ...
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
    缺資料的 key 不會出現 (前端用 ?? 處理)。
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
    # 按 reportDate 由新到舊排序
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


def build_sp500_cache():
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
    companies_cache = {}
    total = len(df)
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
                    # 新增：抽出最近的 10-K / 10-Q
                    filings = extract_filings(data, cik, fy_end)

                if (index + 1) % 50 == 0:
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
        with open('sp500_mapping.json', 'w', encoding='utf-8') as f:
            json.dump(companies_cache, f, ensure_ascii=False, indent=4)
        print(f"\n🎉 成功寫入 {len(companies_cache)} 家公司到 sp500_mapping.json")
        return True
    except Exception as e:
        print(f"❌ 寫入檔案失敗: {e}")
        return False


if __name__ == "__main__":
    if not build_sp500_cache():
        sys.exit(1)
