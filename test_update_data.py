import unittest
from datetime import date

from update_data import (
    apply_sec_matches,
    extract_sec_filing_data,
    match_history_to_filings,
    migrate_ticker_aliases,
    quarter_labels_from_match_sequence,
    validate_sec_matches,
)


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


if __name__ == '__main__':
    unittest.main()
