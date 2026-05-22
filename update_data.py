import os
import yfinance as yf
import requests
import json
import time
import pandas as pd
import math
from datetime import datetime, date, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ==========================================
# 1. 配置與常量
# ==========================================
MAPPING_FILE = 'sp500_mapping.json'
OUTPUT_FILE = 'data.json' # 確保前端引用的文件名與此一致
# 修改為 Bark 的 Key (請在 GitHub Actions Secrets 中設置)
BARK_KEY = os.environ.get('BARK_KEY')

QUARTER_MAPPING = {
    1: "Q1", 2: "Q1", 3: "Q1",
    4: "Q2", 5: "Q2", 6: "Q2",
    7: "Q3", 8: "Q3", 9: "Q3",
    10: "Q4", 11: "Q4", 0: "Q4"
}

HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)',
}

# ==========================================
# 2. 核心邏輯
# ==========================================
def send_bark_notification(companies):
    if not BARK_KEY:
        print("⚠️ 未配置 Bark Key，跳過通知。")
        return
    
    tomorrow_earnings = [c['ticker'] for c in companies if isinstance(c.get('days_left'), int) and c['days_left'] == 1]
    
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
        f"💡 請檢查您的關注名單並做好佈局！\n\n{tomorrow_date}\nhttps://ianhoutsai-afk.github.io/earnings-tracker/"
    )
    
    try:
        url = f"https://api.day.app/{BARK_KEY}/"
        payload = {
            "title": title,
            "body": message.replace("\n", "\\n"), # 確保換行符轉義，避免 API 解析錯誤
            "group": "Earnings Tracker",
            "icon": "https://cdn-icons-png.flaticon.com/512/2950/2950664.png",
            "url": f"https://ianhoutsai-afk.github.io/earnings-tracker/",
            "isArchive": 1
        }
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Bark 通知發送成功！")
        else:
            print(f"❌ Bark 發送失敗 (Status {res.status_code})")
    except Exception as e:
        print(f"🔴 Bark 請求錯誤：{e}")

def get_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update(HEADERS)
    return session

def to_float(value):
    try:
        if isinstance(value, str):
            cleaned = value.replace("$", "").replace(",", "").strip()
            if cleaned in {"", "N/A", "NA", "-", "None", "nan"}:
                return None
            value = cleaned
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None

def humanize_revenue(value):
    num = to_float(value)
    if num is None:
        return "N/A"
    if num >= 1_000_000_000_000:
        return f"{num / 1_000_000_000_000:.2f}T"
    if num >= 1_000_000_000:
        return f"{num / 1_000_000_000:.2f}B"
    if num >= 1_000_000:
        return f"{num / 1_000_000:.2f}M"
    return f"{num:.0f}"

def _to_dataframe(table):
    if isinstance(table, pd.DataFrame):
        return table.copy()
    if isinstance(table, dict):
        try:
            return pd.DataFrame(table)
        except Exception:
            return None
    return None

def _pick_consensus_from_estimate_table(table, value_col="avg", analysts_col="numberOfAnalysts", preferred_periods=("0q", "+1q")):
    df = _to_dataframe(table)
    if df is None or df.empty:
        return None, None, None

    df.index = df.index.map(lambda x: str(x).strip())
    index_lookup = {str(idx).lower(): idx for idx in df.index}

    ordered_periods = []
    for p in preferred_periods:
        p_norm = str(p).lower()
        if p_norm not in ordered_periods:
            ordered_periods.append(p_norm)
    for idx in df.index:
        idx_norm = str(idx).lower()
        if idx_norm not in ordered_periods:
            ordered_periods.append(idx_norm)

    for period_norm in ordered_periods:
        actual_idx = index_lookup.get(period_norm)
        if actual_idx is None:
            continue

        row = df.loc[actual_idx]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]

        value = to_float(row.get(value_col))
        analysts_val = to_float(row.get(analysts_col))
        analysts = int(analysts_val) if analysts_val is not None and not math.isnan(analysts_val) else None

        if value is not None:
            return value, analysts, str(actual_idx)

    return None, None, None

