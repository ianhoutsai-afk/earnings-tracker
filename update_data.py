import yfinance as yf
import json
from datetime import datetime, date

companies = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

def get_earnings_countdown():
    results = []
    today = date.today()
    
    for ticker, chinese_name in companies.items():
        try:
            stock = yf.Ticker(ticker)
            calendar = stock.calendar
            final_date = None
            
            if calendar and 'Earnings Date' in calendar:
                potential_dates = calendar['Earnings Date']
                for d in potential_dates:
                    d_date = d.date() if isinstance(d, datetime) else d
                    # 核心邏輯：只接受今天之後、一年之內的真實日期
                    if d_date >= today and d_date.year <= today.year + 1:
                        final_date = d_date
                        break
            
            earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
            days_remaining = (final_date - today).days if final_date else "N/A"

            results.append({
                "ticker": ticker,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "ir_link": f"https://www.google.com/search?q={ticker}+investor+relations" # 通用 IR 搜尋連結
            })
            print(f"✅ {ticker}: 下一財報日為 {earnings_date_str}")
            
        except Exception as e:
            print(f"❌ {ticker} 處理出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_earnings_countdown()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
