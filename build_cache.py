import pandas as pd
import requests
import json
import time

# SEC 官方要求 User-Agent 必須包含聯絡資訊，否則會被阻擋 (403 Forbidden)
HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)'
}

def build_sp500_cache():
    print("📥 正在從維基百科獲取 S&P 500 最新名單...")
    
    # 1. 抓取維基百科表格
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        df = tables[0]
    except Exception as e:
        print(f"❌ 獲取維基百科失敗: {e}")
        return

    # 2. 清理 Ticker (把 BRK.B 轉成 BRK-B，以符合 Yahoo/SEC 格式)
    df['Symbol'] = df['Symbol'].str.replace('.', '-', regex=False)
    
    companies_cache = {}
    total = len(df)
    print(f"✅ 成功獲取 {total} 家公司名單！")
    print("⏳ 開始透過 SEC 官方 API 獲取財年結算月 (fy_end)...\n")
    
    # 3. 建立連線池
    with requests.Session() as session:
        for index, row in df.iterrows():
            ticker = row['Symbol']
            name = row['Security']
            cik = str(row['CIK']).zfill(10)
            sector = row['GICS Sector']  # 順便把產業別抓下來，未來前端可以用！
            
            fy_end = 12 # 預設為日曆年
            
            try:
                # 請求 SEC API
                url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                res = session.get(url, headers=HEADERS, timeout=10)
                
                if res.status_code == 200:
                    data = res.json()
                    # SEC 的財年格式通常為 "0930" (代表 9月30日)
                    fy_str = data.get("fiscalYearEnd", "1231")
                    if fy_str and len(fy_str) == 4:
                        fy_end = int(fy_str[:2]) # 提取前兩位作為月份
                else:
                    print(f"  [!] API 狀態碼異常 {res.status_code}")
                
                print(f"[{index+1}/{total}] {ticker:<6} | 產業: {sector[:15]:<15} | fy_end: {fy_end}")
            
            except Exception as e:
                print(f"[{index+1}/{total}] ⚠️ {ticker} 獲取失敗 ({e})，預設為 12")
            
            # 寫入字典
            companies_cache[ticker] = {
                "name": name,
                "cik": cik,
                "sector": sector,
                "fy_end": fy_end
            }
            
            # SEC 嚴格限制每秒最多 10 次請求，設定 0.15 秒延遲非常安全
            time.sleep(0.15) 
            
    # 4. 儲存為靜態 JSON 檔案
    with open('sp500_mapping.json', 'w', encoding='utf-8') as f:
        json.dump(companies_cache, f, ensure_ascii=False, indent=4)
        
    print("\n🎉 大功告成！快取檔案 'sp500_mapping.json' 已成功生成！")

if __name__ == "__main__":
    start_time = time.time()
    build_sp500_cache()
    print(f"總耗時: {time.time() - start_time:.2f} 秒")
