export const DEFAULT_LANGUAGE = 'en';
export const LANGUAGE_STORAGE_KEY = 'earningsTrackerLanguage';

export const translations = {
  en: {
    'page.title': 'S&P 500 Earnings Tracker',
    'app.title': 'S&P 500 Earnings Tracker',
    'theme.toggle': 'Toggle light/dark mode',
    'language.button': '中文',
    'language.label': 'Switch to Traditional Chinese',
    'search.label': 'Search by company name or ticker',
    'search.placeholder': 'Search by company name or ticker, for example Apple or AAPL',
    'search.clear': 'Clear search',
    'search.loading': 'Loading company data...',
    'search.resultOne': '1 company matches “{query}”',
    'search.results': '{count} companies match “{query}”',
    'search.starredOne': 'Showing 1 watchlist company',
    'search.starred': 'Showing {count} watchlist companies',
    'search.allOne': 'Showing 1 company',
    'search.all': 'Showing all {count} companies',
    'sort.label': 'Sort by:',
    'sort.countdownAsc': 'Report date (nearest first)',
    'sort.countdownDesc': 'Report date (farthest first)',
    'sort.alphaAsc': 'Ticker (A–Z)',
    'sort.alphaDesc': 'Ticker (Z–A)',
    'filter.onlyFavorites': '⭐ Watchlist only',
    'filter.showAll': '⭐ Show all',
    'table.watch': 'Watch',
    'table.company': 'Company',
    'table.reportDate': 'Next earnings event (New York)',
    'table.dateTba': 'To be announced',
    'table.thirdPartyEstimate': 'Third-party date estimate',
    'table.officialDate': 'Company announcement',
    'table.eps': 'Estimated EPS',
    'table.revenue': 'Estimated revenue',
    'table.sec': 'SEC filings',
    'table.loading': 'Loading data...',
    'countdown.today': 'Event today',
    'countdown.day': '1 day',
    'countdown.days': '{count} days',
    'countdown.published': 'Published',
    'empty.searchTitle': 'No companies match “{query}”',
    'empty.filteredTitle': 'No companies match the current filters',
    'empty.searchHint': 'Check the company name or ticker, or try a shorter query.',
    'empty.filterHint': 'Adjust the current filter settings.',
    'sec.view': 'View',
    'sec.noData': 'No data',
    'sec.annual': '10-K annual report',
    'sec.quarterly': '10-Q quarterly report',
    'sec.revenue': 'Revenue',
    'sec.original': '🏛️ View SEC filing',
    'sec.pending': 'Awaiting SEC filing',
    'sec.noOriginal': 'Filing unavailable',
    'earnings.officialRelease': 'Official earnings release',
    'earnings.releaseSource': 'View earnings release',
    'earnings.metricSource': 'View financial statements',
    'earnings.gaapQuarterEps': 'Quarterly GAAP diluted EPS',
    'earnings.legacyEps': 'EPS (basis unverified)',
    'earnings.periodEnd': 'Quarter ended {date}',
    'earnings.pendingOfficial': 'Latest stored quarter awaits official verification',
    'earnings.discoveryFailed': 'Latest-quarter check unavailable',
    'earnings.notScanned': 'Latest-quarter check pending',
    'earnings.noNewCandidate': 'No newer quarter found in latest check',
    'earnings.verified': 'Latest found quarter officially verified',
    'earnings.officialNewer': 'Official release is newer than the latest Yahoo candidate',
    'earnings.verifiedScanPending': 'Official quarter verified; latest scan pending',
    'history.fiscalQuarter': '{quarter} (company fiscal year)',
    'history.legacyQuarter': '{quarter} · fiscal identity unverified',
    'history.released': 'Released {date}',
    'history.legacyDate': 'Legacy date {date} · release date unverified',
    'history.filed': 'SEC filed {date}',
    'history.latest': 'Latest verified release: {quarter} · {date}',
    'history.latestUnverified': 'Latest stored record: {date} · official check pending',
    'history.note': 'Up to five quarters, newest first. FY denotes company fiscal year. Unverified records do not establish complete latest-quarter coverage.',
    'history.renamedTicker':'Historical ticker · current official ticker: {tickers}',
    'history.tickerUnconfirmed':'Current ticker confirmation pending; future estimate withheld',
    'history.epsSource':'EPS source',
    'history.revenueSource':'Revenue source',
    'history.quarterRevenue': 'Quarterly revenue',
    'history.metricsPending': 'Quarterly GAAP figures await official verification',
    'history.estimatePending': 'Next-quarter estimate unavailable',
    'history.officialCall': 'Official earnings call · release date not confirmed',
    'history.nextTba': 'Next earnings date not yet confirmed',
    'history.secLinkPending': 'SEC filing link pending',
    'history.sourceChecked': 'Official sources checked; see each record for verification status',
    'history.lastChecked': 'Last official check attempted: {time}',
    'history.checkDeferred':'Official check queued for retry · stored history retained',
    'history.sourceFailed': 'Official source unavailable · stored history retained',
    'history.parsePending': 'Official source found · release or metric verification pending',
    'history.mappingMissing': 'Official company identifier unavailable · verification pending',
    'history.short': 'Only {count} records available; {missing} of five still missing',
    'history.health': '{count} companies · {verified} officially verified quarters · {failed} companies with source errors · {pending} companies pending verification',
    'nvda.fiscalQuarter': '{quarter} (company fiscal year)',
    'nvda.released': 'Released {date}',
    'nvda.latest': 'Latest published: {quarter} · {date}',
    'nvda.historyNote': 'Latest five published quarters, newest first. FY denotes the company fiscal year; dates below are release dates.',
    'nvda.quarterRevenue': 'Quarterly revenue',
    'nvda.estimatePending': 'Next-quarter estimate unavailable',
    'nvda.officialCall': 'Official earnings call · release date not confirmed',
    'nvda.nextTba': 'Next release date not yet announced',
    'nvda.secLinkPending': 'SEC filing link pending',
    'nvda.sourceChecked': 'Official NVIDIA sources checked',
    'nvda.lastChecked': 'Last official source check: {time}',
    'data.error': 'Unable to load data. Refresh the page to try again.',
    'data.historyWarning': 'historical_data.json failed to load; filing history is unavailable.',
  },
  'zh-TW': {
    'page.title': 'S&P 500 財報追蹤器',
    'app.title': 'S&P 500 Earnings Tracker',
    'theme.toggle': '切換日／夜模式',
    'language.button': 'EN',
    'language.label': '切換至英文',
    'search.label': '搜尋公司名稱或股票代碼',
    'search.placeholder': '搜尋公司名稱或股票代碼，例如 Apple 或 AAPL',
    'search.clear': '清除搜尋',
    'search.loading': '正在載入公司資料...',
    'search.resultOne': '找到 1 家符合「{query}」的公司',
    'search.results': '找到 {count} 家符合「{query}」的公司',
    'search.starredOne': '顯示 1 家收藏公司',
    'search.starred': '顯示 {count} 家收藏公司',
    'search.allOne': '顯示 1 家公司',
    'search.all': '顯示全部 {count} 家公司',
    'sort.label': '排序方式：',
    'sort.countdownAsc': '發布日倒數（由近到遠）',
    'sort.countdownDesc': '發布日倒數（由遠到近）',
    'sort.alphaAsc': '公司代碼（A–Z）',
    'sort.alphaDesc': '公司代碼（Z–A）',
    'filter.onlyFavorites': '⭐ 只顯示收藏',
    'filter.showAll': '⭐ 顯示全部',
    'table.watch': '關注',
    'table.company': '公司名稱',
    'table.reportDate': '下一次業績事件（美東）',
    'table.dateTba': '待公布',
    'table.thirdPartyEstimate': '第三方日期預估',
    'table.officialDate': '公司公告',
    'table.eps': '預期 EPS',
    'table.revenue': '預估營收',
    'table.sec': 'SEC 財報',
    'table.loading': '正在載入數據...',
    'countdown.today': '今日業績事件',
    'countdown.day': '倒數 1 天',
    'countdown.days': '倒數 {count} 天',
    'countdown.published': '已發布',
    'empty.searchTitle': '找不到符合「{query}」的公司',
    'empty.filteredTitle': '目前沒有符合條件的公司',
    'empty.searchHint': '請確認公司名稱或股票代碼，或嘗試較短的關鍵字。',
    'empty.filterHint': '請調整目前的篩選條件。',
    'sec.view': '查看',
    'sec.noData': '暫無資料',
    'sec.annual': '10-K 年報',
    'sec.quarterly': '10-Q 季報',
    'sec.revenue': '營收',
    'sec.original': '🏛️ SEC 原文',
    'sec.pending': '等待 SEC 申報',
    'sec.noOriginal': '暫無原文',
    'earnings.officialRelease': '公司官方業績公告',
    'earnings.releaseSource': '查看業績公告',
    'earnings.metricSource': '查看官方財務報表',
    'earnings.gaapQuarterEps': '季度 GAAP 稀釋 EPS',
    'earnings.legacyEps': 'EPS（口徑未核實）',
    'earnings.periodEnd': '季度截止日：{date}',
    'earnings.pendingOfficial': '最近儲存的季度等待官方核對',
    'earnings.discoveryFailed': '最新季度檢查暫時失敗',
    'earnings.notScanned': '等待檢查最新季度',
    'earnings.noNewCandidate': '最近檢查未發現較新季度',
    'earnings.verified': '已發現的最新季度經官方核對',
    'earnings.officialNewer': '官方業績公告比 Yahoo 最近線索更新',
    'earnings.verifiedScanPending': '已有官方核對季度；等待下次最新季度掃描',
    'history.fiscalQuarter': '{quarter}（公司財年）',
    'history.legacyQuarter': '{quarter} · 財年季度待核實',
    'history.released': '財報公布日：{date}',
    'history.legacyDate': '舊紀錄日期：{date} · 公布日待核實',
    'history.filed': 'SEC 申報日：{date}',
    'history.latest': '最近官方已核實：{quarter} · {date}',
    'history.latestUnverified': '最近儲存紀錄：{date} · 等待官方核對',
    'history.note': '最多保留五季，最新在前。FY 代表公司財年；待核實紀錄不代表已取得最新完整資料。',
    'history.renamedTicker':'歷史股票代碼 · 官方現行代碼：{tickers}',
    'history.tickerUnconfirmed':'交易代碼待確認；暫不顯示下次日期預估',
    'history.epsSource':'EPS 來源',
    'history.revenueSource':'營收來源',
    'history.quarterRevenue': '季度營收',
    'history.metricsPending': '季度 GAAP 數值等待官方核實',
    'history.estimatePending': '下一季預估待取得',
    'history.officialCall': '官方業績電話會議 · 財報公布日待確認',
    'history.nextTba': '下次業績日期尚未核實',
    'history.secLinkPending': 'SEC 文件連結待取得',
    'history.sourceChecked': '已檢查官方來源；各筆核實狀態見下方',
    'history.lastChecked': '上次嘗試官方核對：{time}',
    'history.checkDeferred':'官方檢查排隊待重試 · 已保留原紀錄',
    'history.sourceFailed': '官方來源暫時無法取得 · 已保留原紀錄',
    'history.parsePending': '已發現官方來源 · 公布日或數值仍待核實',
    'history.mappingMissing': '缺少官方公司識別碼 · 等待核對',
    'history.short': '目前只有 {count} 筆紀錄，距五筆尚缺 {missing} 筆',
    'history.health': '{count} 家公司 · {verified} 個官方核實季度 · {failed} 家官方來源異常 · {pending} 家待補核實',
    'nvda.fiscalQuarter': '{quarter}（公司財年）',
    'nvda.released': '財報公布日：{date}',
    'nvda.latest': '最新已公布：{quarter} · {date}',
    'nvda.historyNote': '最近五個已公布季度，最新在前。FY 代表公司財年；下方日期為財報公布日。',
    'nvda.quarterRevenue': '季度營收',
    'nvda.estimatePending': '下一季預估待取得',
    'nvda.officialCall': '官方業績電話會議 · 財報公布日待確認',
    'nvda.nextTba': '尚未公告下次財報日期',
    'nvda.secLinkPending': 'SEC 文件連結待取得',
    'nvda.sourceChecked': '已檢查 NVIDIA 官方來源',
    'nvda.lastChecked': '上次官方來源核對：{time}',
    'data.error': '無法載入資料，請重新整理頁面',
    'data.historyWarning': 'historical_data.json 載入失敗，歷史財報面板將無法顯示',
  },
};

