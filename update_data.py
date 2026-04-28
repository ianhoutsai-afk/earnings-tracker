import yfinance as yf
import json
from datetime import datetime, date

tickers = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

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
            calendar = ticker.calendar
            
            earnings_date_str = "待公佈"
            days_remaining = "N/A"
            
            if calendar is not None and 'Earnings Date' in calendar:
                raw_date = calendar['Earnings Date'][0]
                target_date = raw_date.date() if isinstance(raw_date, datetime) else raw_date
                
                # 過濾邏輯：如果日期遠大於一年（例如 2026），則設為待公佈
                if target_date.year > 2025:
                    earnings_date_str = "待公佈"
                    days_remaining = "N/A"
                else:
                    earnings_date_str = target_date.strftime('%Y-%m-%d')
                    days_remaining = (target_date - today).days

            results.append({
                "ticker": ticker_symbol,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "ir_link": ir_links[ticker_symbol]
            })
            print(f"成功抓取 {ticker_symbol}")
            
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
