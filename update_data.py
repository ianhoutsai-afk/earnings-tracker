import os
import yfinance as yf
import requests
import json
import time
import pandas as pd
from datetime import datetime, date, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 1. 配置與常量
# ==========================================
MAPPING_FILE = 'sp500_mapping.json'
OUTPUT_FILE = 'data.json'

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

QUARTER_MAPPING = {
    11: "Q4",  0: "Q4",  1: "Q4",
     2: "Q1",  3: "Q1",  4: "Q1",
     5: "Q2",  6: "Q2",  7: "Q2",
     8: "Q3",  9: "Q3", 10: "Q3"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
}

# ==========================================
# 2. 核心邏輯
# ==========================================

def send_telegram_notification(companies):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 未配置 Telegram Token 或 Chat ID，跳過通知。")
        return

    tomorrow_earnings =[c['ticker'] for c in companies if c['days_left'] == 1]
    
    if not tomorrow_earnings:
        print("💤 明日無 S&P 500 公司發報，無需通知。")
        return

    tomorrow_date = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    tickers_str = ", ".join(tomorrow_earnings)
    message = (
        f"📢 *S&P 500 財報預警*\n\n"
        f"📅 日期：`{tomorrow_date}`\n"
        f"🚀 明日將有 {len(tomorrow_earnings)} 家公司發布財報：\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"*{tickers_str}*\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 請檢查您的關注名單並做好佈局！\n"
        f"🔗 查看完整列表: https://ianhoutsai-afk.github.io/earnings-tracker/"
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Telegram 通知發送成功！")
        else:
            print(f"❌ Telegram 發送失敗: {res.status_code}")
    except Exception as e:
        print(f"🔴 Telegram 請求錯誤: {e}")

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)
    return session

def get_quarter_label(ticker, companies_map, form_type, report_date_str):
    if not report_date_str: return "季報" if "10-Q" in form_type else "年報"
    if "10-K" in form_type: return "Q4 / 年報 (10-K)"
    try:
        fy_end = companies_map.get(ticker, {}).get("fy_end", 12)
        report_month = int(report_date_str.split('-')[1])
        diff = (report_month - fy_end) % 12
        return f"{QUARTER_MAPPING.get(diff, 'Q?')} 季報 (10-Q)"
    except:
        return "季報 (10-Q)"

def get_sec_history(session, ticker, cik, companies_map):
    history =[]
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = session.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form",[])
            for i in range(len(forms)):
                form_type = forms[i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    report_date = filings["reportDate"][i]
                    display_form = get_quarter_label(ticker, companies_map, form_type, report_date)
                    if "/A" in form_type: display_form += " (修正)"
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    history.append({
                        "type": display_form, 
                        "date": filing_date, 
                        "html_url": html_url, 
                        "ix_url": ix_url
                    })
                    if len(history) == 5: break
    except Exception as e:
        print(f"🔴 SEC Error {ticker}: {e}")
    return history

def get_tracker_data():
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            companies_map = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 {MAPPING_FILE}")
        return None,[]

    tickers = list(companies_map.keys())
    total = len(tickers)
    results, errors = [],[]
    today = date.today()
    session = get_session()
    
    print(f"🚀 開始同步 {total} 家公司數據...")

    for index, ticker in enumerate(tickers):
        info = companies_map[ticker]
        try:
            stock = yf.Ticker(ticker)
            final_date = None
            timing = "Unknown"
            try:
                earns = stock.get_earnings_dates(limit=5)
                if earns is not None and not earns.empty:
                    if earns.index.tz is None: earns.index = earns.index.tz_localize('US/Eastern')
                    else: earns.index = earns.index.tz_convert('US/Eastern')
                    today_eastern = pd.Timestamp.now(tz='US/Eastern').normalize()
                    future_earns = earns[earns.index >= today_eastern]
                    if not future_earns.empty:
                        next_earn = future_earns.index[0]
                        final_date = next_earn.date()
                        hour = next_earn.hour
                        if hour > 0 and hour != 12: 
                            timing = "BMO" if hour < 13 else "AMC" if hour >= 15 else "Unknown"
            except: pass

            if not final_date:
                try:
                    calendar = stock.calendar
                    if calendar and 'Earnings Date' in calendar:
                        for d in calendar['Earnings Date']:
                            d_date = d.date() if isinstance(d, datetime) else d
                            if d_date >= today and d_date.year <= today.year + 1:
                                final_date = d_date
                                break
                except: pass

            earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
            days_remaining = (final_date - today).days if final_date else "N/A"
            sec_history = get_sec_history(session, ticker, info["cik"], companies_map)
            
            results.append({
                "ticker": ticker, "name": info["name"], "sector": info.get("sector", "Unknown"),
                "date": earnings_date_str, "days_left": days_remaining, "timing": timing, "history": sec_history
            })
            if (index + 1) % 20 == 0: print(f"✅ 進度: {index+1}/{total}")
            time.sleep(0.12) 
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})
            
    return results, errors

if __name__ == "__main__":
    start_time = time.time()
    data, errors = get_tracker_data()
    
    if data:
        output = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "companies": data,
            "errors": errors
        }
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, ensure_ascii=False, separators=(',', ':'))
            
        # 🌟 Telegram 通知頻率控制邏輯 (增強防禦版)
        current_utc_hour = datetime.now(timezone.utc).hour
        event_name = os.environ.get('GITHUB_EVENT_NAME', '')
        
        # 只要是 UTC 0 點到 11點 之間跑完的，都認定為「早上批次」
        # 這完美解決了 GitHub Actions 因為排隊導致延遲 1~3 小時的問題
        is_morning_run = current_utc_hour < 12
        is_manual_trigger = (event_name == 'workflow_dispatch')
        
        if is_morning_run or is_manual_trigger:
            print("🕒 達到通知觸發條件 (晨間預警或手動執行)，準備發送 Telegram...")
            send_telegram_notification(data)
        else:
            print(f"🔕 目前時間 (UTC {current_utc_hour} 點) 為靜默更新時段，跳過 Telegram 通知。")
            
        print(f"🚀 更新完成！耗時: {time.time() - start_time:.2f} 秒")
    else:
        print("❌ 數據同步失敗")