export function historyFilingKey(item) {
  if (item.form === '10-K') return 'sec.annual';
  if (item.form === '10-Q') return 'sec.quarterly';
  if (item.verificationStatus === 'official_verified') return 'earnings.officialRelease';
  return (item.quarter || '').includes('FY') ? 'sec.annual' : 'sec.quarterly';
}

export function earningsMetricLabelKey(item) {
  return item.periodScope === 'quarter' && item.epsBasis === 'GAAP diluted'
    ? 'earnings.gaapQuarterEps'
    : 'earnings.legacyEps';
}

export function historyStatusKey(item) {
  const status = item?.status;
  if (status === 'official_source_checked') return 'history.sourceChecked';
  if (status === 'official_check_deferred') return 'history.checkDeferred';
  if (status === 'official_source_failed') return 'history.sourceFailed';
  if (status === 'official_parse_pending') return 'history.parsePending';
  if (status === 'official_mapping_missing') return 'history.mappingMissing';
  if (status === 'pending_official') return 'earnings.pendingOfficial';
  if (status === 'discovery_failed') return 'earnings.discoveryFailed';
  if (status === 'no_new_candidate') return 'earnings.noNewCandidate';
  if (status === 'verified_to_latest_candidate') return 'earnings.verified';
  if (status === 'official_newer_than_discovery') return 'earnings.officialNewer';
  if (status === 'official_verified_scan_pending') return 'earnings.verifiedScanPending';
  return 'earnings.notScanned';
}

