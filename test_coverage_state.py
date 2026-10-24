import unittest
from datetime import datetime, timezone


class CoverageStateTests(unittest.TestCase):
    def test_new_source_failure_cannot_claim_current_latest_is_identified(self):
        result=self.api().company_status({'ticker':'ABC'},self.rows(),
            {'sourceCheck':{'state':'failed','lastSuccessfulDiscoveryAt':'2026-10-24T00:00:00Z'}},
            '2026-10-24T01:00:00Z')
        self.assertEqual(result['latestQuarter']['state'],'pending_discovery')
        self.assertFalse(result['latestQuarter']['metricsComplete'])

    def api(self):
        import coverage_state
        return coverage_state

    def rows(self):
        return [dict(date='2026-10-20', periodEnd=f'2026-0{i}-30', periodScope='quarter',
                     fiscalYear=2026, fiscalQuarter=1, verificationStatus='official_verified',
                     epsBasis='GAAP diluted', currency='USD', eps_reported='$1.00',
                     revenue_reported='$1B', releaseSourceUrl='https://www.sec.gov/test') for i in (9,6,3)]

    def test_source_success_is_not_latest_identity_or_five_metric_completeness(self):
        result=self.api().company_status({'ticker':'ABC'}, self.rows(),
            {'sourceCheck':{'lastSuccessfulDiscoveryAt':'2026-10-24T00:00:00Z'},
             'candidates':[{'key':'1:a:url','filingDate':'2026-10-23','sourceUrl':'https://www.sec.gov/new','reason':'quarter_identity_unconfirmed'}]},
            '2026-10-24T01:00:00Z')
        self.assertEqual(result['latestQuarter']['state'],'pending_identity')
        self.assertEqual(result['coverage']['completeMetrics'],3)
        self.assertTrue(any(g['reason']=='insufficient_verified_history' for g in result['gaps']))

    def test_only_proven_old_candidate_is_outside_current_window(self):
        rows=self.rows()+[{**self.rows()[0], 'periodEnd':'2025-12-31'}, {**self.rows()[0], 'periodEnd':'2025-09-30'}]
        result=self.api().company_status({'ticker':'ABC'}, rows,
            {'sourceCheck':{'lastSuccessfulDiscoveryAt':'2026-10-24T00:00:00Z'},
             'candidates':[{'key':'old','filingDate':'2025-08-01','sourceUrl':'https://www.sec.gov/old','reason':'format_unsupported'},
                           {'key':'unknown','filingDate':'2026-10-23','sourceUrl':'https://www.sec.gov/new','reason':'format_unsupported'}]},
            '2026-10-24T01:00:00Z')
        self.assertEqual(result['candidates'][0]['scope'],'superseded')
        self.assertEqual(result['candidates'][1]['scope'],'current_or_unknown')
        self.assertEqual(result['latestQuarter']['state'],'pending_identity')

    def test_failed_attempt_does_not_refresh_success_and_thirty_hour_limit(self):
        result=self.api().company_status({'ticker':'ABC'}, self.rows(),
            {'sourceCheck':{'lastSuccessfulDiscoveryAt':'2026-10-22T00:00:00Z','lastAttemptAt':'2026-10-24T01:00:00Z','state':'failed'}},
            '2026-10-24T01:00:00Z')
        self.assertTrue(result['sourceCheck']['stale'])
        self.assertEqual(result['sourceCheck']['lastSuccessfulDiscoveryAt'],'2026-10-22T00:00:00Z')

    def test_conflicted_numeric_value_is_retained_but_not_counted(self):
        rows=self.rows(); rows[0]['epsVerificationStatus']='conflict'
        result=self.api().company_status({'ticker':'ABC'}, rows,{},'2026-10-24T01:00:00Z')
        self.assertEqual(result['coverage']['completeMetrics'],2)
        self.assertTrue(any(g['field']=='epsGaapDiluted' and g['reason']=='official_value_conflict' for g in result['gaps']))


if __name__=='__main__':unittest.main()
