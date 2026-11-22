import unittest
from datetime import date
from official_sources import parse_earnings_release, parse_inline_quarter, normalize_proxy_base

TODAY=date(2026,10,22)
RELEASE='''<html><body><h1>Example reports third quarter 2026 financial results</h1><p>NEW YORK, October 14, 2026 — Example today reported results for the third quarter ended September 30, 2026.</p><p>Adjusted EPS $9.99. The release has no tagged GAAP facts.</p></body></html>'''


def filing(extra='', quarter='Q3'):
 return f'''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>
 <ix:nonNumeric name="dei:DocumentFiscalYearFocus">2026</ix:nonNumeric>
 <ix:nonNumeric name="dei:DocumentFiscalPeriodFocus">{quarter}</ix:nonNumeric>
 <ix:nonNumeric name="dei:DocumentPeriodEndDate">2026-09-30</ix:nonNumeric>
 <xbrli:context id="q"><xbrli:entity><xbrli:identifier>1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2026-07-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="ytd"><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-09-30</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
 <xbrli:unit id="perShare"><xbrli:divide><xbrli:unitNumerator><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unitNumerator><xbrli:unitDenominator><xbrli:measure>xbrli:shares</xbrli:measure></xbrli:unitDenominator></xbrli:divide></xbrli:unit>
 <ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="q" unitRef="perShare">1.25</ix:nonFraction>
 <ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>
 <ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="ytd" unitRef="perShare">4.00</ix:nonFraction>{extra}</body></html>'''


