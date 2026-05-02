import pandas as pd
import requests
import json
import time
import sys

HEADERS = {
    'User-Agent': 'S&P500 Earnings Tracker (ianhoutsai@github.com)'
}

def build_sp500_cache():
    print("📥 正在從維基百科獲取 S&P 500 最新名單...")
    
    try:
        tables = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')
        # 尋找包含 'Symbol' 欄位的表格，而不是死板地用 tables[0]
        df = None
        for t in tables:
            if 'Symbol' in t.columns:
                df = t
                break
        
        if df is None:
            print("❌ 找不到包含 Symbol 的公司表格")
            return False
            
    except Exception as e:
        print(f"❌ 獲取維基百科失敗: {e}")
        return False

    df['Symbol'] = df['Symbol'].str.replace('.', '-', regex=False)
    companies_cache = {}
    total = len(df)
    print(f"✅ 成功獲取 {total} 家公司名單！")
    
    with requests.Session() as session:
        for index, row in df.iterrows():
            ticker = row['Symbol']
            name = row['Security']
            cik = str(row['CIK']).zfill(10)
            sector = row['GICS Sector']
            fy_end = 12
            
            try:
                url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                res = session.get(url, headers=HEADERS, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    fy_str = data.get("fiscalYearEnd", "1231")
                    if fy_str and len(fy_str) == 4:
                        fy_end = int(fy_str[:2])
                time.sleep(0.15) 
            except Exception as e:
                print(f"  ⚠️ {ticker} 獲取失敗: {e}")
            
            companies_cache[ticker] = {
                "name": name, "cik": cik, "sector": sector, "fy_end": fy_end
            }
            
            if (index + 1) % 50 == 0:
                print(f"已處理 {index+1}/{total} 家公司...")

    # 強制寫入檔案，確保 Git 能找到它
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
        sys.exit(1) # 如果失敗，讓 GitHub Action 顯示紅叉
