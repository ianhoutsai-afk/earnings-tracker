import copy
import unittest
from datetime import date

from official_sources import parse_inline_quarter, _statement_scope
from official_metrics import parse_statement_metrics
from quarterly_policy import merge_manifest_record
from test_official_real_documents import document, SOURCES
from test_official_sources import filing


class StatementScopeTests(unittest.TestCase):
    def test_only_nonfinancial_layout_table_can_lend_a_heading(self):
        original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
        fact=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
        target='<table><tr><td>Revenues</td><td>'+fact+'</td></tr></table>'
        layout='<table><tr><td>Consolidated Statements of Income</td></tr></table>'
        self.assertEqual(parse_inline_quarter(filing().replace(original,layout+target),'2026-09-30',cik='1')['revenue'],1200000000)
        dated_layout='<div><table><tr><td>Consolidated Statements of Income</td></tr><tr><td>September 30, 2026</td></tr><tr><td>USD in millions</td></tr></table></div>'
        self.assertEqual(parse_inline_quarter(filing().replace(original,dated_layout+target),'2026-09-30',cik='1')['revenue'],1200000000)
        for previous in ('<table><tr><td>Consolidated Statements of Income</td></tr><tr><td>Revenues</td><td>2000</td></tr></table>',
                         '<table><tr><td>Consolidated Statements of Income Revenues 2000</td></tr></table>',
                         '<div><table><tr><td>Consolidated Statements of Income</td></tr><tr><td>Revenues</td><td>2000</td></tr></table></div>',
                         '<div>Notes to consolidated financial statements<table><tr><td>Consolidated Statements of Income</td></tr></table></div>',
                         '<div>Statements of Cash Flows<table><tr><td>Consolidated Statements of Income</td></tr></table></div>'):
            with self.subTest(previous=previous):
                self.assertIsNone(parse_inline_quarter(filing().replace(original,previous+target),'2026-09-30',cik='1')['revenue'])

    def test_recast_exclusion_composes_with_every_supported_title(self):
        for title in ('Statements of Consolidated Earnings','Consolidated Condensed Statements of Operations',
                      'Statement of Consolidated Operations','Condensed Consolidated Statements of Comprehensive Income',
                      'Condensed Consolidated Statements of Net Income','Consolidated Income Statements'):
            for heading in (title+' Reflecting Ralliant as Discontinued Operations','Proforma '+title,title+' (Pro Forma)'):
                with self.subTest(heading=heading):
                    self.assertEqual(_statement_scope(heading),'recast')
                    body='<h2>'+heading+'</h2><p>USD in millions</p><table><tr><td></td><td>Three months ended June 30, 2026</td></tr><tr><td>Total revenue</td><td>100</td></tr><tr><td>Diluted earnings per share</td><td>1.00</td></tr></table>'
                    row=parse_statement_metrics(body,'2026-06-30',currency='USD',fiscal_year=2026,fiscal_quarter=2)
                    self.assertIsNone(row['revenue'])
                    self.assertIsNone(row['epsGaapDiluted'])

    def test_real_tagged_totals_keep_exact_period_issuer_and_usd(self):
        for ticker,cik,period,amount in (
            ('ADP','8670','2026-03-31',5939200000),
            ('AMAT','6951','2026-07-26',9115000000),
            ('BAX','10456','2025-09-30',2835000000),
            ('CAG','23217','2026-08-30',2595900000),
            ('CDNS','813672','2026-06-30',1584451000),
            ('CMI','26172','2026-06-30',9457000000),
            ('COHR','820318','2026-03-31',1805641000)):
            with self.subTest(ticker=ticker):
                row=parse_inline_quarter(document(ticker+'-scope','filing'),period,cik=cik)
                self.assertEqual(row['revenue'],amount)
                self.assertIsNone(parse_inline_quarter(document(ticker+'-scope','filing'),period,cik='999999')['revenue'])

    def test_title_variants_require_explicit_consolidation(self):
        for title in ('Statements of Consolidated Earnings','Consolidated Condensed Statements of Operations',
                      'Statement of Consolidated Operations','Condensed Consolidated Statements of Comprehensive Income',
                      'Condensed Consolidated Statements of Net Income'):
            with self.subTest(title=title):self.assertEqual(_statement_scope(title),'consolidated')
        for title in ('Segment Statements of Consolidated Earnings','Unconsolidated Condensed Statements of Operations',
                      'Joint Venture Statement of Consolidated Operations'):
            with self.subTest(title=title):self.assertEqual(_statement_scope(title),'nonconsolidated')

    @staticmethod
    def old_ftv():
        source=SOURCES['FTV-scope']
        return dict(ticker='FTV',periodEnd='2025-06-27',fiscalYear=2025,fiscalQuarter=2,date='2025-07-30',
            verifiedAt='2026-10-28',periodScope='quarter',currency='USD',epsBasis='GAAP diluted',
            epsGaapDiluted=0.49,epsVerificationStatus='verified',epsSourceUrl=source['filing']['url'],
            revenue=1016400000,revenueSourceUrl=source['exhibit']['url'],revenueVerificationStatus='verified',
            releaseSourceUrl=source['exhibit']['url'],secUrl=source['filing']['url'],
            metricLocators={'revenue':{'table':8,'row':5,'column':5,'label':'Sales'}})

    def test_supplemental_recast_cannot_compete_with_original_consolidated_sales(self):
        row=parse_statement_metrics(document('FTV-scope','exhibit'),'2025-06-27',currency='USD',fiscal_year=2025,fiscal_quarter=2)
        self.assertEqual(row['revenue'],1518800000)
        self.assertEqual(row['revenueVerificationStatus'],'verified')
        self.assertTrue(any(e['table']==8 and e['reason']=='supplemental_recast_statement' for e in row['excludedStatementTables']))

    def test_reviewed_recast_correction_preserves_old_table_evidence(self):
        old=self.old_ftv()
        parsed=parse_statement_metrics(document('FTV-scope','exhibit'),'2025-06-27',currency='USD',fiscal_year=2025,fiscal_quarter=2)
        exclusions=[{**e,'sourceUrl':old['releaseSourceUrl']} for e in parsed.get('excludedStatementTables',[])]
        new={**old,'revenue':1518800000,'revenueSourceUrl':old['secUrl'],'metricExclusionEvidence':exclusions}
        corrected=merge_manifest_record(old,new)
        self.assertEqual(corrected['revenue'],1518800000)
        self.assertEqual(corrected['revenueVerificationStatus'],'verified')
        self.assertEqual(corrected['metricCorrectionEvidence']['revenue']['oldValue'],1016400000)
        self.assertEqual(merge_manifest_record(corrected,new),corrected)
        unknown=copy.deepcopy(old);unknown['metricConflicts']={'revenue':[{'value':123,'sourceUrl':'https://unknown.test'}]}
        self.assertEqual(merge_manifest_record(unknown,new)['revenueVerificationStatus'],'conflict')
        self.assertEqual(merge_manifest_record(old,{**new,'metricExclusionEvidence':[]})['revenueVerificationStatus'],'conflict')

    def test_original_ftv_filing_and_release_correct_the_recast_value_on_merge(self):
        from official_sync import check_issuer
        source=SOURCES['FTV-scope'];release=source['releaseMetadata']
        filings=[release,dict(form='10-Q',items='',accessionNumber='0001659166-25-000120',
            primaryDocument='ftv-20250627.htm',filingDate='2025-07-30',reportDate='2025-06-27')]
        submissions={'filings':{'recent':{key:[f[key] for f in filings] for key in filings[0]}}}
        def fetch(url):
            for kind in ('primary','exhibit','filing'):
                if url==source[kind]['url']:return document('FTV-scope',kind)
            raise OSError('Not in offline fixture')
        rows,_=check_issuer('1659166',submissions,fetch,date(2026,10,28),known_records=[self.old_ftv()],depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['revenue'],1518800000)
        self.assertEqual(rows[0]['metricCorrectionEvidence']['revenue']['oldValue'],1016400000)
