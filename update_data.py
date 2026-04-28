import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

FMP_API_KEY = os.environ.get("FMP_API_KEY")

if not FMP_API_KEY:
    print("🔴 致命錯誤：在 GitHub Secrets 中找不到 FMP_API_KEY。")
    exit(1)

companies = {
    "NVDA": "輝達 (Nvidia)", "AAPL": "蘋果 (Apple)", "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)", "GOOGL": "Alphabet (Google)", "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

def get_sec_history_plan_b(ticker):
    history = []
    try:
        # 使用 earnings-surprises 接口，它更穩定且包含 SEC 連結
        url = f"https://financialmodelingprep.com/api/v3/earnings-surprises/{ticker}?apikey={FMP_API_KEY}"
        res = requests.get(url, timeout=15)
        
        if res.status_code == 200:
            surprises = res.json()
            if not surprises:
                print(f"   🟡 [FMP] {ticker}: earnings-surprises 返回空列表。")
                return []

            for report in surprises:
                # 尋找 SEC 官方連結 (有些舊財報可能沒有)
                link = report.get('link')
                if link:
                    # 從財報日推斷季度
                    report_date = datetime.strptime(report['date'], '%Y-%m-%d')
                    quarter = f"Q{(report_date.month - 1) // 3 + 1}"
                    display_form = f"{report_date.year} {quarter} 財報"

                    # 巧妙生成互動式閱讀器 (ix) 連結
                    ix_link = link.replace("https://www.sec.gov/Archives/", "https://www.sec.gov/ix?doc=/Archives/")
                    
                    history.append({
                        "type": display_form,
                        "date": report['date'],
                        "html_url": link,
                        "ix_url": ix_link
                    })
                
                if len(history) == 5:
                    break
        else:
            print(f"   🔴 [FMP] API 錯誤: {ticker} 返回狀態碼 {res.status_code}。")
            print(f"   🔴 [FMP] 錯誤內容: {res.text[:100]}")
    except Exception as e:
        print(f"   🔴 [FMP] 請求 {ticker} 時發生例外錯誤: {e}")
        
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, chinese_name in companies.items():
        print(f"\n--- 開始處理 {ticker} ---")
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

            # 2. 抓取歷史財報 (Plan B)
            sec_history = get_sec_history_plan_b(ticker)

            results.append({
                "ticker": ticker, "name": chinese_name, "date": earnings_date_str,
                "days_left": days_remaining, "history": sec_history
            })
            print(f"✅ {ticker} 完成同步，歷史件數: {len(sec_history)}")
            
        except Exception as e:
            print(f"❌ {ticker} 發生嚴重錯誤: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    print("\n--- 所有公司處理完畢 ---")
