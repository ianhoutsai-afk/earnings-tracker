import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 1. 核心設定：Ticker 與 CIK
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "104581"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "78901"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "101872"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044"},
    "META": {"name": "Meta (Facebook)", "cik": "1326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605"}
}

# 2. 關鍵技術：偽裝成真實的 Chrome 瀏覽器，繞過防火牆
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Host': 'data.sec.gov',
}

def get_sec_history_final(cik):
    """從 SEC EDGAR 直接抓取歷史財報，並偽裝成瀏覽器"""
    history = []
    # SEC 的 CIK 碼必須補滿 10 位數，前面補 0
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
                    
                    display_form = "Q4 / 年報 (10-K)" if "10-K" in form_type else "季報 (10-Q)"
                    if "/A" in form_type: display_form += " (修正)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    
                    history.append({"type": display_form, "date": filing_date, "html_url": html_url, "ix_url": ix_url})
                    if len(history) == 5: break
        else:
            print(f"🔴 SEC 連線失敗 for CIK {cik}，狀態碼: {res.status_code}")
    except Exception as e:
        print(f"🔴 抓取 SEC CIK {cik} 時發生錯誤: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        print(f"\n--- 正在處理 {ticker} ---")
        try:
            # 抓取倒數計時
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

            # 抓取 SEC 歷史財報
            sec_history = get_sec_history_final(info["cik"])
            time.sleep(0.2) # 每次請求後休息一下，表現得更像人類

            results.append({
                "ticker": ticker, "name": info["name"], "date": earnings_date_str,
                "days_left": days_remaining, "history": sec_history
            })
            print(f"✅ {ticker} 完成，找到 {len(sec_history)} 筆歷史財報。")
            
        except Exception as e:
            print(f"❌ {ticker} 處理時發生嚴重錯誤: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
