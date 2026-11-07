"""Collect at most 50 original missing revenue facts; do not mutate site data."""
import json,re,hashlib,time
from pathlib import Path
from datetime import date
from decimal import Decimal
from lxml import html
from official_sync import fetch_sec,decode_sec_body
from official_sources import parse_inline_quarter,_local,_desc,_unique_text,REVENUE_TAGS
ISSUER_NAMES={}
BAD=re.compile(r'(?i)non[\s-]*gaap|adjusted|pro[\s-]*forma|reconcil|\bsegment\b|\bnotes?\b')
ALLOWED_TAGS={t.lower() for t in REVENUE_TAGS}|{'us-gaap:regulatedandunregulatedoperatingrevenue'}
def text(n):
 if not isinstance(n.tag,str):return ''
 return clean(' '.join(n.itertext()))
def clean(s):return ' '.join(str(s).translate({0x200b:None,0xfeff:None,0x2060:None}).replace('\xa0',' ').split())
def compact(s):return re.sub('[^a-z0-9]','',clean(s).lower())
def title(raw,issuer):
 s=clean(raw)
 if BAD.search(s):return False
 s=re.sub(r'(?i)\((?:unaudited|in\b|u\.?s\.?\s+dollars|dollars\b)[^)]*\)','',s)
 x=compact(s);name=compact(issuer)
 if name and x.startswith(name):x=x[len(name):];x=re.sub(r'^and(?:its)?subsidiaries','',x)
 if name and x.endswith(name):x=x[:-len(name)]
 if not any(w in x for w in ('consolidated','combined')):return False
 p=r'(?:unaudited)?(?:(?:condensed|consolidated|combined))*(?:statements?of(?:(?:condensed|consolidated|combined))*(?:(?:comprehensive)?income|operations|earnings)(?:loss|orloss)?(?:andcomprehensive(?:income|loss)(?:loss|orloss)?)?|incomestatements?)(?:unaudited)?'
 return bool(re.fullmatch(p,x))
def harmless(raw,issuer):
 s=re.sub(r'(?i)\s*\(\s*unaudited\s*\)\s*$', '', clean(raw)).strip()
 words=set(re.findall('[a-z]+',s.lower()))
 period_words=set('for the three six nine twelve and months month quarter quarters ended ending first second third fourth fiscal unaudited january february march april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec'.split())
 period_header='ended' in words and words<=period_words
 return period_header or bool(re.fullmatch(r'\d{1,3}',s)) or not s or compact(s)==compact(issuer) or bool(re.fullmatch(r'(?i)\(?\s*(?:unaudited|(?:in|amounts in|u\.?s\.?\s+dollars|dollars)[^()]{0,200})\s*\)?',s))
def scope(table,issuer):
 # Only explicit original GAAP income-statement titles may establish scope.
 for row in table.xpath('./caption|./tr|./thead/tr|./tbody/tr')[:24]:
  if any(_local(n)=='nonfraction' for n in row.iter()):break
  strings=[text(row)]+[text(c) for c in row.iterdescendants() if isinstance(c.tag,str) and not any(_local(n)=='nonfraction' for n in c.iter())]
  if any(BAD.search(s) for s in strings):return None
  for s in strings:
   if title(s,issuer):return s
 current=table
 for depth in range(5):
  prev=current.getprevious()
  for count in range(512):
   if prev is None:break
   s=text(prev)
   contains_table=_local(prev)=='table' or bool(prev.xpath('.//table'))
   if title(s,issuer) and not any(_local(n)=='nonfraction' for n in prev.iter()):return s
   if re.fullmatch(r'(?:unaudited)?(?:condensed)?statements?of(?:income|operations|earnings)(?:loss|orloss)?(?:unaudited)?',compact(s)):
    anchor=prev.getprevious()
    for blank in range(8):
     if anchor is None or text(anchor):break
     anchor=anchor.getprevious()
    if anchor is not None and compact(text(anchor)) in {compact(issuer),compact(issuer)+'andsubsidiaries',compact(issuer)+'anditssubsidiaries'}:
     return text(anchor)+' | '+s
   if contains_table or BAD.search(s) or not harmless(s,issuer):return None
   prev=prev.getprevious()
  parent=current.getparent()
  if parent is None or _local(parent) not in ('div','section'):break
  if clean(parent.text or '') or clean(current.tail or ''):break
  siblings=[n for n in parent if n is not current]
  if any((_local(n)=='table' or n.xpath('.//table') or not harmless(text(n),issuer)) for n in siblings):break
  current=parent
 return None
