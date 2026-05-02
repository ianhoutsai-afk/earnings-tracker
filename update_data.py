import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date, timezone
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 1. 配置與常量
# ==========================================
MAPPING_FILE = 'sp500_mapping.json'
OUTPUT_FILE = 'data.json'

QUARTER_MAPPING = {
    11: "Q4",  0: "Q4",  1: "Q4",
     2: "Q1",  3: "Q1",  4: "Q1",
     5: "Q2",  6: "Q2",  7: "Q2",
     8: "Q3",  9: "Q3", 10: "Q3"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
}

# ==========================================
# 2. 核心邏輯
# ==========================================

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)
    return session

def get_quarter_label(ticker, companies_map, form_type, report_date_str):
    if not report_date_str:
        return "季報" if "10-Q" in form_type else "年報"
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    try:
        fy_end = companies_map.get(ticker, {}).get("fy_end", 12)
        report_month = int(report_date_str.split('-')[1])
        diff = (report_month - fy_end) % 12
        quarter = QUARTER_MAPPING.get(diff, "Q?")
        return f"{quarter} 季報 (10-Q)"
    except:
        return "季報 (10-Q)"

def get_sec_history(session, ticker, cik, companies_map):
    history = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = session.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            for i in range(len(forms)):
                form_type = forms[i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    report_date = filings["reportDate"][i]
                    display_form = get_quarter_label(ticker, companies_map, form_type, report_date)
                    if "/A" in form_type: display_form += " (修正)"
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    history.append({"type": display_form, "date": filing_date, "html_url": html_url, "ix_url": ix_url})
                    if len(history) == 5: break
    except Exception as e:
        print(f"🔴 SEC Error {ticker}: {e}")
    return history

def get_tracker_data():
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            companies_map = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 {MAPPING_FILE}")
        return None, []

    results = []
    errors = []
    today = date.today()
    session = get_session()
    tickers = list(companies_map.keys())
    total = len(tickers)
    
    print(f"🚀 開始同步 {total} 家公司數據...")

    for index, ticker in enumerate(tickers):
        info = companies_map[ticker]
        try:
            stock = yf.Ticker(ticker)
            calendar = stock.calendar
            final_date = None
            timing = "Unknown" # BMO / AMC
            
            if calendar and 'Earnings Date' in calendar:
                potential_dates = calendar['Earnings Date']
                for d in potential_dates:
                    d_date = d.date() if isinstance(d, datetime) else d
                    if d_date >= today and d_date.year <= today.year + 1:
                        final_date = d_date
                        break
            
            # 嘗試獲取發布時段 (yfinance calendar 有時包含 time 資訊)
            # 注意：yfinance 的 calendar 格式不統一，這裡做簡單判定
            if calendar and 'Earnings Date' in calendar:
                # 檢查是否有時間戳，如果有，根據時間判定 BMO/AMC
                # 這部分 yfinance 支援度不一，但我們預留欄位
                pass

            earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
            days_remaining = (final_date - today).days if final_date else "N/A"
            sec_history = get_sec_history(session, ticker, info["cik"], companies_map)
            
            results.append({
                "ticker": ticker, 
                "name": info["name"], 
                "sector": info.get("sector", "Unknown"),
                "date": earnings_date_str,
                "days_left": days_remaining, 
                "timing": timing, 
                "history": sec_history
            })
            
            if (index + 1) % 20 == 0:
                print(f"✅ 進度: {index+1}/{total} | {ticker}")
            time.sleep(0.12) 
            
        except Exception as e:
            print(f"❌ {ticker} 失敗: {e}")
            errors.append({"ticker": ticker, "error": str(e), "time": datetime.now().isoformat()})
            
    return results, errors

if __name__ == "__main__":
    start_time = time.time()
    data, errors = get_tracker_data()
    
    if data is not None:
        output = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "companies": data,
            "errors": errors # 記錄失敗的公司
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
        print(f"🚀 更新完成！同步 {len(data)} 家，失敗 {len(errors)} 家。耗時: {time.time() - start_time:.2f} 秒")
    else:
        print("❌ 數據同步失敗")
