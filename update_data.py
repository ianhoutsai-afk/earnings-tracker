import yfinance as yf
import json
from datetime import datetime, date

# 七巨頭清單
tickers = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

# 投資者關係連結
ir_links = {
    "NVDA": "https://investor.nvidia.com/financial-reports/default.aspx",
    "AAPL": "https://investor.apple.com/investor-relations/default.aspx",
    "MSFT": "https://www.microsoft.com/en-us/investor",
    "AMZN": "https://ir.aboutamazon.com/overview/default.aspx",
    "GOOGL": "https://abc.xyz/investor/",
    "META": "https://investor.fb.com/home/default.aspx",
    "TSLA": "https://ir.tesla.com"
}

def get_earnings_data():
    results = []
    today = date.today()
    
    for ticker_symbol, chinese_name in tickers.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            info = ticker.info # 獲取公司概況與預估數據
            
            # --- 獲取預估數據 ---
            # 預估 EPS
            eps_est = info.get('forwardEps', 'N/A')
            
            # 預估營收 (處理成 B 為單位)
            rev_est_raw = info.get('revenueEstimateAvg')
            if rev_est_raw and isinstance(rev_est_raw, (int, float)):
                rev_est = f"${round(rev_est_raw / 1e9, 2)}B"
            else:
                rev_est = "N/A"
            
            # --- 獲取財報日期 ---
            calendar = ticker.calendar
            earnings_date_str = "待公佈"
            days_remaining = "N/A"
            
            if calendar is not None and 'Earnings Date' in calendar:
                raw_date = calendar['Earnings Date'][0]
                target_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
                earnings_date_str = target_date.strftime('%Y-%m-%d')
                days_remaining = (target_date - today).days

            results.append({
                "ticker": ticker_symbol,
                "name": chinese_name,
                "eps_estimate": eps_est,
                "rev_estimate": rev_est,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "ir_link": ir_links[ticker_symbol]
            })
            print(f"已同步: {ticker_symbol}")
            
        except Exception as e:
            print(f"抓取 {ticker_symbol} 時出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_earnings_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