def label_before_numbers(row):
 # A prior-year number before the chosen fact is data, never part of its label.
 out=[]
 class Done(Exception):pass
 def visit(n):
  if _local(n)=='nonfraction':raise Done
  if isinstance(n.tag,str) and n.text:out.append(n.text)
  for child in n:
   visit(child)
   if child.tail:out.append(child.tail)
 try:visit(row)
 except Done:pass
 s=clean(' '.join(out)).strip(' :$')
 s=re.sub(r'^\d+\)\s*','',s)
 s=re.sub(r'\s*\(\s*(?:(?:Note\s*)?\d+(?:\s*(?:and|,)\s*(?:Note\s*)?\d+)*|[A-Za-z])\s*\)\s*$','',s,flags=re.I)
 return s
def eligible_label(label):
 return bool(re.fullmatch(r'(?i)(?:(?:total\s+)?(?:net\s+)?(?:operating\s+)?(?:revenues?|sales)|revenues?,\s*net|revenues?\s+from\s+operations)',label))
def inspect(record,body,cik,issuer_override=None):
 parsed=parse_inline_quarter(body,record['periodEnd'],cik)
 if (parsed['fiscalYear'],parsed['fiscalQuarter'])!=(record['fiscalYear'],record['fiscalQuarter']):return None,'fiscal_identity'
 tree=html.fromstring(body)
 nodes=[n for n in tree.iter() if isinstance(n.tag,str)]
 issuer_values={text(n) for n in nodes if n.get('name','').lower()=='dei:entityregistrantname' and text(n)}
 issuer=next(iter(issuer_values)) if len(issuer_values)==1 else None
 # ServiceNow's cover name is continuation-split; validate its canonical SEC CIK name.
 if not issuer or record['ticker']=='NOW':
  key=str(cik).zfill(10)
  if key not in ISSUER_NAMES:
   payload=json.loads(fetch_sec('https://data.sec.gov/submissions/CIK'+key+'.json'))
   if int(payload.get('cik',0))!=int(cik):return None,'issuer_identity'
   ISSUER_NAMES[key]=payload.get('name')
   time.sleep(.2)
  issuer=ISSUER_NAMES[key]
  if not issuer:return None,'issuer_name'
  print('SEC registrant name '+record['ticker']+': '+issuer,flush=True)
 if issuer_override:issuer=issuer_override
 contexts={}
 for c in (n for n in nodes if _local(n)=='context'):
  entity=_unique_text(_desc(c,'identifier'));start=_unique_text(_desc(c,'startdate'));end=_unique_text(_desc(c,'enddate'))
  if (entity and entity.isdigit() and int(entity)==int(cik) and start and end==record['periodEnd'] and not _desc(c,'segment') and not _desc(c,'scenario') and 70<=(date.fromisoformat(end)-date.fromisoformat(start)).days+1<=110):contexts[c.get('id')]={'entity':entity,'start':start,'end':end}
 units={u.get('id'):_unique_text(_desc(u,'measure')) for u in nodes if _local(u)=='unit' and not _desc(u,'divide')}
 noncontract=any(n.get('name','').lower()=='us-gaap:revenuenotfromcontractwithcustomer' and n.get('contextref') in contexts for n in nodes)
 candidates=[]
 for n in nodes:
  tag=n.get('name','').lower()
  extension=':' in tag and tag.split(':')[0] not in {'us-gaap','dei'} and re.search(r'revenue|sales',tag.split(':',1)[1]) and not re.search(r'adjusted|nongaap|proforma|segment',tag)
  if _local(n)!='nonfraction' or (tag not in ALLOWED_TAGS and not extension) or n.get('contextref') not in contexts:continue
  if (units.get(n.get('unitref')) or '').lower()!='iso4217:usd':continue
  # Accept only the printed company total in the original GAAP statement; unrelated note facts do not change that total.
  if n.get('format','').split(':')[-1] not in ('','num-dot-decimal','numdotdecimal'):continue
  rows=n.xpath('ancestor::tr');tables=n.xpath('ancestor::table')
  if not rows or not tables:continue
  row=rows[-1];table=tables[-1]
  if table.xpath('.//table'):continue
  label=label_before_numbers(row)
  if not eligible_label(label):continue
  heading=scope(table,issuer)
  if heading is None:continue
  value=re.sub(r'\s+','',text(n)).replace(',','')
  if not re.fullmatch(r'\d+(?:\.\d+)?',value):continue
  scale=int(n.get('scale','0'))
  if not -12<=scale<=15 or n.get('sign')=='-':continue
  number=Decimal(value)*(Decimal(10)**scale)
  if not number.is_finite() or number<0:continue
  candidates.append({'value':float(number),'rawValue':value,'scale':scale,'factTag':n.get('name'),'unitMeasure':units[n.get('unitref')],'contextId':n.get('contextref'),'context':contexts[n.get('contextref')],'issuerName':issuer,'statementHeading':heading,'rowLabel':label,'rowText':text(row)[:1800],'rowHtml':html.tostring(row,encoding='unicode')[:18000],'statementText':text(table)[:18000],'contextHtml':html.tostring(next(c for c in nodes if _local(c)=='context' and c.get('id')==n.get('contextref')),encoding='unicode'),'unitHtml':html.tostring(next(u for u in nodes if _local(u)=='unit' and u.get('id')==n.get('unitref')),encoding='unicode'),'hasNoncontractFacts':noncontract})
 values={c['value'] for c in candidates}
 if len(values)!=1:return None,'missing_or_conflicting_total'
 return candidates[0],None


