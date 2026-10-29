"""Regressions reproduced from original SEC quarterly publication statements.

Source TSLA: https://www.sec.gov/Archives/edgar/data/1318605/000162828026066738/tsla-20261021.htm
Source META: https://www.sec.gov/Archives/edgar/data/1326801/000162828026066700/meta-20261019.htm
Fixtures are structural reductions; all financial values in synthetic cases are test data.
"""
import copy
import unittest
from datetime import date
from official_sources import parse_earnings_filing
from official_sync import check_issuer
from test_official_sources import RELEASE, filing
from test_official_sync import SUBMISSIONS, fetch

TODAY = date(2026, 10, 29)

class CompletedPublicationRegressions(unittest.TestCase):
    def test_released_results_is_completed_publication(self):
        doc = '<h2>Item 2.02 Results of Operations and Financial Condition.</h2><p>On October 21, 2026, Tesla, Inc. released its financial results for the quarter ended September 30, 2026 by posting its Third Quarter 2026 Update on its website.</p><h2>Item 9.01 Exhibits</h2>'
        row = parse_earnings_filing(doc, '2026-10-21', '2026-10-21', TODAY)
        self.assertEqual((row['date'], row['periodEnd'], row['fiscalYear'], row['fiscalQuarter']), ('2026-10-21', '2026-09-30', 2026, 3))

    def test_published_update_matches_quarterly_filing(self):
        primary = '<h2>Item 2.02 Results of Operations</h2><p>On October 14, 2026, Example released its financial results for the quarter ended September 30, 2026 by posting its Third Quarter 2026 Update.</p><a href="ex991.htm">99.1</a>'
        def source(url):
            if url.endswith('results.htm'): return primary
            if url.endswith('ex991.htm'): return '<h1>Q3 2026 Update</h1>'
            return fetch(url)
        rows, _ = check_issuer('0000000001', SUBMISSIONS, source, TODAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['epsGaapDiluted'], 1.25)

    def test_issued_release_with_later_call_uses_exhibit_confirmed_date(self):
        doc = '<h2>Item 2.02 Results of Operations</h2><p>On October 21, 2026, the Company issued a press release and will hold a conference call regarding its financial results for the quarter ended September 30, 2026.</p><h2>Item 8.01 Other Events</h2>'
        exhibit = RELEASE.replace('October 14, 2026', 'October 21, 2026')
        row = parse_earnings_filing(doc, '2026-10-19', '2026-10-21', TODAY, exhibit=exhibit)
        self.assertEqual((row['date'], row['periodEnd']), ('2026-10-21', '2026-09-30'))

    def test_later_call_statement_without_confirming_actual_release_stays_pending(self):
        doc = '<h2>Item 2.02 Results of Operations</h2><p>On October 21, 2026, the Company issued a press release and will hold a conference call regarding its financial results for the quarter ended September 30, 2026.</p>'
        for exhibit in [None, '<h1>Example Announces Third Quarter 2026 Results Date</h1><p>October 21, 2026. Results for the quarter ended September 30, 2026 will be released next week.</p>', RELEASE]:
            with self.subTest(exhibit=exhibit):
                with self.assertRaises(ValueError):
                    parse_earnings_filing(doc, '2026-10-19', '2026-10-21', TODAY, exhibit=exhibit)

    def test_release_with_future_publication_verb_is_rejected(self):
        doc = '<h2>Item 2.02 Results of Operations</h2><p>On October 21, 2026, the Company will release financial results for the third quarter ended September 30, 2026.</p>'
        with self.assertRaises(ValueError):
            parse_earnings_filing(doc, '2026-10-21', '2026-10-21', TODAY)
