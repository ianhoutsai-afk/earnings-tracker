import copy
import json
import tempfile
import unittest
from pathlib import Path
from official_sync import check_issuer, sync_all
from test_official_sync import SUBMISSIONS, TODAY, fetch, OfficialSyncTests


class DiscoveryProgressTests(unittest.TestCase):
    def test_completed_quarter_is_revisited_when_amended_report_arrives(self):
        from test_official_sources import filing
        rows,details=check_issuer('1',SUBMISSIONS,fetch,TODAY)
        amended=copy.deepcopy(SUBMISSIONS)
        for key,value in {'form':'10-Q/A','items':'','accessionNumber':'0000000001-26-000099',
            'primaryDocument':'amended.htm','filingDate':'2026-10-20','reportDate':'2026-09-30'}.items():amended['filings']['recent'][key].append(value)
        def source(url):
            if url.endswith('amended.htm'):return filing().replace('>1.25<','>2.50<')
            return fetch(url)
        result,info=check_issuer('1',amended,source,TODAY,progress=details['backfillProgress'],known_records=rows)
        self.assertGreater(info['attemptedAnnouncements'],0)
        self.assertEqual(result[0]['epsVerificationStatus'],'conflict')

    def test_source_failure_does_not_starve_other_issuers_historical_work(self):
        from unittest.mock import patch
        calls=[]
        def inspect(cik,submissions,transport,today,**kwargs):
            calls.append((cik,kwargs['depth']))
            if cik.endswith('1'):raise OSError('source unavailable')
            return [],dict(parsePending=0,metricPending=0,requestFailures=0,sourceErrors=[],
                candidates=[],deferred=False,discoveryComplete=True,backfillProgress={'parserVersion':2,'completedAccessions':[],'filings':[]})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);OfficialSyncTests().setup_root(root,mapping={'ABC':{'cik':'1'},'ABCA':{'cik':'2'}})
            with patch('official_sync.check_issuer',side_effect=inspect):sync_all(root,TODAY,fetch=lambda u:json.dumps(SUBMISSIONS),full=True)
        self.assertIn(('0000000002',5),calls)
        self.assertNotIn(('0000000001',5),calls)

    def test_new_quarterly_filing_retries_previously_unresolved_release(self):
        from test_official_sources import RELEASE, filing
        first=copy.deepcopy(SUBMISSIONS)
        for values in first['filings']['recent'].values():del values[1:]
        # A release with no explicit period end cannot be admitted until the filing appears.
        def source(url):
            if url.endswith('results.htm'):return '<h2>Item 2.02 Results of Operations</h2><p>On October 14, 2026, Example issued a press release announcing its earnings for the third quarter of fiscal year 2026.</p><a href="ex991.htm">99.1 Earnings release</a>'
            if url.endswith('ex991.htm'):return RELEASE.replace('September 30, 2026','the accompanying statements')
            return fetch(url)
        rows,details=check_issuer('1',first,source,TODAY)
        self.assertEqual(rows,[])
        rows,details=check_issuer('1',SUBMISSIONS,source,TODAY,progress=details['backfillProgress'])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['epsGaapDiluted'],1.25)

    def test_relevant_history_is_not_truncated_at_five_supplement_files(self):
        submission=copy.deepcopy(SUBMISSIONS)
        submission['filings']['recent']={}
        submission['filings']['files']=[{'name':f'CIK0000000001-submissions-{i:03}.json',
            'filingFrom':'2026-09-01', 'filingTo':'2026-10-20'} for i in range(6)]
        calls=[]
        def source(url):
            calls.append(url)
            if '-submissions-' in url:
                return json.dumps(SUBMISSIONS['filings']['recent'] if '-005.' in url else {})
            return fetch(url)
        rows, details=check_issuer('1',submission,source,TODAY)
        self.assertEqual(len(rows),1)
        self.assertEqual(sum('-submissions-' in u for u in calls),6)
        self.assertIn('backfillProgress',details)

    def test_budget_interruption_keeps_accepted_rows_and_remaining_source_cursor(self):
        from official_sync import OfficialScanDeferred
        submission=copy.deepcopy(SUBMISSIONS)
        recent=submission['filings']['recent']
        for key,value in {'form':'8-K','items':'2.02','accessionNumber':'0000000001-26-000003',
            'primaryDocument':'older.htm','filingDate':'2026-07-15','reportDate':'2026-07-14'}.items():recent[key].append(value)
        def source(url):
            if url.endswith('older.htm'):raise OfficialScanDeferred('budget')
            return fetch(url)
        rows,details=check_issuer('1',submission,source,TODAY)
        self.assertEqual(len(rows),1)
        self.assertTrue(details['deferred'])
        self.assertIn('0000000001-26-000001',details['backfillProgress']['completedAccessions'])
        self.assertTrue(any(r['primaryDocument']=='older.htm' for r in details['backfillProgress']['filings']))

    def test_all_issuer_latest_passes_precede_any_historical_pass(self):
        from unittest.mock import patch
        calls=[]
        def inspect(cik,submissions,transport,today,**kwargs):
            calls.append((cik,kwargs.get('depth',5)))
            return [],dict(parsePending=0,metricPending=0,requestFailures=0,sourceErrors=[],
                           candidates=[],deferred=False,discoveryComplete=True,
                           backfillProgress={'parserVersion':2,'completedAccessions':[],'filings':[]})
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            OfficialSyncTests().setup_root(root,mapping={'ABC':{'cik':'1'},'ABCA':{'cik':'2'}})
            with patch('official_sync.check_issuer',side_effect=inspect):
                sync_all(root,TODAY,fetch=lambda u:json.dumps(SUBMISSIONS),full=True)
            self.assertEqual([depth for _,depth in calls[:2]],[1,1])
            self.assertEqual([depth for _,depth in calls[2:]],[5,5])
            statuses=json.loads((root/'history_status.json').read_text())
            self.assertEqual(statuses['ABC']['sourceCheck']['state'],'checked')
            self.assertIn('auditAsOf',statuses['ABC']['backfillProgress'])

    def test_global_limiter_spaces_requests_and_retries(self):
        from official_sync import SecLimiter
        now=[0.0]; starts=[]
        limiter=SecLimiter(clock=lambda:now[0],sleep=lambda s:now.__setitem__(0,now[0]+s))
        for _ in range(8):
            limiter.wait();starts.append(now[0])
        self.assertTrue(all(b-a>=0.19999 for a,b in zip(starts,starts[1:])))


if __name__=='__main__':unittest.main()
