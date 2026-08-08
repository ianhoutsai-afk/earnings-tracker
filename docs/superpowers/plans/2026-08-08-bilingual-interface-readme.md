# Bilingual Interface and README Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an English-default English/Traditional Chinese interface, revise promotional README wording into factual descriptions, document compliant controlled SEC proxy use, and add a verified English-interface screenshot.

**Architecture:** Keep the existing static single-page architecture. Move language data and pure language-state helpers into a small ES module that is imported by the existing inline frontend, allowing Node's built-in test runner to verify behavior without adding a framework. Keep application data and filters in the existing page state, and preserve expanded SEC rows when a language change triggers a synchronous table re-render.

**Tech Stack:** HTML, Tailwind CSS CDN, browser ES modules, Vanilla JavaScript, Node.js built-in test runner, Python `unittest`, local static HTTP server, browser visual QA.

## Global Constraints

- English is the first-visit and invalid-preference fallback language.
- A valid `zh-TW` choice is stored in `localStorage` and restored on refresh.
- Company names, tickers, dates, EPS, revenue data, BMO/AMC symbols, and SEC source content remain unchanged.
- Language switching does not fetch data again or reset search, sorting, watchlist, theme, or expanded SEC history state.
- No production dependency or frontend framework is added.
- Bark notification titles and bodies remain in Chinese; `notify_bark.py`, Bark workflow behavior, and Bark scheduler behavior are not modified.
- README language must be factual and must describe a controlled proxy that follows SEC Fair Access requirements, never a mechanism for bypassing SEC controls.
- The README screenshot must be captured from the completed local English interface.

---

### Task 1: Tested Language Module

**Files:**
- Create: `i18n.mjs`
- Create: `test_i18n.mjs`

**Interfaces:**
- Produces: `DEFAULT_LANGUAGE: 'en'`, `LANGUAGE_STORAGE_KEY: 'earningsTrackerLanguage'`, `translations: Record<'en' | 'zh-TW', Record<string, string>>`, `resolveLanguage(value): 'en' | 'zh-TW'`, `createTranslator(language): (key, params?) => string`, `saveLanguage(storage, language): 'en' | 'zh-TW'`, `getExpandedTickers(rows): string[]`, `restoreExpandedTickers(tickers, toggle): void`, and `createLanguageController(options)` with `initialize()` and `toggle()` methods.
- Consumes: A Web Storage-compatible object exposing `getItem` and `setItem`; array-like expanded-row objects with `id` and `classList.contains()`; controller callbacks `apply(language, translator)`, `captureExpanded()`, and `restoreExpanded(tickers)`.

- [ ] **Step 1: Write failing default, persistence, parity, interpolation, and expanded-row tests**

```js
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  DEFAULT_LANGUAGE,
  LANGUAGE_STORAGE_KEY,
  createTranslator,
  createLanguageController,
  getExpandedTickers,
  resolveLanguage,
  restoreExpandedTickers,
  saveLanguage,
  translations,
} from './i18n.mjs';

test('defaults unsupported or missing preferences to English', () => {
  assert.equal(DEFAULT_LANGUAGE, 'en');
  assert.equal(resolveLanguage(null), 'en');
  assert.equal(resolveLanguage('fr'), 'en');
});

test('restores and saves Traditional Chinese preference', () => {
  const values = new Map();
  const storage = { setItem: (key, value) => values.set(key, value) };
  assert.equal(resolveLanguage('zh-TW'), 'zh-TW');
  assert.equal(saveLanguage(storage, 'zh-TW'), 'zh-TW');
  assert.equal(values.get(LANGUAGE_STORAGE_KEY), 'zh-TW');
});

test('both languages expose the same keys', () => {
  assert.deepEqual(Object.keys(translations.en).sort(), Object.keys(translations['zh-TW']).sort());
});

test('translates representative dynamic messages with parameters', () => {
  assert.equal(createTranslator('en')('countdown.days', { count: 3 }), '3 days');
  assert.equal(createTranslator('zh-TW')('countdown.days', { count: 3 }), '倒數 3 天');
});

test('captures and restores expanded history tickers', () => {
  const rows = [
    { id: 'history-AAPL', classList: { contains: () => false } },
    { id: 'history-MSFT', classList: { contains: () => true } },
  ];
  const restored = [];
  assert.deepEqual(getExpandedTickers(rows), ['AAPL']);
  restoreExpandedTickers(['AAPL'], ticker => restored.push(ticker));
  assert.deepEqual(restored, ['AAPL']);
});

test('language controller defaults to English and preserves expanded rows when toggled', () => {
  const values = new Map();
  const applied = [];
  const restored = [];
  const storage = {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
  };
  const controller = createLanguageController({
    storage,
    apply: language => applied.push(language),
    captureExpanded: () => ['AAPL'],
    restoreExpanded: tickers => restored.push(...tickers),
  });

  assert.equal(controller.initialize(), 'en');
  assert.equal(controller.toggle(), 'zh-TW');
  assert.deepEqual(applied, ['en', 'zh-TW']);
  assert.deepEqual(restored, ['AAPL']);
  assert.equal(values.get(LANGUAGE_STORAGE_KEY), 'zh-TW');
});
```

