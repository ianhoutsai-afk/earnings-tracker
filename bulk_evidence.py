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

import argparse,subprocess
parser=argparse.ArgumentParser();parser.add_argument('--form',default='10-Q');args=parser.parse_args()
records=json.loads(Path('official_history.json').read_text());mapping=json.loads(Path('sp500_mapping.json').read_text())
targets=sorted([r for r in records if r.get('secUrl') and r.get('form')==args.form and (r.get('revenue') is None or r.get('epsGaapDiluted') is None) and mapping.get(r['ticker'],{}).get('tickerStatus') not in ('historical_alias','unconfirmed')],key=lambda r:(-date.fromisoformat(r['periodEnd']).toordinal(),r['ticker']))
out=Path('audit-bulk');out.mkdir(exist_ok=True)
selected=[];diagnostics=[];skipped=[];inspected=0
def checkpoint():
 (out/'revenue.json').write_text(json.dumps({'inspected':inspected,'selected':selected,'skipped':skipped},indent=2)+'\n')
 (out/'eps-diagnostic.json').write_text(json.dumps(diagnostics,indent=2)+'\n')
 (out/'progress.json').write_text(json.dumps({'inspected':inspected,'targets':len(targets),'revenueCandidates':len(selected),'epsDiagnosed':len(diagnostics),'skipped':len(skipped)},indent=2)+'\n')
 subprocess.run(['git','add','audit-bulk'],check=True)
 subprocess.run(['git','commit','-m','Checkpoint official missing-field evidence '+str(inspected)+'/'+str(len(targets))],check=True)
 subprocess.run(['git','push','origin','HEAD'],check=True)
for record in targets:
 url=record['secUrl'];cik=mapping[record['ticker']]['cik']
 try:
  cache=Path('.sec_cache/official')/(hashlib.sha256(url.encode()).hexdigest()+'.body')
  body=decode_sec_body(cache.read_bytes()) if cache.exists() else fetch_sec(url)
  if not cache.exists():time.sleep(.2)
  if record.get('revenue') is None and (mapping[record['ticker']].get('sector') not in {'Financials','Real Estate'} or record['ticker'] in {'ARES','BEN','ERIE','FISV','IVZ','MSCI','SPGI'}):
   evidence,reason=inspect(record,body,cik)
   if not evidence:
    key=str(cik).zfill(10)
    if key not in ISSUER_NAMES:
     payload=json.loads(fetch_sec('https://data.sec.gov/submissions/CIK'+key+'.json'))
     if int(payload.get('cik',0))!=int(cik):raise ValueError('SEC registrant CIK mismatch')
     ISSUER_NAMES[key]=payload.get('name');time.sleep(.2)
    if ISSUER_NAMES[key]:evidence,reason=inspect(record,body,cik,ISSUER_NAMES[key])
   if evidence:selected.append({'ticker':record['ticker'],'periodEnd':record['periodEnd'],'fiscalYear':record['fiscalYear'],'fiscalQuarter':record['fiscalQuarter'],'field':'revenue','priorValue':None,'sourceUrl':url,'sourceSha256':hashlib.sha256(body).hexdigest(),'evidence':evidence})
   else:skipped.append({'ticker':record['ticker'],'periodEnd':record['periodEnd'],'reason':reason})
  if record.get('epsGaapDiluted') is None:diagnostics.append(eps_diagnostic(record,body,cik))
 except Exception as exc:skipped.append({'ticker':record['ticker'],'periodEnd':record['periodEnd'],'reason':type(exc).__name__})
 inspected+=1
 if inspected%30==0:checkpoint()
 print(json.dumps({'inspected':inspected,'total':len(targets),'revenueCandidates':len(selected),'epsDiagnosed':len(diagnostics)}),flush=True)
checkpoint()
