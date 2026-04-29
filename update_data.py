import os
import yfinance as yf
import requests
import json
import time
from datetime import datetime, date

# 核心設定
companies = {
    "NVDA": {"name": "輝達 (Nvidia)", "cik": "1045810"},
    "AAPL": {"name": "蘋果 (Apple)", "cik": "320193"},
    "MSFT": {"name": "微軟 (Microsoft)", "cik": "789019"},
    "AMZN": {"name": "亞馬遜 (Amazon)", "cik": "1018724"},
    "GOOGL": {"name": "Alphabet (Google)", "cik": "1652044"},
    "META": {"name": "Meta (Facebook)", "cik": "1326801"},
    "TSLA": {"name": "特斯拉 (Tesla)", "cik": "1318605"}
}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36',
}

def get_quarter_by_fye(form_type, report_date_str, fye_str):
    """
    根據財政年度結束日 (FYE) 和報告日精確計算季度
    """
    if not report_date_str or not fye_str:
        return "季報" if "10-Q" in form_type else "年報"
    
    if "10-K" in form_type:
        return "Q4 / 年報 (10-K)"
    
    try:
        # 提取月份
        report_month = int(report_date_str.split('-')[1])
        fye_month = int(fye_str.split('-')[1])
        
        # 計算月份差 (模 12)
        diff = (report_month - fye_month) % 12
        
        # 根據月份差映射季度
        if 1 <= diff <= 4:
            return "Q1 季報 (10-Q)"
        elif 5 <= diff <= 7:
            return "Q2 季報 (10-Q)"
        elif 8 <= diff <= 10:
            return "Q3 季報 (10-Q)"
        else:
            return "季報 (10-Q)" # 兜底
    except:
        return "季報 (10-Q)"

def get_sec_history_final(cik):
    history = []
    padded_cik = cik.zfill(10)
    try:
        # 1. 獲取公司基本資訊（包含財政年度結束日 fiscalYearEnd）
        url = f"https://data.sec.gov/submissions/CIK{padded_cik}.json"
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code == 200:
            data = res.json()
            # 獲取官方定義的財政年度結束日
            fye = data.get("fiscalYearEnd", "12-31") 
            filings = data.get("filings", {}).get("recent", {})
            
            for i in range(len(filings.get("form", []))):
                form_type = filings["form"][i]
                if "10-Q" in form_type or "10-K" in form_type:
                    acc_num = filings["accessionNumber"][i].replace("-", "")
                    doc_name = filings["primaryDocument"][i]
                    filing_date = filings["filingDate"][i]
                    report_date = filings["reportDate"][i]
                    
                    # 使用財政年度基準計算季度
                    display_form = get_quarter_by_fye(form_type, report_date, fye)
                    if "/A" in form_type: display_form += " (修正)"
                    
                    html_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    ix_url = f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{cik}/{acc_num}/{doc_name}"
                    
                    history.append({"type": display_form, "date": filing_date, "html_url": html_url, "ix_url": ix_url})
                    if len(history) == 5: break
    except Exception as e:
        print(f"🔴 SEC CIK {cik} 錯誤: {e}")
    return history

def get_tracker_data():
    results = []
    today = date.today()
    
    for ticker, info in companies.items():
        print(f"正在同步 {ticker}...")
        try:
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
            sec_history = get_sec_history_final(info["cik"])
            time.sleep(0.2)

            results.append({
                "ticker": ticker, "name": info["name"], "date": earnings_date_str,
                "days_left": days_remaining, "history": sec_history
            })
            
        except Exception as e:
            print(f"❌ {ticker} 出錯: {e}")
            
    return results

if __name__ == "__main__":
    data = get_tracker_data()
    output = {
        "last_updated": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "companies": data
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=4)
