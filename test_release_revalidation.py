import copy
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from official_sources import parse_earnings_filing, parse_earnings_release
from official_sync import check_issuer, sync_all
from test_official_real_documents import document, SOURCES

TODAY=date(2026,10,28)


class NonActualReleaseTests(unittest.TestCase):
    def test_actual_release_can_also_discuss_unfinalized_future_outlook(self):
        body='''<html><h1>Example Reports Third Quarter 2026 Results</h1>
            <p>October 14, 2026. Example today reported third-quarter 2026 earnings results
            for the quarter ended September 30, 2026.</p>
            <p>Example announced today updates to management's current financial outlook for next year.
            Those future estimates are subject to finalization of the financial reporting process.</p></html>'''
        row=parse_earnings_release(body,'2026-10-14','2026-10-14',TODAY)
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,3))
        row=parse_earnings_release(body.replace('Example today reported','Example noted prior estimates. Example today reported'),
            '2026-10-14','2026-10-14',TODAY)
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,3))

    def test_non_actual_primary_cannot_be_readmitted_through_filing_fallback(self):
        body='''<html>Item 2.02 Results of Operations.
            On October 7, 2026, Example announced financial results for the third quarter of 2026
            ended September 30, 2026. This information is intended only to provide additional
            information regarding current estimates management believes will affect results.
            Actual results are subject to finalization of the financial reporting process.
            Item 9.01 Exhibits.</html>'''
        with self.assertRaises(ValueError):
            parse_earnings_filing(body,'2026-10-07','2026-10-07',TODAY)

    def test_explicit_unfinalized_estimates_and_outlook_cannot_supply_release(self):
        for group,event in (('APA-estimate','2026-10-07'),('STZ-outlook','2025-09-02')):
            with self.subTest(group=group):
                with self.assertRaises(ValueError):
                    parse_earnings_release(document(group,'exhibit'),event,event,TODAY)
                with self.assertRaises(ValueError):
                    parse_earnings_filing(document(group,'primary'),event,event,TODAY,
                        exhibit=document(group,'exhibit'))

    def test_positive_original_source_counterevidence_revokes_stored_candidate(self):
        source=SOURCES['APA-estimate'];old=dict(ticker='APA',periodEnd='2026-09-30',
            fiscalYear=2026,fiscalQuarter=3,date='2026-10-07',verifiedAt='2026-10-28',
            periodScope='quarter',currency='USD',epsGaapDiluted=None,revenue=None,
            releaseSourceUrl=source['primary']['url'],releaseAccession='0001841666-26-000058')
        event=dict(form='8-K',accessionNumber='0001841666-26-000058',primaryDocument='apa8k-20261007.htm',
            filingDate='2026-10-07',reportDate='2026-10-07',items='2.02,9.01')
        submissions={'filings':{'recent':{k:[v] for k,v in event.items()}}}
        def fetch(url):
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('APA-estimate',kind)
            raise OSError('Outside fixture')
        before=copy.deepcopy(old)
        rows,details=check_issuer('1841666',submissions,fetch,TODAY,known_records=[old])
        self.assertEqual(rows,[])
        evidence=details['releaseInvalidations'][0]
        self.assertEqual(evidence['originalRecord'],before)
        self.assertEqual(evidence['reason'],'unfinalized_quarter_estimates')
        self.assertEqual(evidence['sourceUrl'],source['exhibit']['url'])
        self.assertEqual(evidence['sourceSha256'],source['exhibit']['sha256'])
        self.assertEqual(old,before)
        self.assertTrue(details['discoveryComplete'])
        self.assertEqual(len(details['candidates']),1)

    def test_unsupported_layout_is_not_positive_counterevidence(self):
        old=dict(ticker='ABC',periodEnd='2026-06-30',fiscalYear=2026,fiscalQuarter=2,
            date='2026-07-28',releaseSourceUrl='https://www.sec.gov/Archives/edgar/data/1/2/ex991.htm',
            epsGaapDiluted=1.23,revenue=123000000)
        rows,details=check_issuer('1',{'filings':{'recent':{}}},lambda u:b'<html>Unrecognized layout</html>',
            TODAY,known_records=[old])
        self.assertEqual(rows,[old])
        self.assertFalse(details.get('releaseInvalidations'))

    def test_unavailable_original_source_preserves_data_and_reports_failure(self):
        source=SOURCES['APA-estimate']['primary']['url']
        old=dict(ticker='ABC',periodEnd='2026-06-30',fiscalYear=2026,fiscalQuarter=2,
            date='2026-07-28',releaseSourceUrl=source,
            epsGaapDiluted=1.23,revenue=123000000)
        def fetch(url):raise OSError('Unavailable')
        rows,details=check_issuer('1841666',{'filings':{'recent':{}}},fetch,TODAY,known_records=[old])
        self.assertEqual(rows,[old])
        self.assertGreater(details['requestFailures'],0)
        self.assertFalse(details['discoveryComplete'])

    def test_changed_reviewed_document_requires_review_and_cannot_revoke(self):
        source=SOURCES['APA-estimate']
        old=dict(ticker='APA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-07',releaseSourceUrl=source['primary']['url'],epsGaapDiluted=1.23,revenue=123000000)
        for changed in ('primary','exhibit'):
            def fetch(url):
                for kind in ('primary','exhibit'):
                    if url==source[kind]['url']:
                        return document('APA-estimate',kind)+(b'<!-- modified source -->' if kind==changed else b'')
                raise OSError('Outside fixture')
            with self.subTest(changed=changed):
                rows,details=check_issuer('1841666',{'filings':{'recent':{}}},fetch,TODAY,known_records=[old])
                self.assertEqual(rows,[old])
                self.assertFalse(details.get('releaseInvalidations'))
                self.assertFalse(details['discoveryComplete'])

    def test_identical_counterevidence_at_an_unreviewed_url_cannot_revoke(self):
        source=SOURCES['APA-estimate']
        unknown=source['primary']['url'].replace('apa8k-20261007.htm','unreviewed.htm')
        old=dict(ticker='APA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-07',releaseSourceUrl=unknown,epsGaapDiluted=1.23,revenue=123000000)
        def fetch(url):
            return document('APA-estimate','exhibit' if url==source['exhibit']['url'] else 'primary')
        rows,details=check_issuer('1841666',{'filings':{'recent':{}}},fetch,TODAY,known_records=[old])
        self.assertEqual(rows,[old])
        self.assertFalse(details.get('releaseInvalidations'))

    def test_revalidation_failure_is_retried_with_the_saved_cursor(self):
        source=SOURCES['APA-estimate']
        old=dict(ticker='APA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-07',releaseSourceUrl=source['primary']['url'],epsGaapDiluted=None,revenue=None)
        def unavailable(url):raise OSError('Unavailable')
        _,first=check_issuer('1841666',{'filings':{'recent':{}}},unavailable,TODAY,known_records=[old])
        def recovered(url):
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('APA-estimate',kind)
            raise OSError('Outside fixture')
        rows,second=check_issuer('1841666',{'filings':{'recent':{}}},recovered,TODAY,
            known_records=[old],progress=first['backfillProgress'])
        self.assertEqual(rows,[])
        self.assertEqual(len(second['releaseInvalidations']),1)

    def test_unrelated_outlook_attachment_does_not_revoke_actual_release(self):
        url='https://www.sec.gov/Archives/edgar/data/1/2/8k.htm'
        primary='<html>Item 2.02 Results <a href="ex991.htm">99.1 Earnings release</a><a href="outlook.htm">Press release</a></html>'
        old=dict(ticker='ABC',periodEnd='2026-06-30',fiscalYear=2026,fiscalQuarter=2,
            date='2026-07-28',releaseSourceUrl=url,epsGaapDiluted=1.23,revenue=123000000)
        def fetch(source):
            if source==url:return primary
            if source.endswith('outlook.htm'):return document('STZ-outlook','exhibit')
            return b'<html>Completed net income results</html>'
        rows,details=check_issuer('1',{'filings':{'recent':{}}},fetch,TODAY,known_records=[old])
        self.assertEqual(rows,[old])
        self.assertFalse(details.get('releaseInvalidations'))

    def test_bundle_revalidation_preserves_other_quarters_and_repeat_evidence(self):
        source=SOURCES['APA-estimate']
        bad=dict(ticker='APA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-07',verifiedAt='2026-10-28',periodScope='quarter',currency='USD',
            epsGaapDiluted=None,revenue=None,releaseSourceUrl=source['primary']['url'],
            releaseAccession='0001841666-26-000058')
        old={**bad,'periodEnd':'2026-06-30','fiscalQuarter':2,'date':'2026-08-05',
            'epsGaapDiluted':2.11,'epsBasis':'GAAP diluted','revenue':2373000000,
            'releaseSourceUrl':'https://www.sec.gov/Archives/edgar/data/1841666/older/ex991.htm',
            'releaseAccession':'older'}
        event=dict(form='8-K',accessionNumber='0001841666-26-000058',primaryDocument='apa8k-20261007.htm',
            filingDate='2026-10-07',reportDate='2026-10-07',items='2.02,9.01')
        submissions={'filings':{'recent':{k:[v] for k,v in event.items()}}}
        def fetch(url):
            if '/submissions/' in url:return json.dumps(submissions)
            if url==old['releaseSourceUrl']:return '<html>Unsupported older actual statement</html>'
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('APA-estimate',kind)
            raise OSError('Outside fixture')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in {'data.json':[{'ticker':'APA'}],'historical_data.json':{'APA':[]},
                    'official_history.json':[bad,old],'history_status.json':{},
                    'sp500_mapping.json':{'APA':{'cik':'0001841666'}}}.items():
                (root/name).write_text(json.dumps(value))
            summary=sync_all(root,TODAY,fetch=fetch,full=True)
            self.assertTrue(summary['healthy'])
            history=json.loads((root/'historical_data.json').read_text())
            self.assertEqual([r['periodEnd'] for r in history['APA']],['2026-06-30'])
            self.assertEqual(history['APA'][0]['eps_reported'],'$2.11')
            status=json.loads((root/'history_status.json').read_text())['APA']
            self.assertEqual(status['latestQuarter']['state'],'pending_identity')
            self.assertEqual(status['releaseInvalidations'][0]['originalRecord'],bad)
            self.assertEqual(len(json.loads((root/'official_history.json').read_text())),1)
            sync_all(root,TODAY,fetch=fetch,full=True)
            self.assertEqual(json.loads((root/'historical_data.json').read_text()),history)
            self.assertEqual(json.loads((root/'history_status.json').read_text())['APA']['releaseInvalidations'],
                status['releaseInvalidations'])

    def test_each_alias_keeps_its_own_original_values_and_evidence_when_revoked(self):
        source=SOURCES['APA-estimate']
        first=dict(ticker='AAA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-07',verifiedAt='2026-10-28',periodScope='quarter',currency='USD',
            epsGaapDiluted=None,revenue=None,releaseSourceUrl=source['primary']['url'])
        second={**first,'ticker':'AAB','epsGaapDiluted':4.56,'epsBasis':'GAAP diluted',
            'revenue':999000000,'aliasEvidence':{'document':'AAB-only'}}
        def fetch(url):
            if '/submissions/' in url:return json.dumps({'filings':{'recent':{}}})
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('APA-estimate',kind)
            raise OSError('Outside fixture')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in {'data.json':[{'ticker':'AAA'},{'ticker':'AAB'}],
                    'historical_data.json':{'AAA':[],'AAB':[]},'official_history.json':[first,second],
                    'history_status.json':{},'sp500_mapping.json':{'AAA':{'cik':'0001841666'},'AAB':{'cik':'0001841666'}}}.items():
                (root/name).write_text(json.dumps(value))
            sync_all(root,TODAY,fetch=fetch,full=True)
            status=json.loads((root/'history_status.json').read_text())
            self.assertEqual(status['AAA']['releaseInvalidations'][0]['originalRecord'],first)
            self.assertEqual(status['AAB']['releaseInvalidations'][0]['originalRecord'],second)
            saved=status['AAB']['releaseInvalidations'][0]
            self.assertEqual(saved['originalHistoryRows'][0]['eps_reported'],'$4.56')
            sync_all(root,TODAY,fetch=fetch,full=True)
            repeated=json.loads((root/'history_status.json').read_text())
            self.assertEqual(repeated['AAB']['releaseInvalidations'],status['AAB']['releaseInvalidations'])

    def test_alias_specific_source_is_revalidated_even_when_first_alias_source_differs(self):
        source=SOURCES['APA-estimate']
        first=dict(ticker='AAA',periodEnd='2026-09-30',fiscalYear=2026,fiscalQuarter=3,
            date='2026-10-20',verifiedAt='2026-10-28',periodScope='quarter',currency='USD',
            epsGaapDiluted=None,revenue=None,
            releaseSourceUrl='https://www.sec.gov/Archives/edgar/data/1841666/actual/ex991.htm')
        second={**first,'ticker':'AAB','date':'2026-10-07','releaseSourceUrl':source['primary']['url']}
        def fetch(url):
            if '/submissions/' in url:return json.dumps({'filings':{'recent':{}}})
            if url==first['releaseSourceUrl']:return '<html>Unsupported older actual statement</html>'
            for kind in ('primary','exhibit'):
                if url==source[kind]['url']:return document('APA-estimate',kind)
            raise OSError('Outside fixture')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,value in {'data.json':[{'ticker':'AAA'},{'ticker':'AAB'}],
                    'historical_data.json':{'AAA':[],'AAB':[]},'official_history.json':[first,second],
                    'history_status.json':{},'sp500_mapping.json':{'AAA':{'cik':'0001841666'},'AAB':{'cik':'0001841666'}}}.items():
                (root/name).write_text(json.dumps(value))
            sync_all(root,TODAY,fetch=fetch,full=True)
            status=json.loads((root/'history_status.json').read_text())
            self.assertEqual(status['AAB']['releaseInvalidations'][0]['originalRecord'],second)
            rows=json.loads((root/'official_history.json').read_text())
            self.assertTrue(all(r['releaseSourceUrl']==first['releaseSourceUrl'] for r in rows))
            corrected=next(r for r in rows if r['ticker']=='AAB')
            self.assertEqual(corrected['releaseCorrectionEvidence']['oldDate'],'2026-10-07')
            self.assertEqual(corrected['releaseCorrectionEvidence']['newDate'],'2026-10-20')
            self.assertEqual(corrected['releaseCorrectionEvidence']['counterevidenceSourceUrl'],source['exhibit']['url'])
            saved=status['AAB']['releaseInvalidations']
            sync_all(root,TODAY,fetch=fetch,full=True)
            self.assertEqual(json.loads((root/'history_status.json').read_text())['AAB']['releaseInvalidations'],saved)
