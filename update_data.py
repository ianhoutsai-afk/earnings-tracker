import yfinance as yf
import json
from datetime import datetime, date, timedelta

tickers = {
    "NVDA": "輝達 (Nvidia)",
    "AAPL": "蘋果 (Apple)",
    "MSFT": "微軟 (Microsoft)",
    "AMZN": "亞馬遜 (Amazon)",
    "GOOGL": "Alphabet (Google)",
    "META": "Meta (Facebook)",
    "TSLA": "特斯拉 (Tesla)"
}

def get_accurate_next_earnings():
    results = []
    today = date.today()
    
    for ticker_symbol, chinese_name in tickers.items():
        try:
            ticker = yf.Ticker(ticker_symbol)
            calendar = ticker.calendar
            
            final_date = None
            status = "官方已確認"
            
            if calendar is not None and 'Earnings Date' in calendar:
                # 獲取所有可能的日期列表
                potential_dates = calendar['Earnings Date']
                
                # 1. 尋找第一個「大於或等於今天」的日期
                for d in potential_dates:
                    d_date = d.date() if isinstance(d, datetime) else d
                    if d_date >= today:
                        # 2. 排除掉錯誤的佔位日期 (例如 2026 年)
                        if d_date.year <= today.year + 1:
                            final_date = d_date
                            break
            
            # 如果找不到未來日期，或日期太遠，則標記為待定
            if not final_date:
                earnings_date_str = "官方公佈中"
                days_remaining = "N/A"
                status = "等待下一季排程"
            else:
                earnings_date_str = final_date.strftime('%Y-%m-%d')
                days_remaining = (final_date - today).days
                # 如果距離超過 4 個月，通常也是佔位符，改為預估
                if days_remaining > 120:
                    status = "下一季預計"

            results.append({
                "ticker": ticker_symbol,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "status": status,
                "ir_link": f"https://www.google.com/search?q={ticker_symbol}+investor+relations"
            })
            print(f"✅ {ticker_symbol}: {earnings_date_str} ({status})")
            
        except Exception as e:
            print(f"❌ {ticker_symbol} 出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_accurate_next_earnings()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
