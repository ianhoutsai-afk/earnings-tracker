import unittest
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pandas as pd

from notify_bark import (
    companies_reporting_on,
    format_notification,
    format_test_notification,
    get_local_date,
    send_bark_notification,
)

from update_data import (
    apply_sec_matches,
    audit_sec_dataset,
    extract_sec_filing_data,
    fetch_earnings_data,
    update_data,
    match_history_to_filings,
    migrate_ticker_aliases,
    quarter_labels_from_match_sequence,
    validate_sec_matches,
)


class FutureEarningsDateTests(unittest.TestCase):
    def test_no_upcoming_company_is_a_successful_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST', 'reportDate': None}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': []}, handle)
                self.assertTrue(update_data())
            finally:
                os.chdir(previous)

    def test_expired_yahoo_row_is_not_used_as_next_report_date(self):
        eastern_today = datetime.now(ZoneInfo('America/New_York')).date()
        yesterday = eastern_today - timedelta(days=1)
        next_week = eastern_today + timedelta(days=7)
        frame = pd.DataFrame(
            {'Earnings Time': ['After market close', 'Before market open']},
            index=pd.to_datetime([yesterday.isoformat(), next_week.isoformat()]),
        )
        stock = type('Stock', (), {'info': {}, 'earnings_dates': frame})()
        with patch('update_data.yf') as finance:
            finance.Ticker.return_value = stock
            result = fetch_earnings_data('TEST', retries=0)
        self.assertEqual(result['reportDate'], next_week.isoformat())
        self.assertEqual(result['bmo_amc'], '☀️')

    def test_updater_preserves_date_provenance_and_does_not_publish_yahoo_timing(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                future = (datetime.now(ZoneInfo('America/New_York')).date() + timedelta(days=5)).isoformat()
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST', 'name': 'Test', 'reportDate': future,
                                'reportDateSource': 'third_party_estimate', 'bmo_amc': '🌙'}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': []}, handle)
                with patch('update_data.fetch_earnings_data', return_value={
                    'reportDate': future, 'bmo_amc': '☀️', 'eps': '-', 'revenue': '-',
                }), patch('update_data.time.sleep'):
                    self.assertTrue(update_data())
                with open('data.json') as handle:
                    result = json.load(handle)[0]
                self.assertEqual(result['reportDateSource'], 'third_party_estimate')
                self.assertIsNone(result['bmo_amc'])
            finally:
                os.chdir(previous)

    def test_official_expected_date_and_time_survive_conflicting_yahoo_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                future = (datetime.now(ZoneInfo('America/New_York')).date() + timedelta(days=5)).isoformat()
                other = (datetime.now(ZoneInfo('America/New_York')).date() + timedelta(days=6)).isoformat()
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST', 'name': 'Test', 'reportDate': future,
                                'reportDateSource': 'official',
                                'reportDateSourceUrl': 'https://example.com/earnings',
                                'bmo_amc': '☀️'}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': []}, handle)
                with patch('update_data.fetch_earnings_data', return_value={
                    'reportDate': other, 'bmo_amc': '🌙', 'eps': '-', 'revenue': '-',
                }), patch('update_data.time.sleep'):
                    self.assertTrue(update_data())
                with open('data.json') as handle:
                    result = json.load(handle)[0]
                self.assertEqual(result['reportDate'], future)
                self.assertEqual(result['reportDateSource'], 'official')
                self.assertEqual(result['bmo_amc'], '☀️')
                self.assertEqual(result['reportDateSourceUrl'], 'https://example.com/earnings')
            finally:
                os.chdir(previous)

    def test_full_schedule_refresh_aborts_with_missing_sec_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST', 'name': 'Test', 'reportDate': '2026-07-01'}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': [{'date': '2026-04-01', 'quarter': '2026 Q1'}]}, handle)
                with open('sp500_mapping.json', 'w') as handle:
                    json.dump({'TEST': {'name': 'Test'}}, handle)
                with patch('update_data.fetch_earnings_data', return_value={
                    'reportDate': None, 'bmo_amc': None, 'eps': '-', 'revenue': '-',
                }), patch('update_data.time.sleep'):
                    self.assertFalse(update_data(full_mode=True))
                with open('historical_data.json') as handle:
                    self.assertEqual(json.load(handle)['TEST'][0]['date'], '2026-04-01')
            finally:
                os.chdir(previous)

    def test_full_schedule_refresh_aborts_after_sec_request_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST', 'name': 'Test', 'reportDate': '2026-07-01'}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': []}, handle)
                with open('sp500_mapping.json', 'w') as handle:
                    json.dump({'TEST': {'name': 'Test', 'cik': '0000000001'}}, handle)
                with patch('update_data.fetch_sec_filing_data', return_value=None), \
                     patch('update_data.fetch_earnings_data', return_value={
                         'reportDate': None, 'bmo_amc': None, 'eps': '-', 'revenue': '-',
                     }), patch('update_data.time.sleep'):
                    self.assertFalse(update_data(full_mode=True))
            finally:
                os.chdir(previous)


