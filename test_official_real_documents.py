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
    def test_pentair_preliminary_results_are_not_completed_earnings(self):
        for event in ('2026-07-10','2026-07-14'):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    parse_earnings_release(document('PNR-preliminary','exhibit'),event,'2026-07-14',date(2026,10,28))
        with self.assertRaises(ValueError):
            parse_earnings_filing(document('PNR-preliminary','primary'),'2026-07-10','2026-07-14',date(2026,10,28),
                exhibit=document('PNR-preliminary','exhibit'))

    def test_preliminary_qualifier_after_results_is_still_excluded(self):
        mutated=document('PNR-preliminary','exhibit').replace(
            b'Provides Preliminary Second Quarter 2026 Financial Results',
            b'Provides Second Quarter 2026 Financial Results (Preliminary)')
        self.assertNotEqual(mutated,document('PNR-preliminary','exhibit'))
        for event in ('2026-07-10','2026-07-14'):
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    parse_earnings_release(mutated,event,'2026-07-14',date(2026,10,28))
        with self.assertRaises(ValueError):
            parse_earnings_filing(document('PNR-preliminary','primary'),'2026-07-10','2026-07-14',date(2026,10,28),exhibit=mutated)

    def test_current_preliminary_body_qualifier_cannot_hide_after_title(self):
        mutated=document('PNR-preliminary','exhibit').replace(b'Provides Preliminary',b'Provides')
        self.assertNotEqual(mutated,document('PNR-preliminary','exhibit'))
        with self.assertRaises(ValueError):
            parse_earnings_release(mutated,'2026-07-14','2026-07-14',date(2026,10,28))
        with self.assertRaises(ValueError):
            parse_earnings_filing(document('PNR-preliminary','primary'),'2026-07-10','2026-07-14',date(2026,10,28),exhibit=mutated)

    def test_keurig_second_quarter_does_not_borrow_first_quarter_date_from_notes(self):
        release=parse_earnings_release(document('KDP-Q2','exhibit'),'2026-08-06','2026-08-06',date(2026,10,28))
        self.assertNotEqual(release['periodEnd'],'2026-03-31')
        from official_sync import _parse_events
        source=SOURCES['KDP-Q2']
        filings=[{'form':'8-K','accessionNumber':'0001418135-26-000048','primaryDocument':'kdp-20260806.htm',
                  'filingDate':'2026-08-06','reportDate':'2026-08-06','items':'2.02,9.01'},
                 {'form':'10-Q','accessionNumber':'0001418135-26-000051','primaryDocument':'kdp-20260630.htm',
                  'filingDate':'2026-08-10','reportDate':'2026-06-30','items':''}]
        def fetch(url):
            for kind in ('primary','exhibit','filing'):
                if url==source[kind]['url']:return document('KDP-Q2',kind)
            raise OSError('Not in offline fixture')
        rows,status=_parse_events('1418135',filings,fetch,date(2026,10,28))
        self.assertEqual(status['requestFailures'],0)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['periodEnd'],rows[0]['fiscalQuarter']),('2026-06-30',2))
        self.assertEqual((rows[0]['epsGaapDiluted'],rows[0]['revenue']),(0.04,7309000000))

    def test_equivalent_numeric_and_named_dei_dates_keep_exact_issuer_metrics(self):
        from official_sources import parse_inline_quarter
        for ticker,cik,eps,revenue in (
            ('HII','1501585',5.27,3418000000),
            ('ETR','65984',1.03,3523638000),
            ('CTVA','1755672',1.73,6379000000),
            ('DLR','1297996',1.21,1924040000),
        ):
            with self.subTest(ticker=ticker):
                row=parse_inline_quarter(document(ticker+'-Q2-date','filing'),'2026-06-30',cik=cik)
                self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,2))
                self.assertEqual((row['epsGaapDiluted'],row['revenue']),(eps,revenue))

    def test_bxp_numeric_date_does_not_override_conflicting_fiscal_focus(self):
        from official_sources import parse_inline_quarter
        from official_sync import _parse_events
        source=SOURCES['BXP-Q2-date']
        row=parse_inline_quarter(document('BXP-Q2-date','filing'),'2026-06-30',cik='1037540')
        # The original 10-Q says FY; its release explicitly reports Q2.
        # Date normalization must not silently invent Q2 from a calendar month.
        self.assertEqual(row['fiscalQuarter'],4)
        filings=[{'form':'8-K','accessionNumber':'0001037540-26-000031','primaryDocument':'bxp-20260728.htm',
                  'filingDate':'2026-07-28','reportDate':'2026-07-28','items':'2.02,9.01'},
                 {'form':'10-Q','accessionNumber':'0001037540-26-000034','primaryDocument':'bxp-20260630.htm',
                  'filingDate':'2026-08-06','reportDate':'2026-06-30','items':''}]
        def fetch(url):
            for kind in ('primary','exhibit','filing'):
                if url==source[kind]['url']:return document('BXP-Q2-date',kind)
            raise OSError('Not in offline fixture')
        records,status=_parse_events('1037540',filings,fetch,date(2026,10,28))
        self.assertEqual(records,[])
        self.assertGreater(status['parsePending'],0)

    def test_genuinely_untagged_eps_retains_explicit_statement_fallback(self):
        from lxml import html
        from official_sources import parse_inline_quarter
        tree=html.fromstring(document('ABNB-Q2','filing'))
        tree.xpath('//*[@id="f-168"]')[0].drop_tag()
        row=parse_inline_quarter(html.tostring(tree),'2026-06-30',cik='1559720')
        self.assertEqual(row['epsGaapDiluted'],1.37)
        self.assertEqual(row['metricLocators']['epsGaapDiluted']['validationBasis'],'untagged_quarter_statement')

    def test_inline_statement_fallback_validates_the_selected_fact_itself(self):
        import copy
        from lxml import html,etree
        from official_sources import parse_inline_quarter,_desc
        for kind in ('ytd','unknown_context','wrong_issuer','dimension','shares','unknown_unit','missing_unit','format','scale','sign'):
            with self.subTest(kind=kind):
                tree=html.fromstring(document('ABNB-Q2','filing'))
                selected=tree.xpath('//*[@id="f-168"]')[0]
                if kind=='ytd':selected.set('contextref','c-1')
                elif kind=='unknown_context':selected.set('contextref','missing-context')
                elif kind in ('wrong_issuer','dimension'):
                    context=copy.deepcopy(tree.xpath('//*[@id="c-17"]')[0]);context.set('id','changed-context')
                    if kind=='wrong_issuer':_desc(context,'identifier')[0].text='9999999'
                    else:_desc(context,'entity')[0].append(etree.Element('{http://www.xbrl.org/2003/instance}segment'))
                    tree.append(context);selected.set('contextref','changed-context')
                elif kind=='shares':selected.set('unitref','shares')
                elif kind=='unknown_unit':selected.set('unitref','unknown-unit')
                elif kind=='missing_unit':selected.attrib.pop('unitref',None)
                elif kind=='format':selected.set('format','ixt:num-comma-decimal')
                elif kind=='scale':selected.set('scale','6')
                elif kind=='sign':selected.set('sign','-')
                row=parse_inline_quarter(html.tostring(tree),'2026-06-30',cik='1559720')
                self.assertIsNone(row['epsGaapDiluted'])

    def test_ameriprise_net_revenue_is_confirmed_by_statement_and_standard_tag(self):
        from official_sources import parse_inline_quarter
        row=parse_inline_quarter(document('AMP-Q2','filing'),'2026-06-30',cik='820027')
        self.assertEqual(row['revenue'],4940000000)
        evidence=row['metricDefinitionEvidence']['revenue']
        self.assertEqual(evidence['selectedTag'],'RevenuesNetOfInterestExpense')
        self.assertEqual(evidence['statementLocator']['label'],'Total net revenues')
        self.assertIn(5013000000,evidence['otherTaggedValues'])

    def test_constellation_statement_period_unlocks_attached_actual_metrics(self):
        from official_sync import check_issuer
        source=SOURCES['STZ-Q2']
        submissions={'filings':{'recent':{'form':['8-K','10-Q'],'items':['2.02,9.01',''],
            'accessionNumber':['0000016918-26-000039','0000016918-26-000040'],
            'primaryDocument':['stz-20261006.htm','stz-20260831.htm'],
            'filingDate':['2026-10-06','2026-10-07'],'reportDate':['2026-10-06','2026-08-31']}}}
        def fetch(url):
            for kind in ('primary','exhibit','filing','exhibit2'):
                if url==source[kind]['url']:return document('STZ-Q2',kind)
            if url.endswith('/CIK0000016918.json'):return b'{"cik":16918,"facts":{}}'
            raise AssertionError(url)
        rows,_=check_issuer('16918',submissions,fetch,date(2026,10,27),depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['epsGaapDiluted'],rows[0]['revenue']),(3.32,2633000000))
        self.assertEqual(rows[0]['epsSourceUrl'],source['exhibit']['url'])
        original=document('STZ-Q2','exhibit')
        wrong=original.replace(b'August 31',b'May 31')
        self.assertNotEqual(original,wrong)
        def wrong_period(url):return wrong if url==source['exhibit']['url'] else fetch(url)
        rejected,_=check_issuer('16918',submissions,wrong_period,date(2026,10,27),depth=1)
        self.assertFalse(any(r.get('epsGaapDiluted')==3.32 or r.get('revenue')==2633000000 for r in rejected))

    def test_simon_joint_venture_revenue_does_not_conflict_with_consolidated_total(self):
        from official_metrics import parse_statement_metrics
        row=parse_statement_metrics(document('SPG-Q2','exhibit'),'2026-06-30',currency='USD',
            fiscal_year=2026,fiscal_quarter=2)
        self.assertEqual(row['revenue'],1790598000)
        self.assertEqual(row['revenueVerificationStatus'],'verified')
        self.assertTrue(any(e['table']==12 and 'Joint Venture' in e['heading']
                            for e in row['excludedStatementTables']))

    def test_ross_future_first_quarter_guidance_does_not_replace_actual_fourth_quarter(self):
        row=parse_earnings_filing(document('ROST-Q4','primary'),'2026-03-03','2026-03-03',
            date(2026,10,27),exhibit=document('ROST-Q4','exhibit'))
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2025,4))

    def test_factset_headline_fiscal_year_precedes_prior_year_comparison(self):
        row=parse_earnings_release(document('FDS-Q4','exhibit'),'2025-09-18','2025-09-18',date(2026,10,27))
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2025,4))

    def test_new_boeing_quarter_can_use_dated_release_and_explicit_statement_end(self):
        from official_sync import check_issuer
        source=SOURCES['BA-Q3']
        submissions={'filings':{'recent':{'form':['8-K'],'items':['2.02,9.01'],
            'accessionNumber':['0001628280-26-067411'],'primaryDocument':['ba-20261027.htm'],
            'filingDate':['2026-10-27'],'reportDate':['2026-10-27']}}}
        def fetch(url):
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('BA-Q3',kind)
            raise AssertionError(url)
        rows,_=check_issuer('12927',submissions,fetch,date(2026,10,27),depth=1)
        self.assertEqual(len(rows),1)
        self.assertEqual((rows[0]['periodEnd'],rows[0]['fiscalYear'],rows[0]['fiscalQuarter']),('2026-09-30',2026,3))
        self.assertEqual(rows[0]['periodEndEvidence']['sourceUrl'],source['exhibit']['url'])

    def test_current_quarter_end_is_explicit_in_boeing_and_cms_tables(self):
        from official_metrics import discover_statement_period
        for ticker in ('BA-Q3','CMS-Q3'):
            with self.subTest(ticker=ticker):
                result=discover_statement_period(document(ticker,'exhibit'),'2026-10-27',2026,3)
                self.assertEqual(result['periodEnd'],'2026-09-30')
                self.assertTrue(result['locator']['header'])
        self.assertIsNone(discover_statement_period(document('BA-Q3','exhibit'),'2026-10-27',None,None))

    def test_kdp_word_quarter_header_does_not_select_annual_values(self):
        from official_metrics import parse_statement_metrics,_target_header
        row=parse_statement_metrics(document('KDP-Q4','exhibit'),'2025-12-31',currency='USD',
            fiscal_year=2025,fiscal_quarter=4)
        self.assertEqual((row['epsGaapDiluted'],row['revenue']),(0.26,4499000000))
        self.assertFalse(_target_header('Fourth Quarter and Full Year 2025','2025-12-31',2025,4))
        self.assertFalse(_target_header('Fourth Quarter and Full Fiscal Year 2025','2025-12-31',2025,4))
        self.assertFalse(_target_header('Fourth Quarter 2025 Guidance','2025-12-31',2025,4))
        self.assertFalse(_target_header('Fourth Quarter 2025 December 31, 2024','2025-12-31',2025,4))

    def test_abbott_eps_excluding_specified_items_is_not_gaap(self):
        from official_metrics import parse_statement_metrics
        row=parse_statement_metrics(document('ABT-Q2','exhibit'),'2026-06-30',currency='USD',
            fiscal_year=2026,fiscal_quarter=2)
        self.assertEqual(row['epsVerificationStatus'],'verified')
        self.assertEqual(row['epsGaapDiluted'],0.53)

    def test_tesla_released_actual_financial_results_attests_publication(self):
        row=parse_earnings_filing(document('TSLA-Q3','primary'),'2026-10-21','2026-10-21',
            date(2026,10,27),exhibit=document('TSLA-Q3','exhibit'))
        self.assertEqual((row['date'],row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),
                         ('2026-10-21','2026-09-30',2026,3))

    def test_tesla_future_release_does_not_attest_actual_publication(self):
        upcoming=document('TSLA-Q3','primary').replace(b'released its financial results',b'will release its financial results')
        with self.assertRaises(ValueError):
            parse_earnings_filing(upcoming,'2026-10-21','2026-10-21',date(2026,10,27),
                exhibit=document('TSLA-Q3','exhibit'))

    def test_monster_statement_layout_keeps_exact_quarter_values(self):
        from official_sources import parse_inline_quarter
        row=parse_inline_quarter(document('MNST-Q2','filing'),'2026-06-30',cik='865752')
        self.assertEqual(row['revenue'],2537473000)
        self.assertEqual(row['epsGaapDiluted'],0.59)

    def test_airbnb_current_revenue_right_of_comparative_retains_total_label(self):
        from official_sources import parse_inline_quarter
        row=parse_inline_quarter(document('ABNB-Q2','filing'),'2026-06-30',cik='1559720')
        self.assertEqual(row['revenue'],3608000000)
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,2))

    def test_airbnb_total_diluted_eps_comes_from_exact_quarter_statement(self):
        from official_sources import parse_inline_quarter
        row=parse_inline_quarter(document('ABNB-Q2','filing'),'2026-06-30',cik='1559720')
        self.assertEqual(row['epsGaapDiluted'],1.37)
        self.assertEqual(row['metricLocators']['epsGaapDiluted']['label'],'Diluted')

    def test_statement_fallback_cannot_bypass_issuer_context_match(self):
        from official_sources import parse_inline_quarter
        row=parse_inline_quarter(document('ABNB-Q2','filing'),'2026-06-30',cik='865752')
        self.assertIsNone(row['revenue'])
        self.assertIsNone(row['epsGaapDiluted'])

    def test_statement_fallback_cannot_relabel_euro_filing_as_us_dollars(self):
        from official_sources import parse_inline_quarter
        euro=document('ABNB-Q2','filing').replace(b'iso4217:USD',b'iso4217:EUR')
        row=parse_inline_quarter(euro,'2026-06-30',cik='1559720')
        self.assertIsNone(row['revenue'])
        self.assertIsNone(row['epsGaapDiluted'])

    def test_ea_guidance_column_does_not_conflict_with_actual_diluted_eps(self):
        from official_metrics import parse_statement_metrics
        result = parse_statement_metrics(document('EA-Q1', 'exhibit'), '2025-06-30',
                                         currency='USD', fiscal_year=2026, fiscal_quarter=1)
        self.assertEqual(result['epsVerificationStatus'], 'verified')
        self.assertEqual(result['epsGaapDiluted'], 0.79)

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
        # An image-backed supplemental page does not supply a consolidated
        # period header. The exact annual filing supplies that evidence below.
        self.assertEqual((row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),(None,2025,4))

    def test_scoped_release_period_uses_matching_real_annual_filing(self):
        from official_sync import _parse_events
        for key,exhibit_key,cik,end in (
            ('APD-Q4-scope','APD','2969','2025-09-30'),
            ('SYF-Q4-scope','SYF-Q4','1601712','2025-12-31')):
            with self.subTest(issuer=key):
                source=SOURCES[key];exhibit=SOURCES[exhibit_key]['exhibit']['url']
                filings=[source[kind]['metadata'] for kind in ('primary','filing')]
                def fetch(url):
                    if url==exhibit:return document(exhibit_key,'exhibit')
                    for kind in ('primary','filing'):
                        if url==source[kind]['url']:return document(key,kind)
                    raise OSError('Not in offline fixture')
                rows,_=_parse_events(cik,filings,fetch,date(2026,10,28))
                self.assertEqual(len(rows),1)
                self.assertEqual((rows[0]['periodEnd'],rows[0]['fiscalYear'],rows[0]['fiscalQuarter']),(end,2025,4))
                wrong=[filings[0],{**filings[1],'reportDate':'2025-06-30'}]
                rejected,_=_parse_events(cik,wrong,fetch,date(2026,10,28))
                self.assertEqual(rejected,[])

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
        # A segment table later in the exhibit cannot name a consolidated
        # quarter. Its matching original annual filing supplies the period.
        self.assertIsNone(row['periodEnd'])
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