def _extract_calendar_metric(cal, candidates):
    if cal is None:
        return None

    if isinstance(cal, pd.DataFrame) and not cal.empty:
        lower_cols = {str(col).strip().lower(): col for col in cal.columns}
        for key in candidates:
            key_norm = key.lower()
            if key_norm in lower_cols:
                series = cal[lower_cols[key_norm]]
                for v in series.tolist():
                    parsed = to_float(v)
                    if parsed is not None:
                        return parsed

        lower_index = {str(idx).strip().lower(): idx for idx in cal.index}
        for key in candidates:
            key_norm = key.lower()
            if key_norm in lower_index:
                row = cal.loc[lower_index[key_norm]]
                if isinstance(row, pd.Series):
                    for v in row.tolist():
                        parsed = to_float(v)
                        if parsed is not None:
                            return parsed

    if isinstance(cal, dict):
        lower_keys = {str(k).strip().lower(): k for k in cal.keys()}
        for key in candidates:
            k = lower_keys.get(key.lower())
            if not k:
                continue
            raw = cal.get(k)
            if isinstance(raw, (list, tuple, pd.Series)):
                for v in raw:
                    parsed = to_float(v)
                    if parsed is not None:
                        return parsed
            else:
                parsed = to_float(raw)
                if parsed is not None:
                    return parsed

    return None

def _safe_getattr(obj, attr):
    try:
        return getattr(obj, attr)
    except Exception:
        return None

def _safe_call(obj, method):
    try:
        fn = getattr(obj, method, None)
        if callable(fn):
            return fn()
    except Exception:
        return None
    return None

def extract_market_snapshot(stock):
    info = {}
    fast_info = {}

    try:
        info = stock.info or {}
    except Exception:
        info = {}

    try:
        fast_info = stock.fast_info or {}
    except Exception:
        fast_info = {}

    cal = _safe_getattr(stock, "calendar")

    earnings_estimate_table = _safe_call(stock, "get_earnings_estimate")
    if earnings_estimate_table is None:
        earnings_estimate_table = _safe_getattr(stock, "earnings_estimate")

    revenue_estimate_table = _safe_call(stock, "get_revenue_estimate")
    if revenue_estimate_table is None:
        revenue_estimate_table = _safe_getattr(stock, "revenue_estimate")

    eps_consensus, eps_analysts, eps_period = _pick_consensus_from_estimate_table(
        earnings_estimate_table, value_col="avg", analysts_col="numberOfAnalysts", preferred_periods=("0q", "+1q")
    )
    rev_consensus, rev_analysts, rev_period = _pick_consensus_from_estimate_table(
        revenue_estimate_table, value_col="avg", analysts_col="numberOfAnalysts", preferred_periods=("0q", "+1q")
    )

    eps_calendar = _extract_calendar_metric(cal, ["Earnings Average", "EPS Estimate", "epsEstimate", "earningsAverage"])
    rev_calendar = _extract_calendar_metric(cal, ["Revenue Average", "Revenue Estimate", "revenueAverage", "revenueEstimate"])

    market_cap = info.get("marketCap") or fast_info.get("market_cap")
    eps_forward = info.get("forwardEps")
    eps_trailing = info.get("trailingEps")
    rev_total = info.get("totalRevenue")

    market_cap_num = to_float(market_cap)
    eps_forward_num = to_float(eps_forward)
    eps_trailing_num = to_float(eps_trailing)
    rev_total_num = to_float(rev_total)

    if eps_consensus is not None:
        eps_num = eps_consensus
        eps_source = "yahoo_analyst_consensus"
        eps_confidence = "high"
        eps_meta = {"period": eps_period, "analysts": eps_analysts}
    elif eps_calendar is not None:
        eps_num = eps_calendar
        eps_source = "yahoo_calendar_estimate"
        eps_confidence = "medium"
        eps_meta = {"period": "calendar", "analysts": None}
    elif eps_forward_num is not None:
        eps_num = eps_forward_num
        eps_source = "yahoo_forward_eps_fallback"
        eps_confidence = "low"
        eps_meta = {"period": "forward", "analysts": None}
    elif eps_trailing_num is not None:
        eps_num = eps_trailing_num
        eps_source = "yahoo_trailing_eps_fallback"
        eps_confidence = "low"
        eps_meta = {"period": "trailing", "analysts": None}
    else:
        eps_num = None
        eps_source = "unavailable"
        eps_confidence = "low"
        eps_meta = {"period": None, "analysts": None}

    if rev_consensus is not None:
        rev_num = rev_consensus
        rev_source = "yahoo_analyst_consensus"
        rev_confidence = "high"
        rev_meta = {"period": rev_period, "analysts": rev_analysts}
    elif rev_calendar is not None:
        rev_num = rev_calendar
        rev_source = "yahoo_calendar_estimate"
        rev_confidence = "medium"
        rev_meta = {"period": "calendar", "analysts": None}
    elif rev_total_num is not None:
        rev_num = rev_total_num
        rev_source = "yahoo_total_revenue_fallback"
        rev_confidence = "low"
        rev_meta = {"period": "ttm_or_reported", "analysts": None}
    else:
        rev_num = None
        rev_source = "unavailable"
        rev_confidence = "low"
        rev_meta = {"period": None, "analysts": None}

    mcap_b = round(market_cap_num / 1_000_000_000, 2) if market_cap_num is not None else None
    eps = f"{eps_num:.2f}" if eps_num is not None else "N/A"
    rev = humanize_revenue(rev_num)

    return {
        "mcap_b": mcap_b,
        "eps": eps,
        "rev": rev,
        "eps_source": eps_source,
        "eps_confidence": eps_confidence,
        "eps_estimate_period": eps_meta.get("period"),
        "eps_analysts": eps_meta.get("analysts"),
        "rev_source": rev_source,
        "rev_confidence": rev_confidence,
        "rev_estimate_period": rev_meta.get("period"),
        "rev_analysts": rev_meta.get("analysts"),
    }

