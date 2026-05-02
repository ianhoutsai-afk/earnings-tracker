# 📈 S&P 500 Earnings Tracker

[![GitHub Actions](https://github.com/ianhoutsai-afk/earnings-tracker/actions/workflows/main.yml/badge.svg)](https://github.com/ianhoutsai-afk/earnings-tracker/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Deployment: GitHub Pages](https://img.shields.io/badge/Deployment-GitHub%20Pages-blue)](https://ianhoutsai-afk.github.io/earnings-tracker/)

An institutional-grade, fully automated monitoring system for S&P 500 corporate earnings. This tool tracks expected earnings dates and retrieves the most recent official SEC filings (10-Q, 10-K) for the entire S&P 500 index.

**🚀 Live Demo:** [ianhoutsai-afk.github.io/earnings-tracker/](https://ianhoutsai-afk.github.io/earnings-tracker/)

---

## English Version

### ✨ Key Features
- **🌐 Full S&P 500 Coverage**: Tracks $\approx$ 500 companies, moving beyond a limited set to provide a comprehensive market view.
- **🤖 Fully Automated Pipeline**: Powered by GitHub Actions, updating the dataset twice daily without manual intervention.
- **🎯 Fiscal Year Precision**: Implements a custom mapping logic to handle varying fiscal year ends (e.g., AAPL, MSFT, NVDA), ensuring that "Q1/Q2/Q3/Q4" labels are accurate to the company's own financial calendar.
- **🏛️ Direct SEC Integration**: Pulls real-time data from SEC EDGAR, providing direct links to official HTML and iXBRL filings.
- **⚡ High-Performance Frontend**: 
  - **Instant Search**: Filter by Ticker or Company Name.
  - **Sector Filtering**: Group and analyze companies by GICS Sector.
  - **Lazy Rendering**: Optimized for 500+ entries to ensure zero lag on mobile and desktop.
  - **Urgency Sorting**: Automatically sorts companies by the closest earnings date.

### 🚀 Quick Deployment (3-Minute Setup)
This repository is configured as a **Template**. You can deploy your own version in seconds:

1. **Create Your Repository**: Click **`Use this template`** $\to$ **`Create a new repository`**. Ensure it is set to **Public**.
2. **Enable Write Permissions**: Go to **`Settings`** $\to$ **`Actions`** $\to$ **`General`** $\to$ **`Workflow permissions`** $\to$ Select **`Read and write permissions`** $\to$ **`Save`**.
3. **Launch Your Website**: Go to **`Settings`** $\to$ **`Pages`** $\to$ Select the `main` branch as the source $\to$ **`Save`**.

### 🛠️ Technical Architecture
- **Backend**: Python 3.9, `yfinance`, `requests` (with exponential backoff), `pandas`.
- **Frontend**: Tailwind CSS, Vanilla JavaScript (ES6+).
- **Infrastructure**: GitHub Actions (Cron Jobs), GitHub Pages (Hosting).
- **Data Flow**: `S&P 500 List` $\to$ `SEC API (Fiscal Year Mapping)` $\to$ `yfinance` $\to$ `SEC EDGAR` $\to$ `data.json` $\to$ `index.html`.

### 📝 Maintenance Note
The S&P 500 constituents change infrequently. If you notice a missing company, simply run the **`Build S&P 500 Cache`** workflow from the **Actions** tab to refresh the mapping database.

### ⚖️ Disclaimer
*This tool is for informational purposes only. All financial data is retrieved from public sources (Yahoo Finance & SEC). No guarantee of 100% accuracy is provided. Please refer to official SEC filings for investment decisions.*

---

## 中文版本

### ✨ 核心功能
- **🌐 全面覆蓋 S&P 500**：追蹤約 500 家成分股，提供全市場視角，不再局限於少數巨頭公司。
- **🤖 全自動化流水線**：由 GitHub Actions 驅動，每日自動更新兩次，無需人工干預。
- **🎯 精準財年計算**：針對不同公司的財年結束月份（如 AAPL、MSFT、NVDA）實作專屬映射邏輯，確保「Q1/Q2/Q3/Q4」標籤完全符合公司自身的財務年度。
- **🏛️ 直連 SEC 官方數據**：直接從 SEC EDGAR 系統獲取即時數據，提供官方 HTML 與 iXBRL 文件的直接連結。
- **⚡ 高性能前端體驗**：
  - **即時搜尋**：支持 Ticker 或公司名稱快速過濾。
  - **產業篩選**：可根據 GICS 產業類別進行分組分析。
  - **延遲渲染 (Lazy Render)**：針對 500+ 筆數據進行優化，確保在手機與電腦端均能流暢運行。
  - **緊急程度排序**：自動將最接近財報發布日期的公司排在最上方。

### 🚀 快速部署指南 (3 分鐘完成)
本倉庫已配置為 **模板 (Template)**，您可以秒級部署自己的追蹤系統：

1. **創建倉庫**：點擊頁面頂部的 **`Use this template`** $\to$ **`Create a new repository`**。請確保倉庫設為 **Public**。
2. **開啟寫入權限**：進入 **`Settings`** $\to$ **`Actions`** $\to$ **`General`** $\to$ 滾動至 **`Workflow permissions`** $\to$ 選擇 **`Read and write permissions`** $\to$ 點擊 **`Save`**。
3. **啟動網站**：進入 **`Settings`** $\to$ **`Pages`** $\to$ 在 Branch 中選擇 `main` 分支 $\to$ 點擊 **`Save`**。

### 🛠️ 技術架構
- **後端**：Python 3.9, `yfinance`, `requests` (含指數退避重試機制), `pandas`。
- **前端**：Tailwind CSS, 原生 JavaScript (ES6+)。
- **基礎設施**：GitHub Actions (定時任務), GitHub Pages (靜態託管)。
- **數據流向**：`S&P 500 名單` $\to$ `SEC API (財年映射)` $\to$ `yfinance` $\to$ `SEC EDGAR` $\to$ `data.json` $\to$ `index.html`。

### 📝 維護指南
S&P 500 成分股變動頻率較低。若發現公司名單有誤或缺失，只需在 **Actions** 標籤頁手動觸發一次 **`Build S&P 500 Cache`** 即可刷新映射數據庫。

### ⚖️ 免責聲明
*本工具僅供資訊參考。所有財務數據均獲取自公開來源 (Yahoo Finance & SEC)。不保證數據 100% 準確。投資決策請務必參考 SEC 官方申報文件。*
