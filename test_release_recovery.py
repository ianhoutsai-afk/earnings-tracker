import unittest
from datetime import date
from official_sources import parse_earnings_release
from test_official_real_documents import document


class ReleaseRecoveryTests(unittest.TestCase):
    def test_current_ibm_results_after_outlook_headline_keep_explicit_fiscal_year(self):
        row=parse_earnings_release(document('IBM-release-recovery','exhibit'),'2026-10-21','2026-10-21',date(2026,10,28))
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2026,3))
        self.assertEqual(row['date'],'2026-10-21')

    def test_idex_three_month_period_proves_end_without_guessing_fiscal_year(self):
        row=parse_earnings_release(document('IEX-release-recovery','exhibit'),'2026-10-28','2026-10-28',date(2026,10,28))
        self.assertEqual(row['periodEnd'],'2026-09-30')
        self.assertIsNone(row['fiscalYear'])
        self.assertIsNone(row['fiscalQuarter'])

    def test_forecast_comparison_and_inconsistent_announcements_cannot_supply_identity(self):
        for claim in ('today announced third-quarter 2026 guidance for earnings results',
                      'previously announced third-quarter 2025 earnings results',
                      'today announced third-quarter 2026 forecast earnings results',
                      'previously today announced third-quarter 2025 earnings results',
                      'today announced third-quarter 2026 earnings results guidance',
                      'today announced third-quarter 2026 earnings results forecast to be published next month',
                      'today announced third-quarter 2026 earnings results. Today reported results for second-quarter 2026',
                      'today announced third-quarter 2026 earnings results. Today reported second-quarter 2026 earnings results'):
            body='<h1>Company raises outlook</h1><p>October 21, 2026. Company '+claim+'.</p>'
            with self.subTest(claim=claim):
                with self.assertRaises(ValueError):parse_earnings_release(body,'2026-10-21','2026-10-21',date(2026,10,28))
