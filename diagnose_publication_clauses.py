import json,re
from pathlib import Path
from datetime import date
from official_sources import parse_earnings_filing,parse_inline_quarter,_text,_local
from lxml import html
rs=json.loads(Path('_diagnostics/report.json').read_text())
for r in rs:
 t=r['ticker'];p=Path('_diagnostics/sources')/(t+'-primary.html')
 if not p.exists():continue
 f=r['filings'][0];entry={'ticker':t}
 try:entry['parsed']=parse_earnings_filing(p.read_bytes(),f['event']['reportDate'],f['event']['filingDate'],date(2026,11,4),exhibit=Path('_diagnostics/sources/'+t+'-release.html').read_bytes() if Path('_diagnostics/sources/'+t+'-release.html').exists() else None)
 except ValueError as e:
  entry['error']=str(e)
  tree=html.fromstring(p.read_bytes())
  for node in tree.iter():
   if _local(node) in ('p','div','tr','h1','h2','h3','h4'):node.tail=(node.tail or '')+'\n'
  txt='\n'.join(' '.join(line.split()) for line in _text(tree).splitlines() if line.strip())
  pos=txt.lower().rfind('item 2.02')
  entry['text']=txt[pos:pos+1800]
 print(json.dumps(entry),flush=True)
