"""Read-only checks for the reviewed quarterly statement adapters."""
import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from official_sync import fetch_sec, check_issuer
from release_metrics import parse_release_quarter_metrics
TARGETS = [
 ('TSLA','0001318605','2025-12-31','https://www.sec.gov/Archives/edgar/data/1318605/000162828026003837/exhibit991.htm', {'revenue':24901000000, 'epsGaapDiluted':0.24}),
 ('SYK','0000310764','2026-09-30','https://www.sec.gov/Archives/edgar/data/310764/000031076426000059/sykex991earningsq32026.htm', {'revenue':6520000000,'epsGaapDiluted':1.96}),
]
def verify():
 for ticker,cik,end,url,expected in TARGETS:
  body=fetch_sec(url)
  result=parse_release_quarter_metrics(body,end,cik)
  assert result==expected, (ticker,result,expected)
  print(json.dumps({'ticker':ticker,'periodEnd':end,'metrics':result,'sourceUrl':url,'sha256':hashlib.sha256(body).hexdigest()}),flush=True)
if __name__=='__main__':
 verify()
