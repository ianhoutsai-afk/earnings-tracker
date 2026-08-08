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
    'table.reportDate': 'Expected report date',
    'table.eps': 'Estimated EPS',
    'table.revenue': 'Estimated revenue',
    'table.sec': 'SEC filings',
    'table.loading': 'Loading data...',
    'countdown.today': 'Reports today!',
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
    'table.reportDate': '預計發布日',
    'table.eps': '預期 EPS',
    'table.revenue': '預估營收',
    'table.sec': 'SEC 財報',
    'table.loading': '正在載入數據...',
    'countdown.today': '今日發布！',
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
    'data.error': '無法載入資料，請重新整理頁面',
    'data.historyWarning': 'historical_data.json 載入失敗，歷史財報面板將無法顯示',
  },
};

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
