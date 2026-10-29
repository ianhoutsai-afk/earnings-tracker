"""Read-only integration check against the original SEC sources."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from official_sync import check_issuer, fetch_sec

today = datetime.now(ZoneInfo('America/New_York')).date()
cache, last = {}, [0.0]
def fetch(url):
    if url not in cache:
        pause = 0.2 - (time.monotonic() - last[0])
        if pause > 0: time.sleep(pause)
        last[0] = time.monotonic()
        cache[url] = fetch_sec(url)
    return cache[url]

for ticker, cik, minimum in [('TSLA','0001318605','2026-10-21'),('META','0001326801','2026-10-21'),('MSFT','0000789019','2026-10-28')]:
    submissions = json.loads(fetch('https://data.sec.gov/submissions/CIK'+cik+'.json'))
    rows, details = check_issuer(cik, submissions, fetch, today)
    print(json.dumps({'ticker':ticker, 'quarters':rows, 'status':details}), flush=True)
    assert rows and rows[0]['date'] >= minimum, ticker+' latest published quarter is missing'
    assert rows[0]['periodEnd'] == '2026-09-30', ticker+' latest period is wrong'
    assert rows[0]['epsGaapDiluted'] is not None, ticker+' latest GAAP diluted EPS is missing'

    if ticker == 'META':
        from release_metrics import _scope, _grid, parse_release_quarter_metrics
        from lxml import html
        q4=next((r for r in rows if r['fiscalQuarter']==4),None)
        if q4:
            document=fetch(q4['releaseSourceUrl'])
            tree=html.fromstring(document)
            for table in tree.xpath('//table'):
                if table.xpath('.//table'): continue
                grid=_grid(table)
                plain=' '.join(' '.join(row) for row in grid)
                if 'Revenue' not in plain or not any('Diluted' in ' '.join(row) for row in grid): continue
                previous=[]
                n=table
                for _ in range(5):
                    n=n.getprevious()
                    if n is None:break
                    previous.append(' '.join(n.itertext())[:200])
                print('META_Q4_LAYOUT',json.dumps({'scope':_scope(table),'headers':grid[:8],'previous':previous,'rows':[r for r in grid if 'Diluted' in ' '.join(r) or 'share' in ' '.join(r) or 'Revenue' in ' '.join(r)]}),flush=True)
