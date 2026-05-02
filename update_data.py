import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date, timezone

# 1. 核心設定：增加了 fy_end (Fiscal Year End Month)
# fy_end 為 12 代表日曆年公司，9 代表蘋果，6 代表微軟，1 代表輝達
COMPANIES = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810", "fy_end": 1},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193", "fy_end": 9},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019", "fy_end": 6},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724", "fy_end": 12},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044", "fy_end": 12},
    "META": {"name": "Meta (Facebook)", "cik": "1326801", "fy_end": 12},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605", "fy_end": 12}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
}

def get_quarter_label(ticker, form_type, report_date_str):
    """根據每家公司的財年結束月份 (Fiscal Year End) 動態計算季度標籤"""
    if not report_date_str:
        return "季報" if "10-Q" in form_type else "年報"
    
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    try:
        # 獲取該公司的財年結束月份
        fy_end = COMPANIES.get(ticker, {}).get("fy_end", 12)
        # 獲取報表結束月份
        report_month = int(report_date_str.split('-')[1])
        
        # 計算季度：(報表月 - 財年結束月) % 12 
        # 例子 AAPL (fy_end=9): 
        # 12月報表: (12-9)%12 = 3 -> 3/3+1 = Q2 (不對, 應為 Q1)
        # 修正邏輯：
        # 財年結束月 = Q4
        # 結束月-3 = Q3
        # 結束月-6 = Q2
        # 結束月-9 = Q1
        
        diff = (report_month - fy_end) % 12
        if diff == 0: quarter = "Q4"
        elif diff == 9: quarter = "Q1"
        elif diff == 6: quarter = "Q2"
        elif diff == 3: quarter = "Q3"
        else: quarter = "Q?" # 兜底處理

        return f"{quarter} 季報 (10-Q)"
    except Exception as e:
        print(f"標籤計算錯誤 {ticker}: {e}")
        return "季報 (10-Q)"

def get_sec_history_final(session, ticker, cik):
    """優化：傳入 ticker 以便計算正確的季度標籤"""
    history = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = session.get(url, headers=HEADERS, timeout=15)
        
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
                    
                    # 【關鍵修改】傳入 ticker
                    display_form = get_quarter_label(ticker, form_type, report_date)
                    if "/A" in form_type: display_form += " (修正)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    
                    history.append({"type": display_form, "date": filing_date, "html_url": html_url, "ix_url": ix_url})
                    if len(history) == 5: break
    except Exception as e:
        print(f"🔴 SEC CIK {cik} 錯誤: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    with requests.Session() as session:
        for ticker, info in COMPANIES.items():
            try:
                stock = yf.Ticker(ticker)
                calendar = stock.calendar
                final_date = None
                if calendar and 'Earnings Date' in calendar:
                    potential_dates = calendar['Earnings Date']
                    for d in potential_dates:
                        d_date = d.date() if isinstance(d, datetime) else d
                        if d_date >= today and d_date.year <= today.year + 1:
                            final_date = d_date
                            break
                earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
                days_remaining = (final_date - today).days if final_date else "N/A"
                
                # 【關鍵修改】傳入 ticker
                sec_history = get_sec_history_final(session, ticker, info["cik"])
                
                time.sleep(0.1) 
                results.append({
                    "ticker": ticker, 
                    "name": info["name"], 
                    "date": earnings_date_str,
                    "days_left": days_remaining, 
                    "history": sec_history
                })
                print(f"✅ {ticker} 同步成功")
            except Exception as e:
                print(f"❌ {ticker} 出錯: {e}")
    return results

if __name__ == "__main__":
    start_time = time.time()
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    print(f"🚀 全部更新完成，耗時: {time.time() - start_time:.2f} 秒")
