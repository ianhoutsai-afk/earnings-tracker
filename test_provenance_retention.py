import copy
import unittest

from quarterly_policy import merge_manifest_record


class StatementEvidenceRetentionTests(unittest.TestCase):
    def record(self):
        return dict(ticker='ABC', periodEnd='2026-06-30', fiscalYear=2026,
            fiscalQuarter=2, date='2026-07-28', verifiedAt='2026-10-28',
            releaseSourceUrl='https://www.sec.gov/Archives/edgar/data/123/456/abc8k.htm',
            releaseAccession='original', secUrl='https://www.sec.gov/Archives/edgar/data/123/789/abc10q.htm',
            accessionNumber='filing', epsGaapDiluted=1.23, revenue=123000000,
            epsVerificationStatus='verified', revenueVerificationStatus='verified')

    def test_identical_reparse_keeps_period_and_statement_proof(self):
        old=self.record()
        old['periodEndEvidence']={'sourceUrl':'https://www.sec.gov/Archives/edgar/data/123/456/ex991.htm',
            'locator':{'table':1,'column':2,'header':'Three months ended June 30, 2026'}}
        old['metricStatementEvidence']={'sourceUrl':old['periodEndEvidence']['sourceUrl'],
            'periodEnd':'2026-06-30','matchedFilingUrl':old['secUrl'],'locator':{'table':1,'column':2}}
        merged=merge_manifest_record(old,self.record())
        for field in ('periodEndEvidence','metricStatementEvidence'):
            self.assertIn(field,merged)
            self.assertEqual(merged[field],old[field])
        merged['periodEndEvidence']['locator']['table']=99
        self.assertEqual(old['periodEndEvidence']['locator']['table'],1)

    def test_different_identity_or_source_does_not_inherit_old_statement_proof(self):
        for key,value in (('periodEnd','2026-03-31'),('fiscalYear',2025),('fiscalQuarter',1),
                ('releaseSourceUrl','https://example.com/another-release'),('releaseAccession','another'),
                ('secUrl','https://example.com/another-filing'),('accessionNumber','amended')):
            with self.subTest(key=key):
                old=self.record()
                old['periodEndEvidence']={'locator':{'header':'old'}}
                old['metricStatementEvidence']={'periodEnd':'2026-06-30','locator':{'table':1}}
                new={**self.record(),key:value}
                merged=merge_manifest_record(old,new)
                self.assertNotIn('periodEndEvidence',merged)
                self.assertNotIn('metricStatementEvidence',merged)

    def test_new_statement_proof_replaces_old_proof(self):
        old=self.record();new=copy.deepcopy(old)
        for field in ('periodEndEvidence','metricStatementEvidence'):
            old[field]={'locator':{'table':1}}
            new[field]={'locator':{'table':2}}
        merged=merge_manifest_record(old,new)
        self.assertEqual(merged['periodEndEvidence']['locator']['table'],2)
        self.assertEqual(merged['metricStatementEvidence']['locator']['table'],2)
