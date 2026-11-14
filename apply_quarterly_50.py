import copy
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from verified_history import apply_official_records, write_json_bundle
from validate_quarterly_data import validate

today = datetime.now(ZoneInfo('America/New_York')).date()
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

manifest = read('official_history.json')
history = read('historical_data.json')
companies = read('data.json')
mapping = read('sp500_mapping.json')
status = read('history_status.json')
before = read('official_scan_state.json')
records = copy.deepcopy(manifest)
by_period = {(r['ticker'], r['periodEnd']): r for r in records}
research = read('../review.json')
candidates = read('../complete25-candidates.json')['selected']
items = list(research['direct'])

for ticker, index in research['table'].items():
    options = [x for x in candidates if x['ticker'] == ticker and x.get('evidence') and
               (ticker, x['periodEnd']) in by_period and
               by_period[ticker, x['periodEnd']]['epsGaapDiluted'] is None]
    x = options[index].copy()
    e = x['evidence']
    column = e['columnIndex']
    assert e['rowCells'][column] == e['rawValue']
    raw = re.sub(r'\s+', '', e['signedRawValue']).replace(',', '').replace('$', '').replace('−', '-')
    value = -float(raw[1:-1]) if raw.startswith('(') and raw.endswith(')') else float(raw)
    if e.get('signFromSplitParentheses'):
        value = -abs(value)
    assert value == e['value'] == x['value'] and e['scale'] == 0 and e['unitMeasure'] == 'USD/shares'
    assert e['headerBasis'] in ('explicit-date', 'fiscal-quarter-column') and e['headerRows']
    assert re.fullmatch(r'[a-f0-9]{64}', e['sourceSha256'])
    x['rowLabel'] = e['rowLabel']
    x['releaseSourceUrl'] = x.pop('parentReleaseUrl')
    items.append(x)

assert len({int(mapping[x['ticker']]['cik']) for x in items}) == len({x['ticker'] for x in items}) == 50
assert len(items) == len({(x['ticker'], x['periodEnd'], x['field']) for x in items})
updates = {}
audit_path = Path('docs/complete-50-issuer-financials-2026-11-14.json')
folder = Path('docs/evidence-complete-50-issuers-2026-11-14')
folder.mkdir(exist_ok=True)
docs = {}
audit_items = []
for item in items:
    ticker = item['ticker']
    key = (ticker, item['periodEnd'])
    row = by_period[key]
    field = item['field']
    issuer = int(mapping[ticker]['cik'])
    assert item['releaseSourceUrl'] == row['releaseSourceUrl']
    assert mapping[ticker].get('tickerStatus') not in ('historical_alias', 'unconfirmed')
    assert row['currency'] == 'USD' and row['periodScope'] == 'quarter'
    assert status[ticker]['officialQuarterCount'] == 5 and status[ticker]['metricsVerifiedQuarterCount'] == 4
    src = urlsplit(item['sourceUrl'])
    assert src.scheme == 'https' and src.netloc == 'www.sec.gov'
    assert src.path.startswith(f'/Archives/edgar/data/{issuer}/')
    assert item['sourceUrl'].rsplit('/', 1)[0] == row['releaseSourceUrl'].rsplit('/', 1)[0]
    if item.get('evidence'):
        assert item['evidence']['entity'] == issuer
        assert (item['fiscalYear'], item['fiscalQuarter']) == (row['fiscalYear'], row['fiscalQuarter'])
    else:
        assert item['sourceLine'] > 0 and item['rowLabel']
    assert field in ('revenue', 'epsGaapDiluted') and row[field] is None and math.isfinite(item['value'])
    old = next(r for r in history[ticker] if r.get('periodEnd') == key[1])
    displayed = 'eps_reported' if field == 'epsGaapDiluted' else 'revenue_reported'
    assert old.get(displayed) in (None, '-') and old['verificationStatus'] == 'official_verified'
    row[field] = item['value']
    row['verifiedAt'] = today.isoformat()
    if field == 'epsGaapDiluted':
        row['epsBasis'] = 'GAAP diluted'
        row['epsSourceUrl'] = item['sourceUrl']
    else:
        assert item['value'] >= 0
        row['revenueSourceUrl'] = item['sourceUrl']
    updates[key] = row
    evidence_file = folder / f'{ticker}-{key[1]}-{field}.json'
    docs[evidence_file] = {**item, 'fiscalYear':row['fiscalYear'], 'fiscalQuarter':row['fiscalQuarter']}
    audit_items.append({k:v for k,v in item.items() if k!='evidence'} | {'evidenceFile':str(evidence_file)})

updated, added = apply_official_records(companies, history, list(updates.values()), today)
assert added == 0
display_fields = {('epsGaapDiluted'): {'eps_reported','epsBasis','epsSourceUrl'}, 'revenue': {'revenue_reported','revenueSourceUrl'}}
allowed = {}
for item in items:
    key = (item['ticker'],item['periodEnd'])
    allowed.setdefault(key, {'verifiedAt'}).update(display_fields[item['field']])

def complete(r):
    return r.get('verificationStatus') == 'official_verified' and r.get('epsBasis') == 'GAAP diluted' and all(
        r.get(f) not in (None, '-') for f in ('revenue_reported', 'eps_reported'))

for ticker, rows in history.items():
    assert len(rows) == len(updated[ticker])
    for old, new in zip(rows, updated[ticker]):
        key = (ticker, old.get('periodEnd'))
        if key in allowed:
            assert complete(new)
            assert {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)} <= allowed[key], key
        else:
            assert old == new, key
    status[ticker]['metricsVerifiedQuarterCount'] = sum(map(complete, updated[ticker]))
assert all(status[t]['metricsVerifiedQuarterCount'] == 5 for t, _ in updates)
state = {**before,
    'completeMetricQuarters':sum(s['metricsVerifiedQuarterCount'] for s in status.values()),
    'fiveCompleteMetricCompanies':sum(s['metricsVerifiedQuarterCount'] == 5 for s in status.values()),
    'pendingCompanies':sum(s['status']!='official_source_checked' or s['officialQuarterCount']<5 or s['metricsVerifiedQuarterCount']<5 for s in status.values()),
    'metricBackfill':{'date':today.isoformat(),'filledFields':len(items),'evidence':str(audit_path)}}
assert state['completeMetricQuarters'] - before['completeMetricQuarters'] == 50
assert state['fiveCompleteMetricCompanies'] - before['fiveCompleteMetricCompanies'] == 50
audit = {'baselineCommit':'0a8de08f1d4554d0f0d3c19648fbaca9e638ed12','companies':50,'quarters':len(updates),'fieldCounts':dict(Counter(x['field'] for x in items)),
         'before':before,'after':state,'selected':audit_items}
docs.update({audit_path:audit, 'official_history.json':records,'historical_data.json':updated,
             'history_status.json':status,'official_scan_state.json':state})
write_json_bundle(docs)
print(json.dumps({'validation':validate(today=today),'counts':audit['fieldCounts'],'complete':state['completeMetricQuarters'],
                  'fiveComplete':state['fiveCompleteMetricCompanies'],'remainingFields':dict(Counter(f for r in records for f in ('revenue','epsGaapDiluted') if r[f] is None))}))