- [ ] **Step 2: Run the test and verify the missing module causes RED**

Run: `node --test test_i18n.mjs`

Expected: FAIL because `i18n.mjs` does not exist.

- [ ] **Step 3: Implement the minimal language module and complete translation dictionary**

```js
export const DEFAULT_LANGUAGE = 'en';
export const LANGUAGE_STORAGE_KEY = 'earningsTrackerLanguage';
export const translations = {
  en: {
    'app.title': '📈 Corporate Earnings Tracker',
    'theme.toggle': 'Toggle light/dark mode',
    'language.button': '中文',
    'language.label': 'Switch to Traditional Chinese',
    'search.label': 'Search by company name or ticker',
    'search.placeholder': 'Search by company name or ticker, for example Apple or AAPL',
    'search.clear': 'Clear search',
    'search.loading': 'Loading company data...',
    'search.results': '{count} companies match “{query}”',
    'search.starred': 'Showing {count} watchlist companies',
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
    'app.title': '📈 企業財報追蹤儀表板',
    'theme.toggle': '切換日／夜模式',
    'language.button': 'EN',
    'language.label': '切換至英文',
    'search.label': '搜尋公司名稱或股票代碼',
    'search.placeholder': '搜尋公司名稱或股票代碼，例如 Apple 或 AAPL',
    'search.clear': '清除搜尋',
    'search.loading': '正在載入公司資料...',
    'search.results': '找到 {count} 家符合「{query}」的公司',
    'search.starred': '顯示 {count} 家收藏公司',
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
  return value === 'zh-TW' || value === 'en' ? value : DEFAULT_LANGUAGE;
}

export function createTranslator(language) {
  const resolved = resolveLanguage(language);
  return (key, params = {}) => Object.entries(params).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    translations[resolved][key] ?? translations[DEFAULT_LANGUAGE][key] ?? key,
  );
}

export function saveLanguage(storage, language) {
  const resolved = resolveLanguage(language);
  storage.setItem(LANGUAGE_STORAGE_KEY, resolved);
  return resolved;
}

export function getExpandedTickers(rows) {
  return Array.from(rows)
    .filter(row => !row.classList.contains('hidden'))
    .map(row => row.id.replace(/^history-/, ''));
}

export function restoreExpandedTickers(tickers, toggle) {
  tickers.forEach(ticker => toggle(ticker));
}

export function createLanguageController({ storage, apply, captureExpanded, restoreExpanded }) {
  let language = DEFAULT_LANGUAGE;
  const activate = (nextLanguage, persist) => {
    const expanded = captureExpanded();
    language = persist ? saveLanguage(storage, nextLanguage) : resolveLanguage(nextLanguage);
    apply(language, createTranslator(language));
    restoreExpanded(expanded);
    return language;
  };
  return {
    initialize: () => activate(storage.getItem(LANGUAGE_STORAGE_KEY), false),
    toggle: () => activate(language === 'en' ? 'zh-TW' : 'en', true),
  };
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `node --test test_i18n.mjs`

Expected: all language-module tests pass.

- [ ] **Step 5: Commit the tested language module**

```bash
git add i18n.mjs test_i18n.mjs
git commit -m "feat: add bilingual interface translations"
```

### Task 2: Integrate English-Default Language Switching

**Files:**
- Modify: `index.html`

**Interfaces:**
- Consumes: `createLanguageController`, `getExpandedTickers`, and `restoreExpandedTickers` from `i18n.mjs` defined in Task 1.
- Produces: translated DOM attributes through `data-i18n`, `data-i18n-placeholder`, and `data-i18n-aria-label`, plus an `#language-toggle` button wired to the tested controller.

