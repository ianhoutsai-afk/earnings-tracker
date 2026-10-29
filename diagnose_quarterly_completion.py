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
                if result['fiscalQuarter'] == 4:
                    for cached_url, cached_doc in list(cache.items()):
                        if '/Archives/' not in cached_url or 'ex99' not in cached_url.lower(): continue
                        release_tree=html.fromstring(cached_doc)
                        for table in release_tree.xpath('//table'):
                            text=' '.join(table.text_content().split())
                            if 'Revenue' in text and 'Diluted' in text and len(text) < 20000:
                                print('RELEASE_TABLE_HTML', cached_url, html.tostring(table,encoding='unicode')[:28000],flush=True)
                                break
                        break
                tree = html.fromstring(document)
                end = result['periodEnd']
                contexts = {n.get('id') for n in tree.iter() if str(n.tag).lower().split(':')[-1] == 'context' and end in ' '.join(n.itertext())}
                facts = [n for n in tree.iter() if 'revenue' in n.get('name','').lower() and n.get('contextref') in contexts]
                for n in facts[:2]:
                    print('REVENUE_DOM', latest_url[0], html.tostring(n, encoding='unicode'), flush=True)
                    ancestors = list(n.iterancestors())
                    for ancestor in ancestors[:6]:
                        prev=ancestor.getprevious()
                        print('ANCESTOR', ancestor.tag, 'TEXT', (ancestor.text or '')[:100], 'PREVIOUS', html.tostring(prev,encoding='unicode')[:1200] if prev is not None else '', flush=True)
                    row=next((p for p in ancestors if str(p.tag).lower()=='tr'),None)
                    print('REVENUE_ROW', html.tostring(row,encoding='unicode')[:5500] if row is not None else '', flush=True)
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
