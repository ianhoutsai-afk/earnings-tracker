import unittest
from lxml import html

from official_metrics import parse_statement_metrics
from test_official_real_documents import document


class RegisteredNetIncomeNarrativeTests(unittest.TestCase):
    def parse(self,body,**changes):
        options=dict(currency='USD',fiscal_year=2026,fiscal_quarter=3,issuer_cik='1014473')
        options.update(changes)
        end=options.pop('period_end','2026-09-30')
        try:return parse_statement_metrics(body,end,**options)
        except TypeError as exc:self.fail('Issuer-bound narrative parsing is missing: '+str(exc))

    def test_five_original_net_income_sentences_match_the_current_statement_period(self):
        for end,year,q,eps in [('2026-09-30',2026,3,2.35),('2026-06-30',2026,2,2.38),
                ('2026-03-31',2026,1,2.34),('2025-12-31',2025,4,2.23),('2025-09-30',2025,3,2.27)]:
            with self.subTest(period=end):
                row=self.parse(document('VRSN-net-eps-'+end,'exhibit'),period_end=end,fiscal_year=year,fiscal_quarter=q)
                self.assertEqual(row['epsGaapDiluted'],eps)
                self.assertEqual(row['epsVerificationStatus'],'verified')
                self.assertEqual(row['metricLocators']['epsGaapDiluted']['basis'],'net_income')
                self.assertIn('Verisign reported net income',row['metricLocators']['epsGaapDiluted']['text'])

    def test_wrong_issuer_period_identity_and_currency_do_not_use_narrative(self):
        body=document('VRSN-net-eps-2026-09-30','exhibit')
        for changes in ({'issuer_cik':None},{'issuer_cik':'1381197'},{'period_end':'2026-06-30'},
                {'fiscal_year':2025},{'fiscal_quarter':2},{'currency':'EUR'}):
            with self.subTest(changes=changes):self.assertIsNone(self.parse(body,**changes)['epsGaapDiluted'])

    def test_adjusted_comparative_and_annual_clauses_do_not_become_net_quarter_eps(self):
        body=document('VRSN-net-eps-2026-09-30','exhibit')
        for old,new in ((b'Verisign reported net income',b'Verisign reported adjusted net income'),
                (b'Verisign reported net income',b'Previously, Verisign reported net income'),
                (b'Verisign reported net income',b'Verisign expects net income'),
                (b'Verisign reported net income',b'Another company reported net income'),
                (b'for the third quarter of 2026, compared',b'for the full year of 2026, compared'),
                (b'for the third quarter of 2026, compared',b'for the third quarter of 2025, compared')):
            changed=body.replace(old,new)
            self.assertNotEqual(body,changed)
            with self.subTest(new=new):self.assertIsNone(self.parse(changed)['epsGaapDiluted'])

    def test_narrative_without_a_matching_consolidated_statement_remains_pending(self):
        tree=html.fromstring(document('VRSN-net-eps-2026-09-30','exhibit'))
        for table in tree.xpath('//table'):table.drop_tree()
        self.assertIsNone(self.parse(html.tostring(tree))['epsGaapDiluted'])

    def test_preceding_scope_cannot_turn_adjusted_foreign_or_segment_eps_into_target(self):
        for qualifier in ('The following financial measures are adjusted and non-GAAP. ',
                'The following amounts are expressed in Canadian dollars. ',
                'The following results are for a segment rather than the consolidated company. '):
            tree=html.fromstring(document('VRSN-net-eps-2026-09-30','exhibit'))
            nodes=tree.xpath('//*[contains(text(),"Verisign reported net income")]')
            self.assertEqual(len(nodes),1)
            nodes[0].text=nodes[0].text.replace('Verisign reported net income',qualifier+'Verisign reported net income')
            with self.subTest(qualifier=qualifier):
                self.assertIsNone(self.parse(html.tostring(tree))['epsGaapDiluted'])

    def test_conflicting_current_net_income_clauses_are_quarantined(self):
        body=document('VRSN-net-eps-2026-09-30','exhibit')
        tree=html.fromstring(body)
        node=tree.xpath('//*[contains(text(),"Verisign reported net income")]')[0]
        extra='<div>'+node.text.replace('$2.35','$9.99')+'</div>'
        node.getparent().addnext(html.fromstring(extra))
        row=self.parse(html.tostring(tree))
        self.assertIsNone(row['epsGaapDiluted'])
        self.assertEqual(row['epsVerificationStatus'],'conflict')
        self.assertEqual({e['value'] for e in row['metricConflicts']['epsGaapDiluted']},{2.35,9.99})

    def test_current_clause_suffix_and_all_explicit_foreign_units_are_checked(self):
        body=document('VRSN-net-eps-2026-09-30','exhibit')
        for suffix in ('on an adjusted basis','for the segment','expressed in EUR'):
            old=b'of $2.35 for the third quarter of 2026, compared'
            changed=body.replace(old,('of $2.35 for the third quarter of 2026, '+suffix+', compared').encode())
            self.assertNotEqual(changed,body)
            with self.subTest(suffix=suffix):self.assertIsNone(self.parse(changed)['epsGaapDiluted'])
        tree=html.fromstring(body)
        node=tree.xpath('//*[contains(text(),"Verisign reported net income")]')[0]
        node.text=node.text.replace('Verisign reported net income','The following amounts are expressed in EUR. Verisign reported net income')
        self.assertIsNone(self.parse(html.tostring(tree))['epsGaapDiluted'])

    def test_parent_and_heading_scope_survives_nested_paragraphs_and_empty_nodes(self):
        for scope in ('Adjusted non-GAAP financial measures:',
                'The following amounts are expressed in EUR.',
                'The following amounts are expressed in KWD.',
                'Financial results for the segment:'):
            tree=html.fromstring(document('VRSN-net-eps-2026-09-30','exhibit'))
            font=tree.xpath('//*[contains(text(),"Verisign reported net income")]')[0]
            div=font.getparent()
            div.remove(font)
            div.text=scope
            p=html.Element('p');p.append(font);div.append(p)
            with self.subTest(parentScope=scope):self.assertIsNone(self.parse(html.tostring(tree))['epsGaapDiluted'])
        tree=html.fromstring(document('VRSN-net-eps-2026-09-30','exhibit'))
        div=tree.xpath('//*[contains(text(),"Verisign reported net income")]')[0].getparent()
        heading=html.Element('h2');heading.text='Adjusted non-GAAP financial measures';div.addprevious(heading)
        for _ in range(3):div.addprevious(html.HtmlComment('layout marker'))
        self.assertIsNone(self.parse(html.tostring(tree))['epsGaapDiluted'])