- [ ] **Step 1: Convert the page to an ES module and translate static nodes**

```html
<html lang="en">
<!-- ... -->
<button id="language-toggle" type="button" aria-label="Switch to Traditional Chinese">中文</button>
<h1 data-i18n="app.title">📈 Corporate Earnings Tracker</h1>
<input data-i18n-placeholder="search.placeholder" placeholder="Search by company name or ticker, for example Apple or AAPL">
<script type="module">
  import {
    createLanguageController,
    getExpandedTickers,
    restoreExpandedTickers,
  } from './i18n.mjs';
</script>
```

- [ ] **Step 2: Wire the tested controller and route dynamic strings through its translator**

```js
let currentLanguage = 'en';
let t;

function applyStaticTranslations() {
  document.documentElement.lang = currentLanguage;
  document.querySelectorAll('[data-i18n]').forEach(node => {
    node.textContent = t(node.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(node => {
    node.placeholder = t(node.dataset.i18nPlaceholder);
  });
  document.querySelectorAll('[data-i18n-aria-label]').forEach(node => {
    node.setAttribute('aria-label', t(node.dataset.i18nAriaLabel));
  });
}

const languageController = createLanguageController({
  storage: localStorage,
  captureExpanded: () => getExpandedTickers(document.querySelectorAll('.expand-row')),
  apply: (language, translator) => {
    currentLanguage = language;
    t = translator;
    applyStaticTranslations();
    updateLanguageToggle();
    if (appData.length > 0) applySort();
  },
  restoreExpanded: tickers => restoreExpandedTickers(tickers, ticker => window.toggleHistory(ticker)),
});
```

Use these exact dynamic substitutions:

```js
// Countdown: t('countdown.today'), t('countdown.days', { count: countdown }),
// and t('countdown.published').
// Search status: t('search.results', { count: resultCount, query: searchQuery }),
// t('search.starred', { count: resultCount }), or t('search.all', { count: resultCount }).
// Empty table: t('empty.searchTitle', { query: escapeHtml(searchQuery) }) with
// t('empty.searchHint'), otherwise t('empty.filteredTitle') with t('empty.filterHint').
// SEC history: t('sec.view'), t('sec.noData'), t('sec.annual'), t('sec.quarterly'),
// t('sec.revenue'), t('sec.original'), t('sec.pending'), and t('sec.noOriginal').
// Failures: t('data.error') in the table and console.warn(t('data.historyWarning')).

document.getElementById('language-toggle').addEventListener('click', () => {
  languageController.toggle();
});

document.addEventListener('DOMContentLoaded', () => {
  languageController.initialize();
  init();
});
```

- [ ] **Step 3: Run the language behavior tests and verify GREEN after integration**

Run: `node --test test_i18n.mjs`

Expected: all bilingual language and state-preservation tests pass.

- [ ] **Step 4: Run existing tests to detect unrelated regressions and confirm Bark stays Chinese**

Run: `python3 -m unittest test_update_data.py && node --test test_bark_scheduler_worker.mjs`

Expected: all existing Python and Node tests pass.

- [ ] **Step 5: Commit the integrated interface**

```bash
git add index.html
git commit -m "feat: add English and Chinese interface toggle"
```

### Task 3: Objective README Copy and Compliance Contract

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: An English-first README introduction, `Project Motivation`, controlled-proxy/Fair Access wording in both language sections, and the image reference `docs/images/earnings-tracker-en.png`.
- Consumes: The final screenshot path produced by Task 4.

