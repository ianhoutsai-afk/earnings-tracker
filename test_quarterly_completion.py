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

class ConsolidatedRevenueLayoutRegressions(unittest.TestCase):
    def test_currency_cell_and_empty_span_wrapper_preserve_total_revenue(self):
        from official_sources import parse_inline_quarter
        original = '<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
        fact = original.replace('us-gaap:Revenues', 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
        statement = '<div>CONDENSED CONSOLIDATED STATEMENTS OF INCOME</div><div>(In millions)</div><div>(Unaudited)</div><div><span> </span><table><tr><td>Revenue</td><td>$</td><td>'+fact+'</td></tr></table></div>'
        self.assertEqual(parse_inline_quarter(filing().replace(original, statement), '2026-09-30')['revenue'], 1200000000)

    def test_note_inside_wrapper_still_blocks_statement_heading(self):
        from official_sources import parse_inline_quarter
        original = '<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
        fact = original.replace('us-gaap:Revenues', 'us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
        for extra in ['<span>Note 2. Revenue</span>', '<table><tr><td>Other table</td></tr></table>']:
            statement = '<div>CONSOLIDATED STATEMENTS OF INCOME</div><div>'+extra+'<table><tr><td>Revenue</td><td>'+fact+'</td></tr></table></div>'
            self.assertIsNone(parse_inline_quarter(filing().replace(original, statement), '2026-09-30')['revenue'])

class CoverageHealthRegressions(unittest.TestCase):
    def test_transport_success_does_not_claim_complete_quarterly_data(self):
        import json
        import tempfile
        from pathlib import Path
        from official_sync import sync_all
        from test_official_sync import OfficialSyncTests
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            OfficialSyncTests().setup_root(root)
            summary = sync_all(root, date(2026,10,22), fetch=fetch, full=True)
            self.assertTrue(summary['sourceHealthy'])
            self.assertFalse(summary['dataComplete'])
            self.assertFalse(summary['healthy'])
            self.assertEqual(summary['completeMetricQuarters'], 2)
            self.assertEqual(summary['storedQuarters'], 10)
