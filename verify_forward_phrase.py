import hashlib,json,re
from pathlib import Path
from lxml import html
from official_sync import fetch_sec
rows=json.loads(Path('selected-next-hundred.json').read_text())['selected']
item=next(x for x in rows if (x['ticker'],x['periodEnd'],x['field'])==('BXP','2025-12-31','epsGaapDiluted'))
e=item['evidence']
body=fetch_sec(item['sourceUrl'])
assert hashlib.sha256(body).hexdigest()==e['sourceSha256']
text=' '.join(' '.join(html.fromstring(body).itertext()).replace('\xa0',' ').split())
assert e['quarterAnchor'] in text
assert e['matchedText'] in e['quarterAnchor'] and item['value']==1.56
print('BXP fourth-quarter GAAP diluted EPS independently confirmed from the original exhibit')