class OfficialParserTests(unittest.TestCase):
 def test_release_date_is_explicit_in_original_release_not_filing_date(self):
  r=parse_earnings_release(RELEASE,'2026-10-14','2026-10-15',TODAY)
  self.assertEqual((r['date'],r['periodEnd'],r['fiscalYear'],r['fiscalQuarter']),('2026-10-14','2026-09-30',2026,3))
  self.assertNotIn('epsGaapDiluted',r)

 def test_fiscal_year_and_fourth_quarter_headlines_take_precedence_over_comparatives(self):
  for title in ('Reports Fiscal 2026 Full-Year and Fourth Quarter Results',
                'Reports Fourth Quarter and Fiscal 2026 Results',
                'Reports Fourth Fiscal Quarter and Full Fiscal Year 2026 Results'):
   with self.subTest(title=title):
    doc = (f'<h1>Example {title}</h1><p>October 14, 2026. Example reported results '
           'for the fourth quarter ended September 30, 2026.</p>'
           '<p>Fourth quarter 2025 results included a lower prior-year total.</p>')
    row = parse_earnings_release(doc,'2026-10-14','2026-10-15',TODAY)
    self.assertEqual((row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),('2026-09-30',2026,4))

 def test_item_202_pairs_completed_quarter_with_exhibit_highlights(self):
  from official_sources import parse_earnings_filing
  for quarter, cumulative, event, end, number in (
      ('Second', 'six', 'February 3, 2026', 'December 31, 2025', 2),
      ('Third', 'nine', 'May 6, 2026', 'March 31, 2026', 3)):
   with self.subTest(quarter=quarter):
    primary = (
        '<h2>Item 2.02 Results of Operations</h2>'
        f'<p>On {event}, the Company issued a press release regarding financial results '
        f'for the {quarter.lower()} quarter and first {cumulative} months of fiscal year 2026.</p>'
        '<h2>Item 9.01 Financial Statements and Exhibits</h2>'
        '<p>See the prior Quarterly Report for the quarter ended June 30, 2025.</p>')
    exhibit = (
        f'<h1>Example Reports Solid {quarter} Quarter Results and Updates Fiscal 2026 Guidance</h1>'
        f'<p>Highlights - Three Months Ended {end}</p>')
    filed = '2026-02-03' if number == 2 else '2026-05-06'
    result = parse_earnings_filing(primary, filed, filed, TODAY, exhibit=exhibit)
    expected_date = date(2026, 2, 3) if number == 2 else date(2026, 5, 6)
    expected_end = date(2025, 12, 31) if number == 2 else date(2026, 3, 31)
    self.assertEqual(result, {'date':expected_date.isoformat(), 'periodEnd':expected_end.isoformat(),
                              'fiscalYear':2026, 'fiscalQuarter':number})
    wrong_exhibit = exhibit.replace(f'{quarter} Quarter', 'First Quarter')
    with self.assertRaises(ValueError):
     parse_earnings_filing(primary, filed, filed, TODAY, exhibit=wrong_exhibit)

 def test_item_202_can_identify_three_and_twelve_months_after_earliest_event(self):
  from official_sources import parse_earnings_filing
  primary = ('<h2>Item 2.02 Results of Operations</h2><p>On October 14, 2026, the Company '
             'issued a press release announcing its results for the three and twelve months ended September 30, 2026.</p>')
  row = parse_earnings_filing(primary,'2026-10-10','2026-10-15',TODAY,
                              exhibit='<h1>Example Reports Fourth Quarter and Fiscal 2026 Results</h1>')
  self.assertEqual((row['date'],row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),
                   ('2026-10-14','2026-09-30',2026,4))

 def test_dated_results_with_quarter_before_results_can_join_matching_filing(self):
  text = ('<h1>Example reports third-quarter results</h1>'
          '<p>MELBOURNE, Fla., October 14, 2026 — Example reported its third quarter 2026 results.</p>')
  result = parse_earnings_release(text, '2026-10-14', '2026-10-15', TODAY)
  self.assertEqual((result['periodEnd'],result['fiscalYear'],result['fiscalQuarter']), (None,2026,3))
  for other in (text.replace('reported','will report'), text.replace('2026 results','2026 results date')):
   with self.assertRaises(ValueError):
    parse_earnings_release(other, '2026-10-14', '2026-10-15', TODAY)

 def test_unconfirmed_event_date_does_not_become_release_date(self):
  with self.assertRaises(ValueError):parse_earnings_release(RELEASE,'2026-10-13','2026-10-15',TODAY)

 def test_period_only_and_future_announcements_are_rejected(self):
  for doc in [RELEASE.replace('October 14, 2026',''),RELEASE.replace('September 30, 2026',''),RELEASE.replace('October 14, 2026','November 14, 2026')]:
   with self.assertRaises(ValueError):parse_earnings_release(doc,'2026-10-14','2026-10-15',TODAY)

 def test_quarterly_gaap_uses_exact_dimensionless_contexts_and_units(self):
  r=parse_inline_quarter(filing(),'2026-09-30')
  self.assertEqual(r['epsGaapDiluted'],1.25)
  self.assertEqual(r['revenue'],1200000000)
  self.assertEqual(r['periodStart'],'2026-07-01')
  self.assertEqual((r['fiscalYear'],r['fiscalQuarter']),(2026,3))

 def test_inline_diluted_eps_allows_omitted_leading_zero(self):
  for attributes, number, expected in [('', '0.24', 0.24), ('', '.24', 0.24),
                                        (' sign="-"', '.24', -0.24), ('', '.', None)]:
   with self.subTest(attributes=attributes, number=number):
    document = filing().replace('>1.25</ix:nonFraction>', f'{attributes}>{number}</ix:nonFraction>')
    self.assertEqual(parse_inline_quarter(document, '2026-09-30')['epsGaapDiluted'], expected)

 def test_vylor_quarter_keeps_carve_out_sales_and_excludes_corteva_eps(self):
  document = filing('<ix:nonNumeric name="dei:EntityCentralIndexKey">0002128626</ix:nonNumeric>')
  document = document.replace('>1</xbrli:identifier>', '>0002128626</xbrli:identifier>')
  document = document.replace('>1.25</ix:nonFraction>', ' sign="-">0.85</ix:nonFraction>')
  for cik in ('2128626', None):
   with self.subTest(cik=cik):
    parsed = parse_inline_quarter(document, '2026-09-30', cik=cik)
    self.assertEqual((parsed['revenue'], parsed['periodStart']), (1200000000, '2026-07-01'))
    self.assertIsNone(parsed['epsGaapDiluted'])
  post_separation = document.replace('2026-09-30', '2026-12-31').replace('2026-07-01', '2026-10-01').replace('>Q3<', '>FY<')
  self.assertEqual(parse_inline_quarter(post_separation, '2026-12-31', '2128626')['epsGaapDiluted'], -0.85)

 def test_standard_revenue_tag_on_explicit_segment_row_is_not_consolidated_total(self):
  fact='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  segment='<table><tr><td>Hybrid Cloud segment net revenues</td><td>'+fact+'</td></tr></table>'
  self.assertIsNone(parse_inline_quarter(filing().replace(fact,segment),'2026-09-30')['revenue'])

 def test_keycorp_uses_gaap_components_in_place_of_taxable_equivalent_revenue(self):
  total = '<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  def row(label, tag, number, context='q'):
   return (f'<tr><td>{label}</td><td><ix:nonFraction name="us-gaap:{tag}" '
           f'contextRef="{context}" unitRef="usd" scale="6">{number}</ix:nonFraction></td></tr>')
  taxable_equivalent = f'<table><tr><td>Total revenue (TE) (a)</td><td>{total}</td></tr></table>'
  net_interest = row('NET INTEREST INCOME', 'InterestIncomeExpenseNet', '730')
  noninterest = row('Total noninterest income', 'NoninterestIncome', '462')
  annual = row('Total noninterest income', 'NoninterestIncome', '1,386', 'ytd')
  doc = filing().replace('>1</xbrli:identifier>', '>91576</xbrli:identifier>')
  for components, expected in ((net_interest + noninterest + annual, 1_192_000_000),
                               (net_interest + annual, None)):
   with self.subTest(expected=expected):
    statement = f'<table>{components}</table>'
    parsed = parse_inline_quarter(doc.replace(total, statement + taxable_equivalent), '2026-09-30', cik='91576')
    self.assertEqual(parsed['revenue'], expected)
    self.assertEqual(parsed['epsGaapDiluted'], 1.25)

 def test_nonzero_eps_scale_requires_independent_reconciliation(self):
  exact_eps = 'name="us-gaap:EarningsPerShareDiluted" contextRef="q" unitRef="perShare"'
  doc = filing().replace(exact_eps + '>1.25', exact_eps + ' scale="3" sign="-">0.10')
  parsed = parse_inline_quarter(doc,'2026-09-30')
  self.assertIsNone(parsed['epsGaapDiluted'])
  self.assertEqual(parsed['revenue'],1200000000)

 def test_us_bancorp_does_not_use_taxable_equivalent_net_revenue(self):
  total = '<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  headline = f'<table><tr><td>Total net revenue</td><td>{total}</td></tr></table>'
  components = (
      '<table><tr><td>Net interest income</td><td><ix:nonFraction name="us-gaap:InterestIncomeExpenseNet" '
      'contextRef="q" unitRef="usd" scale="6">730</ix:nonFraction></td></tr>'
      '<tr><td>Total noninterest income</td><td><ix:nonFraction name="us-gaap:NoninterestIncome" '
      'contextRef="q" unitRef="usd" scale="6">442</ix:nonFraction></td></tr></table>'
  )
  document = filing().replace('>1</xbrli:identifier>', '>36104</xbrli:identifier>')
  for statement, revenue in [(components, 1_172_000_000), ('', None)]:
   with self.subTest(revenue=revenue):
    result = parse_inline_quarter(document.replace(total, headline + statement), '2026-09-30', cik='36104')
    self.assertEqual(result['revenue'], revenue)
    self.assertEqual(result['epsGaapDiluted'], 1.25)

 def test_truist_rebuilds_net_revenue_from_quarter_statement_components(self):
  total = '<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  components = (
      '<table><tr><td>Net Interest Income</td><td><ix:nonFraction name="us-gaap:InterestIncomeExpenseNet" '
      'contextRef="q" unitRef="usd" scale="6">3,629</ix:nonFraction></td></tr>'
      '<tr><td>Total noninterest income</td><td><ix:nonFraction name="us-gaap:NoninterestIncome" '
      'contextRef="q" unitRef="usd" scale="6">1,558</ix:nonFraction></td></tr></table>'
  )
  document = filing().replace(total, components).replace('>1</xbrli:identifier>', '>92230</xbrli:identifier>')
  result = parse_inline_quarter(document, '2026-09-30', cik='92230')
  self.assertEqual(result['revenue'], 5_187_000_000)

 def test_ytd_or_annual_eps_cannot_be_used_as_q4(self):
  doc=filing(quarter='FY').replace('contextRef="q"','contextRef="ytd"')
  r=parse_inline_quarter(doc,'2026-09-30')
  self.assertEqual(r['fiscalQuarter'],4)
  self.assertIsNone(r['epsGaapDiluted'])
  self.assertIsNone(r['revenue'])

 def test_segment_fact_and_wrong_currency_are_rejected(self):
  doc=filing().replace('<xbrli:identifier>1</xbrli:identifier>','<xbrli:identifier>1</xbrli:identifier><xbrli:segment><xbrldi:explicitMember>Segment</xbrldi:explicitMember></xbrli:segment>')
  self.assertIsNone(parse_inline_quarter(doc,'2026-09-30')['epsGaapDiluted'])
  doc=filing().replace('iso4217:USD','iso4217:EUR')
  self.assertIsNone(parse_inline_quarter(doc,'2026-09-30')['epsGaapDiluted'])
  self.assertIsNone(parse_inline_quarter(doc,'2026-09-30')['revenue'])

 def test_conflicting_quarterly_gaap_contexts_remain_missing(self):
  extra='<ix:nonFraction name="us-gaap:EarningsPerShareDiluted" contextRef="q" unitRef="perShare">2.00</ix:nonFraction>'
  self.assertIsNone(parse_inline_quarter(filing(extra),'2026-09-30')['epsGaapDiluted'])

 def test_document_period_end_normalizes_equivalent_date_spellings(self):
  doc=filing().replace('>2026-09-30</ix:nonNumeric>',
      '>SEPTEMBER 30, 2026</ix:nonNumeric><ix:nonNumeric name="dei:DocumentPeriodEndDate">September 30, 2026</ix:nonNumeric>')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['periodEnd'],'2026-09-30')
  with self.assertRaises(ValueError):
   parse_inline_quarter(doc.replace('>September 30, 2026</','>September 29, 2026</'),'2026-09-30')

 def test_document_identity_must_match_period_end(self):
  with self.assertRaises(ValueError):parse_inline_quarter(filing(),'2026-06-30')

 def test_document_period_end_honors_explicit_numeric_date_transform(self):
  doc=filing().replace('name="dei:DocumentPeriodEndDate">2026-09-30',
      'name="dei:DocumentPeriodEndDate" format="ixt:date-month-day-year">9/30/2026')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['periodEnd'],'2026-09-30')
  for changed in (doc.replace('9/30/2026','9/29/2026'),
                  doc.replace('date-month-day-year','date-day-month-year'),
                  doc.replace(' format="ixt:date-month-day-year"','')):
   with self.assertRaises(ValueError):parse_inline_quarter(changed,'2026-09-30')

 def test_numeric_document_period_end_may_use_short_year_and_spaced_separators(self):
  original = 'name="dei:DocumentPeriodEndDate">2026-09-30'
  transformed = 'name="dei:DocumentPeriodEndDate" format="ixt:date-month-day-year">'
  for raw in ('9/30/26', '09/30 /2026'):
   with self.subTest(raw=raw):
    doc = filing().replace(original, transformed + raw)
    self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['periodEnd'],'2026-09-30')
    with self.assertRaises(ValueError):
     parse_inline_quarter(doc, '1926-09-30')
  for raw in ('9/31/26', '9/30/026'):
   with self.assertRaises(ValueError):
    parse_inline_quarter(filing().replace(original, transformed + raw), '2026-09-30')

 def test_document_period_end_follows_explicit_continuation(self):
  doc=filing().replace('name="dei:DocumentPeriodEndDate">2026-09-30',
      'name="dei:DocumentPeriodEndDate" continuedAt="date-year">September 30,')
  doc=doc.replace('</body>', '<ix:continuation id="date-year">2026</ix:continuation></body>')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['periodEnd'],'2026-09-30')
  for changed in (doc.replace('id="date-year"','id="other"'),
                  doc.replace('id="date-year"','id="date-year" continuedAt="date-year"')):
   with self.assertRaises(ValueError):parse_inline_quarter(changed,'2026-09-30')

 def test_proxy_scheme_is_normalized_without_leaking_bad_input(self):
  self.assertEqual(normalize_proxy_base(' sec-proxy.example.workers.dev/ '),'https://sec-proxy.example.workers.dev')
  for value in ['http://unsafe.test','https://user:secret@host.test','https://host.test/?secret=abc','not a hostname','https://host.test/private/path']:
   with self.assertRaisesRegex(ValueError,'Invalid SEC proxy configuration') as exc:normalize_proxy_base(value)
   self.assertNotIn(value,str(exc.exception))

