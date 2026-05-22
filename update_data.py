import json
import logging
import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 設定 Log 格式
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    # 讀取你的 S&P 500 清單 (相容 List 或 Dict 結構)
    try:
        with open('sp500_mapping.json', 'r', encoding='utf-8') as f:
            mapping = json.load(f)
            tickers = list(mapping.keys()) if isinstance(mapping, dict) else mapping
    except Exception as e:
        logging.error(f"無法載入 sp500_mapping.json: {e}，將使用預設示範清單")
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"] # 避免檔案壞掉時全盤崩潰

    results = []
    today = pd.Timestamp.now(tz='UTC')

    for symbol in tickers:
        try:
            logging.info(f"正在獲取 {symbol} 數據...")
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # 基本資訊
            name = info.get("shortName", symbol)
            
            # 取得預估 EPS
            eps = info.get("forwardEps", "N/A")
            eps_str = f"${eps:.2f}" if isinstance(eps, (int, float)) else "N/A"
            
            # 取得預估營收，並轉換為易讀格式 (Billions / Millions)
            rev = info.get("totalRevenue", "N/A")
            if isinstance(rev, (int, float)):
                if rev >= 1e9:
                    rev_str = f"${rev / 1e9:.2f}B"
                elif rev >= 1e6:
                    rev_str = f"${rev / 1e6:.2f}M"
                else:
                    rev_str = f"${rev:,.0f}"
            else:
                rev_str = "N/A"

            # 處理財報日期與歷史數據
            earnings_dates = ticker.earnings_dates
            report_date_str = "-"
            bmo_amc = ""
            history_data = []

            if earnings_dates is not None and not earnings_dates.empty:
                # 1. 抓取未來的財報發布日
                future = earnings_dates[earnings_dates.index >= today]
                if not future.empty:
                    next_date = future.index[0]
                    report_date_str = next_date.strftime("%Y-%m-%d")
                    # 判斷盤前(BMO) 或 盤後(AMC)
                    if next_date.hour < 12:
                        bmo_amc = "☀️"
                    elif next_date.hour >= 16:
                        bmo_amc = "🌙"

                # 2. 抓取過去 4 個季度的歷史發布 EPS
                past = earnings_dates[earnings_dates.index < today].head(4)
                for date_idx, row in past.iterrows():
                    rep_eps = row.get('Reported EPS', 'N/A')
                    if pd.isna(rep_eps):
                        rep_eps_str = 'N/A'
                    else:
                        rep_eps_str = f"${rep_eps:.2f}"
                        
                    history_data.append({
                        "date": date_idx.strftime("%Y-%m-%d"),
                        "eps_reported": rep_eps_str
                    })
            
            # 寫入單家公司結果
            results.append({
                "ticker": symbol,
                "name": name,
                "reportDate": report_date_str,
                "bmo_amc": bmo_amc,
                "eps": eps_str,
                "revenue": rev_str,
                "history": history_data
            })
            
        except Exception as e:
            logging.error(f"處理 {symbol} 時發生錯誤: {e}")

    # 匯出資料供前端 Table 讀取
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logging.info("成功寫入 data.json")

    # Bark 財報提醒功能 (無須更動，保留原專案支援)
    bark_key = os.getenv('BARK_KEY')
    if bark_key:
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_list = [r['ticker'] for r in results if r['reportDate'] == tomorrow]
        if tomorrow_list:
            msg = f"明日即將發布財報: {', '.join(tomorrow_list)}"
            try:
                requests.get(f"https://api.day.app/{bark_key}/{msg}")
                logging.info("Bark 推播已發送。")
            except Exception as e:
                logging.error(f"Bark 推播失敗: {e}")

if __name__ == "__main__":
    main()
