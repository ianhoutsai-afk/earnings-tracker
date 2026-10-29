"""Reviewed issuer adapters use explicit quarterly columns, never EPS subtraction."""
import unittest
from datetime import date
from test_official_sources import filing
from test_official_sync import SUBMISSIONS, fetch

def statement(quarter_heading='Three Months Ended September 30,', heading='INCOME STATEMENTS'):
    return '<html><body><h2>'+heading+'</h2><p>(In millions, except per share amounts) (Unaudited)</p><table><tr><td></td><td colspan="2">'+quarter_heading+'</td><td colspan="2">Nine Months Ended September 30,</td></tr><tr><td></td><td>2026</td><td>2025</td><td>2026</td><td>2025</td></tr><tr><td>Revenue:</td><td></td><td></td><td></td><td></td></tr><tr><td>Product</td><td>200</td><td>180</td><td>600</td><td>500</td></tr><tr><td>Service and other</td><td>1,000</td><td>900</td><td>3,000</td><td>2,500</td></tr><tr><td>Total revenue</td><td>1,200</td><td>1,080</td><td>3,600</td><td>3,000</td></tr><tr><td>Earnings per share:</td><td></td><td></td><td></td><td></td></tr><tr><td>Basic</td><td>$1.30</td><td>$1.20</td><td>$4.20</td><td>$4.00</td></tr><tr><td>Diluted</td><td>$1.25</td><td>$1.15</td><td>$4.00</td><td>$3.80</td></tr><tr><td>Weighted average shares outstanding:</td><td></td><td></td><td></td><td></td></tr><tr><td>Diluted</td><td>900</td><td>800</td><td>850</td><td>750</td></tr></table></body></html>'

class ReviewedReleaseMetricTests(unittest.TestCase):
    def parse(self, doc, end='2026-09-30', cik='0000789019'):
        from release_metrics import parse_release_quarter_metrics
        return parse_release_quarter_metrics(doc, end, cik)

    def test_exact_quarter_column_and_diluted_eps_group(self):
        result=self.parse(statement())
        self.assertEqual(result, {'revenue':1200000000, 'epsGaapDiluted':1.25})

    def test_q4_comes_from_three_months_not_full_year(self):
        doc=statement().replace('September 30,','June 30,').replace('Nine Months','Twelve Months')
        self.assertEqual(self.parse(doc,'2026-06-30')['epsGaapDiluted'],1.25)

    def test_annual_only_and_wrong_period_do_not_provide_quarterly_metrics(self):
        self.assertEqual(self.parse(statement('Twelve Months Ended September 30,')),{})
        self.assertEqual(self.parse(statement(),'2026-06-30'),{})

    def test_non_gaap_and_comprehensive_statements_are_excluded(self):
        for title in ['NON-GAAP INCOME STATEMENTS','COMPREHENSIVE INCOME STATEMENTS','SEGMENT INCOME STATEMENTS','Note 3. Revenue']:
            with self.subTest(title=title):
                self.assertEqual(self.parse(statement(heading=title)),{})

    def test_unreviewed_issuer_has_no_implicit_currency_or_layout_adapter(self):
        self.assertEqual(self.parse(statement(),cik='0000000001'),{})

    def test_unsupported_units_and_missing_year_are_pending(self):
        for doc in [statement().replace('In millions','In billions'),statement().replace('2026','2027')]:
            self.assertEqual(self.parse(doc),{})

    def test_total_cannot_be_replaced_by_components_or_weighted_share_count(self):
        doc=statement().replace('Total revenue','Service revenue').replace('Earnings per share:','Other measures:')
        self.assertEqual(self.parse(doc),{})

    def test_conflicting_duplicate_statements_remain_pending(self):
        doc='<html><body>'+statement().replace('<html><body>','').replace('</body></html>','')+statement().replace('<html><body>','').replace('</body></html>','').replace('1,200','1,300').replace('$1.25','$1.35')+'</body></html>'
        self.assertEqual(self.parse(doc),{})

    def test_plain_gaap_revenue_and_parenthesized_loss(self):
        doc=statement(heading='CONDENSED CONSOLIDATED STATEMENTS OF INCOME').replace('Total revenue','Revenue').replace('$1.25','$(1.25)')
        self.assertEqual(self.parse(doc,cik='0001326801'),{'revenue':1200000000,'epsGaapDiluted':-1.25})

    def test_blank_currency_cells_and_rowspan_headers_do_not_shift_values(self):
        doc='<h2>INCOME STATEMENTS</h2><p>($ in millions, except per share amounts)</p><table><tr><td rowspan="2"></td><td colspan="4">Three Months Ended September 30,</td></tr><tr><td colspan="2">2026</td><td colspan="2">2025</td></tr><tr><td>Total revenue</td><td>$</td><td>1,200</td><td>$</td><td>1,080</td></tr><tr><td>Diluted earnings per share</td><td>$</td><td>1.25</td><td>$</td><td>1.15</td></tr></table>'
        self.assertEqual(self.parse(doc),{'revenue':1200000000,'epsGaapDiluted':1.25})

    def test_integration_missing_inline_total_uses_release_and_records_metric_source(self):
        import copy
        from official_sync import check_issuer
        sub=copy.deepcopy(SUBMISSIONS)
        sub['filings']['recent']['accessionNumber']=['0000789019-26-000001','0000789019-26-000002']
        release='<h1>Example reports third quarter 2026 results</h1><p>October 14, 2026. Today reported results for the quarter ended September 30, 2026.</p>'+statement()
        def source(url):
            if url.endswith('results.htm'):return '<a href="ex991.htm">99.1</a>'
            if url.endswith('ex991.htm'):return release
            if url.endswith('quarter.htm'):return filing().replace('<xbrli:identifier>1</xbrli:identifier>','<xbrli:identifier>789019</xbrli:identifier>').replace('us-gaap:Revenues','msft:UnsupportedRevenue')
            return fetch(url)
        rows,_=check_issuer('0000789019',sub,source,date(2026,10,29))
        self.assertEqual(rows[0]['revenue'],1200000000)
        self.assertTrue(rows[0]['revenueSourceUrl'].endswith('/ex991.htm'))
        self.assertTrue(rows[0]['secUrl'].endswith('/quarter.htm'))