def eps_diagnostic(record,body,cik):
 tree=html.fromstring(body);nodes=[n for n in tree.iter() if isinstance(n.tag,str)]
 contexts={}
 for c in (n for n in nodes if _local(n)=='context'):
  entity=_unique_text(_desc(c,'identifier'));start=_unique_text(_desc(c,'startdate'));end=_unique_text(_desc(c,'enddate'))
  if not(entity and entity.isdigit() and int(entity)==int(cik) and start and end==record['periodEnd'] and 70<=(date.fromisoformat(end)-date.fromisoformat(start)).days+1<=110):continue
  dimensions=[{'axis':n.get('dimension'),'member':text(n)} for n in _desc(c,'explicitmember')]
  contexts[c.get('id')]={'entity':entity,'start':start,'end':end,'dimensions':dimensions,'hasTyped':bool(_desc(c,'typedmember')),'scenario':bool(_desc(c,'scenario')),'html':html.tostring(c,encoding='unicode')}
 units={}
 for u in (n for n in nodes if _local(n)=='unit'):
  units[u.get('id')]={'text':text(u),'html':html.tostring(u,encoding='unicode')}
 issuer_values={text(n) for n in nodes if n.get('name','').lower()=='dei:entityregistrantname' and text(n)}
 issuer=next(iter(issuer_values)) if len(issuer_values)==1 else None
 key=str(cik).zfill(10)
 if key in ISSUER_NAMES:canonical=ISSUER_NAMES[key]
 else:canonical=None
 facts=[]
 for n in nodes:
  if _local(n)!='nonfraction' or n.get('name','').lower() not in {'us-gaap:earningspersharediluted','us-gaap:earningspersharebasic'} or n.get('contextref') not in contexts:continue
  rows=n.xpath('ancestor::tr');tables=n.xpath('ancestor::table')
  if not rows or not tables:continue
  table=tables[-1];row=rows[-1]
  heading=scope(table,issuer or '')
  if not heading and canonical:heading=scope(table,canonical)
  facts.append({'tag':n.get('name'),'rawValue':text(n),'sign':n.get('sign'),'scale':n.get('scale','0'),'format':n.get('format'),'contextId':n.get('contextref'),'context':contexts[n.get('contextref')],'unit':units.get(n.get('unitref')),'rowLabel':label_before_numbers(row),'rowText':text(row)[:2500],'heading':heading,'statementText':text(table)[:18000],'rowHtml':html.tostring(row,encoding='unicode')[:18000]})
 return {'ticker':record['ticker'],'periodEnd':record['periodEnd'],'sourceUrl':record['secUrl'],'sourceSha256':hashlib.sha256(body).hexdigest(),'fiscalYear':record['fiscalYear'],'fiscalQuarter':record['fiscalQuarter'],'facts':facts}

