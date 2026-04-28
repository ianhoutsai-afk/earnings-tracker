import yfinance as yf
import requests
import json
from datetime import datetime, date

# 1. 基礎設定：Ticker 與對應的 SEC 專屬代碼 (CIK)
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "0000104581"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "0000320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "0000078901"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "0000101872"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "0001652044"},
    "META": {"name": "Meta (Facebook)", "cik": "0001326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "0001318605"}
}

# SEC 要求必須提供 User-Agent (表明身分)，否則會被阻擋
headers = {
    'User-Agent': 'M7_Tracker_App/1.0 (contact@example.com)'
}

def get_sec_history(cik):
    """從 SEC EDGAR 抓取最近 5 季的 10-Q 和 10-K"""
    history = []
    try:
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            
            # 遍歷所有文件，找出 10-Q 和 10-K
            for i in range(len(filings.get("form", []))):
                form_type = filings["form"][i]
                if form_type in ["10-Q", "10-K"]:
                    # 解析資料
                    acc_num = filings["accessionNumber"][i]
                    acc_num_no_dash = acc_num.replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    
                    # 重新命名 10-K 讓使用者容易理解
                    display_form = "Q4 / 年報 (10-K)" if form_type == "10-K" else "季報 (10-Q)"
                    
                    # 生成兩種連結
                    # 1. 手機友善的純 HTML 格式
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_num_no_dash}/{doc_name}"
                    # 2. 電腦友善的互動式閱讀器
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{int(cik)}/{acc_num_no_dash}/{doc_name}"
                    
                    history.append({
                        "type": display_form,
                        "date": filing_date,
                        "html_url": html_url,
                        "ix_url": ix_url
                    })
                    
                    # 只要最新的 5 筆
                    if len(history) == 5:
                        break
    except Exception as e:
        print(f"抓取 SEC CIK {cik} 失敗: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        chinese_name = info["name"]
        cik = info["cik"]
        
        try:
            # --- 1. 處理倒數計時 (yfinance) ---
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

            # --- 2. 處理 SEC 歷史財報 ---
            sec_history = get_sec_history(cik)

            results.append({
                "ticker": ticker,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "history": sec_history
            })
            print(f"✅ 完成同步: {ticker} (包含 {len(sec_history)} 筆歷史財報)")
            
        except Exception as e:
            print(f"❌ {ticker} 處理出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
