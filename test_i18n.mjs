import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_LANGUAGE,
  LANGUAGE_STORAGE_KEY,
  createLanguageController,
  createTranslator,
  getExpandedTickers,
  historyFilingKey,
  historyStatusKey,
  earningsMetricLabelKey,
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

test('restores and saves a valid Traditional Chinese preference', () => {
  const values = new Map();
  const storage = {
    setItem(key, value) {
      values.set(key, value);
    },
  };

  assert.equal(resolveLanguage('zh-TW'), 'zh-TW');
  assert.equal(saveLanguage(storage, 'zh-TW'), 'zh-TW');
  assert.equal(values.get(LANGUAGE_STORAGE_KEY), 'zh-TW');
});

test('both languages expose the same translation keys', () => {
  assert.deepEqual(
    Object.keys(translations.en).sort(),
    Object.keys(translations['zh-TW']).sort(),
  );
});

test('reviewed quarterly metrics remain quarterly when linked to an annual filing', () => {
  assert.equal(historyFilingKey({ form: '10-K', periodScope: 'quarter' }), 'sec.annual');
  assert.equal(earningsMetricLabelKey({ form: '10-K', periodScope: 'quarter', epsBasis: 'GAAP diluted' }), 'earnings.gaapQuarterEps');
  assert.equal(historyFilingKey({ verificationStatus: 'official_verified' }), 'earnings.officialRelease');
  assert.equal(earningsMetricLabelKey({ quarter: '2025 FY' }), 'earnings.legacyEps');
  assert.equal(historyStatusKey({ status: 'pending_official' }), 'earnings.pendingOfficial');
  assert.equal(historyStatusKey({ status: 'official_newer_than_discovery' }), 'earnings.officialNewer');
  assert.equal(historyStatusKey({ status: 'official_verified_scan_pending' }), 'earnings.verifiedScanPending');
});

test('translates representative dynamic messages with parameters', () => {
  assert.equal(
    createTranslator('en')('app.title'),
    'S&P 500 Earnings Tracker',
  );
  assert.equal(
    createTranslator('zh-TW')('app.title'),
    'S&P 500 Earnings Tracker',
  );
  assert.equal(
    createTranslator('en')('countdown.days', { count: 3 }),
    '3 days',
  );
  assert.equal(
    createTranslator('zh-TW')('countdown.days', { count: 3 }),
    '倒數 3 天',
  );
  assert.equal(
    createTranslator('en')('search.results', { count: 2, query: 'Apple' }),
    '2 companies match “Apple”',
  );
  assert.equal(createTranslator('en')('table.dateTba'), 'To be announced');
  assert.equal(createTranslator('zh-TW')('table.dateTba'), '待公布');
  assert.equal(createTranslator('zh-TW')('table.thirdPartyEstimate'), '第三方日期預估');
});

test('captures and restores expanded history tickers', () => {
  const rows = [
    {
      id: 'history-AAPL',
      classList: { contains: className => className === 'hidden' ? false : false },
    },
    {
      id: 'history-MSFT',
      classList: { contains: className => className === 'hidden' },
    },
  ];
  const restored = [];

  assert.deepEqual(getExpandedTickers(rows), ['AAPL']);
  restoreExpandedTickers(['AAPL'], ticker => restored.push(ticker));
  assert.deepEqual(restored, ['AAPL']);
});

test('controller defaults to English and preserves expanded rows when toggled', () => {
  const values = new Map();
  const applied = [];
  const restored = [];
  const storage = {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, value);
    },
  };
  const controller = createLanguageController({
    storage,
    apply(language) {
      applied.push(language);
    },
    captureExpanded() {
      return ['AAPL'];
    },
    restoreExpanded(tickers) {
      restored.push(...tickers);
    },
  });

  assert.equal(controller.initialize(), 'en');
  assert.equal(controller.toggle(), 'zh-TW');
  assert.deepEqual(applied, ['en', 'zh-TW']);
  assert.deepEqual(restored, ['AAPL', 'AAPL']);
  assert.equal(values.get(LANGUAGE_STORAGE_KEY), 'zh-TW');
});

test('controller restores a saved Traditional Chinese preference', () => {
  const applied = [];
  const storage = {
    getItem() {
      return 'zh-TW';
    },
    setItem() {},
  };
  const controller = createLanguageController({
    storage,
    apply(language) {
      applied.push(language);
    },
    captureExpanded() {
      return [];
    },
    restoreExpanded() {},
  });

  assert.equal(controller.initialize(), 'zh-TW');
  assert.deepEqual(applied, ['zh-TW']);
});
