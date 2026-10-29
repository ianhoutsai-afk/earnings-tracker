"""Read-only, bounded diagnostics for official quarterly parser failures."""
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from lxml import html
import official_sync as sync

TODAY = datetime.now(ZoneInfo('America/New_York')).date()
latest_url = ['']
seen = set()
cache = {}
last = [0.0]

def fetch(url):
    latest_url[0] = url
    if url in cache:
        return cache[url]
    pause = 0.2 - (time.monotonic() - last[0])
    if pause > 0:
        time.sleep(pause)
    last[0] = time.monotonic()
    cache[url] = sync.fetch_sec(url)
    return cache[url]

def trace(name, original):
    def run(document, *args, **kwargs):
        try:
            result = original(document, *args, **kwargs)
            if name == 'inline' and (result.get('epsGaapDiluted') is None or result.get('revenue') is None):
                print('INCOMPLETE', latest_url[0], json.dumps(result), flush=True)
                tree = html.fromstring(document)
                for table in tree.xpath('//table'):
                    text = ' '.join(table.text_content().split())
                    if any(w in text[:1000].lower() for w in ('statements of operations','statements of income','statements of earnings')):
                        print('STATEMENT', text[:6000], flush=True)
                        break
            return result
        except ValueError as exc:
            key = (name, latest_url[0])
            if key not in seen and len(seen) < 32:
                seen.add(key)
                tree = html.fromstring(document)
                for node in tree.xpath('//script|//style'):
                    node.drop_tree()
                text = ' '.join(tree.text_content().split())
                print('REJECTED', name, latest_url[0], str(exc), 'ARGS', args, 'TEXT', text[:4500], flush=True)
            raise
    return run

for name, attr in [('release','parse_earnings_release'),('filing','parse_earnings_filing'),('inline','parse_inline_quarter')]:
    setattr(sync, attr, trace(name, getattr(sync, attr)))

for ticker, cik in [('TSLA','0001318605'),('META','0001326801'),('MSFT','0000789019')]:
    print('ISSUER', ticker, flush=True)
    try:
        submissions = json.loads(fetch('https://data.sec.gov/submissions/CIK'+cik+'.json'))
        records, details = sync.check_issuer(cik, submissions, fetch, TODAY)
        print('RESULT', ticker, json.dumps({'records':records,'details':details}), flush=True)
    except Exception as exc:
        print('SOURCE_ERROR', ticker, type(exc).__name__, str(exc), flush=True)
