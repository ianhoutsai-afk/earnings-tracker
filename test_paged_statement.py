"""Registered page transcription must preserve the pictured quarter column."""
import copy
import unittest
from datetime import date
from pathlib import Path

from lxml import html
from official_metrics import parse_statement_metrics, discover_statement_period
from test_official_real_documents import document

ROOT = Path(__file__).parent


class PagedStatementTests(unittest.TestCase):
    def original(self):
        return document('ABNB-Q4-paged','exhibit')

    def mutated_page(self, transform):
        tree=html.fromstring(self.original())
        for p in tree.xpath('//p'):
            if ''.join(p.itertext()).startswith('Condensed Consolidated Statements of Operations'):
                transform(p)
        return html.tostring(tree)

    def replace(self, before, after):
        def change(p):
            for node in p.iter():
                if node.text and before in node.text:
                    node.text=node.text.replace(before,after)
        return self.mutated_page(change)

    def parsed(self, document=None, **kwargs):
        args=dict(currency='USD',fiscal_year=2025,fiscal_quarter=4)
        args.update(kwargs)
        return parse_statement_metrics(document or self.original(),'2025-12-31',**args)

    def test_real_picture_quarter_not_annual_or_weighted_shares(self):
        # Independently read from official shareholder letter, page 20.
        row=self.parsed()
        self.assertEqual(row['epsGaapDiluted'],0.56)
        self.assertEqual(row['revenue'],2778000000)
        self.assertEqual(row['metricLocators']['revenue']['column'],2)
        self.assertEqual(row['metricLocators']['revenue']['page'],20)
        self.assertEqual(row['metricLocators']['epsGaapDiluted']['label'],'Diluted')

    def test_explicit_quarter_identity_and_header_establish_period(self):
        row=discover_statement_period(self.original(),'2026-02-12',2025,4)
        self.assertIsNotNone(row)
        self.assertEqual(row['periodEnd'],'2025-12-31')
        self.assertEqual(row['locator']['page'],20)
        for year,quarter in ((2026,4),(2025,3),(None,4)):
            self.assertIsNone(discover_statement_period(self.original(),'2026-02-12',year,quarter))

    def test_values_come_from_selected_transcript_cells(self):
        changed=self.replace('$2,480 $2,778 $11,102 $12,241','$9,999 $3,123 $88,888 $77,777')
        changed=changed.replace(b'Diluted $0.73 $0.56 $4.11 $4.03',b'Diluted $9.99 $0.61 $8.88 $7.77')
        row=self.parsed(changed)
        self.assertEqual(row['revenue'],3123000000)
        self.assertEqual(row['epsGaapDiluted'],0.61)

    def test_unregistered_or_incompatible_page_layout_is_rejected(self):
        changes=(
            ('Three Months Ended Year Ended','Year Ended Three Months Ended'),
            ('December 31 December 31','September 30 December 31'),
            ('2024 2025 2024 2025','2025 2024 2024 2025'),
            ('2024 2025 2024 2025','2023 2025 2023 2025'),
            ('Condensed Consolidated Statements of Operations','Pro Forma Condensed Consolidated Statements of Operations'),
            ('Condensed Consolidated Statements of Operations','Condensed Consolidated Statements of Operations (Adjusted)'),
            ('in millions,','in thousands,'),
            ('Revenue $2,480 $2,778 $11,102 $12,241','Revenue $2,480 $2,778 $11,102'),
        )
        for old,new in changes:
            with self.subTest(new=new):
                doc=self.replace(old,new)
                self.assertNotEqual(doc,self.original())
                row=self.parsed(doc)
                self.assertIsNone(row['revenue'])
                self.assertIsNone(row['epsGaapDiluted'])
        for transform in (
            lambda p:p.getprevious().getparent().remove(p.getprevious()),
            lambda p:p.getprevious().xpath('.//img')[0].set('src','page19.jpg'),
            lambda p:p.set('style','font-size:12pt;color:black'),
            lambda p:p.addprevious(copy.deepcopy(p.getprevious())),
        ):
            with self.subTest(transform=transform):
                row=self.parsed(self.mutated_page(transform))
                self.assertIsNone(row['revenue'])
                self.assertIsNone(row['epsGaapDiluted'])

    def test_missing_eps_parent_never_borrows_weighted_average_diluted(self):
        for label in ('Adjusted net income per share attributable to Class A and Class B common',
                      'Net income from continuing operations per share attributable to Class A and Class B common',
                      'Weighted-average shares attributable to Class A and Class B common'):
            doc=self.replace('Net income per share attributable to Class A and Class B common',label)
            row=self.parsed(doc)
            self.assertIsNone(row['epsGaapDiluted'])
            self.assertEqual(row['revenue'],2778000000)

    def test_dollar_currency_and_target_identity_are_required(self):
        for args in ({'currency':None},{'currency':'EUR'},{'fiscal_year':2026},{'fiscal_quarter':3}):
            with self.subTest(args=args):
                row=self.parsed(**args)
                self.assertIsNone(row['revenue'])
                self.assertIsNone(row['epsGaapDiluted'])

    def test_later_adjusted_or_annual_scope_cannot_lend_eps(self):
        for prefix in ('Adjusted ','Year Ended ','Non-GAAP ','Segment '):
            with self.subTest(prefix=prefix):
                doc=self.replace('Net income $461 $341 $2,648 $2,511',prefix+'Net income $461 $341 $2,648 $2,511')
                doc=doc.replace(b'Diluted $0.73 $0.56 $4.11 $4.03',b'Diluted $0.73 $9.99 $4.11 $4.03')
                self.assertIsNone(self.parsed(doc)['epsGaapDiluted'])

    def test_duplicate_revenue_rows_are_ambiguous(self):
        for label in ('Revenue $2,480 $9,999 $11,102 $12,241',
                      'Revenue: $2,480 $9,999 $11,102 $12,241',
                      'Revenue 2,480 9,999 11,102 12,241'):
            with self.subTest(label=label):
                doc=self.replace('Costs and expenses:','Costs and expenses: '+label)
                self.assertIsNone(self.parsed(doc)['revenue'])

    def test_duplicate_statement_pages_are_not_silently_selected(self):
        def duplicate(p):
            p.addnext(copy.deepcopy(p))
            p.getnext().addprevious(copy.deepcopy(p.getprevious()))
        row=self.parsed(self.mutated_page(duplicate))
        self.assertIsNone(row['revenue'])
        self.assertIsNone(row['epsGaapDiluted'])

    def test_issuer_scan_uses_exact_release_transcript_with_matching_annual_identity(self):
        from official_sync import check_issuer
        prefix='https://www.sec.gov/Archives/edgar/data/1559720/'
        urls={prefix+'000119312526048670/d58192d8k.htm':'primary',
              prefix+'000119312526048670/d58192dex991.htm':'exhibit',
              prefix+'000155972026000004/abnb-20251231.htm':'filing'}
        records=[dict(form='8-K',items='2.02,9.01',accessionNumber='0001193125-26-048670',
            primaryDocument='d58192d8k.htm',filingDate='2026-02-12',reportDate='2026-02-12'),
            dict(form='10-K',items='',accessionNumber='0001559720-26-000004',
            primaryDocument='abnb-20251231.htm',filingDate='2026-02-12',reportDate='2025-12-31')]
        submissions={'filings':{'recent':{key:[r[key] for r in records] for key in records[0]}}}
        def fetch(url):
            if url not in urls:raise OSError('Outside fixture')
            return document('ABNB-Q4-paged',urls[url])
        rows,status=check_issuer('1559720',submissions,fetch,date(2026,10,28),depth=1)
        self.assertEqual(len(rows),1)
        row=rows[0]
        self.assertEqual((row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),('2025-12-31',2025,4))
        self.assertEqual(row['date'],'2026-02-12')
        self.assertEqual(row['epsGaapDiluted'],0.56)
        self.assertEqual(row['revenue'],2778000000)
        self.assertEqual(row['epsSourceUrl'],prefix+'000119312526048670/d58192dex991.htm')
        self.assertEqual(row['revenueSourceUrl'],row['epsSourceUrl'])
        self.assertEqual(row['metricStatementEvidence']['locator']['page'],20)


if __name__=='__main__':unittest.main()
