# 最新季度財報補錄：首批核對紀錄

核查基準：2026-09-29（美東時間）。本報告的單位是 **503 個股票代碼**，不等於 503 個不同法人：GOOG／GOOGL、FOXA／FOX、NWSA／NWS 分別是同一發行人的不同股票類別。本批新增 9 個代碼、8 個發行人的季度紀錄。官方公告日期是業績**公布日**；季度截止日與 SEC 申報日是另外兩個欄位，不互相替代。

## 已核對並補入網站資料

所有金額均為美元；營收以百萬美元列示。表中 EPS 是當季 GAAP 稀釋每股收益，不是 Yahoo `Reported EPS` 或全年 EPS。新紀錄的核對日是 2026-09-29，完整來源及原始整數金額見 [`official_history.json`](../official_history.json)。

| 股票代碼 | 網站原最新日期（未重核） | 新公布日 | 財季／截止日 | GAAP 稀釋 EPS | 季度營收（百萬美元） | 官方依據 |
| --- | --- | --- | --- | ---: | ---: | --- |
| AAPL | 2026-04-30 | 2026-07-30 | FY2026 Q3／2026-06-27 | 2.02 | 109,417 | [Apple 公告](https://www.apple.com/newsroom/2026/07/apple-reports-third-quarter-results/)、[財務報表](https://www.apple.com/newsroom/pdfs/fy2026q3/FY26_Q3_Consolidated_Financial_Statements.pdf) |
| MSFT | 2026-04-29 | 2026-07-29 | FY2026 Q4／2026-06-30 | 4.81 | 90,007 | [Microsoft 公告及 GAAP 對照表](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast) |
| NVDA | 2026-05-20 | 2026-08-26 | FY2027 Q2／2026-07-26 | 2.46 | 96,221 | [NVIDIA 公告](https://investor.nvidia.com/news/press-release-details/2026/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2027/) |
| CPB | 2026-06-08 | 2026-09-03 | FY2026 Q4／2026-08-02 | -0.23 | 2,137 | [Campbell's 公告及 GAAP 對照表](https://investor.thecampbellscompany.com/news-releases/news-release-details/campbells-reports-fourth-quarter-fiscal-2026-results) |
| AMZN | 2026-04-29 | 2026-07-30 | FY2026 Q2／2026-06-30 | 5.75 | 200,606 | [Amazon 公告及損益表](https://ir.aboutamazon.com/news-release/news-release-details/2026/Amazon-com-Announces-Second-Quarter-Results/default.aspx?mode=light) |
| META | 2026-04-29 | 2026-07-29 | FY2026 Q2／2026-06-30 | 6.18 | 60,801 | [Meta 公告及損益表](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Second-Quarter-2026-Results/) |
| TSLA | 2026-04-22 | 2026-07-22 | FY2026 Q2／2026-06-30 | 0.32 | 28,236 | [Tesla 公告](https://ir.tesla.com/press-release/tesla-releases-second-quarter-2026-financial-results)、[8-K 附件](https://ir.tesla.com/_flysystem/s3/sec/000162828026049213/tsla-20260722-gen.pdf) |
| GOOG | 2026-04-29 | 2026-07-22 | FY2026 Q2／2026-06-30 | 9.11 | 119,796 | [Alphabet 8-K 業績附件](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm) |
| GOOGL | 2026-04-29 | 2026-07-22 | FY2026 Q2／2026-06-30 | 9.11 | 119,796 | [Alphabet 8-K 業績附件](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm) |

容易誤讀的差異：Microsoft 的 GAAP EPS 是 4.81，公告另列非 GAAP 4.74；NVIDIA 的 GAAP EPS 是 2.46，非 GAAP 2.22；Campbell's 的 GAAP EPS 是虧損 0.23，調整後 EPS 為正。Amazon 的 GAAP EPS 包含主要與 Anthropic 投資有關的 534 億美元營業外稅前收益；Alphabet 的 GAAP EPS 包含 980 億美元股權證券未實現淨收益。網站對後兩者另外顯示註記。這些差異說明不能直接把 Yahoo 候選 EPS 寫為 GAAP EPS。

## 涵蓋範圍與未完成事項

`history_status.json` 按 503 個代碼記錄掃描狀態、原因、最近儲存的公布日與檢查時間。`pending_official` 表示 Yahoo 提示較新日期但還沒有完成官方數值核對；`discovery_failed` 表示該次候選掃描不可用；`no_new_candidate` 只代表 Yahoo 沒提供較新線索，**不是**官方確認為最新；`verified_to_latest_candidate` 表示掃描所見最近日期已由官方紀錄覆蓋。若狀態是 `official_verified_scan_pending`，表示已有官方紀錄，但仍需下次候選掃描確認是否存在更晚的季度。`latestStoredOfficial` 只描述最近儲存那一筆是否有官方來源，不代表全部歷史紀錄都已驗證。

本批狀態採用 2026-09-29 UTC 14:27–15:01 已完成的 503 代碼唯讀試抓，僅從工作區的試抓結果取公布日線索；Yahoo EPS／營收數值沒有寫入網站。後續重試未完成全量掃描，因此不納入覆蓋率。已完成試抓對應的狀態是：**9／503（1.8%）最近季度經官方核對；488／503（97.0%）有較新線索、待官方核對；4／503（0.8%）沒有可用的 Yahoo 已公布 EPS 日期；2／503（0.4%）沒有較新線索**。後兩類都不計入官方確認。4 個掃描不可用的代碼是 AVB、SATS、EA、EQR；未發現較新線索的是 JBL、L，其中 L 的網站舊紀錄仍停留在 2020-02-10，尤其需要另找官方資料，不可視為已更新。

補錄後 `historical_data.json` 有 2,520 筆歷史紀錄，比本批前多 9 筆；503 個代碼均有逐筆狀態。資料更新覆蓋率（已有新增季度）與官方確認率均為 9／503；Yahoo 發現線索的 497／503 不是官方核對率。新紀錄的 9 筆 EPS、營收、公布日及季度截止日均有官方來源；其餘代碼的最新季度數值尚未核對。

本批只核對新增季度；原有 2,511 筆歷史紀錄的 EPS／營收及其口徑未逐筆重算，網站已將其 EPS 標作「口徑未核實」。首頁既有的「預期 EPS／預估營收」仍屬舊流程的預測欄位，本批沒有把它們當成已公布的季度實績，也沒有全面核對其數值。已過期的下次預計發布日會清空，不能從舊日期推斷下一次財報。SEC 的 10-Q／10-K 連結若暫時無法取得，已核對的公司業績公告仍可補入，但 SEC 連結會保持待驗證或缺席。

下次財報日期與已公布季度實績分開處理。Yahoo 的未來日期僅以「第三方日期預估」顯示，可在之後的每日全量掃描中修訂；Yahoo 所稱盤前／盤後不直接顯示。首次發布時 502 個代碼沒有仍在未來的已確認日期，會顯示「待公布」，待後續日期掃描補上明確標示的預估值。唯一在本批找到公司公告支持的未來日期是 ACN 的 2026-10-01，Accenture 說明業績新聞稿會在美東上午 8 時的電話會議前發布，因此可標記為盤前並附上[公司公告](https://newsroom.accenture.com/news/2026/accenture-to-announce-fourth-quarter-and-full-year-fiscal-2026-results)。第三方預估與官方確認日期不可合併計入同一確認率。

本次核查發現 `sp500_mapping.json` 有 5 個目前追蹤代碼缺少 CIK 映射：CPB、CAG、SATS、EPAM、POOL。這不妨礙核對公司公告，但會妨礙自動配對 SEC 文件；需要另行補齊並校對映射。

## 交付檢查

本地驗證：與最新版 `main` 整合並修正獨立程式審查發現的問題後，50 個 Python 測試、8 個前端模組測試通過；桌面 1440×900 與手機 390×844 的瀏覽器檢查均載入 503 行，搜尋、代碼倒序、收藏篩選、歷史展開、中英文切換、負 EPS、Alphabet 特別註記和官方來源連結正常，沒有頁面程式錯誤或本機資料請求失敗。另以瀏覽器測試資料驗證第三方預估日期的中英文標籤及 ACN 官方日期來源連結，桌面和手機均通過。

最終合併與部署核對時，應以 GitHub Pages 實際載入的 `data.json`、`historical_data.json` 和 `history_status.json` 與已審核資料逐項比對；GitHub Actions 顯示成功本身不足以證明內容更新。網站只會逐批增加官方核對通過的季度，因此這份首批報告不表示 503 個代碼都已補齊。
