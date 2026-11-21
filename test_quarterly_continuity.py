"""Count records separately from continuous, correctly ordered fiscal quarters."""
import unittest
from quarterly_policy import history_continuity_issues, pending_history_companies


def row(end, year, quarter):
    return {'periodEnd': end, 'fiscalYear': year, 'fiscalQuarter': quarter,
            'periodScope': 'quarter', 'verificationStatus': 'official_verified'}


class QuarterlyContinuityTests(unittest.TestCase):
    def test_five_records_do_not_establish_five_consecutive_quarters(self):
        rows = [row('2026-09-30', 2026, 3), row('2026-06-30', 2026, 2),
                row('2026-03-31', 2026, 1), row('2025-09-30', 2025, 3),
                row('2025-06-30', 2025, 2)]
        issues = history_continuity_issues({'ABC': rows})
        self.assertEqual(len(issues['ABC']), 1)
        self.assertEqual(issues['ABC'][0]['newerPeriodEnd'], '2026-03-31')
        self.assertEqual(issues['ABC'][0]['olderPeriodEnd'], '2025-09-30')

    def test_complete_metrics_with_skipped_quarter_remain_pending(self):
        periods = [('2026-09-30', 2026, 3), ('2026-06-30', 2026, 2),
                   ('2026-03-31', 2026, 1), ('2025-09-30', 2025, 3),
                   ('2025-06-30', 2025, 2)]
        rows = [dict(row(*period), currency='USD', epsBasis='GAAP diluted',
                     eps_reported='$1.00', revenue_reported='$1.00B') for period in periods]
        self.assertEqual(pending_history_companies({'ABC': rows}), 1)

    def test_publication_cannot_claim_complete_data_with_a_skipped_quarter(self):
        import json
        import tempfile
        from pathlib import Path
        from datetime import date, timedelta
        from quarterly_policy import retain_manifest
        from verified_history import apply_official_records
        from validate_quarterly_data import validate
        periods = [('2026-09-30', 2026, 3), ('2026-06-30', 2026, 2),
                   ('2026-03-31', 2026, 1), ('2025-09-30', 2025, 3),
                   ('2025-06-30', 2025, 2)]
        companies = [dict(ticker='ABC', eps='-', revenue='-', reportDate=None)]
        records = [dict(ticker='ABC', periodEnd=end, fiscalYear=year, fiscalQuarter=quarter,
                        date=(date.fromisoformat(end)+timedelta(days=30)).isoformat(),
                        verifiedAt='2026-11-18', periodScope='quarter', currency='USD',
                        epsBasis='GAAP diluted', epsGaapDiluted=1.0, revenue=1000000000,
                        releaseSourceUrl='https://issuer.example/results') for end, year, quarter in periods]
        history, _ = apply_official_records(companies, {}, records, date(2026,11,18))
        state = dict(historyComplete=False, dataComplete=True, filingDatedQuarters=0,
                     releaseDatesComplete=True, historyContinuityPendingCompanies=1,
                     fiveConsecutiveQuarterCompanies=0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in {'data.json':companies, 'historical_data.json':history,
                                'official_history.json':retain_manifest(records),
                                'history_status.json':{'ABC':{'recordCount':5}},
                                'official_scan_state.json':state}.items():
                (root/name).write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, 'consecutive'):
                validate(root, date(2026,11,18))

    def test_sixteen_week_quarter_is_not_a_missing_quarter(self):
        self.assertFalse(history_continuity_issues({'ABC': [
            row('2026-08-29', 2026, 4), row('2026-05-09', 2026, 3)]}))

    def test_reviewed_calendar_transition_only_exempts_its_exact_period_pair(self):
        transition = [row('2026-09-30', 2026, 3), row('2026-05-31', 2026, 4)]
        self.assertFalse(history_continuity_issues({'FDX': transition}))
        self.assertIn('OTHER', history_continuity_issues({'OTHER': transition}))
        wrong = [transition[0], row('2026-02-28', 2026, 3)]
        self.assertIn('FDX', history_continuity_issues({'FDX': wrong}))

    def test_comparative_fiscal_year_cannot_hide_a_bad_identity(self):
        issues = history_continuity_issues({'WDAY': [
            row('2026-01-31', 2026, 4), row('2025-10-31', 2025, 3)]})
        self.assertIn('WDAY', issues)
        self.assertEqual(issues['WDAY'][0]['newerFiscalQuarter'], '2026 Q4')


if __name__ == '__main__':
    unittest.main()