if __name__=='__main__':unittest.main()

class SecTransportTests(unittest.TestCase):
 def test_transport_normalizes_proxy_and_archive_path(self):
  from unittest.mock import patch
  from update_data import _sec_request
  with patch('update_data.SEC_PROXY_URL','sec-proxy.example.workers.dev'), patch('update_data.requests') as requests:
   request = requests.get
   _sec_request('https://www.sec.gov/Archives/edgar/data/1/results.htm')
   self.assertEqual(request.call_args.args[0], 'https://sec-proxy.example.workers.dev/archives/edgar/data/1/results.htm')

 def test_invalid_proxy_fails_before_a_network_request(self):
  from unittest.mock import patch
  from update_data import _sec_request
  with patch('update_data.SEC_PROXY_URL','https://user:secret@invalid.test'), patch('update_data.requests') as requests:
   request = requests.get
   with self.assertRaises(ValueError): _sec_request('https://data.sec.gov/submissions/CIK0000000001.json')
   request.assert_not_called()

class OfficialEncodingTests(unittest.TestCase):
 def test_real_sec_xml_encoding_declarations_are_accepted(self):
  prefix='<?xml version="1.0" encoding="UTF-8"?>'
  self.assertEqual(parse_inline_quarter(prefix+filing(),'2026-09-30')['epsGaapDiluted'],1.25)
  self.assertEqual(parse_earnings_release(prefix+RELEASE,'2026-10-14','2026-10-15',TODAY)['date'],'2026-10-14')