def filing(form, report_date, filing_date, url):
    return {
        'form': form,
        'original_form': form,
        'is_amendment': False,
        'report_date': report_date,
        'filing_date': filing_date,
        'url': url,
    }


class SecFilingMatchingTests(unittest.TestCase):
    def test_reviewed_q4_matches_exact_period_and_keeps_quarter_label(self):
        history = [{
            'date': '2026-07-29', 'periodEnd': '2026-06-30',
            'periodScope': 'quarter', 'quarter': '2026 Q4',
            'verificationStatus': 'official_verified',
        }]
        filings = [
            filing('10-Q', '2026-07-01', '2026-08-10', 'https://sec.test/wrong'),
            filing('10-K', '2026-06-30', '2026-07-30', 'https://sec.test/right'),
        ]
        stats = apply_sec_matches(history, filings, fy_end_month=6)
        self.assertEqual(stats['matched'], 1)
        self.assertEqual(history[0]['secUrl'], 'https://sec.test/right')
        self.assertEqual(history[0]['form'], '10-K')
        self.assertEqual(history[0]['quarter'], '2026 Q4')

    def test_sec_audit_accepts_quarterly_q4_values_with_10k_filing(self):
        url = 'https://www.sec.gov/ix?doc=/Archives/edgar/data/1/000000000126000001/report.htm'
        with tempfile.TemporaryDirectory() as tmp:
            previous = os.getcwd()
            try:
                os.chdir(tmp)
                with open('data.json', 'w') as handle:
                    json.dump([{'ticker': 'TEST'}], handle)
                with open('historical_data.json', 'w') as handle:
                    json.dump({'TEST': [{
                        'date': '2026-07-29', 'periodEnd': '2026-06-30',
                        'periodScope': 'quarter', 'quarter': '2026 Q4',
                        'form': '10-K', 'secUrl': url,
                    }]}, handle)
                with open('sp500_mapping.json', 'w') as handle:
                    json.dump({'TEST': {'cik': '0000000001'}}, handle)
                with patch('update_data.fetch_sec_filing_data', return_value={
                    'filings': [filing('10-K', '2026-06-30', '2026-07-30', url)],
                    'fy_end_month': 6,
                }):
                    self.assertTrue(audit_sec_dataset())
            finally:
                os.chdir(previous)

    def test_non_calendar_fiscal_year_matches_nearest_official_period(self):
        history = [
            {'date': '2025-11-20', 'quarter': '2025 Q3'},
            {
                'date': '2026-02-19',
                'quarter': '2025 FY',
                'form': '10-K',
                'secUrl': 'https://www.sec.gov/ix?doc=/Archives/wrong-quarter.htm',
            },
        ]
        filings = [
            filing('10-K', '2026-01-31', '2026-03-13', 'https://sec.test/wmt-20260131'),
            filing('10-Q', '2025-10-31', '2025-12-03', 'https://sec.test/wmt-20251031'),
        ]

        matches = match_history_to_filings(history, filings)

        self.assertEqual(matches[0]['form'], '10-Q')
        self.assertEqual(matches[0]['report_date'], '2025-10-31')
        self.assertEqual(matches[1]['form'], '10-K')
        self.assertEqual(matches[1]['report_date'], '2026-01-31')

    def test_apply_uses_official_form_and_fiscal_labels_atomically(self):
        history = [
            {
                'date': '2026-02-19',
                'quarter': '2025 FY',
                'form': '10-K',
                'secUrl': 'https://sec.test/old-10q',
            },
            {'date': '2026-05-21', 'quarter': '2026 Q1'},
        ]
        filings = [
            filing('10-K', '2026-01-31', '2026-03-13', 'https://sec.test/2026-10k'),
            filing('10-Q', '2026-04-30', '2026-05-29', 'https://sec.test/2026-q1'),
        ]

        stats = apply_sec_matches(history, filings, fy_end_month=1)

        self.assertEqual(stats['matched'], 2)
        self.assertEqual(history[0]['form'], '10-K')
        self.assertEqual(history[0]['secUrl'], 'https://sec.test/2026-10k')
        self.assertEqual(history[0]['quarter'], '2026 FY')
        self.assertEqual(history[1]['form'], '10-Q')
        self.assertEqual(history[1]['quarter'], '2027 Q1')

    def test_unmatched_item_does_not_keep_stale_url_or_guessed_form(self):
        history = [{
            'date': '2026-02-19',
            'quarter': '2025 FY',
            'form': '10-K',
            'secUrl': 'https://sec.test/stale',
        }]

        stats = apply_sec_matches(history, [], fy_end_month=12)

        self.assertEqual(stats['unmatched'], 1)
        self.assertNotIn('form', history[0])
        self.assertNotIn('secUrl', history[0])

    def test_extract_prefers_original_filing_over_amendment(self):
        submissions = {
            'fiscalYearEnd': '0131',
            'filings': {
                'recent': {
                    'form': ['10-K/A', '10-K'],
                    'accessionNumber': ['0001-26-000002', '0001-26-000001'],
                    'primaryDocument': ['amended.htm', 'original.htm'],
                    'reportDate': ['2026-01-31', '2026-01-31'],
                    'filingDate': ['2026-04-01', '2026-03-13'],
                },
            },
        }

        result = extract_sec_filing_data(submissions, '0000000001')

        self.assertEqual(result['fy_end_month'], 1)
        self.assertEqual(len(result['filings']), 1)
        self.assertFalse(result['filings'][0]['is_amendment'])
        self.assertIn('original.htm', result['filings'][0]['url'])

    def test_extract_merges_supplemental_sec_submission_files(self):
        submissions = {
            'fiscalYearEnd': '1231',
            'filings': {
                'recent': {
                    'form': ['10-Q'],
                    'accessionNumber': ['0001-26-000001'],
                    'primaryDocument': ['current.htm'],
                    'reportDate': ['2026-03-31'],
                    'filingDate': ['2026-05-01'],
                },
            },
            '_supplemental_filings': [{
                'form': ['10-Q'],
                'accessionNumber': ['0001-25-000001'],
                'primaryDocument': ['older.htm'],
                'reportDate': ['2025-03-31'],
                'filingDate': ['2025-05-01'],
            }],
        }

        result = extract_sec_filing_data(submissions, '0000000001')

        self.assertEqual(len(result['filings']), 2)
        self.assertEqual(result['filings'][1]['report_date'], '2025-03-31')

    def test_validator_rejects_form_mismatch(self):
        filings = [
            filing('10-Q', '2025-10-31', '2025-12-03', 'https://sec.test/q3'),
        ]
        history = [{'date': '2026-02-19', 'form': '10-K', 'secUrl': 'https://sec.test/q3'}]

        issues = validate_sec_matches(history, filings)

        self.assertEqual(issues[0]['type'], 'form_mismatch')
        self.assertEqual(issues[0]['expected'], '10-Q')

    def test_validator_rejects_wrong_period_even_when_form_matches(self):
        filings = [
            filing('10-Q', '2026-03-31', '2026-05-01', 'https://sec.test/current-q'),
            filing('10-Q', '2025-12-31', '2026-02-01', 'https://sec.test/old-q'),
        ]
        history = [{
            'date': '2026-04-15',
            'form': '10-Q',
            'secUrl': 'https://sec.test/old-q',
        }]

        issues = validate_sec_matches(history, filings)

        self.assertEqual(issues[0]['type'], 'wrong_report')
        self.assertEqual(issues[0]['expected_url'], 'https://sec.test/current-q')

    def test_recent_release_may_wait_for_sec_filing(self):
        history = [{
            'date': date.today().isoformat(),
            'quarter': '2026 Q2',
        }]

        stats = apply_sec_matches(history, [], fy_end_month=12)
        issues = validate_sec_matches(history, [])

        self.assertEqual(stats['pending'], 1)
        self.assertEqual(history[0]['secStatus'], 'pending')
        self.assertEqual(issues, [])

    def test_quarter_labels_use_actual_10k_as_fiscal_year_anchor(self):
        matches = {
            0: filing('10-K', '2025-09-30', '2025-11-01', 'https://sec.test/fy'),
            1: filing('10-Q', '2025-12-31', '2026-02-01', 'https://sec.test/q1'),
            2: filing('10-Q', '2026-03-31', '2026-05-01', 'https://sec.test/q2'),
        }

        labels = quarter_labels_from_match_sequence(matches, fy_end_month=12)

        self.assertEqual(labels[0], '2025 FY')
        self.assertEqual(labels[1], '2026 Q1')
        self.assertEqual(labels[2], '2026 Q2')

    def test_quarter_labels_handle_52_week_periods_crossing_months(self):
        matches = {
            0: filing('10-K', '2025-03-28', '2025-05-01', 'https://sec.test/fy'),
            1: filing('10-Q', '2025-07-04', '2025-08-01', 'https://sec.test/q1'),
            2: filing('10-Q', '2025-10-03', '2025-11-01', 'https://sec.test/q2'),
            3: filing('10-Q', '2026-01-02', '2026-02-01', 'https://sec.test/q3'),
        }

        labels = quarter_labels_from_match_sequence(matches, fy_end_month=3)

        self.assertEqual(labels[1], '2026 Q1')
        self.assertEqual(labels[2], '2026 Q2')
        self.assertEqual(labels[3], '2026 Q3')

    def test_retired_ticker_is_migrated_with_its_history(self):
        companies = [{'ticker': 'BK', 'name': 'Bank of New York Mellon'}]
        history = {'BK': [{'date': '2026-04-16'}]}

        migrations = migrate_ticker_aliases(companies, history)

        self.assertEqual(migrations, 1)
        self.assertEqual(companies[0]['ticker'], 'BNY')
        self.assertNotIn('BK', history)
        self.assertIn('BNY', history)


