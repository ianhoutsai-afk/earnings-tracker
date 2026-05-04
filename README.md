# 📈 S&P 500 Earnings Tracker

[![GitHub Actions](https://github.com/ianhoutsai-afk/earnings-tracker/actions/workflows/main.yml/badge.svg)](https://github.com/ianhoutsai-afk/earnings-tracker/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Deployment: GitHub Pages](https://img.shields.io/badge/Deployment-GitHub%20Pages-blue)](https://ianhoutsai-afk.github.io/earnings-tracker/)

An institutional-grade, fully automated monitoring system for S&P 500 corporate earnings. This tool tracks expected earnings dates, BMO/AMC timings, and retrieves the most recent official SEC filings (10-Q, 10-K) for the entire S&P 500 index.

**🚀 Live Demo:**[ianhoutsai-afk.github.io/earnings-tracker/](https://ianhoutsai-afk.github.io/earnings-tracker/)

---

## English Version

### ✨ Key Features
- **🌐 Full S&P 500 Coverage**: Tracks $\approx$ 500 companies, providing a comprehensive market view.
- **🤖 Automated Telegram Alerts**: Sends a daily morning summary of companies reporting earnings the next day.
- **⏱️ BMO / AMC Indicators**: Intelligently identifies if earnings will be released Before Market Open (☀️) or After Market Close (🌙).
- **⭐ Personalized Watchlist**: Save your favorite tickers directly to your browser's local storage for pinned access and quick filtering.
- **🎯 Fiscal Year Precision**: Implements a custom mapping logic to handle varying fiscal year ends, ensuring that "Q1/Q2/Q3/Q4" labels match the company's official financial calendar.
- **⚡ Pro-Grade Dashboard**: 
  - **Dark Mode**: Native Dark/Light theme toggle for a professional terminal feel.
  - **Mobile Card View**: Responsive design that transforms data rows into thumb-friendly cards on mobile devices.
  - **Lazy Rendering**: Optimized to render 500+ entries with zero lag.

### 🚀 Quick Deployment (3-Minute Setup)
This repository is configured as a **Template**. Deploy your own serverless tracker in seconds:

1. **Create Your Repository**: Click **`Use this template`** $\to$ **`Create a new repository`**. Ensure it is set to **Public**.
2. **Enable Write Permissions**: Go to **`Settings`** $\to$ **`Actions`** $\to$ **`General`** $\to$ **`Workflow permissions`** $\to$ Select **`Read and write permissions`** $\to$ **`Save`**.
3. **Launch Your Website**: Go to **`Settings`** $\to$ **`Pages`** $\to$ Select the `main` branch as the source $\to$ **`Save`**.
4. **Enable Telegram Alerts (Optional)**: 
   - Get a bot token from `@BotFather` and your Chat ID.
   - Go to **`Settings`** $\to$ **`Secrets and variables`** $\to$ **`Actions`**.
   - Add two secrets: `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`.

### 🛠️ Technical Architecture
- **Backend**: Python 3.9, `yfinance`, `requests` (with exponential backoff).
- **Frontend**: Tailwind CSS, Vanilla JavaScript (ES6+) with `localStorage`.
- **Infrastructure**: GitHub Actions (Cron Jobs), GitHub Pages (Hosting).

---

## 中文版本

### ✨ 核心功能
- **🌐 全面覆蓋 S&P 500**：追蹤約 500 家成分股，提供全市場視角，不再局限於少數巨頭公司。
- **🤖 Telegram 每日預警**：每日早晨自動推播「明日即將發布財報」的公司名單，輔助交易決策。
- **⏱️ 盤前 / 盤後精準標示**：智能解析財報發布時間段，清楚標示 ☀️盤前 (BMO) 或 🌙盤後 (AMC)。
- **⭐ 本地專屬收藏夾**：點擊星星圖示即可將關注公司存入瀏覽器本地 (Local Storage)，自動置頂並支援專屬篩選。
- **🎯 精準財年計算**：針對不同公司的財年結束月份實作專屬映射邏輯，確保「Q1/Q2/Q3/Q4」標籤完全符合公司財務年度。
- **⚡ 專業級前端體驗**：
  - **深色模式 (Dark Mode)**：內建日/夜間模式一鍵切換，打造彭博終端機般的專業質感。
  - **手機端卡片化佈局**：在行動裝置上自動將表格轉化為獨立卡片，極致的觸控體驗。
  - **延遲渲染 (Lazy Render)**：針對 500+ 筆數據進行底層優化，保證跨裝置零卡頓。

### 🚀 快速部署指南 (3 分鐘完成)
本倉庫已配置為 **模板 (Template)**，您可以實現零伺服器成本秒級部署：

1. **創建倉庫**：點擊頁面頂部的 **`Use this template`** $\to$ **`Create a new repository`**。請確保倉庫設為 **Public**。
2. **開啟寫入權限**：進入 **`Settings`** $\to$ **`Actions`** $\to$ **`General`** $\to$ 滾動至 **`Workflow permissions`** $\to$ 選擇 **`Read and write permissions`** $\to$ 點擊 **`Save`**。
3. **啟動網站**：進入 **`Settings`** $\to$ **`Pages`** $\to$ 在 Branch 中選擇 `main` 分支 $\to$ 點擊 **`Save`**。
4. **啟用 Telegram 通知 (選填)**：
   - 從 `@BotFather` 獲取 Token，並獲取你的 Chat ID。
   - 進入 **`Settings`** $\to$ **`Secrets and variables`** $\to$ **`Actions`**。
   - 新增兩個機密變數：`TELEGRAM_TOKEN` 和 `TELEGRAM_CHAT_ID`。

### 🛠️ 技術架構
- **後端**：Python 3.9, `yfinance`, `requests` (含指數退避重試機制)。
- **前端**：Tailwind CSS, 原生 JavaScript (ES6+), Local Storage API。
- **基礎設施**：GitHub Actions (定時自動化), GitHub Pages (靜態託管)。

### 📝 維護指南
S&P 500 成分股變動頻率極低。若發生指數季度調整（如剔除舊公司/加入新公司），只需在 **Actions** 標籤頁手動觸發一次 **`Build S&P 500 Cache`** 即可透過 DataHub 刷新快取庫。

### ⚖️ 免責聲明
*本工具僅供資訊參考。所有財務數據均獲取自公開來源 (Yahoo Finance & SEC)。不保證數據 100% 準確。投資決策請務必參考 SEC 官方申報文件。*