class OfficialDateTransformTests(unittest.TestCase):
 def test_inline_dei_formatted_month_date_is_normalized(self):
  doc=filing().replace('name="dei:DocumentPeriodEndDate">2026-09-30','name="dei:DocumentPeriodEndDate" format="ixt:date-monthname-day-year-en">September 30 , 2026')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['fiscalQuarter'],3)

class OfficialFallbackTests(unittest.TestCase):
 def test_broken_proxy_can_fall_back_to_same_public_sec_document(self):
  from unittest.mock import patch,Mock
  from official_sync import fetch_sec
  stream=Mock();stream.read.return_value=b'<html>official</html>'
  context=Mock();context.__enter__=Mock(return_value=stream);context.__exit__=Mock(return_value=False)
  with patch('official_sync._DIRECT_SEC',False),patch('update_data.SEC_PROXY_URL','https://proxy.example'),patch('update_data._sec_request',return_value=Mock(status_code=404)),patch('official_sync.urlopen',return_value=context) as direct:
   self.assertEqual(fetch_sec('https://www.sec.gov/Archives/edgar/data/1/report.htm'),b'<html>official</html>')
   self.assertEqual(direct.call_args.args[0].full_url,'https://www.sec.gov/Archives/edgar/data/1/report.htm')

 def test_transport_error_does_not_leak_proxy_details(self):
  from unittest.mock import patch
  from official_sync import fetch_sec
  with patch('official_sync._DIRECT_SEC',False),patch('update_data._sec_request',side_effect=OSError('secret-value')),patch('official_sync.urlopen',side_effect=OSError('other-secret')):
   with self.assertRaises(OSError) as error:fetch_sec('https://data.sec.gov/submissions/CIK0000000001.json')
   self.assertNotIn('secret',str(error.exception))