from urllib.parse import urljoin,urlparse
from release_metrics import _grid
records=json.loads(Path('official_history.json').read_text());mapping=json.loads(Path('sp500_mapping.json').read_text())
out=Path('audit-bulk');(out/'releases').mkdir(parents=True,exist_ok=True)
eps_selected=[];wide=[];release_selected=[];skipped=[]
def num(raw,sign=None,scale=0):
 v=clean(raw).replace(',','').replace('$','').replace(' ','')
 neg=v.startswith('(') and v.endswith(')')
 if neg:v=v[1:-1]
 if v.startswith('.'):v='0'+v
 if not re.fullmatch(r'-?\d+(?:\.\d+)?',v):return None
 try:x=Decimal(v)*(Decimal(10)**int(scale))
 except Exception:return None
 if neg or sign=='-':x=-abs(x)
 return float(x) if x.is_finite() else None
def getbody(url):
 cache=Path('.sec_cache/official')/(hashlib.sha256(url.encode()).hexdigest()+'.body')
 b=decode_sec_body(cache.read_bytes()) if cache.exists() else fetch_sec(url)
 if not cache.exists():time.sleep(.2)
 return b
def canonical(cik):
 key=str(cik).zfill(10)
 if key not in ISSUER_NAMES:
  p=json.loads(fetch_sec('https://data.sec.gov/submissions/CIK'+key+'.json'))
  if int(p.get('cik',0))!=int(cik):raise ValueError('Registrant mismatch')
  ISSUER_NAMES[key]=p.get('name');time.sleep(.2)
 return ISSUER_NAMES[key]
