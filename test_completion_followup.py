"""Quarterly completeness regressions; numeric values below are synthetic."""
import unittest
from datetime import date
from official_sources import parse_earnings_filing, parse_inline_quarter
from test_official_sources import filing
TODAY=date(2026,11,4)
class PublicationTests(unittest.TestCase):
 def test_toc_before_actual_item(self):
  doc='<p>Item 2.02 Results</p><p>Item 9.01 Exhibits</p><p>Item 2.02 Results</p><p>On October 14, 2026, Example reported financial results for the third quarter ended September 30, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['periodEnd'],'2026-09-30')
 def test_setting_forth_results(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, Example issued a press release setting forth its results of operations for the quarter ended September 30, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['periodEnd'],'2026-09-30')
class RevenueTests(unittest.TestCase):
 def statement(self,heading='CONSOLIDATED STATEMENTS OF OPERATIONS',label='Total revenues',tag='us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  fact=original.replace('us-gaap:Revenues',tag)
  return filing().replace(original,'<div>'+heading+'</div><div><!-- SEC comment --><table><tr><td>'+label+'</td><td>'+fact+'</td></tr></table></div>')
 def test_comment_is_not_a_statement_boundary(self):
  self.assertEqual(parse_inline_quarter(self.statement(),'2026-09-30')['revenue'],1200000000)
 def test_extension_total(self):
  self.assertEqual(parse_inline_quarter(self.statement(tag='example:TotalRevenue'),'2026-09-30')['revenue'],1200000000)
 def test_note_component_and_wrong_currency_rejected(self):
  for doc in (self.statement(heading='Note 2. Revenue',tag='example:TotalRevenue'),self.statement(label='Service revenue',tag='example:TotalRevenue'),self.statement(tag='example:TotalRevenue').replace('iso4217:USD','iso4217:EUR')):
   with self.subTest(doc=doc[-100:]):self.assertIsNone(parse_inline_quarter(doc,'2026-09-30')['revenue'])
 def test_reviewed_heading_orders_and_customer_sales_label(self):
  for heading,label in [('Consolidated Condensed Statements of Operations','Net revenue'),('Statements of Consolidated Earnings','TOTAL REVENUES'),('Condensed Consolidated Income Statements','Total revenue'),('Consolidated Statements of Comprehensive Income','Total revenue'),('Consolidated Statements of Earnings','Sales to customers (Note 9)')]:
   with self.subTest(heading=heading):self.assertEqual(parse_inline_quarter(self.statement(heading,label),'2026-09-30')['revenue'],1200000000)