def get_quarter_label(ticker, companies_map, form_type, report_date_str):
    if not report_date_str: 
        return "季報" if form_type in ["10-Q", "10-K"] else "未知"
    
    try:
        fy_end = companies_map.get(ticker, {}).get("fy_end", 12)
        report_month = int(report_date_str.split('-')[1])
        
        # 修正季度計算邏輯
        diff = (report_month - fy_end) % 12
        
        if form_type == "10-K":
            return f"{QUARTER_MAPPING.get(diff, 'Q?')} 季報 (年報 10-K)"
        else:
            return f"{QUARTER_MAPPING.get(diff, 'Q?')} 季報 (10-Q)"
    except Exception:
        return "季報 (10-Q)"

def get_sec_history(session, ticker, cik, companies_map):
    history = []
    if not cik:
        return history
        
    # SEC API 需要將 CIK 補零到 10 位數，先強制轉為字串避免 int 報錯
    padded_cik = str(cik).zfill(10)
    
    url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
    try:
        res = session.get(url, timeout=15)
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {})
            recent_filings = filings.get("recent", {}) 
            
            # 判斷 recent 是否為非空字典
            if isinstance(recent_filings, dict) and "form" in recent_filings:
                forms = recent_filings.get("form", [])
                accession_numbers = recent_filings.get("accessionNumber", [])
                primary_documents = recent_filings.get("primaryDocument", [])
                filing_dates = recent_filings.get("filingDate", [])
                report_dates = recent_filings.get("reportDate", [])
                
                # 遍歷各同等長度的欄位列表
                for i in range(len(forms)):
                    form_type = forms[i]
                    if "10-Q" in form_type or "10-K" in form_type:
                        raw_acc = accession_numbers[i] if i < len(accession_numbers) else ""
                        # 連結需要去掉橫線的完整 Accession Number (18位)，不能只取前 10 位
                        acc_num = raw_acc.replace("-", "") 
                        doc_name = primary_documents[i] if i < len(primary_documents) else ""
                        filing_date = filing_dates[i] if i < len(filing_dates) else ""
                        report_date = report_dates[i] if i < len(report_dates) else ""
                        
                        display_form = get_quarter_label(ticker, companies_map, form_type, report_date)
                        if "/A" in form_type: display_form += " (修正)"
                        
                        # 使用未補零的原始 cik 產生 URL (這是 SEC 的規範)
                        html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                        ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                        
                        history.append({
                            "type": display_form, 
                            "date": filing_date, 
                            "html_url": html_url, 
                            "ix_url": ix_url
                        })
                        
                        # 限制只取最近 5 筆，防止長度暴增
                        if len(history) >= 5:
                            break
    except Exception as e:
        print(f"[{ticker}] 獲取 SEC 歷史失敗：{e}")
        
    return history