- [ ] **Step 1: Rewrite README claims and SEC instructions**

Use this factual opening and motivation statement, then align both language sections with the same claims:

```markdown
This personal project tracks expected earnings dates, BMO/AMC timing, and recent SEC 10-Q and 10-K filings for companies in the S&P 500.

![English interface](docs/images/earnings-tracker-en.png)

## Project Motivation

I independently defined the product requirements for this personal project and used AI-assisted development to help implement and review parts of the code. I personally test the workflows, validate the output, and maintain the project as its requirements and data sources evolve.
```

Rename the SEC section to `Controlled SEC Proxy and Fair Access` / `受控 SEC 代理與 Fair Access`, explain token restriction and identifying contact information, and remove all bypass/circumvention wording.

- [ ] **Step 2: Validate the required README content and prohibited wording**

Run: `rg -n -i "institutional-grade|pro-grade|zero lag|繞過 sec|bypass.*sec" README.md; rg -n "Project Motivation|AI-assisted|personally test|SEC Fair Access|受控代理|docs/images/earnings-tracker-en.png" README.md`

Expected: the prohibited-wording search returns no matches; the required-content search finds the motivation, Fair Access, controlled-proxy, and screenshot-reference lines.

- [ ] **Step 3: Commit objective documentation text**

```bash
git add README.md
git commit -m "docs: revise project description and SEC guidance"
```

### Task 4: Browser QA, English Screenshot, and Full Verification

**Files:**
- Create: `docs/images/earnings-tracker-en.png`
- Modify only if QA finds a failing acceptance criterion: `index.html`, `i18n.mjs`, `test_i18n.mjs`, or `README.md`.

**Interfaces:**
- Consumes: completed English-default interface and README screenshot reference.
- Produces: a real English desktop screenshot and verification evidence for both language states and responsive layouts.

- [ ] **Step 1: Start the repository through a local static HTTP server**

Run: `python3 -m http.server 8000`

Expected: the site is available at `http://127.0.0.1:8000/` and `data.json`, `historical_data.json`, and `i18n.mjs` load successfully.

- [ ] **Step 2: Verify the English desktop interface in a browser**

Open a clean browser context at `http://127.0.0.1:8000/`. Confirm the page language is `en`, visible controls and statuses are English, search and sort work, and expanding an SEC row then switching languages preserves the expanded row.

- [ ] **Step 3: Verify Traditional Chinese and persistence**

Switch to Traditional Chinese, refresh, and confirm `zh-TW` persists. Confirm search, sort, watchlist filtering, theme, dynamic countdown/status text, and SEC history text are Traditional Chinese. Switch back to English before capture.

- [ ] **Step 4: Verify mobile layout**

At a mobile viewport near 390 by 844 pixels, inspect both languages for clipped controls, inaccessible actions, horizontal page overflow, or untranslated application text.

- [ ] **Step 5: Capture the verified English desktop screenshot**

At a desktop viewport near 1440 by 1000 pixels with English active, capture the page to `docs/images/earnings-tracker-en.png`. Confirm the image is readable and does not expose browser chrome, local paths, secrets, or debugging overlays.

- [ ] **Step 6: Run complete automated verification**

Run: `python3 -m unittest test_update_data.py && node --test test_bark_scheduler_worker.mjs test_i18n.mjs && git diff --check`

Expected: all tests pass, no failures are reported, and `git diff --check` exits successfully.

- [ ] **Step 7: Inspect the final change set against every acceptance criterion**

Run: `git status --short && git diff --stat HEAD~3 && rg -n -i "institutional-grade|pro-grade|zero lag|繞過 sec|bypass.*sec" README.md`

Expected: only the planned files are changed or newly added; the search for prohibited README phrases returns no matches.

- [ ] **Step 8: Commit the verified screenshot and any QA corrections**

```bash
git add docs/images/earnings-tracker-en.png index.html i18n.mjs test_i18n.mjs README.md
git commit -m "docs: add verified English interface screenshot"
```