def release_metrics(r,body,url,cik):
 tree=html.fromstring(body)
 issuer=canonical(cik) or mapping[r['ticker']].get('name','')
 end=date.fromisoformat(r['periodEnd'])
 values={'revenue':[],'epsGaapDiluted':[]}
 for ti,table in enumerate(tree.xpath('//table')):
  if table.xpath('.//table'):continue
  heading=scope(table,issuer)
  if not heading:continue
  try:grid=[[clean(x) for x in row] for row in _grid(table)]
  except Exception:continue
  labels=[]
  for row in grid:
   label=next((x for x in row if x and not re.fullmatch(r'\d+\)|\(\d+\)',x)),'')
   label=re.sub(r'\s*\((?:\d+|[a-z])\)\s*$','',label,flags=re.I).strip(' :')
   labels.append(label)
  boundary=next((i for i,x in enumerate(labels) if eligible_label(x) or re.fullmatch(r'(?i)sales and other operating revenues',x)),None)
  if boundary is None:continue
  headers=grid[:boundary]
  prefix=[heading,' '.join(' '.join(row) for row in headers)]
  cur=table
  for depth in range(5):
   prev=cur.getprevious()
   for k in range(20):
    if prev is None:break
    tx=text(prev)
    if _local(prev)=='table' or prev.xpath('.//table'):break
    prefix.append(tx)
    if title(tx,issuer):break
    if tx and not harmless(tx,issuer):break
    prev=prev.getprevious()
   par=cur.getparent()
   if par is None or _local(par) not in {'div','section'}:break
   if clean(par.text or '') or clean(cur.tail or ''):break
   cur=par
  unit_text=' '.join(prefix)
  if re.search(r'(?i)\b(?:EUR|GBP|CAD|AUD|JPY|CNY|euros?|renminbi|yen)\b',unit_text):continue
  scale=6 if re.search(r'(?i)\bmillions\b',unit_text) else 3 if re.search(r'(?i)\bthousands\b',unit_text) else None
  if scale is None or r.get('currency')!='USD' or not ('$' in text(table) or re.search(r'(?i)U\.?S\.?\s+dollars|USD',unit_text)):continue
  width=max(map(len,grid),default=0);columns=[];column_headers={}
  for x in range(1,width):
   h=' '.join(dict.fromkeys(row[x] for row in headers if x<len(row) and row[x]));column_headers[x]=h
   if not re.search(r'(?i)\b(?:three months|quarters?|(?:twelve|thirteen|fourteen) weeks)\s+ended\b',h):continue
   if re.search(r'(?i)\b(?:six|nine|twelve) months|\byears?\s+ended\b|\bfiscal year\b',h):continue
   years=set(re.findall(r'\b20\d{2}\b',h))
   if years!={str(end.year)}:continue
   months={end.strftime('%B'),end.strftime('%b')}
   if end.month==9:months.add('Sept')
   if not any(re.search(r'(?i)\b'+mo+r'\.?\s+'+str(end.day)+r'\b',h) for mo in months):continue
   columns.append(x)
  if not columns:continue
  if re.search(r'(?i)continuing|discontinued|non[\s-]*gaap|adjusted\s+(?:diluted|earnings|income|EPS)',text(table)):continue
  eps_heading=re.compile(r'(?i)(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+)?share')
  table_rows=grid[boundary:]
  table_labels=labels[boundary:]
  for i,(row,label) in enumerate(zip(table_rows,table_labels)):
   if not re.fullmatch(r'(?i)diluted|basic\s*(?:and|&)\s*diluted',label):continue
   k=i-1
   if k>=0 and re.fullmatch(r'(?i)basic',table_labels[k]):
    if not re.fullmatch(r'(?i)diluted',label):continue
    k-=1
   if k<0 or not eps_heading.fullmatch(table_labels[k]):continue
   section=table_rows[k]
   if any(v and not eps_heading.fullmatch(v.strip(' :')) for v in section):continue
   metric='epsGaapDiluted'
   if not re.search(r'(?i)except.{0,120}per.{0,30}share|per.{0,30}share.{0,50}(?:data|amounts|except)',unit_text):continue
   for x in columns:
    if x>=len(row):continue
    raw=row[x];v=num(raw)
    if v is None:continue
    left=row[x-1] if x else '';right=row[x+1] if x+1<len(row) else ''
    if left.strip() in {'(','$(','($'} or right.strip()==')':
     if left.strip() not in {'(','$(','($'} or right.strip()!=')' or column_headers.get(x-1)!=column_headers.get(x) or column_headers.get(x+1)!=column_headers.get(x):continue
     v=-abs(v)
    if metric=='revenue':
     if v<0:continue
     v=float(Decimal(str(v))*Decimal(10)**scale)
    values[metric].append({'value':v,'rawValue':raw,'scale':scale if metric=='revenue' else 0,'unitMeasure':'USD' if metric=='revenue' else 'USD/shares','statementHeading':heading,'statementText':text(table)[:20000],'rowLabel':label,'rowText':' | '.join(row),'header':column_headers[x],'unitCaption':unit_text[:3000],'tableIndex':ti,'columnIndex':x,'signFromSplitParentheses':left.strip() in {'(','$(','($'},'epsSectionLabel':table_labels[k],'sectionRows':table_rows[k:i+1],'rowIndex':boundary+i})
 return {f:vs[0] for f,vs in values.items() if vs and len({v['value'] for v in vs})==1}

original={(r['ticker'],r['periodEnd']):r for r in records}
for seed in json.loads(Path('eps-seeds.json').read_text()):
 key=seed['ticker'],seed['periodEnd']
 r=original.get(key)
 if not r or r.get('epsGaapDiluted') is not None or r.get('releaseSourceUrl')!=seed['parentReleaseUrl']:continue
 url=seed['sourceUrl']
 try:
  cik=mapping[r['ticker']]['cik']
  if int(url.split('/data/')[1].split('/')[0])!=int(cik):continue
  body=getbody(url)
  digest=hashlib.sha256(body).hexdigest()
  if digest!=seed['sourceSha256']:raise ValueError('Source digest changed')
  found=release_metrics(r,body,url,cik).get('epsGaapDiluted')
  if found is None:continue
  item={**seed,'sourceSha256':digest,'sourceKind':'explicit_quarter_release_table','fiscalYear':r['fiscalYear'],'fiscalQuarter':r['fiscalQuarter'],'field':'epsGaapDiluted','priorValue':None,'evidence':found}
  (out/'releases'/(r['ticker']+'-'+r['periodEnd']+'.json')).write_text(json.dumps([item],indent=2)+'\n')
  print(r['ticker'],r['periodEnd'],found['value'],found['epsSectionLabel'],flush=True)
 except Exception as exc:print('Skipped',key,type(exc).__name__,flush=True)
(out/'revenue.json').write_text('{"selected":[]}\n')
(out/'eps-selected.json').write_text('[]\n')