def get_tracker_data():
    try:
        with open(MAPPING_FILE, 'r', encoding='utf-8') as f:
            companies_map = json.load(f)
    except FileNotFoundError:
        print(f"❌ 找不到 {MAPPING_FILE}")
        return [], []
    except json.JSONDecodeError:
        print(f"❌ {MAPPING_FILE} 格式錯誤")
        return [], []

    tickers = list(companies_map.keys())
    total = len(tickers)
    results, errors = [], []
    
    today = date.today()
    session = get_session()
    
    print(f"🚀 開始同步 {total} 家公司數據...")
    
    for index, ticker in enumerate(tickers):
        info = companies_map.get(ticker) # 確保能取到 info
        if not info: continue
        
        try:
            stock = yf.Ticker(ticker)
            snapshot = extract_market_snapshot(stock)
            
            # 1. 嘗試通過 earnings_dates 獲取
            final_date = None
            timing = "Unknown"
            
            try:
                earns = stock.get_earnings_dates(limit=5)
                if earns is not None and not earns.empty:
                    # yfinance 返回的 index 本身即為 DatetimeIndex，其時區可能為 UTC 或美國東部
                    if earns.index.tz is None:
                        earns.index = earns.index.tz_localize('UTC').tz_convert('US/Eastern')
                    else:
                        earns.index = earns.index.tz_convert('US/Eastern')
                        
                    today_eastern = pd.Timestamp.now(tz='US/Eastern').normalize()
                    
                    # 篩選大於等於今天且最接近未來的財報日期
                    future_earns = earns[earns.index >= today_eastern]
                    
                    if not future_earns.empty:
                        # 升序排序，確保取到最接近今天的那一天
                        future_earns = future_earns.sort_index()
                        next_earn_date = future_earns.index[0] # 這是一個 Timestamp 對象
                        final_date = next_earn_date.date() # 只取日期部分
                        
                        hour = next_earn_date.hour
                        if 0 < hour <= 12: timing = "BMO" # 早上
                        elif 13 <= hour < 20: timing = "AMC" # 下午
                        else: timing = "Unknown"
                        
            except Exception as e:
                print(f"[{ticker}] 獲取 earnings_dates 失敗：{e}")
            
            # 2. 如果 earnings_dates 沒抓到，嘗試 calendar
            if not final_date:
                try:
                    cal = stock.calendar
                    calendar_dates = []

                    if isinstance(cal, pd.DataFrame) and 'Earnings Date' in cal.columns:
                        calendar_dates = cal['Earnings Date'].tolist()
                    elif isinstance(cal, dict) and 'Earnings Date' in cal:
                        raw = cal['Earnings Date']
                        calendar_dates = list(raw) if isinstance(raw, (list, tuple, pd.Series)) else [raw]

                    for d in calendar_dates:
                        if isinstance(d, pd.Timestamp):
                            d_date = d.date()
                        elif isinstance(d, datetime):
                            d_date = d.date()
                        elif isinstance(d, date):
                            d_date = d
                        elif isinstance(d, str):
                            try:
                                d_date = datetime.strptime(d[:10], "%Y-%m-%d").date()
                            except ValueError:
                                continue
                        else:
                            continue

                        if d_date > today:
                            final_date = d_date
                            break
                except Exception:
                    pass

            if final_date:
                earnings_date_str = final_date.strftime('%Y-%m-%d')
            else:
                earnings_date_str = "官方公佈中"
                
            days_remaining = (final_date - today).days if final_date else "N/A"
            
            # 3. 獲取 SEC 歷史財報
            sec_history = get_sec_history(session, ticker, info.get("cik"), companies_map)
            
            results.append({
                "ticker": ticker, 
                "name": info.get("name", ticker), # 使用 tickers 中的 key
                "sector": info.get("sector", "Unknown"),
                "date": earnings_date_str, 
                "days_left": days_remaining, 
                "time": timing,
                "timing": timing,
                "mcap": snapshot.get("mcap_b"),
                "eps": snapshot.get("eps"),
                "rev": snapshot.get("rev"),
                "eps_source": snapshot.get("eps_source"),
                "eps_confidence": snapshot.get("eps_confidence"),
                "eps_estimate_period": snapshot.get("eps_estimate_period"),
                "eps_analysts": snapshot.get("eps_analysts"),
                "rev_source": snapshot.get("rev_source"),
                "rev_confidence": snapshot.get("rev_confidence"),
                "rev_estimate_period": snapshot.get("rev_estimate_period"),
                "rev_analysts": snapshot.get("rev_analysts"),
                "history": sec_history
            })
            
        except Exception as e:
            errors.append({"ticker": ticker, "error": str(e)})
            
        if (index + 1) % 20 == 0: 
            print(f"✅ 進度：{index+1}/{total}")
        time.sleep(0.5) # 稍微延遲，避免被封殺
        
    return results, errors

