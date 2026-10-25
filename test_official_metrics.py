import unittest
from datetime import date


STATEMENT = '''<h2>Consolidated Statements of Income</h2>
<p>Dollars in millions, except per-share amounts</p><table>
<tr><th rowspan="2">Metric</th><th colspan="2">Three Months Ended September 30</th><th>Nine Months Ended September 30</th></tr>
<tr><th>2026</th><th>2025</th><th>2026</th></tr>
<tr><td>Total revenue</td><td>2,322</td><td>2,118</td><td>6,900</td></tr>
<tr><td>Diluted earnings per share</td><td>1.41</td><td>1.05</td><td>3.50</td></tr>
<tr><td>Adjusted diluted earnings per share</td><td>1.55</td><td>1.20</td><td>3.90</td></tr>
</table>'''


class OfficialMetricTests(unittest.TestCase):
    def test_real_statement_sections_do_not_create_false_conflicts(self):
        from test_official_real_documents import document, SOURCES
        expected = {'BIIB':(0.66,2736000000), 'BLK':(12.19,7084000000),
                    'CEG':(None,7504000000), 'CMG':(0.32,3348562000),
                    'DD':(1.05,1819000000), 'DPZ':(None,1185598000),
                    'ELV':(None,51429000000), 'GS':(20.98,20338000000),
                    'NVR':(83.96,None), 'TROW':(2.88,1907400000),
                    'VTRS':(-0.10,3756800000), 'ZBH':(1.03,2177000000),
                    'WMT':(0.80,187937000000), 'HST':(None,1640000000),
                    'NDAQ':(0.96,None), 'TAP':(None,3096500000)}
        for ticker,(eps,revenue) in expected.items():
            with self.subTest(ticker=ticker):
                s=SOURCES[ticker]
                row=self.api.parse_statement_metrics(document(ticker,'exhibit'),s['periodEnd'],currency='USD',fiscal_year=s['fiscalYear'],fiscal_quarter=s['fiscalQuarter'])
                if eps is not None:self.assertEqual(row['epsGaapDiluted'],eps)
                if ticker != 'NDAQ':self.assertEqual(row['revenue'],revenue)
                self.assertNotEqual(row['epsVerificationStatus'],'conflict')
                self.assertNotEqual(row['revenueVerificationStatus'],'conflict')

    def test_real_conflicting_statement_values_keep_each_locator(self):
        body=STATEMENT.replace('</table>','<tr><td>Diluted earnings per share</td><td>9.99</td></tr></table>')
        row=self.api.parse_statement_metrics(body,'2026-09-30',currency='USD')
        self.assertEqual(row['epsVerificationStatus'],'conflict')
        evidence=row['metricConflicts']['epsGaapDiluted']
        self.assertEqual({e['value'] for e in evidence},{1.41,9.99})
        self.assertTrue(all(e['locator']['row'] for e in evidence))

    def test_real_apple_amd_alphabet_eps_excludes_diluted_share_counts(self):
        from test_official_real_documents import document,SOURCES
        for ticker,expected in [('AAPL',2.02),('AMD',1.38),('GOOGL',9.11)]:
            with self.subTest(ticker=ticker):
                s=SOURCES[ticker]
                result=self.api.parse_statement_metrics(document(ticker,'exhibit'),s['periodEnd'],currency='USD',fiscal_year=s['fiscalYear'],fiscal_quarter=s['fiscalQuarter'])
                self.assertEqual(result['epsGaapDiluted'],expected)
                self.assertEqual(result['epsVerificationStatus'],'verified')

    def test_share_count_sections_and_share_calculation_rows_never_become_eps(self):
        body=STATEMENT.replace('</table>', '<tr><td>Shares used in computing earnings per share</td></tr><tr><td>Diluted</td><td>14714676</td></tr><tr><td>Number of shares used in diluted net income per common share calculation</td><td>12309</td></tr></table>')
        result=self.api.parse_statement_metrics(body,'2026-09-30',currency='USD')
        self.assertEqual(result['epsGaapDiluted'],1.41)
        self.assertEqual(result['epsVerificationStatus'],'verified')

    def test_unknown_revenue_scale_is_not_assumed_to_mean_single_dollars(self):
        body=STATEMENT.replace('Dollars in millions, except per-share amounts','')
        self.assertIsNone(self.api.parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'])

    def test_continuing_operations_section_resets_net_eps_parent(self):
        body='<h2>Consolidated Statements of Income</h2><p>USD in millions</p><table><tr><td></td><td>Three months ended September 30, 2026</td></tr><tr><td>Earnings per share</td><td></td></tr><tr><td>Continuing operations</td><td></td></tr><tr><td>Diluted</td><td>2.00</td></tr></table>'
        self.assertIsNone(self.api.parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'])

    def test_html_comments_between_heading_and_table_are_not_parser_errors(self):
        from official_metrics import parse_statement_metrics
        document='<h2>Consolidated Statements of Income</h2><p>USD in millions</p><!-- printer metadata --><table><tr><td></td><td>Three months ended September 30, 2026</td></tr><tr><td>Total revenues</td><td>2,322</td></tr></table>'
        self.assertEqual(parse_statement_metrics(document,'2026-09-30',currency='USD')['revenue'],2322000000)

    def setUp(self):
        try:
            import official_metrics
        except ModuleNotFoundError:
            self.fail('Official statement and CompanyFacts readers are not implemented')
        self.api = official_metrics

    def test_expanded_header_columns_select_quarter_not_nine_months(self):
        row = self.api.parse_statement_metrics(STATEMENT, '2026-09-30', currency='USD')
        self.assertEqual(row['epsGaapDiluted'], 1.41)
        self.assertEqual(row['revenue'], 2322000000)

    def test_negative_accounting_eps_and_dollar_separator_cells(self):
        body = STATEMENT.replace('<td>1.41</td>', '<td>$(0.43)</td>')
        row = self.api.parse_statement_metrics(body, '2026-09-30', currency='USD')
        self.assertEqual(row['epsGaapDiluted'], -0.43)

    def test_annual_only_and_unknown_currency_do_not_fill_quarter_metrics(self):
        annual = STATEMENT.replace('Three Months Ended', 'Year Ended')
        self.assertIsNone(self.api.parse_statement_metrics(annual, '2026-09-30', currency='USD')['epsGaapDiluted'])
        self.assertIsNone(self.api.parse_statement_metrics(STATEMENT, '2026-09-30')['revenue'])

    def test_segment_component_and_adjusted_values_never_replace_consolidated_actuals(self):
        body = STATEMENT.replace('Total revenue', 'Product revenue').replace('Diluted earnings per share', 'Adjusted diluted earnings per share')
        row = self.api.parse_statement_metrics(body, '2026-09-30', currency='USD')
        self.assertIsNone(row['revenue'])
        self.assertIsNone(row['epsGaapDiluted'])

    def test_real_are_statement_uses_net_loss_eps_not_adjusted_ffo(self):
        from test_official_real_documents import document
        row = self.api.parse_statement_metrics(document('ARE', 'exhibit'), '2026-06-30', currency='USD', fiscal_year=2026, fiscal_quarter=2)
        self.assertEqual(row['epsGaapDiluted'], -0.43)
        self.assertEqual(row['revenue'], 662784000)

    def test_real_ge_gaap_revenue_does_not_use_adjusted_or_nine_month_revenue(self):
        from test_official_real_documents import document
        row = self.api.parse_statement_metrics(document('GE', 'exhibit'), '2026-09-30', currency='USD', fiscal_year=2026, fiscal_quarter=3)
        self.assertEqual(row['revenue'], 14118000000)

    def facts(self):
        return {'cik': 1, 'facts': {'us-gaap': {
            'EarningsPerShareDiluted': {'units': {'USD/shares': [
                {'start': '2026-07-01', 'end': '2026-09-30', 'val': 1.41, 'accn': '0000000001-26-000001', 'form': '10-Q', 'filed': '2026-10-16', 'fy': 2026, 'fp': 'Q3'},
                {'start': '2026-01-01', 'end': '2026-09-30', 'val': 3.50, 'accn': '0000000001-26-000001', 'form': '10-Q', 'filed': '2026-10-16', 'fy': 2026, 'fp': 'Q3'}]}},
            'Revenues': {'units': {'USD': [{'start': '2026-07-01', 'end': '2026-09-30', 'val': 2322000000, 'accn': '0000000001-26-000001', 'form': '10-Q', 'filed': '2026-10-16', 'fy': 2026, 'fp': 'Q3'}]}}
        }}}

    def test_companyfacts_requires_exact_cik_accession_period_currency_and_duration(self):
        payload = self.facts()
        row = self.api.parse_companyfacts(payload, cik='0000000001', period_end='2026-09-30', accessions={'0000000001-26-000001'}, today=date(2026, 10, 24))
        self.assertEqual(row['epsGaapDiluted'], 1.41)
        self.assertEqual(row['revenue'], 2322000000)
        for change in [{'cik': '2'}, {'accessions': {'other'}}, {'period_end': '2026-06-30'}]:
            args = dict(cik='1', period_end='2026-09-30', accessions={'0000000001-26-000001'}, today=date(2026, 10, 24))
            args.update(change)
            result = self.api.parse_companyfacts(payload, **args)
            self.assertIsNone(result['epsGaapDiluted'])

    def test_later_comparative_fact_cannot_override_matching_original_accession(self):
        payload = self.facts()
        rows = payload['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares']
        rows.append({**rows[0], 'accn': '0000000001-26-000099', 'val': 9.99, 'filed': '2026-10-23'})
        row = self.api.parse_companyfacts(payload, cik='1', period_end='2026-09-30', accessions={'0000000001-26-000001'}, today=date(2026, 10, 24))
        self.assertEqual(row['epsGaapDiluted'], 1.41)

    def test_conflicting_same_period_facts_remain_pending(self):
        payload = self.facts()
        rows = payload['facts']['us-gaap']['EarningsPerShareDiluted']['units']['USD/shares']
        rows.append({**rows[0], 'val': 2.00})
        row = self.api.parse_companyfacts(payload, cik='1', period_end='2026-09-30', accessions={'0000000001-26-000001'}, today=date(2026, 10, 24))
        self.assertIsNone(row['epsGaapDiluted'])
        self.assertEqual(row['epsVerificationStatus'], 'conflict')


if __name__ == '__main__':
    unittest.main()
