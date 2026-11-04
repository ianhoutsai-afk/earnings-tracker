"""Original official release statement coverage; no network in these tests."""
import unittest
from pathlib import Path
from release_metrics import parse_release_quarter_metrics
class OriginalReleaseSources(unittest.TestCase):
 def test_original_releases_supply_direct_quarter_metrics(self):
  for ticker,cik,end,revenue,eps in [('AAPL','0000320193','2026-09-26',114477000000,2.10),('AMD','0000002488','2026-09-26',13377000000,1.46),('AMZN','0001018724','2026-09-30',201944000000,1.89),('ANET','0001596532','2026-09-30',3657600000,1.22),('ABT','0000001800','2026-09-30',13013000000,0.53)]:
   with self.subTest(ticker=ticker):
    doc=Path('_diagnostics/sources/'+ticker+'-release.html').read_bytes()
    self.assertEqual(parse_release_quarter_metrics(doc,end,cik),{'revenue':revenue,'epsGaapDiluted':eps})