# ==========================================
# 🌟 宏觀數據生成 (獨立任務，不依賴 earnings data)
# ==========================================
def update_macro_data():
    try:
        now = datetime.now(timezone.utc)
        
        # 這裡是硬編碼的未來時間，如果是自動化運行的 script，建議用 API 抓取真實利率
        # 這裡保持原樣以確保代碼可運行，但需注意年份過期問題
        fed_meetings = ["2026-06-17T18:00:00Z", "2026-07-29T18:00:00Z"] 
        ecb_meetings = ["2026-06-04T12:15:00Z", "2026-07-16T12:15:00Z"]
        
        # 簡單推算下一次會議時間 (僅供示例，實際應查詢 API)
        next_fed = now + timedelta(days=30) # 假設
        next_ecb = now + timedelta(days=45)
        
        macro_data = [
            { "id": "FED", "name": "美联储 (Fed)", "rate": "5.25% - 5.50%", "nextDate": next_fed.isoformat(), "flag": "🇺🇸" },
            { "id": "ECB", "name": "欧洲央行 (ECB)", "rate": "4.25%", "nextDate": next_ecb.isoformat(), "flag": "🇪🇺" }
        ]
        
        with open('macro_data.json', 'w', encoding='utf-8') as f:
            json.dump(macro_data, f, ensure_ascii=False, indent=4)
        print("✅ 宏觀利率數據 (macro_data.json) 更新完成！")
        
        return macro_data # 返回數據供主程序使用，或僅寫入文件
    except Exception as e:
        print(f"🔴 宏觀數據生成錯誤：{e}")

if __name__ == "__main__":
    start_time = time.time()
    
    # 1. 更新宏觀數據
    update_macro_data() 
    
    # 2. 獲取財報數據
    data, errors = get_tracker_data()
    
    final_output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "companies": data, 
        "errors": errors
    }
    
    # 3. 寫入正確的文件 (data.json) 
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        # 寫入純 JSON，方便前端直接讀取
        json.dump(final_output, f, ensure_ascii=False, indent=2) 
        print(f"💾 財報數據已寫入 {OUTPUT_FILE}")
        
    # 4. Bark 通知發送 (依賴於 data)
    if data and len(data) > 0:
        print("🕒 檢查明日財報...")
        send_bark_notification(data)
        
    print(f"🚀 更新完成！耗時：{time.time() - start_time:.2f} 秒")
