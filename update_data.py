import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# --- 1. 檢查 API Key 是否存在 ---
FMP_API_KEY = os.environ.get("FMP_API_KEY")
if not FMP_API_KEY:
    print("🔴 致命錯誤：在 GitHub Secrets 中找不到 FMP_API_KEY。")
    exit(1) # 直接中止程式
else:
    print("🟢 成功讀取 API Key。")

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
    history = []
    try:
        url = f"https://financialmodelingprep.com/api/v3/sec_filings/{ticker}?page=0&apikey={FMP_API_KEY}"
        print(f"   [FMP] 正在向 FMP 請求 {ticker} 的歷史財報...")
        res = requests.get(url, timeout=15)
        
        if res.status_code == 200:
            filings = res.json()
            if not filings:
                print(f"   🟡 [FMP] {ticker}: FMP 返回了空列表，可能暫無數據。")
                return []

            print(f"   🟢 [FMP] 成功獲取 {ticker} 的申報列表，共 {len(filings)} 筆。")
            for filing in filings:
                form_type = filing.get('type', '')
                if "10-Q" in form_type or "10-K" in form_type:
                    filing_date = filing.get('fillingDate', '').split(' ')[0]
                    final_link = filing.get('finalLink')
                    
                    if final_link:
                        display_form = "Q4 / 年報 (10-K)" if "10-K" in form_type else "季報 (10-Q)"
                        if "/A" in form_type: display_form += " (修正案)"
                        
                        ix_link = final_link.replace("https://www.sec.gov/Archives/", "https://www.sec.gov/ix?doc=/Archives/")
                        history.append({"type": display_form, "date": filing_date, "html_url": final_link, "ix_url": ix_link})
                
                if len(history) == 5: break
        else:
            print(f"   🔴 [FMP] API 錯誤: {ticker} 返回狀態碼 {res.status_code}。")
            print(f"   🔴 [FMP] 錯誤內容: {res.text[:100]}") # 印出前 100 字錯誤訊息
            return []
            
    except Exception as e:
        print(f"   🔴 [FMP] 請求 {ticker} 時發生例外錯誤: {e}")
        return []
        
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, chinese_name in companies.items():
        print(f"\n--- 開始處理 {ticker} ---")
        try:
            # 1. 抓取日期倒數 (yfinance)
            print(f"   [yfinance] 正在獲取 {ticker} 的財報日期...")
            stock = yf.Ticker(ticker)
            calendar = stock.calendar
            
            if calendar is None or 'Earnings Date' not in calendar:
                print(f"   🟡 [yfinance] {ticker}: yfinance 未返回財報日期。")
                final_date = None
            else:
                potential_dates = calendar['Earnings Date']
                final_date = None
                for d in potential_dates:
                    d_date = d.date() if isinstance(d, datetime) else d
                    if d_date >= today and d_date.year <= today.year + 1:
                        final_date = d_date
                        break
                if final_date:
                    print(f"   🟢 [yfinance] {ticker}: 找到下一個財報日 {final_date}")
                else:
                    print(f"   🟡 [yfinance] {ticker}: 未找到有效的未來財報日。")

            earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
            days_remaining = (final_date - today).days if final_date else "N/A"

            # 2. 抓取歷史財報 (FMP API)
            sec_history = get_sec_history_from_fmp(ticker)

            results.append({
                "ticker": ticker,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "history": sec_history
            })
            
        except Exception as e:
            print(f"   🔴 [yfinance] 抓取 {ticker} 時發生嚴重錯誤: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    print("\n--- 所有公司處理完畢，已生成 data.json ---")
