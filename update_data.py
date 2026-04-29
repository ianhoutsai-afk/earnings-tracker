import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 核心設定
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

def get_sec_history_professional(cik):
    """
    基於 SEC 報告期 (Period of Report) 的順序標記法
    確保 Q1, Q2, Q3 標記 100% 準確，且 Q4 併入年報
    """
    history_all = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            # 1. 提取所有 10-Q 和 10-K，並包含 reportDate
            raw_list = []
            for i in range(len(filings.get("form", []))):
                form_type = filings["form"][i]
                if "10-Q" in form_type or "10-K" in form_type:
                    raw_list.append({
                        "form": form_type,
                        "acc_num": filings["accessionNumber"][i].replace("-", ""),
                        "doc_name": filings["primaryDocument"][i],
                        "filing_date": filings["filingDate"][i],
                        "report_date": filings["reportDate"][i] # 這就是 Period of Report
                    })
            
            # 2. 按報告期 (report_date) 從舊到新排序
            # 這樣我們可以根據 10-K 作為錨點來計算 Q1, Q2, Q3
            raw_list.sort(key=lambda x: x["report_date"])
            
            q_counter = 0 # 季度計數器
            final_history = []
            
            for f in raw_list:
                if "10-K" in f["form"]:
                    q_counter = 0 # 遇到年報，重置計數器
                    label = "Q4 / 年報 (10-K)"
                elif "10-Q" in f["form"]:
                    q_counter += 1
                    # 根據順序標記 Q1, Q2, Q3
                    if q_counter == 1: label = "Q1 季報 (10-Q)"
                    elif q_counter == 2: label = "Q2 季報 (10-Q)"
                    elif q_counter >= 3: label = "Q3 季報 (10-Q)"
                    else: label = "季報 (10-Q)"
                else:
                    continue
                
                if "/A" in f["form"]: label += " (修正)"
                
                # 生成連結
                html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['acc_num']}/{f['doc_name']}"
                ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{f['acc_num']}/{f['doc_name']}"
                
                final_history.append({
                    "type": label,
                    "date": f["filing_date"],
                    "html_url": html_url,
                    "ix_url": ix_url
                })
            
            # 3. 取最近的 5 筆，並翻轉回 (最新在前)
            return final_history[-5:][::-1]
            
    except Exception as e:
        print(f"🔴 SEC CIK {cik} 錯誤: {e}")
    return []

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        print(f"正在處理 {ticker}...")
        try:
            # 1. 抓取日期倒數 (yfinance)
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

            # 2. 抓取歷史財報 (使用基於 Report Date 的順序法)
            sec_history = get_sec_history_professional(info["cik"])
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
