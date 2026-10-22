import copy
import unittest
from datetime import date

from quarterly_policy import retain_history, retain_manifest, company_fields
from verified_history import apply_official_records

TODAY = date(2026, 10, 22)


def official(end, quarter, released, eps=1.0):
    return dict(ticker='MSFT', date=released, periodEnd=end, fiscalYear=2026,
                fiscalQuarter=quarter, periodScope='quarter', currency='USD',
                epsGaapDiluted=eps, epsBasis='GAAP diluted', revenue=1000000000,
                releaseSourceUrl='https://www.microsoft.com/investor/release', verifiedAt='2026-10-22')


class QuarterlyPolicyTests(unittest.TestCase):
    def test_every_company_retains_five_newest_without_mutating_input(self):
        rows = [dict(date=f'2026-0{i}-15', quarter=f'legacy {i}') for i in range(1, 7)]
        original = {'ABC': rows, 'NEW': rows[:3]}
        before = copy.deepcopy(original)
        result = retain_history(original, TODAY)
        self.assertEqual([r['date'] for r in result['ABC']], [f'2026-0{i}-15' for i in range(6, 1, -1)])
        self.assertEqual(len(result['NEW']), 3)
        self.assertEqual(original, before)

    def test_period_identity_deduplicates_amendment_but_not_different_same_day_periods(self):
        rows = [dict(date='2026-08-01', periodEnd='2026-06-30', verifiedAt='2026-08-01'),
                dict(date='2026-09-01', periodEnd='2026-06-30', verifiedAt='2026-09-01'),
                dict(date='2026-08-01', periodEnd='2026-03-31', verifiedAt='2026-08-01')]
        result = retain_history({'ABC': rows}, TODAY)['ABC']
        self.assertEqual([r['periodEnd'] for r in result], ['2026-06-30', '2026-03-31'])
        self.assertEqual(result[0]['verifiedAt'], '2026-09-01')

    def test_verified_identity_is_backfilled_but_legacy_fy_remains_unverified(self):
        result = retain_history({'ABC': [dict(date='2026-01-20', quarter='2025 FY'),
            dict(date='2026-05-20', quarter='2026 Q1', verificationStatus='official_verified', periodScope='quarter', periodEnd='2026-03-31')]}, TODAY)['ABC']
        self.assertEqual(result[0]['fiscalYear'], 2026)
        self.assertEqual(result[0]['fiscalQuarter'], 1)
        self.assertNotIn('fiscalQuarter', result[1])
        self.assertEqual(result[1]['verificationStatus'], 'legacy_unverified')

    def test_unverified_duplicate_quarter_labels_are_not_period_evidence(self):
        rows=[dict(date='2026-01-10',quarter='2026 Q1'),dict(date='2026-04-10',quarter='2026 Q1')]
        self.assertEqual(len(retain_history({'ABC':rows},TODAY)['ABC']),2)

    def test_future_records_are_rejected(self):
        with self.assertRaises(ValueError):
            retain_history({'ABC': [dict(date='2027-01-01')]}, TODAY)

    def test_old_seed_replay_does_not_resurrect_sixth_quarter(self):
        rows = [dict(date=f'2026-0{i}-15', quarter=f'legacy {i}') for i in range(1, 7)]
        result = retain_history({'ABC': rows}, TODAY)
        result['ABC'].append(rows[0])
        self.assertEqual(len(retain_history(result, TODAY)['ABC']), 5)
        self.assertEqual(retain_history(result, TODAY)['ABC'][0]['date'], '2026-06-15')

    def test_active_manifest_is_also_limited_to_five_periods(self):
        records = [dict(ticker='ABC', periodEnd=f'2026-0{i}-28', verifiedAt='2026-10-22') for i in range(1, 7)]
        self.assertEqual([r['periodEnd'] for r in retain_manifest(records)], [f'2026-0{i}-28' for i in range(6, 1, -1)])

    def test_unscoped_estimates_clear_for_all_companies_and_old_calls_expire(self):
        c = dict(ticker='ABC', eps='$19.5', revenue='$100B', reportDate='2026-10-01', nextEarningsCallDate='2026-10-01', nextEarningsCallSourceUrl='https://abc.com/call')
        result = company_fields(c, {}, TODAY)
        self.assertEqual(result['eps'], '-')
        self.assertEqual(result['revenue'], '-')
        self.assertIsNone(result['reportDate'])
        self.assertNotIn('nextEarningsCallDate', result)

    def test_partial_reparse_preserves_all_company_verified_values_and_provenance(self):
        r = official('2026-06-30', 4, '2026-07-29')
        h, _ = apply_official_records([{'ticker':'MSFT'}], {}, [r], TODAY)
        second = {**r, 'date':'2026-10-21', 'epsGaapDiluted':None, 'revenue':None,
                  'releaseSourceUrl':'https://www.microsoft.com/investor/restatement'}
        h, added = apply_official_records([{'ticker':'MSFT'}], h, [second], TODAY)
        row = h['MSFT'][0]
        self.assertEqual(added, 0)
        self.assertEqual(row['date'], '2026-07-29')
        self.assertEqual(row['eps_reported'], '$1.00')
        self.assertEqual(row['revenue_reported'], '$1.00B')
        self.assertEqual(row['metricSourceUrl'], r['releaseSourceUrl'])

    def test_old_manifest_cannot_overwrite_later_verified_revision(self):
        r = official('2026-06-30', 4, '2026-07-29')
        h, _ = apply_official_records([{'ticker':'MSFT'}], {}, [r], TODAY)
        h['MSFT'][0]['eps_reported'] = '$8.00'
        r['verifiedAt'] = '2026-09-01'
        result, _ = apply_official_records([{'ticker':'MSFT'}], h, [r], TODAY)
        self.assertEqual(result['MSFT'][0]['eps_reported'], '$8.00')

    def test_nonfinite_financial_values_are_not_accepted(self):
        for value in [float('nan'), float('inf'), -float('inf')]:
            with self.assertRaises(ValueError):
                apply_official_records([{'ticker':'MSFT'}], {}, [official('2026-06-30',4,'2026-07-29',value)], TODAY)

    def test_same_release_day_different_official_periods_are_not_merged(self):
        records=[official('2026-03-31',3,'2026-07-29'),official('2026-06-30',4,'2026-07-29')]
        result, added = apply_official_records([{'ticker':'MSFT'}], {}, records, TODAY)
        self.assertEqual(added,2)
        self.assertEqual(len(result['MSFT']),2)

if __name__ == '__main__':
    unittest.main()
