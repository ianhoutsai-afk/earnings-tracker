import json
import logging
import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 設定 Log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    try:
        with open('sp500_mapping.json', 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            tickers = list(mapping.keys()) if isinstance(mapping, dict) else mapping
    except Exception as e:
        logging.error(f"無法載入清單: {e}，使用預設清單")
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

    results = []
    today = pd.Timestamp.now(tz='UTC')
    today_date = today.date()

    for symbol in tickers:
        try:
            logging.info(f"正在獲取 {symbol} 數據...")
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            name = info.get("shortName", symbol)
            
            # EPS & 營收轉換
            eps = info.get("forwardEps", "N/A")
            eps_str = f"${eps:.2f}" if isinstance(eps, (int, float)) else "N/A"
            
            rev = info.get("totalRevenue", "N/A")
            if isinstance(rev, (int, float)):
                if rev >= 1e9: rev_str = f"${rev / 1e9:.2f}B"
                elif rev >= 1e6: rev_str = f"${rev / 1e6:.2f}M"
                else: rev_str = f"${rev:,.0f}"
            else:
                rev_str = "N/A"

            earnings_dates = ticker.earnings_dates
            report_date_str = "-"
            bmo_amc = ""
            countdown_days = None  # 關鍵：計算倒數天數供前端排序
            history_data = []

            if earnings_dates is not None and not earnings_dates.empty:
                # 1. 未來財報與倒數天數
                future = earnings_dates[earnings_dates.index >= today]
                if not future.empty:
                    next_date = future.index[0]
                    report_date_str = next_date.strftime("%Y-%m-%d")
                    # 計算天數差
                    countdown_days = (next_date.date() - today_date).days
                    
                    if next_date.hour < 12: bmo_amc = "☀️"
                    elif next_date.hour >= 16: bmo_amc = "🌙"

                # 2. 過去 4 個季度的歷史發布 EPS
                past = earnings_dates[earnings_dates.index < today].head(4)
                for date_idx, row in past.iterrows():
                    rep_eps = row.get('Reported EPS', 'N/A')
                    history_data.append({
                        "date": date_idx.strftime("%Y-%m-%d"),
                        "eps_reported": f"${rep_eps:.2f}" if not pd.isna(rep_eps) else 'N/A'
                    })
            
            results.append({
                "ticker": symbol,
                "name": name,
                "reportDate": report_date_str,
                "bmo_amc": bmo_amc,
                "countdown": countdown_days, # 輸出給前端
                "eps": eps_str,
                "revenue": rev_str,
                "history": history_data
            })
            
        except Exception as e:
            logging.error(f"處理 {symbol} 時發生錯誤: {e}")

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logging.info("成功寫入 data.json")

if __name__ == "__main__":
    main()