export function resolveLanguage(value) {
  return value === 'en' || value === 'zh-TW' ? value : DEFAULT_LANGUAGE;
}

export function createTranslator(language) {
  const resolvedLanguage = resolveLanguage(language);

  return (key, params = {}) => Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    translations[resolvedLanguage][key]
      ?? translations[DEFAULT_LANGUAGE][key]
      ?? key,
  );
}

export function saveLanguage(storage, language) {
  const resolvedLanguage = resolveLanguage(language);
  storage.setItem(LANGUAGE_STORAGE_KEY, resolvedLanguage);
  return resolvedLanguage;
}

export function getExpandedTickers(rows) {
  return Array.from(rows)
    .filter(row => !row.classList.contains('hidden'))
    .map(row => row.id.replace(/^history-/, ''));
}

export function restoreExpandedTickers(tickers, toggle) {
  tickers.forEach(ticker => toggle(ticker));
}

export function createLanguageController({
  storage,
  apply,
  captureExpanded,
  restoreExpanded,
}) {
  let language = DEFAULT_LANGUAGE;

  const activate = (nextLanguage, persist) => {
    const expandedTickers = captureExpanded();
    language = persist
      ? saveLanguage(storage, nextLanguage)
      : resolveLanguage(nextLanguage);
    apply(language, createTranslator(language));
    restoreExpanded(expandedTickers);
    return language;
  };

  return {
    initialize() {
      return activate(storage.getItem(LANGUAGE_STORAGE_KEY), false);
    },
    toggle() {
      return activate(language === 'en' ? 'zh-TW' : 'en', true);
    },
  };
}
