import unittest
from quarterly_policy import merge_manifest_record


class MetricRevisionTests(unittest.TestCase):
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
