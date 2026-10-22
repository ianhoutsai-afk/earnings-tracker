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
