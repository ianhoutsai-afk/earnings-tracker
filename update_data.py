import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date, timezone

# ==========================================
# 1. 核心配置區 (Configuration)
# ==========================================

# 公司清單與財年結束月份 (fy_end)
# fy_end = 12 (日曆年), 9 (蘋果), 6 (微軟), 1 (輝達)
# 若要擴充追蹤公司，只需在此處新增字典項目即可，無需修改下方邏輯。
COMPANIES = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810", "fy_end": 1},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193", "fy_end": 9},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019", "fy_end": 6},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724", "fy_end": 12},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044", "fy_end": 12},
    "META": {"name": "Meta (Facebook)", "cik": "1326801", "fy_end": 12},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605", "fy_end": 12}
}

# 季度偏移量映射表 (Quarter Offset Mapping)
# 鍵(Key): (報表月份 - 財年結束月份) % 12
# 值(Value): 對應的財報季度
# 加入相鄰月份(±1)作為容錯區間，處理跨月邊界問題
QUARTER_MAPPING = {
    11: "Q4",  0: "Q4",  1: "Q4",
     2: "Q1",  3: "Q1",  4: "Q1",
     5: "Q2",  6: "Q2",  7: "Q2",
     8: "Q3",  9: "Q3", 10: "Q3"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
}

# ==========================================
# 2. 核心邏輯區 (Core Functions)
# ==========================================

def get_quarter_label(ticker, form_type, report_date_str):
    """基於財年偏移量計算季度標籤 (Data-Driven Approach)"""
    if not report_date_str:
        return "季報" if "10-Q" in form_type else "年報"
    
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    try:
        fy_end = COMPANIES.get(ticker, {}).get("fy_end", 12)
        report_month = int(report_date_str.split('-')[1])
        
        # 計算偏移量並查表
        diff = (report_month - fy_end) % 12
        quarter = QUARTER_MAPPING.get(diff, "Q?")
        
        return f"{quarter} 季報 (10-Q)"
    except Exception as e:
        print(f"標籤計算錯誤 {ticker}: {e}")
        return "季報 (10-Q)"

def get_sec_history_final(session, ticker, cik):
    """獲取 SEC 歷史申報文件"""
    history =[]
    padded_cik = cik.zfill(10)
    try:
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = session.get(url, headers=HEADERS, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            filings = data.get("filings", {}).get("recent", {})
            forms = filings.get("form", [])
            
            for i in range(len(forms)):
                form_type = forms[i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    report_date = filings["reportDate"][i]
                    
                    display_form = get_quarter_label(ticker, form_type, report_date)
                    if "/A" in form_type: 
                        display_form += " (修正)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    
                    history.append({
                        "type": display_form, 
                        "date": filing_date, 
                        "html_url": html_url, 
                        "ix_url": ix_url
                    })
                    if len(history) == 5: 
                        break
    except Exception as e:
        print(f"🔴 SEC CIK {cik} 錯誤: {e}")
    return history

def get_tracker_data():
    """主控函數：整合 yfinance 與 SEC 數據"""
    results =[]
    today = date.today()
    with requests.Session() as session:
        for ticker, info in COMPANIES.items():
            try:
                # 獲取下次財報日
                stock = yf.Ticker(ticker)
                calendar = stock.calendar
                final_date = None
                
                if calendar and 'Earnings Date' in calendar:
                    potential_dates = calendar['Earnings Date']
                    for d in potential_dates:
                        d_date = d.date() if isinstance(d, datetime) else d
                        if d_date >= today and d_date.year <= today.year + 1:
                            final_date = d_date
                            break
                            
                earnings_date_str = final_date.strftime('%Y-%m-%d') if final_date else "官方公佈中"
                days_remaining = (final_date - today).days if final_date else "N/A"
                
                # 獲取 SEC 歷史紀錄
                sec_history = get_sec_history_final(session, ticker, info["cik"])
                
                time.sleep(0.1)  # 避免 SEC API 速率限制
                
                results.append({
                    "ticker": ticker, 
                    "name": info["name"], 
                    "date": earnings_date_str,
                    "days_left": days_remaining, 
                    "history": sec_history
                })
                print(f"✅ {ticker} 同步成功")
            except Exception as e:
                print(f"❌ {ticker} 出錯: {e}")
    return results

# ==========================================
# 3. 執行入口 (Entry Point)
# ==========================================
if __name__ == "__main__":
    start_time = time.time()
    
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "companies": data
    }
    
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
    
    print(f"🚀 全部更新完成，耗時: {time.time() - start_time:.2f} 秒")
