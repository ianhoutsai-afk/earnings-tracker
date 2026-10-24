"""Regressions use original SEC documents with source URLs and byte hashes in fixtures."""
import gzip
import json
import unittest
from datetime import date
from pathlib import Path

from official_sources import parse_earnings_filing, parse_earnings_release

FIXTURES = Path(__file__).parent / 'tests/fixtures/official'
SOURCES = json.loads((FIXTURES / 'sources.json').read_text())


def document(ticker, kind):
    return gzip.decompress((FIXTURES / f'{ticker}-{kind}.html.gz').read_bytes())


class OriginalDocumentRegressions(unittest.TestCase):
    def test_conagra_fiscal_quarter_which_ended_on_preserves_fiscal_year(self):
        row=parse_earnings_release(document('CAG','exhibit'),'2026-09-30','2026-09-30',date(2026,10,24))
        self.assertEqual(row['periodEnd'],'2026-08-30')
        self.assertEqual((row['fiscalYear'],row['fiscalQuarter']),(2027,1))

    def test_alexandria_nested_item_blocks_establish_original_publication(self):
        row = parse_earnings_filing(document('ARE', 'primary'), '2026-08-03', '2026-08-03',
                                   date(2026, 10, 24), exhibit=document('ARE', 'exhibit'))
        self.assertEqual(row['date'], '2026-08-03')
        self.assertEqual(row['periodEnd'], '2026-06-30')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 2))

    def test_citizens_publication_statement_does_not_turn_into_a_call_announcement(self):
        row = parse_earnings_filing(document('CFG', 'primary'), '2026-10-16', '2026-10-16',
                                   date(2026, 10, 24), exhibit=document('CFG', 'exhibit'))
        self.assertEqual(row['date'], '2026-10-16')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 3))

    def test_ge_explicit_quarter_ending_is_a_completed_period(self):
        row = parse_earnings_release(document('GE', 'exhibit'), '2026-10-20', '2026-10-20', date(2026, 10, 24))
        self.assertEqual(row['periodEnd'], '2026-09-30')
        self.assertEqual((row['fiscalYear'], row['fiscalQuarter']), (2026, 3))


if __name__ == '__main__':
    unittest.main()
