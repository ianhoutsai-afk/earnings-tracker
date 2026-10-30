"""Read-only diagnostics; original sources stay in an evidence artifact."""
import json, hashlib
from pathlib import Path
from lxml import html
from official_sync import fetch_sec
from release_metrics import _scope, _grid, _text, parse_release_quarter_metrics
targets=[
 ('TSLA','0001318605','2025-12-31','https://www.sec.gov/Archives/edgar/data/1318605/000162828026003837/exhibit991.htm'),
 ('SYK','0000310764','2026-09-30','https://www.sec.gov/Archives/edgar/data/310764/000031076426000059/sykex991earningsq32026.htm'),
]
root=Path('metric-evidence');root.mkdir(exist_ok=True)
for ticker,cik,end,url in targets:
 body=fetch_sec(url)
 if isinstance(body,str):body=body.encode()
 (root/(ticker+'.html')).write_bytes(body)
 tree=html.fromstring(body)
 print('SOURCE',json.dumps({'ticker':ticker,'url':url,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'currentParsed':parse_release_quarter_metrics(body,end,cik)}),flush=True)
 print('INTRO',_text(tree)[:4500],flush=True)
 print('LINKS',json.dumps([(a.get('href'),_text(a)) for a in tree.xpath('//a[@href]')][:35]),flush=True)
 for i,table in enumerate(tree.xpath('//table')):
  if table.xpath('.//table'):continue
  text=_text(table)
  if not any(w in text.lower() for w in ('revenue','sales','income','earnings')):continue
  try:grid=_grid(table)
  except Exception:continue
  scope=_scope(table)
  print('TABLE',ticker,i,'SCOPE',str(scope)[:300],json.dumps([list(dict.fromkeys(v for v in row if v)) for row in grid[:65]]),flush=True)
  if scope is not None or ticker=='TSLA':
   for node in table.iter():
    for attr in list(node.attrib):
     if attr not in ('rowspan','colspan') and not (attr=='style' and 'display:none' in node.get(attr,'').replace(' ','')):
      del node.attrib[attr]
   print('FIXTURE',json.dumps({'ticker':ticker,'index':i,'html':html.tostring(table,encoding='unicode')}),flush=True)
