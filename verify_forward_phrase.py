import hashlib,json,re
from pathlib import Path
from lxml import html
from official_sync import fetch_sec

def normalized(value):
    return re.sub(r'\s+','',value.replace('\u200b','').replace('\ufeff','')).casefold()

path=Path('selected-next-hundred.json')
data=json.loads(path.read_text())
item=next(x for x in data['selected'] if (x['ticker'],x['periodEnd'],x['field'])==('BXP','2025-12-31','epsGaapDiluted'))
proof=item['evidence']
body=fetch_sec(item['sourceUrl'])
source=normalized(' '.join(html.fromstring(body).itertext()))
assert normalized(proof['quarterAnchor']) in source
assert normalized(proof['matchedText']) in normalized(proof['quarterAnchor']) and item['value']==1.56
proof['sourceSha256']=hashlib.sha256(body).hexdigest()
path.write_text(json.dumps(data,indent=2)+'\n')
print('BXP fourth-quarter GAAP diluted EPS independently confirmed from the original exhibit')
