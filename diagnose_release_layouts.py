from pathlib import Path
import re
import release_metrics as r
from lxml import html
for t,cik,end in [('AAPL','0000320193','2026-09-26'),('AMD','0000002488','2026-09-26'),('AMZN','0001018724','2026-09-30'),('ANET','0001596532','2026-09-30'),('ABT','0000001800','2026-09-30')]:
 r.SUPPORTED_ISSUERS.add(cik)
 doc=Path('_diagnostics/sources/'+t+'-release.html').read_bytes()
 print(t,'EXPLORATORY',r.parse_release_quarter_metrics(doc,end,cik),flush=True)
 tree=html.fromstring(doc)
 for table in tree.xpath('//table'):
  if table.xpath('.//table'):continue
  scope=r._scope(table)
  if scope is None:continue
  grid=r._grid(table)
  labels=[next((v for v in row if v),'') for row in grid]
  print('TABLE',t,scope[:500],grid[:6],[(i,l) for i,l in enumerate(labels) if re.search(r'(?i)revenue|sales|diluted|per share',l)][:15],flush=True)