class OfficialComparativeIdentityTests(unittest.TestCase):
 def test_full_year_headline_beats_prior_year_comparative_text(self):
  doc='<h1>Accenture Reports Fourth-Quarter and Full-Year Fiscal 2026 Results</h1><p>NEW YORK; October 1, 2026 — reported results for the fourth quarter and full fiscal year ended August 31, 2026. All comparisons are to the fourth quarter of fiscal 2025.</p>'
  result=parse_earnings_release(doc,'2026-10-01','2026-10-01',TODAY)
  self.assertEqual((result['fiscalYear'],result['fiscalQuarter']),(2026,4))

class OfficialCommentTests(unittest.TestCase):
 def test_sec_html_comments_do_not_abort_quarter_parsing(self):
  doc=filing().replace('<body>','<body><!-- SEC filing comment -->')
  self.assertEqual(parse_inline_quarter(doc,'2026-09-30')['epsGaapDiluted'],1.25)

class RevenueScopeTests(unittest.TestCase):
 def test_standard_revenue_component_is_not_a_consolidated_total(self):
  for tag in ['RevenueNotFromContractWithCustomer','RevenueFromContractWithCustomerExcludingAssessedTax']:
   doc=filing().replace('us-gaap:Revenues','us-gaap:'+tag)
   self.assertIsNone(parse_inline_quarter(doc,'2026-09-30')['revenue'])

