import unittest
from quarterly_policy import merge_manifest_record


class MetricRevisionTests(unittest.TestCase):
    def test_four_reviewed_rsg_gross_values_are_corrected_to_official_net_revenue(self):
        pairs=[
            ('2026-06-30',5076000000,4430000000,'000106039126000275/rsg-20260630.htm','000106039126000273/exhibit991q22026.htm'),
            ('2025-09-30',4827000000,4212000000,'000162828025047655/rsg-20250930.htm','000162828025047534/exhibit991q32025.htm'),
            ('2025-06-30',4882000000,4235000000,'000106039125000216/rsg-20250630.htm','000106039125000215/exhibit991q22025.htm'),
            ('2025-03-31',4593000000,4009000000,'000106039125000170/rsg-20250331.htm','000106039125000169/exhibit991q12025.htm')]
        prefix='https://www.sec.gov/Archives/edgar/data/1060391/'
        for period,old_value,new_value,filing,release in pairs:
            with self.subTest(period=period):
                old={**self.original(),'ticker':'RSG','periodEnd':period,'revenue':old_value,
                     'revenueSourceUrl':prefix+filing}
                new={**old,'verifiedAt':'2026-10-26','revenue':new_value,
                     'revenueSourceUrl':prefix+release}
                corrected=merge_manifest_record(old,new)
                self.assertEqual(corrected['revenue'],new_value)
                self.assertEqual(corrected['revenueVerificationStatus'],'verified')
                self.assertEqual(corrected['metricCorrectionEvidence']['revenue']['oldValue'],old_value)
                self.assertEqual(corrected['metricCorrectionEvidence']['revenue']['newSourceUrl'],prefix+release)
                parsed_without_ticker={k:v for k,v in new.items() if k!='ticker'}
                self.assertEqual(merge_manifest_record(old,parsed_without_ticker)['revenue'],new_value)
                repeated=merge_manifest_record(corrected,new)
                self.assertEqual(repeated['revenue'],new_value)
                self.assertEqual(repeated['metricCorrectionEvidence'],corrected['metricCorrectionEvidence'])
                wrong_source={**new,'revenueSourceUrl':prefix+'unreviewed.htm'}
                self.assertEqual(merge_manifest_record(old,wrong_source)['revenueVerificationStatus'],'conflict')

    def original(self):
        return {'ticker': 'ABC', 'periodEnd': '2026-06-30', 'date': '2026-07-20',
                'verifiedAt': '2026-10-22', 'epsGaapDiluted': 1.41, 'revenue': 2322000000,
                'epsBasis': 'GAAP diluted', 'releaseSourceUrl': 'https://example.invalid/original',
                'metricSourceUrl': 'https://example.invalid/statement',
                'epsSourceUrl': 'https://example.invalid/statement',
                'revenueSourceUrl': 'https://example.invalid/statement'}

    def test_later_different_official_value_is_a_conflict_without_explicit_revision(self):
        old = self.original()
        new = {**old, 'verifiedAt': '2026-10-24', 'epsGaapDiluted': 2,
               'epsSourceUrl': 'https://example.invalid/later-comparative'}
        result = merge_manifest_record(old, new)
        self.assertEqual(result['epsGaapDiluted'], 1.41)
        self.assertEqual(result.get('epsVerificationStatus'), 'conflict')
        self.assertEqual(result['metricConflicts']['epsGaapDiluted'][1]['value'], 2)
        self.assertEqual(result['revenue'], 2322000000)

    def test_confirmed_partial_restatement_updates_only_that_field_and_keeps_original_release(self):
        old = self.original()
        new = {**old, 'verifiedAt': '2026-10-24', 'date': '2026-10-23',
               'epsGaapDiluted': 1.5, 'revenue': None,
               'epsSourceUrl': 'https://example.invalid/correction',
               'metricRevision': {'epsGaapDiluted': '2026-10-23'}}
        result = merge_manifest_record(old, new)
        self.assertEqual(result['epsGaapDiluted'], 1.5)
        self.assertEqual(result['revenue'], 2322000000)
        self.assertEqual(result['revenueSourceUrl'], old['revenueSourceUrl'])
        self.assertEqual(result['date'], '2026-07-20')

    def test_older_comparative_cannot_reverse_a_confirmed_restatement(self):
        revised = {**self.original(), 'epsGaapDiluted': 1.5,
                   'metricRevision': {'epsGaapDiluted': '2026-10-23'}}
        repeated = {**self.original(), 'verifiedAt': '2026-10-24'}
        result = merge_manifest_record(revised, repeated)
        self.assertEqual(result['epsGaapDiluted'], 1.5)
        self.assertNotEqual(result.get('epsVerificationStatus'), 'conflict')

    def test_rechecking_one_source_does_not_silently_clear_an_unresolved_conflict(self):
        old = self.original()
        conflict = merge_manifest_record(old, {**old, 'epsGaapDiluted': 2})
        result = merge_manifest_record(conflict, old)
        self.assertEqual(result.get('epsVerificationStatus'), 'conflict')


if __name__ == '__main__':
    unittest.main()
