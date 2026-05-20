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

# 修改為 Bark 的 Key
BARK_KEY = os.environ.get('BARK_KEY')

QUARTER_MAPPING = {
    11: "Q4", 0: "Q4", 1: "Q4",
    2: "Q1", 3: "Q1", 4: "Q1",
    5: "Q2", 6: "Q2", 7: "Q2",
    8: "Q3", 9: "Q3", 10: "Q3"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
}

# ==========================================
# 2. 核心邏輯
# ==========================================

def send_bark_notification(companies):
    if not BARK_KEY:
        print("⚠️ 未配置 Bark Key，跳過通知。")
        return

    tomorrow_earnings = [c['ticker'] for c in companies if c['days_left'] == 1]
    
    if not tomorrow_earnings:
        print("💤 明日無 S&P 500 公司發報，無需通知。")
        return

    tomorrow_date = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
    tickers_str = ", ".join(tomorrow_earnings)
    
    title = "📊 S&P 500 財報預警"
    message = (
        f"📅 日期：{tomorrow_date}\n"
        f"🚀 明日將有 {len(tomorrow_earnings)} 家公司發布財報：\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"{tickers_str}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 請檢查您的關注名單並做好佈局！"
    )

    try:
        url = f"https://api.day.app/{BARK_KEY}/"
        payload = {
            "title": title,
            "body": message,
            "group": "Earnings Tracker",
            "icon": "https://cdn-icons-png.flaticon.com/512/2950/2950664.png",
            "url": "https://ianhoutsai-afk.github.io/earnings-tracker/", # 點擊通知將直接跳轉您的前端網頁
            "isArchive": 1
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Bark 通知發送成功！")
        else:
            print(f"❌ Bark 發送失敗: {res.status_code}")
    except Exception as e:
        print(f"🔴 Bark 請求錯誤: {e}")

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

# ==========================================
# 🌟 新增：全球央行利率數據生成 (不影響舊功能)
# ==========================================
def update_macro_data():
    try:
        now = datetime.now(timezone.utc)
        
        # 美联储与欧央行时间表
        fed_meetings = ["2026-06-17T18:00:00Z", "2026-07-29T18:00:00Z", "2026-09-16T18:00:00Z", "2026-11-04T18:00:00Z", "2026-12-16T18:00:00Z", "2027-01-27T18:00:00Z"]
        next_fed = next((d for d in fed_meetings if datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > now), "2027-01-27T18:00:00Z")

        ecb_meetings = ["2026-06-04T12:15:00Z", "2026-07-16T12:15:00Z", "2026-09-10T12:15:00Z", "2026-10-15T12:15:00Z", "2026-12-10T12:15:00Z"]
        next_ecb = next((d for d in ecb_meetings if datetime.strptime(d, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > now), "2027-01-21T12:15:00Z")

        # 中国央行LPR时间推算
        if now.day < 20 or (now.day == 20 and now.hour < 1):
            next_pboc_month, next_pboc_year = now.month, now.year
        else:
            next_pboc_month = now.month + 1 if now.month < 12 else 1
            next_pboc_year = now.year if now.month < 12 else now.year + 1
        next_pboc = f"{next_pboc_year}-{next_pboc_month:02d}-20T01:15:00Z"

        macro_data = [
            { "id": "FED", "name": "美联储 (Fed)", "rate": "5.25% - 5.50%", "nextDate": next_fed, "flag": "🇺🇸" },
            { "id": "PBOC", "name": "中国央行 (PBOC)", "rate": "3.45% (LPR)", "nextDate": next_pboc, "flag": "🇨🇳" },
            { "id": "ECB", "name": "欧洲央行 (ECB)", "rate": "4.25%", "nextDate": next_ecb, "flag": "🇪🇺" }
        ]

        with open('macro_data.json', 'w', encoding='utf-8') as f:
            json.dump(macro_data, f, ensure_ascii=False, indent=4)
        print("✅ 宏观利率数据 (macro_data.json) 更新完成！")
    except Exception as e:
        print(f"🔴 宏观数据生成错误: {e}")

if __name__ == "__main__":
    start_time = time.time()
    
    # 👇 仅仅在此处调用了新增的宏观函数，生成 macro_data.json
    update_macro_data()
    
    data, errors = get_tracker_data()
    
    if data:
        output = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "companies": data,
            "errors": errors
        }
        with open('data.js', 'w', encoding='utf-8') as f:
            f.write("window.earningsData = ")
            json.dump(macro_data, f, ensure_ascii=False, indent=2) # 這裡的 earnings_data 請替換成您原本寫入 JSON 的變數名
            f.write(";")
        
        # 🌟 Bark 通知頻率控制邏輯 (增強防禦版)
        current_utc_hour = datetime.now(timezone.utc).hour
        event_name = os.environ.get('GITHUB_EVENT_NAME', '')
        
        # 只要是 UTC 0 點到 11點 之間跑完的，都認定為「早上批次」
        # 這完美解決了 GitHub Actions 因為排隊導致延遲 1~3 小時的問題
        is_morning_run = current_utc_hour < 12
        is_manual_trigger = (event_name == 'workflow_dispatch')
        
        if is_morning_run or is_manual_trigger:
            print("🕒 達到通知觸發條件 (晨間預警或手動執行)，準備發送 Bark...")
            send_bark_notification(data)
        else:
            print(f"🔕 目前時間 (UTC {current_utc_hour} 點) 為靜默更新時段，跳過 Bark 通知。")
            
        print(f"🚀 更新完成！耗時: {time.time() - start_time:.2f} 秒")
    else:
        print("❌ 數據同步失敗")
