import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 1. 核心設定 (使用正確的 CIK)
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044"},
    "META": {"name": "Meta (Facebook)", "cik": "1326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605"}
}

# 偽裝瀏覽器 Header
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
}

def get_simple_quarter_label(form_type, filing_date):
    """最簡單的月份對照法，確保標籤一定會出現"""
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    if "10-Q" in form_type:
        try:
            # 提取月份 (例如 '2024-11-20' -> 11)
            month = int(filing_date.split('-')[1])
            
            # 定義簡單的月份映射 (美股通用發布時間)
            # 1月: Q3 | 2-4月: 通常是年報 | 5-7月: Q1 | 8-10月: Q2 | 11-12月: Q3
            if month == 1: return "Q3 季報 (10-Q)"
            if 5 <= month <= 7: return "Q1 季報 (10-Q)"
            if 8 <= month <= 10: return "Q2 季報 (10-Q)"
            if 11 <= month <= 12: return "Q3 季報 (10-Q)"
            
            return "季報 (10-Q)" # 兜底
        except:
            return "季報 (10-Q)"
            
    return "財報文件"

def get_sec_history_stable(cik):
    """回歸最穩定的偽裝瀏覽器抓取方式"""
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
                    
                    # 呼叫簡單標籤函數
                    display_form = get_simple_quarter_label(form_type, filing_date)
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
    
    for ticker, info in companies.items():
        print(f"正在同步 {ticker}...")
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
            
            # 使用最穩定的抓取函數
            sec_history = get_sec_history_stable(info["cik"])
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
