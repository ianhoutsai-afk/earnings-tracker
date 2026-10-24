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
