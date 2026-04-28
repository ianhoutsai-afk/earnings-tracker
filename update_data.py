import yfinance as yf
import json
from datetime import datetime, date

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

# 投資者關係網站連結
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
                # 獲取原始日期物件
                raw_date = calendar['Earnings Date'][0]
                
                # 核心修正：檢查 raw_date 是 datetime 還是 date
                if isinstance(raw_date, datetime):
                    target_date = raw_date.date()
                else:
                    target_date = raw_date
                
                earnings_date_str = target_date.strftime('%Y-%m-%d')
                
                # 計算天數差
                delta = target_date - today
                days_remaining = delta.days

            results.append({
                "ticker": ticker_symbol,
                "name": chinese_name,
                "date": earnings_date_str,
                "days_left": days_remaining,
                "ir_link": ir_links[ticker_symbol]
            })
            print(f"成功抓取 {ticker_symbol}: {earnings_date_str}")
            
        except Exception as e:
            print(f"抓取 {ticker_symbol} 時出錯: {e}")
            results.append({
                "ticker": ticker_symbol,
                "name": chinese_name,
                "date": "錯誤",
                "days_left": "N/A",
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
    print("data.json 已更新完成")
