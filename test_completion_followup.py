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

class WrappedPublicationTests(unittest.TestCase):
 def test_line_wrap_inside_issuer_name(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, Example\nCompany issued a press release announcing financial results for the third quarter ended September 30, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-09-30','2026-10-14',TODAY)['date'],'2026-10-14')
 def test_us_abbreviation_is_not_a_sentence_boundary(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, U.S. Example issued a press release reporting financial results for the third quarter ended September 30, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['date'],'2026-10-14')
 def test_joint_fourth_quarter_and_fiscal_year(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, Example issued a press release regarding financial results for the fourth quarter and for the fiscal year ended September 30, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['periodEnd'],'2026-09-30')
 def test_posted_earnings_release_is_completed_publication(self):
  doc='<p>Item 2.02</p><p>The Third-Quarter 2026 Earnings Release furnished as Exhibit 99 was posted on the Company website on October 14, 2026.</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['fiscalQuarter'],3)
 def test_future_date_release_stays_rejected_after_wrapping(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, Example\nCompany issued a press release announcing the date of financial results for the third quarter ended September 30, 2026.</p><p>Item 9.01</p>'
  with self.assertRaises(ValueError):parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)

class ExplicitActualReleaseWithoutPeriodTests(unittest.TestCase):
 def test_dated_actuals_with_explicit_fiscal_identity_can_join_filing(self):
  from official_sources import parse_earnings_release
  doc='<h1>Example Reports Third Quarter 2026 Results</h1><p>October 14, 2026 - Example today announced financial results for the third quarter 2026. Revenue was $1.2 billion.</p>'
  r=parse_earnings_release(doc,'2026-10-14','2026-10-14',TODAY)
  self.assertEqual((r['date'],r['periodEnd'],r['fiscalYear'],r['fiscalQuarter']),('2026-10-14',None,2026,3))
 def test_schedule_with_identity_cannot_join_filing(self):
  from official_sources import parse_earnings_release
  doc='<h1>Example Announces Third Quarter 2026 Earnings Date</h1><p>October 14, 2026 - Example today announced financial results will be released next week.</p>'
  with self.assertRaises(ValueError):parse_earnings_release(doc,'2026-10-14','2026-10-14',TODAY)
 def test_issued_result_title_with_inc_abbreviation(self):
  doc='<p>Item 2.02</p><p>On October 14, 2026, Example Inc. issued a press release entitled “Example Inc. Reports Third Quarter Ended September 30, 2026 Financial and Operating Results.”</p><p>Item 9.01</p>'
  self.assertEqual(parse_earnings_filing(doc,'2026-10-14','2026-10-14',TODAY)['periodEnd'],'2026-09-30')

class FinalReviewRegressions(unittest.TestCase):
 def test_no_period_release_cannot_take_its_conference_call_date(self):
  from official_sources import parse_earnings_release
  doc='<h1>Example Reports Third Quarter 2026 Results</h1><p>October 13, 2026 - Example today announced financial results for the third quarter 2026. Revenue was $1.2 billion.</p><p>A conference call will take place October 14, 2026.</p>'
  with self.assertRaises(ValueError):parse_earnings_release(doc,'2026-10-14','2026-10-14',TODAY)
  self.assertEqual(parse_earnings_release(doc,'2026-10-13','2026-10-14',TODAY)['date'],'2026-10-13')

 def test_primary_publication_date_wins_over_later_exhibit_call(self):
  from official_sync import check_issuer
  from test_official_sync import SUBMISSIONS,fetch
  import copy
  submissions=copy.deepcopy(SUBMISSIONS)
  primary='<p>Item 2.02</p><p>On October 13, 2026, Example announced its financial results for the third quarter ended September 30, 2026.</p><p>Item 9.01</p><a href="ex991.htm">99.1</a>'
  exhibit='<h1>Example Reports Third Quarter 2026 Results</h1><p>October 13, 2026 - Example today announced financial results for the third quarter 2026. Revenue was $1.2 billion.</p><p>A conference call will take place October 14, 2026.</p>'
  def source(url):
   if url.endswith('results.htm'):return primary
   if url.endswith('ex991.htm'):return exhibit
   return fetch(url)
  rows,_=check_issuer('0000000001',submissions,source,TODAY)
  self.assertEqual(rows[0]['date'],'2026-10-13')
  self.assertEqual(rows[0]['periodEnd'],'2026-09-30')

 def test_adjusted_pro_forma_and_narrative_extensions_are_not_gaap_totals(self):
  base=RevenueTests()
  for title in ('NON-GAAP CONSOLIDATED STATEMENTS OF OPERATIONS','Unaudited Pro Forma Condensed Consolidated Statements of Income','Revenue recognized in the Consolidated Statements of Income is reconciled below:'):
   for tag in ('example:AdjustedRevenue','example:TotalRevenue','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax'):
    with self.subTest(title=title,tag=tag):
     self.assertIsNone(parse_inline_quarter(base.statement(heading=title,tag=tag),'2026-09-30')['revenue'])

 def test_adjusted_table_does_not_conflict_with_genuine_gaap_total(self):
  doc=RevenueTests().statement()
  adjusted=RevenueTests().statement(heading='NON-GAAP CONSOLIDATED STATEMENTS OF OPERATIONS',tag='example:AdjustedRevenue')
  extra=adjusted.split('<body>',1)[1].rsplit('</body>',1)[0].replace('1,200','1,500')
  self.assertEqual(parse_inline_quarter(doc.replace('</body>',extra+'</body>'),'2026-09-30')['revenue'],1200000000)

 def test_extension_tag_itself_cannot_claim_adjusted_revenue(self):
  self.assertIsNone(parse_inline_quarter(RevenueTests().statement(tag='example:AdjustedRevenue'),'2026-09-30')['revenue'])

 def test_authoritative_issuer_name_can_prefix_exact_gaap_heading(self):
  doc=RevenueTests().statement(heading='Example Inc. and subsidiaries consolidated statements of earnings')
  doc=doc.replace('<body>','<body><ix:nonNumeric name="dei:EntityRegistrantName">Example Inc.</ix:nonNumeric>')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['revenue'],1200000000)