class ConsolidatedContractRevenueTests(unittest.TestCase):
 def test_republic_services_uses_unaudited_consolidated_revenue_instead_of_segment_gross(self):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  consolidated=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
  gross=original.replace('1,200','1,400')
  statement=('<div>UNAUDITED CONSOLIDATED STATEMENTS OF INCOME</div>'
             '<div>(in millions, except per share data)</div>'
             '<div><span> </span><table><tr><td>Revenue</td><td>$</td><td>'+consolidated+'</td></tr></table>'
             '<span>The accompanying notes are an integral part of these statements.</span></div>')
  note='<div>Note 12. Segment Reporting</div><table><tr><td>Gross revenue</td><td>'+gross+'</td></tr></table>'
  for html, expected in ((statement+note,1200000000),(note,None)):
   with self.subTest(has_statement=expected is not None):
    doc=filing().replace('<xbrli:identifier>1</xbrli:identifier>','<xbrli:identifier>1060391</xbrli:identifier>')
    self.assertEqual(parse_inline_quarter(doc.replace(original,html),'2026-09-30','1060391')['revenue'],expected)

 def test_wrapped_consolidated_statement_total_is_not_lost(self):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  fact=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
  statement='<div>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)</div><div>(In millions)</div><div></div><div><table><tr><td>Total net sales</td><td>'+fact+'</td></tr></table></div>'
  self.assertEqual(parse_inline_quarter(filing().replace(original,statement),'2026-09-30')['revenue'],1200000000)

 def test_statement_heading_cannot_leak_into_a_later_note_table(self):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  fact=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
  note='<div>CONSOLIDATED STATEMENTS OF OPERATIONS</div><div><table><tr><td>Net income</td><td>100</td></tr></table></div><div>Note 2. Revenue recognition</div><div><table><tr><td>Total revenues</td><td>'+fact+'</td></tr></table></div>'
  self.assertIsNone(parse_inline_quarter(filing().replace(original,note),'2026-09-30')['revenue'])

 def test_direct_note_text_inside_wrapper_blocks_heading_inheritance(self):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  fact=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
  note='<div>CONSOLIDATED STATEMENTS OF OPERATIONS</div><div>Note 2. Revenue recognition<table><tr><td>Total revenues</td><td>'+fact+'</td></tr></table></div>'
  self.assertIsNone(parse_inline_quarter(filing().replace(original,note),'2026-09-30')['revenue'])

 def test_contract_revenue_requires_consolidated_statement_total_row(self):
  original='<ix:nonFraction name="us-gaap:Revenues" contextRef="q" unitRef="usd" scale="6">1,200</ix:nonFraction>'
  fact=original.replace('us-gaap:Revenues','us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax')
  table='<table><caption>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS</caption><tr><td>Total revenues</td><td>'+fact+'</td></tr></table>'
  self.assertEqual(parse_inline_quarter(filing().replace(original,table),'2026-09-30')['revenue'],1200000000)
  mixed=filing().replace(original,table).replace('</body>','<ix:nonFraction name="us-gaap:RevenueNotFromContractWithCustomer" contextRef="q" unitRef="usd">100</ix:nonFraction></body>')
  self.assertIsNone(parse_inline_quarter(mixed,'2026-09-30')['revenue'])

