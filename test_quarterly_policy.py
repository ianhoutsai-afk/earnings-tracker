import copy
import unittest
from datetime import date

from quarterly_policy import retain_history, retain_manifest, company_fields, merge_manifest_record, pending_history_companies
from verified_history import apply_official_records

TODAY = date(2026, 10, 22)


def official(end, quarter, released, eps=1.0):
    return dict(ticker='MSFT', date=released, periodEnd=end, fiscalYear=2026,
                fiscalQuarter=quarter, periodScope='quarter', currency='USD',
                epsGaapDiluted=eps, epsBasis='GAAP diluted', revenue=1000000000,
                releaseSourceUrl='https://www.microsoft.com/investor/release', verifiedAt='2026-10-22')


class QuarterlyPolicyTests(unittest.TestCase):
    def test_reviewed_preliminary_release_does_not_survive_a_final_release(self):
        final = dict(official('2026-03-29', 1, '2026-05-20'), ticker='HAS',
                     releaseAccession='0000046080-26-000029', releaseFilingDate='2026-05-20',
                     releaseSourceUrl='https://www.sec.gov/final')
        earlier = dict(final, date='2026-04-23', releaseAccession='0000046080-26-000016',
                       releaseFilingDate='2026-04-23', releaseSourceUrl='https://www.sec.gov/preliminary')
        for args in ((earlier, final), (final, dict(earlier, verifiedAt='2026-11-22'))):
            merged = merge_manifest_record(*args)
            for field in ('date', 'releaseAccession', 'releaseFilingDate', 'releaseSourceUrl'):
                self.assertEqual(merged[field], final[field])

    def test_manifest_retains_known_start_only_for_the_same_quarter(self):
        older = dict(official('2026-06-30', 4, '2026-07-29'), verifiedAt='2026-08-01')
        newer = dict(older, verifiedAt='2026-10-22', periodStart=None)
        known = dict(older, periodStart='2026-04-01')
        updated = dict(newer, periodStart='2026-04-02')
        self.assertEqual(merge_manifest_record(known, newer)['periodStart'], '2026-04-01')
        self.assertEqual(merge_manifest_record(newer, known)['periodStart'], '2026-04-01')
        self.assertEqual(merge_manifest_record(known, updated)['periodStart'], '2026-04-02')
        for change in ({'ticker':'EL'}, {'periodEnd':'2026-06-29'}, {'periodScope':'year'},
                       {'fiscalYear':2027}, {'fiscalQuarter':3}):
            with self.subTest(change=change):
                self.assertIsNone(merge_manifest_record(known, {**newer, **change})['periodStart'])

    def test_manifest_preserves_a_financial_filing_as_one_source(self):
        filing = {
            'secUrl':'https://www.sec.gov/Archives/edgar/data/1/000000000126000001/quarter.htm',
            'accessionNumber':'0000000001-26-000001',
            'filingDate':'2026-08-03',
            'form':'10-Q',
        }
        original = dict(official('2026-06-30', 2, '2026-07-29'), verifiedAt='2026-08-03', **filing)
        refreshed = dict(official('2026-06-30', 2, '2026-07-29'), verifiedAt='2026-10-22', epsGaapDiluted=1.25)
        for previous,incoming in ((original,refreshed), (refreshed,original)):
            actual = merge_manifest_record(previous,incoming)
            self.assertEqual({name:actual.get(name) for name in filing},filing)
            self.assertEqual(actual['epsGaapDiluted'],1.25)
        for change in ({'fiscalQuarter':3}, {'ticker':'AAPL'},
                       {'secUrl':'https://www.sec.gov/Archives/edgar/data/1/000000000126000002/other.htm'}):
            with self.subTest(change=change):
                actual = merge_manifest_record(original, {**refreshed, **change})
                self.assertIsNone(actual.get('accessionNumber'))
        revised_filing = {**filing,'filingDate':'2026-08-04'}
        actual = merge_manifest_record(original, {**refreshed, **revised_filing})
        self.assertEqual({name:actual.get(name) for name in filing},revised_filing)

    def test_reviewed_comparative_metrics_survive_a_refresh_of_the_original_filing(self):
        original = official('2026-06-30', 2, '2026-07-29')
        source = 'https://www.sec.gov/Archives/edgar/data/1/000000000126000005/revised.htm'
        revised = dict(original, verifiedAt='2026-10-20', revenue=1_050_000_000, epsGaapDiluted=1.21,
                       metricRevisionFilingDate='2026-10-19', metricSourceUrl=source,
                       revenueSourceUrl=source, epsSourceUrl=source)
        refreshed = dict(original, verifiedAt='2026-10-22', filingDate='2026-08-03')
        saved = merge_manifest_record(revised, refreshed)
        self.assertEqual((saved['revenue'], saved['epsGaapDiluted']), (1_050_000_000, 1.21))
        self.assertEqual(saved['epsSourceUrl'], source)
        self.assertEqual(saved['metricRevisionFilingDate'], '2026-10-19')
        self.assertEqual(saved['filingDate'], '2026-08-03')
        self.assertEqual(saved['date'], '2026-07-29')
        later = dict(revised, metricRevisionFilingDate='2026-10-21', verifiedAt='2026-10-21', revenue=1_060_000_000)
        self.assertEqual(merge_manifest_record(saved, later)['revenue'], 1_060_000_000)
        different = dict(refreshed, fiscalQuarter=3)
        self.assertEqual(merge_manifest_record(revised, different)['revenue'], 1_000_000_000)

    def test_reviewed_metric_revision_requires_a_later_dated_source_and_both_metrics(self):
        source = 'https://www.sec.gov/Archives/edgar/data/1/000000000126000005/revised.htm'
        revised = dict(official('2026-06-30', 2, '2026-07-29'),
                       metricRevisionFilingDate='2026-10-19', epsSourceUrl=source,
                       revenueSourceUrl=source, metricSourceUrl=source)
        companies = [{'ticker':'MSFT'}]
        result, added = apply_official_records(companies, {}, [revised], TODAY)
        self.assertEqual(added, 1)
        self.assertEqual(result['MSFT'][0]['date'], '2026-07-29')
        for changed in ({'metricRevisionFilingDate':'2026-10-23'}, {'metricRevisionFilingDate':'2026-07-28'},
                        {'epsGaapDiluted':None}, {'revenueSourceUrl':None}):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    apply_official_records(companies, {}, [{**revised, **changed}], TODAY)

    def test_pending_history_uses_retained_metrics_and_date_provenance(self):
        periods = [('2026-09-30',2026,3), ('2026-06-30',2026,2), ('2026-03-31',2026,1),
                   ('2025-12-31',2025,4), ('2025-09-30',2025,3)]
        complete = [dict(periodEnd=end, fiscalYear=year, fiscalQuarter=quarter, periodScope='quarter', currency='USD',
                         verificationStatus='official_verified', epsBasis='GAAP diluted',
                         eps_reported='$0.00', revenue_reported='$0.00M') for end,year,quarter in periods]
        history = {
            'COMPLETE': complete,
            'RECAST': [dict(complete[0], dateSource='recast'), *complete[1:]],
            'FILING': [dict(complete[0], dateSource='sec_filing'), *complete[1:]],
            'MISSING': [dict(complete[0], eps_reported='-'), *complete[1:]],
            'LEGACY': [dict(complete[0], verificationStatus='legacy_unverified'), *complete[1:]],
            'SHORT': complete[1:],
        }
        self.assertEqual(pending_history_companies(history), 4)
        self.assertFalse(pending_history_companies({'COMPLETE': complete, 'RECAST': history['RECAST']}))

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

