import copy
import json
import unittest
from issuer_mapping import fill_missing_ciks

class MappingTests(unittest.TestCase):
 def test_official_ticker_map_fills_missing_without_changing_existing_identity(self):
  companies=[{'ticker':'NEW','name':'New Co'},{'ticker':'OLD','name':'Old Co'}]
  mapping={'OLD':{'cik':'0000000007','name':'Old Co'}};before=copy.deepcopy(mapping)
  def fetch(url):return json.dumps({'0':{'ticker':'NEW','cik_str':123,'title':'New Co'},'1':{'ticker':'OLD','cik_str':999,'title':'Other'}})
  result=fill_missing_ciks(companies,{},mapping,fetch)
  self.assertEqual(result['NEW']['cik'],'0000000123')
  self.assertEqual(result['OLD'],mapping['OLD'])
  self.assertEqual(mapping,before)

 def test_legacy_filing_cik_requires_official_current_ticker_confirmation(self):
  companies=[{'ticker':'AVB','name':'AvalonBay'}]
  history={'AVB':[{'secUrl':'https://www.sec.gov/ix?doc=/Archives/edgar/data/915912/0001/doc.htm'}]}
  def good(url):return '{}' if '/files/' in url else json.dumps({'cik':915912,'tickers':['AVB'],'fiscalYearEnd':'1231'})
  self.assertEqual(fill_missing_ciks(companies,history,{},good)['AVB']['cik'],'0000915912')
  def bad(url):return '{}' if '/files/' in url else json.dumps({'cik':915912,'tickers':['OTHER']})
  self.assertNotIn('AVB',fill_missing_ciks(companies,history,{},bad))

 def test_unavailable_registry_does_not_invent_identifiers(self):
  def fail(url):raise OSError('source unavailable')
  self.assertEqual(fill_missing_ciks([{'ticker':'NEW'}],{}, {},fail),{})

class LegacyIssuerNameTests(unittest.TestCase):
 def test_exact_official_name_can_confirm_a_historical_issuer_without_current_ticker(self):
  history={'EA':[{'secUrl':'https://www.sec.gov/Archives/edgar/data/712515/0001/doc.htm'}]}
  def fetch(url):return '{}' if '/files/' in url else json.dumps({'cik':712515,'name':'ELECTRONIC ARTS INC.','tickers':[]})
  self.assertEqual(fill_missing_ciks([{'ticker':'EA','name':'Electronic Arts Inc.'}],history,{},fetch)['EA']['cik'],'0000712515')

class RenamedIssuerTests(unittest.TestCase):
 def test_sec_former_name_confirms_same_cik_and_exposes_changed_ticker(self):
  history={'EQR':[{'secUrl':'https://www.sec.gov/Archives/edgar/data/906107/0001/doc.htm'}]}
  def fetch(url):return '{}' if '/files/' in url else json.dumps({'cik':906107,'name':'VIVMARK RESIDENTIAL','tickers':['VMRK'],'formerNames':[{'name':'EQUITY RESIDENTIAL'}]})
  result=fill_missing_ciks([{'ticker':'EQR','name':'Equity Residential'}],history,{},fetch)
  self.assertEqual(result['EQR']['cik'],'0000906107')
  self.assertEqual(result['EQR']['officialTickers'],['VMRK'])
  self.assertEqual(result['EQR']['tickerStatus'],'historical_alias')
