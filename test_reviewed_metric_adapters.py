"""Regression checks against captured official shareholder statements."""
import unittest

class StrykerStatementTests(unittest.TestCase):
    def document(self):
        from pathlib import Path
        return (Path(__file__).parent/'tests/fixtures/reviewed/syk-q3-2026.html').read_text()

    def parse(self, document=None, end='2026-09-30', cik='0000310764'):
        from release_metrics import parse_release_quarter_metrics
        return parse_release_quarter_metrics(document or self.document(), end, cik)

    def test_original_split_date_and_duration_headers(self):
        self.assertEqual(self.parse(), {'revenue':6520000000, 'epsGaapDiluted':1.96})

    def test_wrong_date_year_and_issuer_stay_pending(self):
        for end in ('2026-06-30','2025-09-30','2026-09-29'):
            result=self.parse(end=end)
            if end=='2025-09-30':
                self.assertEqual(result, {'revenue':6057000000,'epsGaapDiluted':2.22})
            else:
                self.assertEqual(result,{})
        self.assertEqual(self.parse(cik='0000000001'),{})

    def test_ytd_only_and_non_usd_units_are_rejected(self):
        for document in (self.document().replace('Three Months','Twelve Months'),
                         self.document().replace('Millions of Dollars','Millions of Euros')):
            with self.subTest(document=document[:80]):
                self.assertEqual(self.parse(document),{})

    def test_adjusted_statement_and_components_are_not_totals(self):
        self.assertEqual(self.parse(self.document().replace('CONSOLIDATED STATEMENTS OF EARNINGS','NON-GAAP CONSOLIDATED STATEMENTS OF EARNINGS')), {})
        self.assertNotIn('revenue',self.parse(self.document().replace('Net sales','Orthopaedics sales')))

    def test_conflicting_statements_remain_pending(self):
        self.assertEqual(self.parse('<div>'+self.document()+self.document().replace('6,520','6,521').replace('1.96','1.97')+'</div>'), {})

    def test_source_provenance_when_the_ten_q_is_not_available(self):
        from official_sync import check_issuer
        from datetime import date
        submissions={'filings':{'recent':{
            'form':['8-K'], 'accessionNumber':['0000310764-26-000059'],
            'primaryDocument':['syk-20261029.htm'], 'filingDate':['2026-10-29'],
            'reportDate':['2026-10-29'], 'items':['2.02,9.01']}}}
        primary='<p>Item 2.02</p><p>On October 29, 2026, Stryker reported third quarter 2026 results for the quarter ended September 30, 2026.</p><p>Item 9.01</p><a href="sykex991.htm">99.1</a>'
        def fetch(url):
            return self.document() if url.endswith('sykex991.htm') else primary
        rows,_=check_issuer('0000310764',submissions,fetch,date(2026,10,30))
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['revenue'],rows[0]['epsGaapDiluted']),(6520000000,1.96))
        for field in ('revenueSourceUrl','epsSourceUrl'):
            self.assertTrue(rows[0][field].endswith('/sykex991.htm'))
        self.assertNotIn('secUrl',rows[0])

    def test_generic_millions_wording_cannot_bypass_currency_evidence(self):
        self.assertEqual(self.parse(self.document().replace('Millions of Dollars','In millions of Euros')), {})

    def test_contradictory_full_width_dates_and_years_stay_pending(self):
        from lxml import html
        for text in ('For the Three and Nine Months June 30','2025'):
            tree=html.fromstring(self.document())
            row=next(row for row in tree.xpath('.//tr') if ''.join(row.itertext()).strip().startswith('Net sales'))
            row.addprevious(html.fromstring('<tr><td colspan="36">'+text+'</td></tr>'))
            with self.subTest(text=text):
                self.assertEqual(self.parse(html.tostring(tree,encoding='unicode')), {})

class TeslaUpdateTests(unittest.TestCase):
    def document(self):
        from pathlib import Path
        return (Path(__file__).parent/'tests/fixtures/reviewed/tsla-q4-2025.html').read_text()

    def parse(self, document=None, end='2025-12-31', cik='0001318605'):
        from release_metrics import parse_release_quarter_metrics
        return parse_release_quarter_metrics(document or self.document(),end,cik)

    def test_original_quarterly_gaap_values_come_from_statement_slide(self):
        self.assertEqual(self.parse(),{'revenue':24901000000,'epsGaapDiluted':0.24})

    def test_other_explicit_quarter_column_is_selected_by_verified_period(self):
        self.assertEqual(self.parse(end='2025-09-30'),{'revenue':28095000000,'epsGaapDiluted':0.39})

    def test_wrong_period_end_and_issuer_are_not_inferred(self):
        for end in ('2025-12-30','2026-12-31'):
            self.assertEqual(self.parse(end=end),{})
        self.assertEqual(self.parse(cik='0000000001'),{})

    def test_annual_and_reconciliation_slides_cannot_substitute_for_statement(self):
        self.assertEqual(self.parse(self.document().replace('S T A T E M E N T   O F   O P E R A T I O N S','R E C O N C I L I A T I O N')),{})

    def test_wrong_currency_and_missing_quarter_columns_stay_pending(self):
        self.assertEqual(self.parse(self.document().replace('millions of USD','millions of EUR')), {})
        self.assertEqual(self.parse(self.document().replace('Q4-2025','2025')), {})

    def test_short_row_does_not_shift_columns(self):
        self.assertNotIn('revenue',self.parse(self.document().replace('25,707 19,335 22,496 28,095 24,901 COST OF REVENUES','25,707 19,335 22,496 24,901 COST OF REVENUES')))

    def test_share_count_and_non_gaap_values_do_not_replace_diluted_eps(self):
        document=self.document().replace('Diluted (1) $        0.60 $        0.12 $        0.33 $        0.39 $       0.24','Diluted shares (1) $        0.60 $        0.12 $        0.33 $        0.39 $       0.24')
        self.assertNotIn('epsGaapDiluted',self.parse(document))

    def test_conflicting_statement_slides_remain_pending(self):
        self.assertEqual(self.parse('<div>'+self.document()+self.document().replace('24,901','24,902').replace('$       0.24','$       0.25')+'</div>'), {})

    def test_explicit_adjusted_basis_cannot_keep_a_gaap_statement_marker(self):
        title='S T A T E M E N T   O F   O P E R A T I O N S'
        for prefix in ('NON-GAAP ','ADJUSTED ','A D J U S T E D '):
            document=self.document().replace(title,prefix+title).replace('$       0.24','$       0.50')
            with self.subTest(prefix=prefix):
                self.assertEqual(self.parse(document), {})
