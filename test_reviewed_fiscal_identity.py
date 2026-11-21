"""Original release identities override only independently reviewed bad DEI tags."""
import unittest
from datetime import date
from official_sync import check_issuer
from test_official_sources import filing


class ReviewedFiscalIdentityTests(unittest.TestCase):
    def test_known_tag_errors_require_exact_filing_and_matching_release_identity(self):
        cases = (
            ('0001037540', '0001037540-26-000034', '2026-06-30', '2026-04-01', 2, 2026, 2026, '2026-07-28', 4),
            ('0001521332', '0001521332-26-000048', '2026-03-31', '2026-01-01', 1, 2025, 2026, '2026-05-05'),
            ('0001108524', '0001108524-26-000060', '2026-01-31', '2025-11-01', 4, 2025, 2026, '2026-02-25'),
            ('0000034903', '0000034903-26-000017', '2025-12-31', '2025-10-01', 4, 2024, 2025, '2026-02-12'),
            ('0001327811', '0001327811-25-000198', '2025-10-31', '2025-08-01', 3, 2025, 2026, '2025-11-25'),
            ('0001327811', '0001327811-25-000184', '2025-07-31', '2025-05-01', 2, 2025, 2026, '2025-08-21'),
            ('0000820318', '0000820318-26-000023', '2026-09-30', '2026-07-01', 1, 2026, 2027, '2026-11-04'),
            ('0001037646', '0001037646-26-000051', '2026-06-30', '2026-04-01', 2, 2024, 2026, '2026-07-30'),
            ('0001037646', '0001037646-26-000074', '2026-09-30', '2026-07-01', 3, 2025, 2026, '2026-11-05'),
            ('0001002047', '0001193125-26-380207', '2026-07-31', '2026-05-01', 1, 2026, 2027, '2026-09-02'),
            ('0001002047', '0001193125-25-297237', '2025-10-24', '2025-07-26', 2, 2025, 2026, '2025-11-25'),
            ('0001002047', '0001193125-25-189700', '2025-07-25', '2025-04-26', 1, 2025, 2026, '2025-08-27'),
        )
        ordinal = ('First', 'Second', 'Third', 'Fourth')
        for cik, accession, end, start, quarter, wrong, correct, published, *tagged_quarter in cases:
            reported = tagged_quarter[0] if tagged_quarter else quarter
            for actual_accession in (accession, '0000000000-26-999999'):
                with self.subTest(cik=cik, accession=actual_accession):
                    end_day = date.fromisoformat(end).strftime('%B %d, %Y')
                    release_day = date.fromisoformat(published).strftime('%B %d, %Y')
                    exhibit = (f'<h1>Example Reports {ordinal[quarter-1]} Quarter Fiscal {correct} Results</h1>'
                               f'<p>{release_day}. Example reported results for the quarter ended {end_day}.</p>')
                    doc = filing(quarter='FY' if reported == 4 else f'Q{reported}')
                    doc = (doc.replace('>2026<', f'>{wrong}<').replace('2026-09-30', end)
                           .replace('2026-07-01', start).replace('2026-01-01', end[:4]+'-01-01')
                           .replace('<xbrli:identifier>1</xbrli:identifier>',
                                    f'<xbrli:identifier>{int(cik)}</xbrli:identifier>'))
                    submissions = {'filings': {'recent': {
                        'form': ['8-K', '10-K' if quarter == 4 else '10-Q'],
                        'items': ['2.02,9.01', ''], 'accessionNumber': ['0000000000-26-000001', actual_accession],
                        'primaryDocument': ['release.htm', 'quarter.htm'],
                        'filingDate': [published, published], 'reportDate': [published, end],
                    }}}
                    def fetch(url):
                        if url.endswith('release.htm'):
                            return '<a href="ex991.htm">99.1 Earnings release</a>'
                        return exhibit if url.endswith('ex991.htm') else doc
                    rows, _ = check_issuer(cik, submissions, fetch, date(2026, 11, 18))
                    expected = [(correct, quarter)] if actual_accession == accession else []
                    self.assertEqual([(r['fiscalYear'], r['fiscalQuarter']) for r in rows], expected)


if __name__ == '__main__':
    unittest.main()