class OfficialLegacyEncodingTests(unittest.TestCase):
 def test_cp1252_sec_documents_preserve_ascii_facts(self):
  document=('<?xml version="1.0" encoding="UTF-8"?>'+filing().replace('<body>','<body><p>Company’s quarterly statement</p>')).encode('cp1252')
  self.assertEqual(parse_inline_quarter(document,'2026-09-30')['epsGaapDiluted'],1.25)

class CompressedSecBodyTests(unittest.TestCase):
 def test_compressed_official_json_and_cached_html_are_decoded(self):
  import gzip
  from official_sync import decode_sec_body
  body=b'{"cik":123}'
  self.assertEqual(decode_sec_body(gzip.compress(body)),body)
  self.assertEqual(decode_sec_body(body),body)

class EntityContextTests(unittest.TestCase):
 def test_another_registrants_context_cannot_supply_the_issuers_values(self):
  doc=filing().replace('<xbrli:identifier>1</xbrli:identifier>','<xbrli:identifier>2</xbrli:identifier>')
  self.assertIsNone(parse_inline_quarter(doc,'2026-09-30',cik='0000000001')['epsGaapDiluted'])

class CompletedQuarterWordingTests(unittest.TestCase):
 def test_completed_results_can_use_quarter_ending_in_publication_sentence(self):
  doc = '''<html><h1>Example Releases Fourth Quarter Fiscal 2026 Results</h1>
  <p>August 12, 2026 — Example today reported its financial results for the fourth quarter ending June 30, 2026.</p>
  <p>Net earnings are presented for the year and compared with the quarter ended June 30, 2025.</p></html>'''
  result = parse_earnings_release(doc,'2026-08-12','2026-08-12',date(2026,11,14))
  self.assertEqual(result, {'date':'2026-08-12','periodEnd':'2026-06-30','fiscalYear':2026,'fiscalQuarter':4})

 def test_second_quarter_and_first_half_are_anchored_to_the_completed_period(self):
  doc = """<html><h1>Example reports first half fiscal 2026 results</h1>
  <p>December 4, 2025 — Example Corporation reported financial results for its second quarter
  and first half of fiscal 2026, ended October 31, 2025.</p>
  <p>Earlier results for the quarter ended April 30, 2025 were previously reported.</p></html>"""
  row=parse_earnings_release(doc,'2025-12-04','2025-12-04',TODAY)
  self.assertEqual((row['periodEnd'],row['fiscalYear'],row['fiscalQuarter']),('2025-10-31',2026,2))

 def test_release_schedule_using_quarter_ending_is_rejected(self):
  doc = '''<html><h1>Example Schedules Fourth Quarter Fiscal 2026 Results</h1>
  <p>August 12, 2026 — Example will report its financial results for the fourth quarter ending June 30, 2026.</p></html>'''
  with self.assertRaises(ValueError):
   parse_earnings_release(doc,'2026-08-12','2026-08-12',date(2026,11,14))
