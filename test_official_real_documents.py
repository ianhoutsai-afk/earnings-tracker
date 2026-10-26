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
