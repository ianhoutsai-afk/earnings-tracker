import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

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

def get_sec_history_anchor(cik):
    """使用深度錨點法標記季度：以最近的 10-K 為 Q4 基準點"""
    history_all = []
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            # 1. 提取所有 10-Q 和 10-K，保持最新在前
            raw_list = []
            for i in range(len(filings.get("form", []))):
                form_type = filings["form"][i]
                if "10-Q" in form_type or "10-K" in form_type:
                    raw_list.append({
                        "form": form_type,
                        "acc_num": filings["accessionNumber"][i].replace("-", ""),
                        "doc_name": filings["primaryDocument"][i],
                        "date": filings["filingDate"][i]
                    })
            
            if not raw_list: return []

            # 2. 尋找最近的一份 10-K 作為錨點 (Index 0 是最新的)
            anchor_idx = -1
            for idx, f in enumerate(raw_list):
                if "10-K" in f["form"]:
                    anchor_idx = idx
                    break
            
            final_history = []
            # 3. 處理最近的 5 筆 (raw_list[:5])
            for idx in range(min(5, len(raw_list))):
                f = raw_list[idx]
                form_type = f["form"]
                
                if "10-K" in form_type:
                    label = "Q4 / 年報 (10-K)"
                else:
                    # 如果有錨點，根據相對位置標記
                    if anchor_idx != -1:
                        if idx < anchor_idx:
                            # 錨點之後的文件 -> Q1, Q2, Q3
                            q_num = (idx % 3) + 1
                            label = f"Q{q_num} 季報 (10-Q)"
                        else:
                            # 錨點之前的文件 -> 倒推 Q3, Q2, Q1
                            # 計算與錨點的距離
                            dist = anchor_idx - idx
                            q_num = 4 - (dist % 3 + 1) if dist % 3 != 0 else 3
                            # 簡化處理：既然是 10-K 之前的，且在最近 5 筆內，通常是 Q3
                            label = "Q3 季報 (10-Q)" 
                    else:
                        label = "季報 (10-Q)"
                
                if "/A" in form_type: label += " (修正)"
                
                html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{f['acc_num']}/{f['doc_name']}"
                ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{f['acc_num']}/{f['doc_name']}"
                
                final_history.append({"type": label, "date": f["date"], "html_url": html_url, "ix_url": ix_url})
                
            return final_history
    except Exception as e:
        print(f"🔴 SEC CIK {cik} 錯誤: {e}")
    return []

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
            sec_history = get_sec_history_anchor(info["cik"])
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
