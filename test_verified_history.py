import copy
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from verified_history import (
    apply_official_records,
    clear_past_report_dates,
    date_in_new_york,
    scan_yahoo_candidates,
    refresh_site_data,
    status_from_discovery,
    write_json_bundle,
)


OFFICIAL = {
    'ticker': 'MSFT',
    'date': '2026-07-29',
    'periodEnd': '2026-06-30',
    'fiscalYear': 2026,
    'fiscalQuarter': 4,
    'periodScope': 'quarter',
    'epsGaapDiluted': 4.81,
    'epsBasis': 'GAAP diluted',
    'revenue': 90007000000,
    'currency': 'USD',
    'releaseSourceUrl': 'https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast',
    'verifiedAt': '2026-09-29',
}


class VerifiedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.companies = [{'ticker': 'MSFT', 'reportDate': '2026-07-29', 'bmo_amc': '🌙'}]
        self.history = {'MSFT': [{'date': '2026-04-29', 'quarter': '2026 Q3', 'eps_reported': '$3.50'}]}

    def test_official_gaap_values_append_once_and_preserve_existing_history(self):
        original = copy.deepcopy(self.history)
        result, added = apply_official_records(self.companies, self.history, [OFFICIAL], date(2026, 9, 29))
        self.assertEqual(added, 1)
        self.assertEqual(self.history, original)
        self.assertEqual(len(result['MSFT']), 2)
        latest = result['MSFT'][-1]
        self.assertEqual(latest['eps_reported'], '$4.81')
        self.assertEqual(latest['revenue_reported'], '$90.01B')
        self.assertEqual(latest['quarter'], '2026 Q4')
        self.assertEqual(latest['periodScope'], 'quarter')
        self.assertEqual(latest['epsBasis'], 'GAAP diluted')
        self.assertEqual(latest['releaseSourceUrl'], OFFICIAL['releaseSourceUrl'])
        self.assertEqual(latest['metricSourceUrl'], OFFICIAL['releaseSourceUrl'])
        self.assertNotIn('secUrl', latest)
        again, second_added = apply_official_records(self.companies, result, [OFFICIAL], date(2026, 9, 29))
        self.assertEqual(second_added, 0)
        self.assertEqual(again, result)

    def test_missing_official_metrics_stay_blank(self):
        record = {**OFFICIAL, 'epsGaapDiluted': None, 'revenue': None}
        result, _ = apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))
        self.assertEqual(result['MSFT'][-1]['eps_reported'], '-')
        self.assertEqual(result['MSFT'][-1]['revenue_reported'], '-')
        self.assertIsNone(result['MSFT'][-1]['epsBasis'])

    def test_negative_gaap_eps_is_shown_as_a_loss(self):
        record = {**OFFICIAL, 'epsGaapDiluted': -0.23}
        result, _ = apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))
        self.assertEqual(result['MSFT'][-1]['eps_reported'], '-$0.23')

    def test_reviewed_record_reformats_on_rerun_without_losing_sec_link(self):
        record = {**OFFICIAL, 'epsGaapDiluted': -0.23}
        history = {'MSFT': [{
            'date': '2026-07-29', 'periodEnd': '2026-06-30',
            'periodScope': 'quarter', 'verificationStatus': 'official_verified',
            'eps_reported': '$-0.23', 'secUrl': 'https://www.sec.gov/Archives/example',
            'form': '10-K',
        }]}
        result, added = apply_official_records(self.companies, history, [record], date(2026, 9, 29))
        self.assertEqual(added, 0)
        self.assertEqual(result['MSFT'][0]['eps_reported'], '-$0.23')
        self.assertEqual(result['MSFT'][0]['form'], '10-K')

    def test_adjusted_eps_cannot_be_published_as_gaap(self):
        record = {**OFFICIAL, 'epsBasis': 'adjusted', 'epsGaapDiluted': 4.74}
        with self.assertRaisesRegex(ValueError, 'GAAP'):
            apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))

    def test_non_null_eps_requires_explicit_gaap_basis(self):
        record = {key: value for key, value in OFFICIAL.items() if key != 'epsBasis'}
        with self.assertRaisesRegex(ValueError, 'GAAP'):
            apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))

    def test_official_metric_note_is_carried_into_public_record(self):
        note = {'en': 'Includes a one-time investment gain.', 'zh-TW': '包含一次性投資收益。'}
        record = {**OFFICIAL, 'metricNote': note}
        result, _ = apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))
        self.assertEqual(result['MSFT'][-1]['metricNote'], note)

    def test_untrusted_or_future_official_record_aborts_without_changing_history(self):
        original = copy.deepcopy(self.history)
        record = {**OFFICIAL, 'releaseSourceUrl': 'https://finance.yahoo.com/quote/MSFT', 'date': '2026-10-01'}
        with self.assertRaises(ValueError):
            apply_official_records(self.companies, self.history, [record], date(2026, 9, 29))
        self.assertEqual(self.history, original)

    def test_new_york_date_handles_cross_timezone_boundary(self):
        timestamp = datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(date_in_new_york(timestamp), date(2026, 7, 29))

    def test_stale_expected_dates_clear_without_changing_future_date(self):
        companies = self.companies + [{'ticker': 'AAPL', 'reportDate': '2026-10-01', 'bmo_amc': '☀️'}]
        result = clear_past_report_dates(companies, date(2026, 9, 29))
        self.assertIsNone(result[0]['reportDate'])
        self.assertIsNone(result[0]['bmo_amc'])
        self.assertEqual(result[1], companies[1])

    def test_every_company_gets_a_status_without_publishing_yahoo_values(self):
        companies = self.companies + [{'ticker': 'AAPL'}]
        candidates = {'MSFT': ['2026-07-29'], 'AAPL': ['2026-07-30']}
        status = status_from_discovery(companies, self.history, candidates, {}, '2026-09-29T12:00:00Z')
        self.assertEqual(set(status), {'MSFT', 'AAPL'})
        self.assertEqual(status['MSFT']['status'], 'pending_official')
        self.assertEqual(status['AAPL']['status'], 'pending_official')
        self.assertFalse(status['MSFT']['latestStoredOfficial'])
        self.assertEqual(status['MSFT']['discoverySource'], 'yfinance.get_earnings_dates')
        self.assertNotIn('eps', str(status).lower())
        self.assertNotIn('revenue', str(status).lower())

    def test_verified_status_requires_latest_candidate_to_be_reviewed(self):
        history = {'MSFT': [
            {'date': '2026-04-29', 'verificationStatus': 'official_verified'},
            {'date': '2026-07-29'},
        ]}
        status = status_from_discovery(
            self.companies, history, {'MSFT': ['2026-07-29']}, {}, '2026-09-29T12:00:00Z',
        )
        self.assertEqual(status['MSFT']['status'], 'pending_official')
        history['MSFT'][-1]['verificationStatus'] = 'official_verified'
        status = status_from_discovery(
            self.companies, history, {'MSFT': ['2026-07-29']}, {}, '2026-09-29T12:00:00Z',
        )
        self.assertEqual(status['MSFT']['status'], 'verified_to_latest_candidate')
        self.assertTrue(status['MSFT']['latestStoredOfficial'])

    def test_scan_failure_retains_separate_official_history_fact(self):
        history = {'MSFT': [{'date': '2026-07-29', 'verificationStatus': 'official_verified'}]}
        status = status_from_discovery(
            self.companies, history, {'MSFT': []}, {'MSFT': 'yahoo_dns_failed'},
            '2026-09-29T12:00:00Z',
        )['MSFT']
        self.assertEqual(status['status'], 'discovery_failed')
        self.assertEqual(status['reason'], 'yahoo_dns_failed')
        self.assertTrue(status['latestStoredOfficial'])
        self.assertEqual(status['discoverySource'], 'yfinance.get_earnings_dates')

    def test_scan_all_tickers_keeps_dates_but_no_yahoo_eps(self):
        frame = pd.DataFrame(
            {'Reported EPS': [4.74, None]},
            index=pd.to_datetime(['2026-07-30T01:00:00Z', '2026-10-01T01:00:00Z']),
        )
        calls = []

        def fetch(ticker):
            calls.append(ticker)
            if ticker == 'AAPL':
                raise RuntimeError('rate limited')
            return frame

        companies = self.companies + [{'ticker': 'AAPL'}]
        candidates, errors = scan_yahoo_candidates(companies, fetch, date(2026, 9, 29), sleep=lambda _: None)
        self.assertEqual(calls, ['MSFT', 'AAPL'])
        self.assertEqual(candidates['MSFT'], ['2026-07-29'])
        self.assertEqual(errors['AAPL'], 'yahoo_request_failed')
        self.assertNotIn('4.74', str(candidates))

    def test_empty_yahoo_history_is_discovery_failure_not_up_to_date(self):
        candidates, errors = scan_yahoo_candidates(
            self.companies, lambda _: pd.DataFrame(), date(2026, 9, 29), sleep=lambda _: None,
        )
        self.assertEqual(candidates['MSFT'], [])
        self.assertEqual(errors['MSFT'], 'no_reported_eps_from_yahoo')

    def test_json_bundle_rolls_back_when_second_replace_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp, 'data.json')
            second = Path(tmp, 'historical_data.json')
            first.write_text('{"old": 1}')
            second.write_text('{"old": 2}')
            real_replace = os.replace
            attempts = [0]

            def fail_second_replace(src, dest):
                attempts[0] += 1
                if attempts[0] == 2:
                    raise OSError('write failed')
                return real_replace(src, dest)

            with patch('verified_history.os.replace', side_effect=fail_second_replace):
                with self.assertRaises(OSError):
                    write_json_bundle({first: {'new': 1}, second: {'new': 2}})
            self.assertEqual(json.loads(first.read_text()), {'old': 1})
            self.assertEqual(json.loads(second.read_text()), {'old': 2})

    def test_refresh_writes_only_reviewed_values_and_status_for_every_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data.json').write_text(json.dumps(self.companies))
            (root / 'historical_data.json').write_text(json.dumps(self.history))
            (root / 'official_history.json').write_text(json.dumps([OFFICIAL]))
            result = refresh_site_data(root, today=date(2026, 9, 29), scan=False)
            self.assertEqual(result['added'], 1)
            saved = json.loads((root / 'historical_data.json').read_text())
            self.assertEqual(saved['MSFT'][-1]['eps_reported'], '$4.81')
            self.assertIsNone(json.loads((root / 'data.json').read_text())[0]['reportDate'])
            status = json.loads((root / 'history_status.json').read_text())
            self.assertEqual(status['MSFT']['status'], 'official_verified_scan_pending')
            self.assertEqual(refresh_site_data(root, today=date(2026, 9, 29), scan=False)['added'], 0)

    def test_invalid_manifest_causes_no_partial_site_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data.json').write_text(json.dumps(self.companies))
            (root / 'historical_data.json').write_text(json.dumps(self.history))
            (root / 'official_history.json').write_text(json.dumps([{**OFFICIAL, 'epsBasis': 'adjusted'}]))
            before = (root / 'data.json').read_bytes()
            with self.assertRaises(ValueError):
                refresh_site_data(root, today=date(2026, 9, 29), scan=False)
            self.assertEqual((root / 'data.json').read_bytes(), before)
            self.assertFalse((root / 'history_status.json').exists())

    def test_reviewing_pending_same_date_updates_its_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'data.json').write_text(json.dumps(self.companies))
            (root / 'historical_data.json').write_text(json.dumps({
                'MSFT': [{'date': OFFICIAL['date'], 'quarter': '2026 Q4'}],
            }))
            (root / 'official_history.json').write_text(json.dumps([OFFICIAL]))
            (root / 'history_status.json').write_text(json.dumps({
                'MSFT': {
                    'status': 'pending_official', 'reason': 'newer_release_requires_official_check',
                    'latestStoredDate': OFFICIAL['date'], 'checkedAt': '2026-09-29T10:00:00Z',
                },
            }))
            refresh_site_data(root, today=date(2026, 9, 29), scan=False)
            status = json.loads((root / 'history_status.json').read_text())['MSFT']
            self.assertEqual(status['status'], 'official_verified_scan_pending')
            self.assertTrue(status['latestStoredOfficial'])
            self.assertEqual(status['officialSourceUrl'], OFFICIAL['releaseSourceUrl'])


if __name__ == '__main__':
    unittest.main()
