"""Regressions for original November 2026 financial release layouts."""
from datetime import date
from pathlib import Path
import unittest

from nvda_history import parse_release
from official_sources import parse_earnings_release
from release_metrics import parse_release_quarter_metrics

ROOT = Path(__file__).parent / 'tests' / 'fixtures'


class NovemberQuarterlySourceTests(unittest.TestCase):
    def test_nvidia_billion_summary_uses_precise_million_statement(self):
        document = (ROOT / 'nvda' / 'fy2027-q3.html').read_bytes()
        url = 'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-third-quarter-fiscal-2027'
        record = parse_release(document, url, date(2026, 11, 18))
        self.assertEqual((record['revenue'], record['epsGaapDiluted']), (115844000000, 2.70))
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2027, 3, '2026-10-25'))

    def test_disney_current_fiscal_year_precedes_comparative_quarters(self):
        document = (ROOT / 'reviewed' / 'dis-q4-2026.html').read_bytes()
        record = parse_earnings_release(document, '2026-11-17', '2026-11-17', date(2026, 11, 18))
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2026, 4, '2026-10-03'))

    def test_target_current_results_after_prior_year_comparison(self):
        document = (ROOT / 'reviewed' / 'tgt-q3-2026.html').read_bytes()
        record = parse_earnings_release(document, '2026-11-18', '2026-11-18', date(2026, 11, 18))
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2026, 3, '2026-10-31'))

    def test_comparative_results_included_cannot_establish_current_fiscal_year(self):
        document = ('<p>November 18, 2026 — Company today reported results for the quarter ended '
                    'October 31, 2026. Compared with last year, third quarter 2025 results '
                    'included a nonrecurring gain.</p>')
        record = parse_earnings_release(document, '2026-11-18', '2026-11-18', date(2026, 11, 18))
        self.assertIsNone(record['fiscalYear'])
        self.assertIsNone(record['fiscalQuarter'])

    def test_dated_full_year_and_fourth_quarter_results_can_join_financial_filing(self):
        document = ('<p>January 29, 2026 — Company today announced its full year and '
                    'fourth quarter 2025 results.</p>'
                    '<table><tr><td>Three Months Ended December 31,</td>'
                    '<td>Twelve Months Ended December 31, (unaudited)</td></tr>'
                    '<tr><td>2025</td><td>2024</td></tr></table>')
        record = parse_earnings_release(document, '2026-01-29', '2026-01-29', date(2026, 11, 18))
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2025, 4, None))

    def test_statement_totals_use_quarter_dates_and_gaap_eps(self):
        cases = (
            ('dis-q4-2026.html', '0001744489', '2026-10-03', 25947000000, 1.51),
            ('hd-q3-2026.html', '0000354950', '2026-11-01', 43398000000, 3.72),
            ('tgt-q3-2026.html', '0000027419', '2026-10-31', 27067000000, 2.65),
            ('low-q3-2026.html', '0000060667', '2026-10-30', 22756000000, 2.98),
        )
        for filename, cik, end, revenue, eps in cases:
            with self.subTest(issuer=cik):
                document = (ROOT / 'reviewed' / filename).read_bytes()
                self.assertEqual(parse_release_quarter_metrics(document, end, cik),
                                 {'revenue': revenue, 'epsGaapDiluted': eps})
                self.assertEqual(parse_release_quarter_metrics(document, '2026-12-31', cik), {})


class NovemberOutlookTests(unittest.TestCase):
    def test_outlook_subtitle_does_not_set_results_quarter(self):
        source = """
        <h1>Ross Stores Reports Strong Third Quarter Sales and Earnings Results</h1>
        <h2>Updates Fourth Quarter and Fiscal 2026 Outlook</h2>
        <p>Dublin, California, November 19, 2026 — Ross Stores, Inc. today
        reported financial results for the 13-week quarter ended October 31, 2026.</p>
        <p>Total sales for the third quarter of fiscal 2026 increased
        versus last year.</p>
        """
        record = parse_earnings_release(source, '2026-11-19', '2026-11-19',
                                        date(2026, 11, 20))
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2026, 3, '2026-10-31'))

    def test_walmart_fiscal_year_requires_current_quarter_header(self):
        document = (ROOT / 'reviewed' / 'wmt-nov20-statement.html').read_text()
        args = ('2026-11-19', '2026-11-19', date(2026, 11, 20))
        record = parse_earnings_release(document, *args)
        self.assertEqual((record['fiscalYear'], record['fiscalQuarter'], record['periodEnd']),
                         (2027, 3, '2026-10-31'))
        record = parse_earnings_release(document.replace('Q3 FY27', 'Q4 FY27'), *args)
        self.assertIsNone(record['fiscalYear'])


class NovemberStatementMetricsTests(unittest.TestCase):
    def test_reviewed_sec_statements(self):
        cases = (
            ('tjx', '0000109198', '2026-10-31', 15952000000, 1.39),
            ('panw', '0001327567', '2026-10-31', 3445000000, 0.57),
            ('p', '0001474432', '2026-11-01', 1459791000, 0.29),
            ('keys', '0001601046', '2026-10-31', 1994000000, 2.82),
            ('rost', '0000745732', '2026-10-31', 6255954000, 1.91),
            ('wmt', '0000104169', '2026-10-31', 188835000000, 0.62),
            ('wsm', '0000719955', '2026-11-01', 1991175000, 2.38),
            ('low', '0000060667', '2026-10-30', 22756000000, 2.98),
        )
        for ticker, cik, end, revenue, eps in cases:
            with self.subTest(ticker=ticker):
                path = ROOT / 'reviewed' / f'{ticker}-nov20-statement.html'
                document = path.read_bytes()
                self.assertEqual(parse_release_quarter_metrics(document, end, cik),
                                 {'revenue': revenue, 'epsGaapDiluted': eps})
                self.assertEqual(parse_release_quarter_metrics(document, '2026-12-31', cik), {})


if __name__ == '__main__':
    unittest.main()