class TrustedWindowTests(unittest.TestCase):
    def test_unverified_later_date_never_evicts_a_fifth_verified_period(self):
        rows=[dict(date=f'2026-0{i}-15',periodEnd=f'2026-0{i}-01',periodScope='quarter',verificationStatus='official_verified',quarter=f'2026 Q{min(i,4)}') for i in range(1,6)]
        rows.append(dict(date='2026-06-15',quarter='legacy pending'))
        result=retain_history({'ABC':rows},TODAY)['ABC']
        self.assertEqual(len(result),5)
        self.assertTrue(all(r['verificationStatus']=='official_verified' for r in result))

class MetricProvenanceTests(unittest.TestCase):
    def test_partial_restatement_tracks_each_numeric_source(self):
        first={**official('2026-06-30',4,'2026-07-29'),'releaseFilingDate':'2026-07-30','releaseAccession':'original'}
        h,_=apply_official_records([{'ticker':'MSFT'}],{},[first],TODAY)
        second={**first,'date':'2026-10-20','epsGaapDiluted':1.5,'revenue':None,
                'releaseSourceUrl':'https://www.microsoft.com/new-release','metricSourceUrl':'https://www.microsoft.com/new-statements',
                'releaseFilingDate':'2026-10-21','releaseAccession':'amendment'}
        h,_=apply_official_records([{'ticker':'MSFT'}],h,[second],TODAY)
        r=h['MSFT'][0]
        self.assertEqual(r['epsSourceUrl'],second['metricSourceUrl'])
        self.assertEqual(r['revenueSourceUrl'],first['releaseSourceUrl'])
        self.assertEqual(r['releaseFilingDate'],first['releaseFilingDate'])
        self.assertEqual(r['releaseAccession'],first['releaseAccession'])
