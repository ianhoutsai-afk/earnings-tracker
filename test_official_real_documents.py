"""Regressions use original SEC documents with source URLs and byte hashes in fixtures."""
import gzip
import json
import unittest
from datetime import date
from pathlib import Path

from official_sources import parse_earnings_filing, parse_earnings_release

FIXTURES = Path(__file__).parent / 'tests/fixtures/official'
SOURCES = json.loads((FIXTURES / 'sources.json').read_text())


def document(ticker, kind):
    return gzip.decompress((FIXTURES / f'{ticker}-{kind}.html.gz').read_bytes())


class OriginalDocumentRegressions(unittest.TestCase):
    def test_nrg_future_acquisition_closing_is_not_the_reported_quarter(self):
        row = parse_earnings_release(document('NRG-Q3', 'exhibit'), '2025-11-06',
                                     '2025-11-06', date(2026, 10, 27))
        self.assertEqual((row['periodEnd'], row['fiscalYear'], row['fiscalQuarter']),
                         ('2025-09-30', 2025, 3))

    def test_cms_publication_sentence_split_across_lines_keeps_quarter_identity(self):
        row=parse_earnings_filing(document('CMS','primary'),'2026-07-28','2026-07-28',
                                  date(2026,10,27),exhibit=document('CMS','exhibit'))
        self.assertEqual(row['date'],'2026-07-28')
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,2))

    def test_broadridge_matching_fiscal_headline_unlocks_quarterly_exhibit_metrics(self):
        from official_sync import check_issuer
        primary=SOURCES['BR']['primary']['url'];exhibit=SOURCES['BR']['exhibit']['url']
        filing_url='https://www.sec.gov/Archives/edgar/data/1383312/000162828025037656/br-20250630.htm'
        submissions={'cik':1383312,'filings':{'recent':{
            'form':['8-K','10-K'],'items':['2.02,9.01',''],
            'accessionNumber':['0001383312-25-000024','0001628280-25-037656'],
            'primaryDocument':['br-20250804.htm','br-20250630.htm'],
            'filingDate':['2025-08-05','2025-08-05'],'reportDate':['2025-08-04','2025-06-30']}}}
        annual=b'''<html><body>
          <ix:nonNumeric name="dei:DocumentFiscalYearFocus">2025</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">FY</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentPeriodEndDate">2025-06-30</ix:nonNumeric>
        </body></html>'''
        def source(url):
            if url==primary:return document('BR','primary')
            if url==exhibit:return document('BR','exhibit')
            if url==filing_url:return annual
            if url.endswith('/ex992earningspresentatio.htm'):return '<html><h1>Presentation</h1></html>'
            if url=='https://data.sec.gov/api/xbrl/companyfacts/CIK0001383312.json':return b'{"cik":1383312,"facts":{}}'
            raise AssertionError(url)
        rows,_=check_issuer('1383312',submissions,source,date(2026,10,27),depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['date'],rows[0]['epsGaapDiluted'],rows[0]['revenue']),
                         ('2025-08-05',3.16,2065400000))
        self.assertEqual((rows[0]['epsSourceUrl'],rows[0]['revenueSourceUrl']),(exhibit,exhibit))

    def test_schw_prior_year_comparison_does_not_name_the_current_quarter(self):
        for q,event,end in [('Q1','2026-04-16','2026-03-31'),('Q2','2026-07-21','2026-06-30'),('Q3','2026-10-15','2026-09-30')]:
            with self.subTest(quarter=q):
                row=parse_earnings_release(document('SCHW-'+q,'exhibit'),event,event,date(2026,10,27))
                self.assertEqual(row['periodEnd'],end)
                self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,int(q[-1])))

    def test_synchrony_release_date_year_does_not_replace_fiscal_year(self):
        row=parse_earnings_release(document('SYF-Q4','exhibit'),'2026-01-27','2026-01-27',date(2026,10,27))
        self.assertEqual((row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),('2025-12-31',2025,4))

    def test_workday_fiscal_exception_does_not_accept_an_unreviewed_filing(self):
        from official_sync import check_issuer
        exhibit=SOURCES['WDAY-FY26-Q3']['exhibit']['url']
        base='https://www.sec.gov/Archives/edgar/data/1327811/000132781125000196/'
        submissions={'cik':1327811,'filings':{'recent':{
            'form':['8-K','10-Q'],'items':['2.02,9.01',''],
            'accessionNumber':['0001327811-25-000196','0001327811-25-000198'],
            'primaryDocument':['primary.htm','unreviewed.htm'],
            'filingDate':['2025-11-25','2025-11-26'],'reportDate':['2025-11-25','2025-10-31']}}}
        def source(url):
            if url==base+'primary.htm':return f'<a href="{exhibit.rsplit("/",1)[-1]}">Exhibit 99.1 earnings release</a>'
            if url==exhibit:return document('WDAY-FY26-Q3','exhibit')
            if url.endswith('/unreviewed.htm'):return document('WDAY-FY26-Q3','filing')
            raise AssertionError(url)
        rows,_=check_issuer('1327811',submissions,source,date(2026,10,27),depth=1)
        self.assertEqual(rows,[])

    def test_workday_fiscal_2026_quarters_use_reviewed_release_identity(self):
        from official_sync import check_issuer
        from official_sources import parse_inline_quarter
        annual=parse_inline_quarter(document('WDAY-FY26-Q4','filing'),'2026-01-31',cik='1327811')
        self.assertEqual((annual['fiscalYear'],annual['fiscalQuarter']),(2026,4))
        for q,period,event,filing_day,release_acc,filing_acc,primary in [
            (2,'2025-07-31','2025-08-21','2025-08-22','0001327811-25-000181','0001327811-25-000184','wday-20250821.htm'),
            (3,'2025-10-31','2025-11-25','2025-11-26','0001327811-25-000196','0001327811-25-000198','wday-20251125.htm')]:
            with self.subTest(quarter=q):
                name=f'WDAY-FY26-Q{q}'
                exhibit=SOURCES[name]['exhibit']['url'];filing_url=SOURCES[name]['filing']['url']
                base='https://www.sec.gov/Archives/edgar/data/1327811/'+release_acc.replace('-','')+'/'
                submissions={'cik':1327811,'filings':{'recent':{
                    'form':['8-K','10-Q'],'items':['2.02,9.01',''],
                    'accessionNumber':[release_acc,filing_acc],
                    'primaryDocument':[primary,filing_url.rsplit('/',1)[-1]],
                    'filingDate':[event,filing_day],'reportDate':[event,period]}}}
                old={'ticker':'WDAY','periodEnd':period,'periodScope':'quarter','date':event,
                     'fiscalYear':2025,'fiscalQuarter':q,'verifiedAt':'2026-10-26',
                     'releaseSourceUrl':exhibit,'currency':'USD'}
                def source(url):
                    if url==base+primary:return f'<a href="{exhibit.rsplit("/",1)[-1]}">Exhibit 99.1 earnings release</a>'
                    if url==exhibit:return document(name,'exhibit')
                    if url==filing_url:return document(name,'filing')
                    if url=='https://data.sec.gov/api/xbrl/companyfacts/CIK0001327811.json':return b'{"cik":1327811,"facts":{}}'
                    raise AssertionError(url)
                rows,_=check_issuer('1327811',submissions,source,date(2026,10,27),known_records=[old],depth=1)
                self.assertEqual((rows[0]['fiscalYear'],rows[0]['fiscalQuarter']),(2026,q))
                self.assertEqual(rows[0]['fiscalIdentityCorrectionEvidence']['filingFiscalYear'],2025)
                self.assertEqual(rows[0]['fiscalIdentityCorrectionEvidence']['releaseSourceUrl'],exhibit)

    def test_broadridge_release_date_is_not_the_earlier_board_event(self):
        row=parse_earnings_filing(document('BR','primary'),'2025-08-04','2025-08-05',
                                  date(2026,10,27),exhibit=document('BR','exhibit'))
        self.assertEqual(row['date'],'2025-08-05')
        self.assertEqual(row['periodEnd'],'2025-06-30')

    def test_amcor_fourth_quarter_statement_uses_explicit_dollar_millions(self):
        from official_metrics import parse_statement_metrics
        row = parse_statement_metrics(document('AMCR-Q4', 'exhibit'), '2026-06-30',
                                      currency='USD', fiscal_year=2026, fiscal_quarter=4)
        self.assertEqual(row['epsGaapDiluted'], 0.83)
        self.assertEqual(row['revenue'], 6398000000)

    def test_amcor_filing_fallback_reads_matching_exhibit_metrics_with_their_source(self):
        from official_sync import check_issuer
        base='https://www.sec.gov/Archives/edgar/data/1748790/'
        primary=SOURCES['AMCR-Q4']['primary']['url']
        exhibit=SOURCES['AMCR-Q4']['exhibit']['url']
        filing_url=base+'000174879026000022/amcr-20260630.htm'
        submissions={'cik':1748790,'filings':{'recent':{
            'form':['8-K','10-K'],'items':['2.02,9.01',''],
            'accessionNumber':['0001748790-26-000020','0001748790-26-000022'],
            'primaryDocument':['amcr-20260812.htm','amcr-20260630.htm'],
            'filingDate':['2026-08-12','2026-08-14'],
            'reportDate':['2026-08-12','2026-06-30']}}}
        annual=b'''<html><body>
          <ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">FY</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-06-30</ix:nonNumeric>
        </body></html>'''
        def fetch(url):
            if url==primary:return document('AMCR-Q4','primary')
            if url==exhibit:return document('AMCR-Q4','exhibit')
            if url==filing_url:return annual
            if url=='https://data.sec.gov/api/xbrl/companyfacts/CIK0001748790.json':
                return b'{"cik":1748790,"facts":{}}'
            raise AssertionError(url)
        rows,_=check_issuer('1748790',submissions,fetch,date(2026,10,26),depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['periodEnd'],rows[0]['epsGaapDiluted'],rows[0]['revenue']),
                         ('2026-06-30',0.83,6398000000))
        self.assertEqual((rows[0]['epsSourceUrl'],rows[0]['revenueSourceUrl']),(exhibit,exhibit))

    def test_amcor_earnings_exhibits_match_their_actual_quarter_periods(self):
        for quarter, event, end in [('Q2', '2026-02-03', '2025-12-31'),
                                    ('Q3', '2026-05-06', '2026-03-31'),
                                    ('Q4', '2026-08-12', '2026-06-30')]:
            with self.subTest(quarter=quarter):
                row = parse_earnings_filing(document('AMCR-' + quarter, 'primary'), event,
                                            event, date(2026, 10, 26),
                                            exhibit=document('AMCR-' + quarter, 'exhibit'))
                self.assertEqual((row['date'], row['periodEnd']), (event, end))

    def test_snap_on_net_sales_excludes_financial_services_revenue(self):
        from official_metrics import parse_statement_metrics
        row = parse_statement_metrics(document('SNA', 'exhibit'), '2026-10-03',
                                      currency='USD', fiscal_year=2026, fiscal_quarter=3)
        self.assertEqual(row['epsGaapDiluted'], 4.64)
        self.assertIsNone(row['revenue'])

    def test_aep_release_can_leave_period_end_for_matching_quarterly_filing(self):
        row = parse_earnings_release(document('AEP', 'exhibit'), '2026-07-30',
                                     '2026-07-30', date(2026, 10, 26))
        self.assertEqual(row['date'], '2026-07-30')
        self.assertIsNone(row['periodEnd'])
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 2))

    def test_aep_quarter_is_admitted_only_with_matching_official_filing(self):
        from official_sync import check_issuer
        exhibit_url = SOURCES['AEP']['exhibit']['url']
        base = 'https://www.sec.gov/Archives/edgar/data/4904/'
        primary_url = base + '000000490426000055/aep-20260730.htm'
        filing_url = base + '000000490426000059/aep-20260630.htm'
        submissions = {'cik': 4904, 'filings': {'recent': {
            'form': ['8-K', '10-Q'], 'items': ['2.02,9.01', ''],
            'accessionNumber': ['0000004904-26-000055', '0000004904-26-000059'],
            'primaryDocument': ['aep-20260730.htm', 'aep-20260630.htm'],
            'filingDate': ['2026-07-30', '2026-07-30'],
            'reportDate': ['2026-07-30', '2026-06-30'],
        }}}
        filing = b'''<html><body>
          <ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">Q2</ix:nonNumeric>
          <ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-06-30</ix:nonNumeric>
        </body></html>'''
        def fetch(url):
            if url == primary_url:
                return b'<html><body><a href="a2q20268kpressreleaseex991.htm">Exhibit 99.1 Earnings release</a></body></html>'
            if url == exhibit_url:
                return document('AEP', 'exhibit')
            if url == filing_url:
                return filing
            if url == 'https://data.sec.gov/api/xbrl/companyfacts/CIK0000004904.json':
                return b'{"cik":4904,"facts":{}}'
            raise AssertionError(url)
        rows, _ = check_issuer('4904', submissions, fetch, date(2026, 10, 26), depth=1)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['date'], rows[0]['periodEnd']), ('2026-07-30', '2026-06-30'))
        self.assertEqual((rows[0]['fiscalYear'], rows[0]['fiscalQuarter']), (2026, 2))
        unmatched = {**submissions, 'filings': {'recent': {**submissions['filings']['recent'],
                     'reportDate': ['2026-07-30', '2026-03-31']}}}
        rejected, _ = check_issuer('4904', unmatched, fetch, date(2026, 10, 26), depth=1)
        self.assertEqual(rejected, [])

    def test_aos_release_preserves_fourth_quarter_identity_without_period_end(self):
        row = parse_earnings_release(document('AOS', 'exhibit'), '2026-01-29',
                                     '2026-01-29', date(2026, 10, 26))
        self.assertEqual(row['date'], '2026-01-29')
        self.assertIsNone(row['periodEnd'])
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2025, 4))

    def test_air_products_fiscal_2025_fourth_quarter_precedes_2026_guidance(self):
        row = parse_earnings_release(document('APD', 'exhibit'), '2025-11-06',
                                     '2025-11-06', date(2026, 10, 26))
        self.assertEqual(row['periodEnd'], '2025-09-30')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2025, 4))

    def test_republic_services_does_not_use_gross_tag_when_net_total_exists(self):
        from official_sources import parse_inline_quarter
        from official_metrics import parse_statement_metrics
        row=parse_inline_quarter(document('RSG','filing'),'2026-06-30',cik='1060391')
        self.assertIsNone(row['revenue'])
        statement=parse_statement_metrics(document('RSG','exhibit'),'2026-06-30',currency='USD',fiscal_year=2026,fiscal_quarter=2)
        self.assertEqual(statement['revenue'],4430000000)

    def test_republic_services_full_issuer_merge_corrects_old_gross_value(self):
        from official_sync import check_issuer
        old={'ticker':'RSG','periodEnd':'2026-06-30','fiscalYear':2026,'fiscalQuarter':2,
             'date':'2026-08-06','verifiedAt':'2026-10-24','revenue':5076000000,
             'revenueSourceUrl':SOURCES['RSG']['filing']['url']}
        submissions={'filings':{'recent':{
            'form':['8-K','10-Q'],'items':['2.02,9.01',''],
            'accessionNumber':['0001060391-26-000273','0001060391-26-000275'],
            'primaryDocument':['primary.htm','rsg-20260630.htm'],
            'filingDate':['2026-08-06','2026-08-07'],
            'reportDate':['2026-08-06','2026-06-30']}}}
        base='https://www.sec.gov/Archives/edgar/data/1060391/'
        def source(url):
            if url==base+'000106039126000273/primary.htm':
                return '<html><body>Item 2.02 Financial Results <a href="exhibit991q22026.htm">Exhibit 99.1 Earnings release</a></body></html>'
            if url==SOURCES['RSG']['exhibit']['url']:return document('RSG','exhibit')
            if url==SOURCES['RSG']['filing']['url']:return document('RSG','filing')
            raise AssertionError(url)
        rows,_=check_issuer('1060391',submissions,source,date(2026,10,25),known_records=[old],depth=5)
        self.assertEqual(rows[0]['revenue'],4430000000)
        self.assertEqual(rows[0]['revenueVerificationStatus'],'verified')
        self.assertEqual(rows[0]['metricCorrectionEvidence']['revenue']['oldValue'],5076000000)

    def test_conagra_fiscal_quarter_which_ended_on_preserves_fiscal_year(self):
        row=parse_earnings_release(document('CAG','exhibit'),'2026-09-30','2026-09-30',date(2026,10,24))
        self.assertEqual(row['periodEnd'],'2026-08-30')
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2027,1))

    def test_alexandria_nested_item_blocks_establish_original_publication(self):
        row = parse_earnings_filing(document('ARE', 'primary'), '2026-08-03', '2026-08-03',
                                   date(2026, 10, 24), exhibit=document('ARE', 'exhibit'))
        self.assertEqual(row['date'], '2026-08-03')
        self.assertEqual(row['periodEnd'], '2026-06-30')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 2))

    def test_citizens_publication_statement_does_not_turn_into_a_call_announcement(self):
        row = parse_earnings_filing(document('CFG', 'primary'), '2026-10-16', '2026-10-16',
                                   date(2026, 10, 24), exhibit=document('CFG', 'exhibit'))
        self.assertEqual(row['date'], '2026-10-16')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 3))

    def test_ge_explicit_quarter_ending_is_a_completed_period(self):
        row = parse_earnings_release(document('GE', 'exhibit'), '2026-10-20', '2026-10-20', date(2026, 10, 24))
        self.assertEqual(row['periodEnd'], '2026-09-30')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 3))


if __name__ == '__main__':
    unittest.main()
