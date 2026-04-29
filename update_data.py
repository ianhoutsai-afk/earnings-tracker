import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 1. 核心設定
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044"},
    "META": {"name": "Meta (Facebook)", "cik": "1326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605"}
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
}

def get_quarter_label(form_type, filing_date):
    """根據文件類型和發布日期精確映射季度"""
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    if "10-Q" in form_type:
        try:
            # 提取月份 (例如 '2024-05-15' -> 5)
            month = int(filing_date.split('-')[1])
            
            # 建立月份與季度的精確映射表
            # Q1 通常在 4,5,6,7 月發布
            # Q2 通常在 8,9,10 月發布
            # Q3 通常在 11,12,1 月發布
            month_to_quarter = {
                4: "Q1 季報 (10-Q)", 5: "Q1 季報 (10-Q)", 6: "Q1 季報 (10-Q)", 7: "Q1 季報 (10-Q)",
                8: "Q2 季報 (10-Q)", 9: "Q2 季報 (10-Q)", 10: "Q2 季報 (10-Q)",
                11: "Q3 季報 (10-Q)", 12: "Q3 季報 (10-Q)", 1: "Q3 季報 (10-Q)"
            }
            
            return month_to_quarter.get(month, "季報 (10-Q)")
        except:
            return "季報 (10-Q)"
            
    return "其他申報"

def get_sec_history_final(cik):
    history = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            for i in range(len(filings.get("form", []))):
                form_type = filings["form"][i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    
                    # 使用修正後的映射邏輯
                    display_form = get_quarter_label(form_type, filing_date)
                    if "/A" in form_type: display_form += " (修正)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    
                    history.append({"type": display_form, "date": filing_date, "html_url": html_url, "ix_url": ix_url})
                    if len(history) == 5: break
    except Exception as e:
        print(f"🔴 抓取 SEC CIK {cik} 時發生錯誤: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        print(f"正在處理 {ticker}...")
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

            sec_history = get_sec_history_final(info["cik"])
            time.sleep(0.2)

            results.append({
                "ticker": ticker, "name": info["name"], "date": earnings_date_str,
                "days_left": days_remaining, "history": sec_history
            })
            
        except Exception as e:
            print(f"❌ {ticker} 出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
