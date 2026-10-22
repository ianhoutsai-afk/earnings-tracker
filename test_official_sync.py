import json
import tempfile
import unittest
from pathlib import Path
from datetime import date
from official_sync import sync_all
from test_official_sources import RELEASE, filing

TODAY=date(2026,10,22)
SUBMISSIONS={'filings':{'recent':{
 'form':['8-K','10-Q'], 'items':['2.02,9.01',''],
 'accessionNumber':['0000000001-26-000001','0000000001-26-000002'],
 'primaryDocument':['results.htm','quarter.htm'],
 'filingDate':['2026-10-15','2026-10-16'], 'reportDate':['2026-10-14','2026-09-30']}}}
BASE='https://www.sec.gov/Archives/edgar/data/1/'

def fetch(url):
 if '/submissions/' in url:return json.dumps(SUBMISSIONS)
 if url.endswith('/results.htm'):return '<html><body>Item 2.02. Financial Results <a href="ex991.htm">99.1 Earnings release</a></body></html>'
 if url.endswith('/ex991.htm'):return RELEASE
 if url.endswith('/quarter.htm'):return filing()
 raise ValueError('Unexpected URL')

class OfficialSyncTests(unittest.TestCase):
 def setup_root(self,root,companies=None,mapping=None):
  companies=companies or [{'ticker':'ABC'},{'ticker':'ABCA'}]
  history={c['ticker']:[dict(date=f'2025-0{i}-15',quarter=f'legacy-{i}',eps_reported='$9.99')] for c in [] for i in []}
  history={c['ticker']:[dict(date=f'2025-0{i}-15',quarter=f'legacy-{i}',eps_reported='$9.99') for i in range(1,6)] for c in companies}
  docs={'data.json':companies,'historical_data.json':history,'official_history.json':[], 'history_status.json':{},'sp500_mapping.json':mapping or {c['ticker']:{'cik':'0000000001'} for c in companies}}
  for name,data in docs.items():(root/name).write_text(json.dumps(data))
  return history

 def test_shared_cik_checked_once_and_new_quarter_replaces_one_old_row(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root);calls=[]
   def tracked(url):calls.append(url);return fetch(url)
   result=sync_all(root,TODAY,fetch=tracked,full=True)
   h=json.loads((root/'historical_data.json').read_text())
   self.assertEqual(result['issuersChecked'],1)
   self.assertEqual(sum('/submissions/' in u for u in calls),1)
   self.assertEqual(len(h['ABC']),5)
   self.assertEqual(h['ABC'][0]['date'],'2026-10-14')
   self.assertEqual(h['ABC'][0]['filingDate'],'2026-10-16')
   self.assertEqual(h['ABC'][0]['eps_reported'],'$1.25')
   self.assertEqual(h['ABC'][0]['fiscalQuarter'],3)
   self.assertEqual(h['ABC'],h['ABCA'])
   before=(root/'historical_data.json').read_text()
   sync_all(root,TODAY,fetch=tracked,full=True)
   self.assertEqual((root/'historical_data.json').read_text(),before)

 def test_source_failure_preserves_values_and_publishes_failure_for_each_company(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root)
   def fail(url):raise OSError('sensitive transport details should not appear in public status')
   result=sync_all(root,TODAY,fetch=fail,full=True)
   h=json.loads((root/'historical_data.json').read_text());s=json.loads((root/'history_status.json').read_text())
   self.assertEqual(len(h['ABC']),5)
   self.assertEqual(h['ABC'][0]['eps_reported'],'$9.99')
   self.assertEqual(result['sourceFailures'],1)
   self.assertEqual(s['ABC']['status'],'official_source_failed')
   self.assertNotIn('sensitive',json.dumps(s))

 def test_new_release_with_missing_metrics_does_not_copy_legacy_adjusted_values(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root)
   def missing(url):
    if url.endswith('/quarter.htm'):raise ValueError('Unsupported layout')
    return fetch(url)
   sync_all(root,TODAY,fetch=missing,full=True)
   h=json.loads((root/'historical_data.json').read_text())
   self.assertEqual(h['ABC'][0]['date'],'2026-10-14')
   self.assertEqual(h['ABC'][0]['eps_reported'],'-')

 def test_missing_mapping_is_explicit_and_does_not_drop_company(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root,mapping={'ABC':{'cik':'0000000001'}})
   sync_all(root,TODAY,fetch=fetch,full=True)
   s=json.loads((root/'history_status.json').read_text())
   self.assertEqual(s['ABCA']['status'],'official_mapping_missing')
   self.assertEqual(len(s),2)

 def test_failed_exhibit_never_evicts_a_quarter(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root)
   def bad(url):return '<html>not earnings</html>' if url.endswith('ex991.htm') else fetch(url)
   sync_all(root,TODAY,fetch=bad,full=True)
   h=json.loads((root/'historical_data.json').read_text());s=json.loads((root/'history_status.json').read_text())
   self.assertEqual(h['ABC'][0]['date'],'2025-05-15')
   self.assertEqual(s['ABC']['status'],'official_parse_pending')

 def test_hourly_mode_still_checks_stale_or_undated_companies(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);self.setup_root(root)
   sync_all(root,TODAY,fetch=fetch,full=False)
   self.assertEqual(json.loads((root/'history_status.json').read_text())['ABC']['officialCheckedAt'][:10],'2026-10-22')

if __name__=='__main__':unittest.main()