class BarkNotificationTests(unittest.TestCase):
    def test_local_date_uses_configured_timezone(self):
        now = datetime(2026, 6, 30, 17, 30, tzinfo=timezone.utc)

        self.assertEqual(
            get_local_date('Asia/Shanghai', now),
            date(2026, 7, 1),
        )

    def test_selects_only_companies_reporting_on_target_date(self):
        companies = [
            {'ticker': 'MSFT', 'reportDate': '2026-07-01'},
            {'ticker': 'AAPL', 'reportDate': '2026-07-01'},
            {'ticker': 'NVDA', 'reportDate': '2026-07-02'},
            {'name': 'Missing ticker', 'reportDate': '2026-07-01'},
        ]

        matches = companies_reporting_on(companies, date(2026, 7, 1))

        self.assertEqual([company['ticker'] for company in matches], ['AAPL', 'MSFT'])

    def test_formats_companies_by_release_time(self):
        companies = [
            {'ticker': 'JPM', 'bmo_amc': '☀️'},
            {'ticker': 'NFLX', 'bmo_amc': '🌙'},
            {'ticker': 'UNH', 'bmo_amc': 'BMO'},
            {'ticker': 'TSLA', 'bmo_amc': None},
        ]

        title, body = format_notification(companies, date(2026, 7, 1))

        self.assertEqual(title, '今日財報｜07/01｜4 家')
        self.assertIn('今日共有 4 家 S&P 500 公司發布財報。', body)
        self.assertIn('股票代碼：JPM · NFLX · TSLA · UNH', body)
        self.assertIn('☀️ 盤前（2）\nJPM · UNH', body)
        self.assertIn('🌙 盤後（1）\nNFLX', body)
        self.assertIn('⏱️ 時間待確認（1）\nTSLA', body)

    def test_formats_empty_day_notification(self):
        title, body = format_notification([], date(2026, 7, 4))

        self.assertEqual(title, '今日財報｜07/04｜0 家')
        self.assertEqual(
            body,
            '今日共有 0 家 S&P 500 公司發布財報。\n\n股票代碼：無',
        )

    def test_formats_test_notification_in_configured_timezone(self):
        now = datetime(2026, 7, 4, 1, 5, tzinfo=timezone.utc)

        title, body = format_test_notification('Asia/Shanghai', now)

        self.assertEqual(title, 'Bark 測試成功')
        self.assertIn('2026-07-04 09:05（Asia/Shanghai）', body)

    def test_sends_json_post_to_bark(self):
        captured = {}

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"code": 200, "message": "success"}'

        def fake_opener(request, timeout):
            captured['request'] = request
            captured['timeout'] = timeout
            return FakeResponse()

        send_bark_notification(
            'test/key',
            '今日財報',
            'AAPL',
            notification_id='earnings-2026-07-01',
            opener=fake_opener,
        )

        request = captured['request']
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(request.full_url, 'https://api.day.app/test%2Fkey')
        self.assertEqual(request.method, 'POST')
        self.assertEqual(payload['title'], '今日財報')
        self.assertEqual(payload['body'], 'AAPL')
        self.assertEqual(payload['group'], 'Earnings Tracker')
        self.assertEqual(payload['id'], 'earnings-2026-07-01')
        self.assertEqual(captured['timeout'], 15)

    def test_raises_when_bark_rejects_notification(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def read(self):
                return b'{"code": 400, "message": "invalid device key"}'

        with self.assertRaisesRegex(RuntimeError, 'invalid device key'):
            send_bark_notification(
                'invalid-key',
                '今日財報',
                'AAPL',
                opener=lambda _request, timeout: FakeResponse(),
            )


if __name__ == '__main__':
    unittest.main()
