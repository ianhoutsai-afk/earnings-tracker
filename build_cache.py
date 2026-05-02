import pandas as pd
import requests
import json
import time
import sys

# SEC 官方要求 User-Agent 必須包含聯絡資訊
HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)',
}

def build_sp500_cache():
    print("📥 正在從 DataHub 獲取 S&P 500 最新名單 (CSV)...")
    
    try:
        # 【關鍵變更】：不再抓取維基百科 HTML，改用直接的 CSV 連結
        # 這個來源對 GitHub Actions 友善得多，且包含 Symbol, Security, CIK, GICS Sector
        csv_url = "https://datahub.io/core/s-and-p-500-companies/r/constituents.csv"
        df = pd.read_csv(csv_url)
        
        if df.empty:
            print("❌ 獲取的名單為空")
            return False
            
    except Exception as e:
        print(f"❌ 獲取名單失敗: {e}")
        return False

    # 清理 Ticker (把 BRK.B 轉成 BRK-B)
    df['Symbol'] = df['Symbol'].str.replace('.', '-', regex=False)
    companies_cache = {}
    total = len(df)
    print(f"✅ 成功獲取 {total} 家公司名單！")
    
    print("⏳ 開始透過 SEC 官方 API 獲取財年結算月 (fy_end)...\n")
    
    with requests.Session() as session:
        session.headers.update(HEADERS)
        
        for index, row in df.iterrows():
            ticker = row['Symbol']
            name = row['Security']
            # 確保 CIK 是 10 位數字
            try:
                cik = str(int(row['CIK'])).zfill(10)
            except:
                cik = str(row['CIK']).zfill(10)
                
            sector = row['GICS Sector']
            fy_end = 12 # 預設
            
            try:
                url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                res = session.get(url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    fy_str = data.get("fiscalYearEnd", "1231")
                    if fy_str and len(fy_str) == 4:
                        fy_end = int(fy_str[:2])
                
                if (index + 1) % 50 == 0:
                    print(f"已處理 {index+1}/{total} 家公司...")
                    
            except Exception as e:
                print(f"  ⚠️ {ticker} 獲取失敗: {e}")
            
            companies_cache[ticker] = {
                "name": name, "cik": cik, "sector": sector, "fy_end": fy_end
            }
            
            # SEC 嚴格限制每秒 10 次請求
            time.sleep(0.15) 

    try:
        with open('sp500_mapping.json', 'w', encoding='utf-8') as f:
            json.dump(companies_cache, f, ensure_ascii=False, indent=4)
        print(f"\n🎉 成功寫入 {len(companies_cache)} 家公司到 sp500_mapping.json")
        return True
    except Exception as e:
        print(f"❌ 寫入檔案失敗: {e}")
        return False

if __name__ == "__main__":
    if not build_sp500_cache():
        sys.exit(1)
