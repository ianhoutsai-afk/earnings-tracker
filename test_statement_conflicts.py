import unittest
from datetime import date
from pathlib import Path
from official_metrics import parse_statement_metrics
from test_official_real_documents import document

ROOT=Path(__file__).parent


class StatementConflictTests(unittest.TestCase):
    def test_explicit_diluted_net_eps_can_follow_weighted_average_share_counts(self):
        for end,year,quarter,eps in [('2026-07-31',2026,4,0.35),('2026-04-30',2026,3,0.43),
                                    ('2026-01-31',2026,2,0.36),('2025-10-31',2026,1,0.41),('2025-07-31',2025,4,0.41)]:
            with self.subTest(period=end):
                row=parse_statement_metrics(document('CPRT-'+end,'exhibit'),end,
                    currency='USD',fiscal_year=year,fiscal_quarter=quarter)
                self.assertEqual(row['epsGaapDiluted'],eps)
                self.assertEqual(row['epsVerificationStatus'],'verified')

    def test_explicit_combined_service_revenue_and_vehicle_sales_total_is_consolidated_revenue(self):
        for end,year,quarter,revenue in [('2026-07-31',2026,4,1152439000),('2026-04-30',2026,3,1237066000),
                                    ('2026-01-31',2026,2,1121674000),('2025-10-31',2026,1,1155030000),('2025-07-31',2025,4,1125097000)]:
            with self.subTest(period=end):
                row=parse_statement_metrics(document('CPRT-'+end,'exhibit'),end,
                    currency='USD',fiscal_year=year,fiscal_quarter=quarter)
                self.assertEqual(row['revenue'],revenue)
                self.assertEqual(row['metricLocators']['revenue']['label'],'Total service revenues and vehicle sales')


    def test_numeric_actual_per_share_line_resets_share_count_section_only_for_actual_eps(self):
        body=('<h2>Consolidated Statements of Income</h2><p>USD in millions</p><table>'
            '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
            '<tr><td>Weighted average common shares outstanding</td><td>999</td></tr>'
            '<tr><td>Diluted</td><td>998</td></tr>'
            '<tr><td>Diluted net income per common share</td><td>1.23</td></tr>'
            '<tr><td>Diluted weighted average common shares outstanding</td><td>997</td></tr></table>')
        self.assertEqual(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'],1.23)
        for label in ('Adjusted diluted net income per common share','Diluted net income per common share excluding specified items',
                      'Weighted average shares used in diluted net income per common share computation',
                      'Net income for diluted earnings per share of common stock'):
            with self.subTest(label=label):
                mutated=body.replace('Diluted net income per common share',label)
                self.assertIsNone(parse_statement_metrics(mutated,'2026-09-30',currency='USD')['epsGaapDiluted'])

    def test_explicit_per_share_label_under_weighted_share_heading_is_still_a_count(self):
        for label in ('Diluted earnings per share attributable to Example Inc.', 'Diluted net income per common share'):
            body=('<h2>Consolidated Statements of Income</h2><p>USD in millions</p><table>'
                '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
                '<tr><td>Weighted-average shares used in calculating:</td></tr>'
                '<tr><td>'+label+'</td><td>999</td></tr></table>')
            self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'])

    def test_original_on_pipeline_preserves_input_exclusion_and_resolves_only_proven_conflict(self):
        from official_sync import _parse_events
        from quarterly_policy import merge_manifest_record
        from verified_history import apply_official_records
        from test_official_real_documents import SOURCES
        source=SOURCES['ON-numerator']
        filings=[{'form':'10-K','accessionNumber':'0001097864-26-000006','primaryDocument':'on-20251231.htm',
                  'filingDate':'2026-02-09','reportDate':'2025-12-31','items':''},
                 {'form':'8-K','accessionNumber':'0001140361-26-004405','primaryDocument':'ef20065070_8k.htm',
                  'filingDate':'2026-02-09','reportDate':'2026-02-09','items':'2.02,9.01'}]
        def fetch(url):
            for kind,item in source.items():
                if url==item['url']:return document('ON-numerator',kind)
            raise AssertionError(url)
        rows,status=_parse_events('1097864',filings,fetch,date(2026,10,29))
        self.assertEqual(status['requestFailures'],0)
        self.assertEqual(len(rows),1)
        new={**rows[0],'ticker':'ON'}
        self.assertEqual((new['epsGaapDiluted'],new['revenue']),(0.45,1530100000))
        self.assertTrue(new['metricInputExclusionEvidence'])
        release=source['exhibit']['url']
        evidence=[{'value':181.8,'sourceUrl':release,'locator':{'table':19,'row':26,'column':4,
            'label':'Net income for diluted earnings per share of common stock'}},
            {'value':0.45,'sourceUrl':release,'locator':{'table':19,'row':30,'column':4,'label':'Diluted'}}]
        old={**new,'epsGaapDiluted':None,'epsVerificationStatus':'conflict','metricConflicts':{'epsGaapDiluted':evidence}}
        old.pop('metricInputExclusionEvidence')
        row=merge_manifest_record(old,new)
        self.assertEqual((row['epsGaapDiluted'],row['epsVerificationStatus']),(0.45,'verified'))
        history,_=apply_official_records([{'ticker':'ON'}],{},[row],date(2026,10,29))
        self.assertEqual(history['ON'][0]['metricInputExclusionEvidence'],row['metricInputExclusionEvidence'])
        self.assertEqual(history['ON'][0]['metricConflictResolutionEvidence']['epsGaapDiluted']['previousEvidence'],evidence)

    def test_net_income_for_diluted_eps_is_a_numerator_not_a_per_share_value(self):
        row=parse_statement_metrics(document('ON-numerator','exhibit'),'2025-12-31',
            currency='USD',fiscal_year=2025,fiscal_quarter=4)
        self.assertEqual(row['epsGaapDiluted'],0.45)
        self.assertEqual(row['epsVerificationStatus'],'verified')
        excluded=row['excludedEpsInputs']
        self.assertTrue(any(e['value']==181.8 and e['locator']=={'table':19,'row':26,'column':4,
            'label':'Net income for diluted earnings per share of common stock'} for e in excluded))

    def test_comprehensive_titles_do_not_erase_explicit_net_income_eps(self):
        for ticker,end,year,quarter,value in (
                ('DECK','2026-03-31',2026,4,0.96),
                ('RCL','2025-12-31',2025,4,2.76),
                ('VEEV','2026-01-31',2026,4,1.45)):
            with self.subTest(ticker=ticker):
                row=parse_statement_metrics(document(ticker+'-net-eps','exhibit'),end,
                    currency='USD',fiscal_year=year,fiscal_quarter=quarter)
                self.assertEqual(row['epsGaapDiluted'],value)
                self.assertEqual(row['epsVerificationStatus'],'verified')

    def test_original_statements_do_not_compare_different_metric_scopes(self):
        for ticker,end,year,quarter,field,value in (
                ('ACN','2026-08-31',2026,4,'epsGaapDiluted',3.29),
                ('IBKR','2026-06-30',2026,2,'epsGaapDiluted',0.69),
                ('MSI','2026-07-04',2026,2,'revenue',3133000000),
                ('RVTY','2026-07-05',2026,2,'revenue',729688000)):
            with self.subTest(ticker=ticker):
                row=parse_statement_metrics(document(ticker+'-metric-scope','exhibit'),end,
                    currency='USD',fiscal_year=year,fiscal_quarter=quarter)
                self.assertEqual(row[field],value)
                self.assertEqual(row['epsVerificationStatus' if field=='epsGaapDiluted' else 'revenueVerificationStatus'],'verified')

    def test_eps_calculation_numerators_never_become_per_share_values(self):
        for label in ('Net income for diluted earnings per share calculation',
                      'Net income for diluted earnings per share of common stock',
                      'Net earnings used in diluted EPS computation',
                      'Diluted earnings per share numerator',
                      'Net income used in the calculation of diluted earnings per share',
                      'Net income used to calculate diluted earnings per share',
                      'Net income for the computation of diluted earnings per share',
                      'Net income (diluted earnings per share calculation)',
                      'Net income in diluted earnings per share computation',
                      'Net income in the calculation of earnings per diluted common share'):
            body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
                '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
                '<tr><td>'+label+'</td><td>999</td></tr>'
                '<tr><td>Earnings per share</td><td></td></tr>'
                '<tr><td>Diluted</td><td>1.23</td></tr></table>')
            self.assertEqual(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'],1.23)

    def test_comprehensive_eps_is_not_net_earnings_eps(self):
        for label in ('Comprehensive earnings per share','Earnings per share'):
            body=('<h2>Consolidated Statements of Comprehensive Income</h2><p>USD in millions</p><table>'
                '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
                '<tr><td>'+label+'</td><td></td></tr><tr><td>Diluted</td><td>1.23</td></tr></table>')
            self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'])

    def test_combined_income_statement_can_report_explicit_net_eps(self):
        for title in ('Consolidated Statements of Income and Comprehensive Income',
                      'Consolidated Statements of Comprehensive Income and Net Income'):
            body=('<h2>'+title+'</h2><p>USD in millions</p><table>'
                '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
                '<tr><td>Net income per share</td><td></td></tr><tr><td>Diluted</td><td>1.23</td></tr></table>')
            self.assertEqual(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'],1.23)

    def test_pro_forma_column_does_not_compete_with_as_reported(self):
        for label in ('Pro Forma','Proforma','Pro-Forma'):
            body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
                '<tr><td></td><td>Three months ended September 30, 2026</td><td>Three months ended September 30, 2026</td></tr>'
                '<tr><td></td><td>As Reported</td><td>'+label+'</td></tr>'
                '<tr><td>Revenue</td><td>100</td><td>999</td></tr></table>')
            self.assertEqual(parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'],100000000)

    def test_mixed_basis_requires_explicit_as_reported_column(self):
        body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
            '<tr><td></td><td>Three months ended September 30, 2026</td><td>Three months ended September 30, 2026</td><td>Three months ended September 30, 2026</td></tr>'
            '<tr><td></td><td>As Reported</td><td>Pro Forma</td><td></td></tr>'
            '<tr><td>Revenue</td><td></td><td>999</td><td>100</td></tr></table>')
        self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'])

    def test_footnoted_pro_forma_basis_cannot_disable_allowlist(self):
        for basis in ('Pro Forma (1)','Pro Forma (a)','Pro Forma¹'):
            with self.subTest(basis=basis):
                headers='<td>Three months ended September 30, 2026</td>'*4
                body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
                    '<tr><td></td>'+headers+'</tr><tr><td></td><td>As Reported</td><td>'+basis+'</td><td></td><td></td></tr>'
                    '<tr><td>Revenue</td><td></td><td>999</td><td></td><td>100</td></tr></table>')
                self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'])

    def test_comprehensive_section_requires_explicit_net_eps_to_leave(self):
        body=('<h2>Consolidated Statements of Income and Comprehensive Income</h2><p>USD in millions</p><table>'
            '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
            '<tr><td>Comprehensive income</td><td>999</td></tr>'
            '<tr><td>Earnings per share</td><td></td></tr><tr><td>Diluted</td><td>9.99</td></tr></table>')
        self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['epsGaapDiluted'])
        restored=body.replace('Earnings per share','Net income per share').replace('9.99','1.23')
        self.assertEqual(parse_statement_metrics(restored,'2026-09-30',currency='USD')['epsGaapDiluted'],1.23)

    def test_percentage_rows_cannot_reuse_dollar_headers(self):
        body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
            '<tr><td></td><td>Three months ended September 30, 2026</td><td></td></tr>'
            '<tr><td>Revenue</td><td>123</td><td></td></tr>'
            '<tr><td>Percentage of Net Sales</td><td></td><td></td></tr>'
            '<tr><td>Revenue</td><td>100</td><td>%</td></tr></table>')
        self.assertEqual(parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'],123000000)
        no_header=body.replace('<tr><td>Percentage of Net Sales</td><td></td><td></td></tr>','')
        self.assertEqual(parse_statement_metrics(no_header,'2026-09-30',currency='USD')['revenue'],123000000)

    def test_percentage_header_variants_never_create_dollar_totals(self):
        for title in ('Percentages of Net Sales','Percentage (%) of Net Sales','As percent of Net Sales'):
            with self.subTest(title=title):
                body=('<h2>Consolidated Income Statements</h2><p>USD in millions</p><table>'
                    '<tr><td></td><td>Three months ended September 30, 2026</td></tr>'
                    '<tr><td>Diluted earnings per share</td><td>1.23</td></tr>'
                    '<tr><td>'+title+'</td><td></td></tr><tr><td>Revenue</td><td>100</td></tr></table>')
                self.assertIsNone(parse_statement_metrics(body,'2026-09-30',currency='USD')['revenue'])

    def test_actual_source_difference_is_not_cleared_by_scope_exclusions(self):
        from official_sync import check_issuer
        base='https://www.sec.gov/Archives/edgar/data/1973266/'
        urls={base+'000119312526071552/tko-20260225.htm':'TKO-primary',
            base+'000119312526071552/tko-ex99_1.htm':'TKO-release',
            base+'000119312526071651/tko-20251231.htm':'TKO-filing'}
        records=[dict(form='8-K',items='2.02,9.01',accessionNumber='0001193125-26-071552',
            primaryDocument='tko-20260225.htm',filingDate='2026-02-25',reportDate='2026-02-25'),
            dict(form='10-K',items='',accessionNumber='0001193125-26-071651',
            primaryDocument='tko-20251231.htm',filingDate='2026-02-25',reportDate='2025-12-31')]
        submissions={'filings':{'recent':{key:[r[key] for r in records] for key in records[0]}}}
        def fetch(url):
            if url not in urls:raise OSError('Outside fixture')
            return document('TKO-metric-scope','exhibit' if urls[url]=='TKO-release' else urls[url].removeprefix('TKO-'))
        rows,_=check_issuer('1973266',submissions,fetch,date(2026,10,28),depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['revenue'],1037995000)
        self.assertEqual(rows[0]['revenueVerificationStatus'],'conflict')
        self.assertEqual({e['value'] for e in rows[0]['metricConflicts']['revenue']},{1037995000,1038100000})


if __name__=='__main__':unittest.main()
