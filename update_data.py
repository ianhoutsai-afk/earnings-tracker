import yfinance as yf
import json
from datetime import datetime

# 七巨頭股票代碼與中文名稱
tickers = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

# 投資者關係網站連結 (SEC 列表或官網)
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
    for ticker_symbol, chinese_name in tickers.items():
        ticker = yf.Ticker(ticker_symbol)
        
        # 抓取財報日曆
        calendar = ticker.calendar
        earnings_date = "待公佈"
        days_remaining = "N/A"
        
        if calendar is not None and 'Earnings Date' in calendar:
            # 獲取下一個財報日期
            date_obj = calendar['Earnings Date'][0]
            earnings_date = date_obj.strftime('%Y-%m-%d')
            
            # 計算剩餘天數
            delta = date_obj.date() - datetime.now().date()
            days_remaining = delta.days

        results.append({
            "ticker": ticker_symbol,
            "name": chinese_name,
            "date": earnings_date,
            "days_left": days_remaining,
            "ir_link": ir_links[ticker_symbol]
        })
    
    return results

if __name__ == "__main__":
    data = get_earnings_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
