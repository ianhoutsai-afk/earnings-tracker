import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 1. 核心設定
COMPANIES = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044"},
    "META": {"name": "Meta (Facebook)", "cik": "1326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605"}
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
}

def get_quarter_label(form_type, report_date_str):
    """根據報告期結束日 (Report Date) 的絕對映射法"""
    if not report_date_str:
        return "季報" if "10-Q" in form_type else "年報"
    
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    try:
        month = int(report_date_str.split('-')[1])
        # 標準映射
        mapping = {3: "Q1 季報 (10-Q)", 6: "Q2 季報 (10-Q)", 9: "Q3 季報 (10-Q)", 12: "Q4 / 年報 (10-K)"}
        if month in mapping: return mapping[month]
        
        # 財政年度不同的兜底邏輯
        if month in [4, 5]: return "Q1 季報 (10-Q)"
        if month in [7, 8]: return "Q2 季報 (10-Q)"
        if month in [10, 11]: return "Q3 季報 (10-Q)"
        
        return "季報 (10-Q)"
    except:
        return "季報 (10-Q)"

def get_sec_history_final(session, cik):
    """優化：傳入 session 以複用 TCP 連接"""
    history = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        # 使用 session.get 代替 requests.get
        res = session.get(url, headers=HEADERS, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            # 獲取所有 form 列表
            forms = filings.get("form", [])
            for i in range(len(forms)):
                form_type = forms[i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    report_date = filings["reportDate"][i]
                    
                    display_form = get_quarter_label(form_type, report_date)
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
    
    # 【優化】創建一個 Session 對象，所有 SEC 請求複用這個連接
    with requests.Session() as session:
        for ticker, info in COMPANIES.items():
            try:
                # yfinance 的 Ticker 物件建議在循環內創建
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
                
                # 【優化】將 session 傳入，減少握手時間
                sec_history = get_sec_history_final(session, info["cik"])
                
                # SEC 要求每秒請求不能過快，但有了 Session 可以稍微縮短 sleep
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
        from datetime import datetime, timezone
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    print(f"🚀 全部更新完成，耗時: {time.time() - start_time:.2f} 秒")
