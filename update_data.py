import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 🚨 安全寫法：從 GitHub 環境變數中讀取，不寫死在代碼中！
FMP_API_KEY = os.environ.get("FMP_API_KEY")

if not FMP_API_KEY:
    print("警告：找不到 API Key，請檢查 GitHub Secrets 設定！")
    
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "0000104581"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "0000320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "0000078901"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "0000101872"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "0001652044"},
    "META": {"name": "Meta (Facebook)", "cik": "0001326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "0001318605"}
}

# 嚴格遵守 SEC 規範的 User-Agent
headers = {
    'User-Agent': 'M7_Financial_Research_Project (contact.me@gmail.com)',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'data.sec.gov'
}

def get_sec_history(cik):
    history = []
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        # 設定 timeout 防止卡死
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            form_list = filings.get("form", [])
            for i in range(len(form_list)):
                form_type = form_list[i]
                if form_type in ["10-Q", "10-K"]:
                    acc_num = filings["accessionNumber"][i]
                    acc_num_no_dash = acc_num.replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    
                    display_form = "Q4 / 年報 (10-K)" if form_type == "10-K" else "季報 (10-Q)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_num_no_dash}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{int(cik)}/{acc_num_no_dash}/{doc_name}"
                    
                    history.append({
                        "type": display_form,
                        "date": filing_date,
                        "html_url": html_url,
                        "ix_url": ix_url
                    })
                    
                    if len(history) == 5:
                        break
        else:
            print(f"SEC 拒絕連線，狀態碼: {res.status_code}")
    except Exception as e:
        print(f"抓取 SEC CIK {cik} 發生例外錯誤: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        chinese_name = info["name"]
        cik = info["cik"]
        
        try:
            # 1. 抓取日期
            stock = yf.Ticker(ticker)
            calendar = stock.calendar
            final_date = None
            
            if calendar is not None and 'Earnings Date' in calendar:
                potential_dates = calendar['Earnings Date']
                for d in potential_dates:
                    d_date = d.date() if isinstance(d, datetime) else d
                    if d_date >= today and d_date.year <= today.year + 1:
                        final_date = d_date
                        break
            
            if not final_date:
                earnings_date_str = "官方公佈中"
                days_remaining = "N/A"
            else:
                earnings_date_str = final_date.strftime('%Y-%m-%d')
                days_remaining = (final_date - today).days

            # 2. 抓取歷史財報 (加上 0.5 秒延遲，避免被 SEC 封鎖)
            time.sleep(0.5) 
            sec_history = get_sec_history(cik)

            results.append({
                "ticker": ticker,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "history": sec_history
            })
            print(f"✅ 完成: {ticker} (找到 {len(sec_history)} 筆 SEC 紀錄)")
            
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
