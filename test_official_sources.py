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

 def test_document_identity_must_match_period_end(self):
  with self.assertRaises(ValueError):parse_inline_quarter(filing(),'2026-06-30')

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
