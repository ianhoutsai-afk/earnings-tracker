import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 🚨 請確保 GitHub Secrets 已設定 FMP_API_KEY
FMP_API_KEY = os.environ.get("FMP_API_KEY")

companies = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

def get_sec_history_from_fmp(ticker):
    """透過 FMP 獲取 SEC 官方歷史財報連結 (強化版)"""
    history = []
    try:
        # 不在 URL 篩選 type，先拿最近所有的文件再到下面過濾
        url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}?page=0&apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=10)
        
        if res.status_code == 200:
            filings = res.json()
            print(f"正在檢查 {ticker} 的最近申報紀錄...")
            
            for filing in filings:
                form_type = filing.get('type', '')
                # 只要是 10-Q 或 10-K (包含修正案 /A)
                if "10-Q" in form_type or "10-K" in form_type:
                    filing_date = filing.get('fillingDate', '').split(' ')[0]
                    final_link = filing.get('finalLink')
                    
                    if final_link:
                        # 顯示名稱美化
                        display_form = "Q4 / 年報 (10-K)" if "10-K" in form_type else "季報 (10-Q)"
                        if "/A" in form_type:
                            display_form += " (修正案)"
                        
                        # 生成互動閱讀器連結
                        ix_link = final_link.replace("https://www.sec.gov/Archives/", "https://www.sec.gov/ix?doc=/Archives/")
                        
                        history.append({
                            "type": display_form,
                            "date": filing_date,
                            "html_url": final_link,
                            "ix_url": ix_link
                        })
                
                # 抓滿 5 份就停
                if len(history) == 5:
                    break
            
            if not history:
                print(f"警告：{ticker} 沒找到任何 10-Q 或 10-K")
        else:
            print(f"FMP API 回報錯誤: {res.status_code}")
    except Exception as e:
        print(f"抓取 {ticker} 發生例外: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, chinese_name in companies.items():
        try:
            # 1. 抓取日期倒數
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
            
            earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
            days_remaining = (final_date - today).days if final_date else "N/A"

            # 2. 抓取歷史財報
            sec_history = get_sec_history_from_fmp(ticker)

            results.append({
                "ticker": ticker,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "history": sec_history
            })
            print(f"✅ {ticker} 完成同步，歷史件數: {len(sec_history)}")
            
        except Exception as e:
            print(f"❌ {ticker} 發生錯誤: {e}")
            
    return results

if __name__ == "__main__":
    if not FMP_API_KEY:
        print("錯誤：找不到 API Key，請檢查 GitHub Secrets!")
    else:
        data = get_tracker_data()
        output = {
            "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "companies": data
        }
        with open('data.json', 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, indent=4)
