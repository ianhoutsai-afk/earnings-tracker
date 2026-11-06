"""Read-only missing EPS and original quarterly-release statement evidence."""
exec(__import__('pathlib').Path('bulk_evidence.py').read_text().split('\nimport argparse,subprocess')[0])
import subprocess
from urllib.parse import urljoin,urlparse
from release_metrics import _grid
records=json.loads(Path('official_history.json').read_text());mapping=json.loads(Path('sp500_mapping.json').read_text())
out=Path('audit-bulk');(out/'releases').mkdir(exist_ok=True)
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
def commit_progress(phase,done,total):
 (out/'eps-selected.json').write_text(json.dumps(eps_selected,indent=2)+'\n')
 (out/'eps-wide.json').write_text(json.dumps(wide,indent=2)+'\n')
 (out/'expanded-progress.json').write_text(json.dumps({'phase':phase,'done':done,'total':total,'epsFields':len(eps_selected),'releaseFields':len(release_selected),'skips':len(skipped)},indent=2)+'\n')
 (out/'expanded-skips.json').write_text(json.dumps(skipped,indent=2)+'\n')
 subprocess.run(['git','add','audit-bulk'],check=True)
 subprocess.run(['git','commit','-m','Checkpoint '+phase+' official evidence '+str(done)+'/'+str(total)],check=True)
 subprocess.run(['git','push','origin','HEAD'],check=True)
def canonical(cik):
 key=str(cik).zfill(10)
 if key not in ISSUER_NAMES:
  p=json.loads(fetch_sec('https://data.sec.gov/submissions/CIK'+key+'.json'))
  if int(p.get('cik',0))!=int(cik):raise ValueError('Registrant mismatch')
  ISSUER_NAMES[key]=p.get('name');time.sleep(.2)
 return ISSUER_NAMES[key]
def dims(c):
 return [(n.get('dimension','').lower(),text(n)) for n in _desc(c,'explicitmember')]
def select_eps(r,body,cik):
 parsed=parse_inline_quarter(body,r['periodEnd'],cik)
 if (parsed['fiscalYear'],parsed['fiscalQuarter'])!=(r['fiscalYear'],r['fiscalQuarter']):return None,'fiscal_identity'
 root=html.fromstring(body);nodes=[n for n in root.iter() if isinstance(n.tag,str)]
 cs={}
 allcontexts={}
 for c in (n for n in nodes if _local(n)=='context'):
  ent=_unique_text(_desc(c,'identifier'))
  if not ent or not ent.isdigit() or int(ent)!=int(cik):continue
  allcontexts[c.get('id')]=c
  st=_unique_text(_desc(c,'startdate'));en=_unique_text(_desc(c,'enddate'))
  if st and en==r['periodEnd'] and 70<=(date.fromisoformat(en)-date.fromisoformat(st)).days+1<=110:cs[c.get('id')]=c
 units={}
 for u in (n for n in nodes if _local(n)=='unit'):
  nu=_desc(u,'unitnumerator');de=_desc(u,'unitdenominator')
  if nu and de and (_unique_text(_desc(nu[0],'measure')) or '').lower()=='iso4217:usd' and (_unique_text(_desc(de[0],'measure')) or '').lower()=='xbrli:shares':units[u.get('id')]=u
 names={text(n) for n in nodes if n.get('name','').lower()=='dei:entityregistrantname' and text(n)}
 issuer=next(iter(names)) if len(names)==1 else None
 canon=canonical(cik)
 symbols=[]
 for n in nodes:
  if n.get('name','').lower()!='dei:tradingsymbol' or n.get('contextref') not in allcontexts:continue
  symbol=text(n).strip().replace('.','-')
  c=allcontexts[n.get('contextref')]
  if symbol==r['ticker']:
   symbols.append({'symbol':symbol,'dimensions':dims(c),'factHtml':html.tostring(n,encoding='unicode'),'contextHtml':html.tostring(c,encoding='unicode')})
 candidates=[];other=[]
 for n in nodes:
  tag=n.get('name','').lower()
  if _local(n)!='nonfraction' or n.get('contextref') not in cs or n.get('unitref') not in units:continue
  if not re.search(r'pershare|perunit',tag):continue
  c=cs[n.get('contextref')];rows=n.xpath('ancestor::tr');tables=n.xpath('ancestor::table')
  if not rows or not tables or tables[-1].xpath('.//table'):continue
  row=rows[-1];table=tables[-1];label=label_before_numbers(row)
  heading=scope(table,issuer or '') or scope(table,canon or '')
  other.append({'tag':n.get('name'),'raw':text(n),'sign':n.get('sign'),'label':label,'heading':heading,'dimensions':dims(c),'statementText':text(table)[:18000]})
  if not heading or _desc(c,'typedmember') or _desc(c,'scenario'):continue
  ds=dims(c)
  if ds and not(len(ds)==1 and ds[0][0]=='us-gaap:statementclassofstockaxis' and re.fullmatch(r'(?i)(?:us-gaap:Common(?:Stock|Class[A-Z])Member|[a-z0-9_-]+:Common(?:Stock|Class[A-Z0-9]+)Member)',ds[0][1])):continue
  is_diluted=tag=='us-gaap:earningspersharediluted'
  combined=tag=='us-gaap:earningspersharebasic' and bool(re.search(r'(?i)basic\s*(?:and|&)\s*diluted|basic\s+and\s+diluted',label))
  if not (is_diluted or combined):continue
  if BAD.search(label) or re.search(r'(?i)continuing|discontinued',label):continue
  if n.get('format','').split(':')[-1] not in ('','num-dot-decimal','numdotdecimal'):continue
  v=num(text(n),n.get('sign'),n.get('scale','0'))
  if v is None:continue
  candidates.append({'value':v,'rawValue':text(n),'scale':int(n.get('scale','0')),'sign':n.get('sign'),'factTag':n.get('name'),'unitMeasure':'USD/shares','contextId':n.get('contextref'),'context':{'entity':str(cik),'start':_unique_text(_desc(c,'startdate')),'end':r['periodEnd'],'dimensions':ds},'contextHtml':html.tostring(c,encoding='unicode'),'unitHtml':html.tostring(units[n.get('unitref')],encoding='unicode'),'issuerName':canon or issuer,'statementHeading':heading,'statementText':text(table)[:18000],'rowLabel':label,'rowText':text(row)[:2500],'rowHtml':html.tostring(row,encoding='unicode')[:18000],'combinedBasicDilutedCaption':combined})
 dimensionless=[x for x in candidates if not x['context']['dimensions']]
 chosen=dimensionless;basis='dimensionless'
 if not chosen:
  common=[x for x in candidates if x['context']['dimensions']]
  mapped={ds[0][1] for s in symbols for ds in [s['dimensions']] if len(ds)==1 and ds[0][0]=='us-gaap:statementclassofstockaxis'}
  matched=[x for x in common if x['context']['dimensions'][0][1] in mapped]
  if matched:chosen=matched;basis='exact SEC trading-symbol stock-class context'
  elif len({x['value'] for x in common})==1:chosen=common;basis='all reported common-stock diluted EPS facts agree'
 if not chosen or len({x['value'] for x in chosen})!=1:
  wide.append({'ticker':r['ticker'],'periodEnd':r['periodEnd'],'facts':other,'symbols':symbols})
  return None,'no_unambiguous_primary_total_eps'
 e=chosen[0];e['stockClassBasis']=basis;e['stockSymbolEvidence']=symbols;e['allPrimaryDilutedClassValues']=[{'value':x['value'],'dimensions':x['context']['dimensions']} for x in candidates]
 return e,None

eps_targets=sorted([r for r in records if r.get('form')=='10-Q' and r.get('secUrl') and r.get('epsGaapDiluted') is None],key=lambda r:(-date.fromisoformat(r['periodEnd']).toordinal(),r['ticker']))
for i,r in enumerate(eps_targets,1):
 try:
  b=getbody(r['secUrl']);e,reason=select_eps(r,b,mapping[r['ticker']]['cik'])
  if e:eps_selected.append({'ticker':r['ticker'],'periodEnd':r['periodEnd'],'fiscalYear':r['fiscalYear'],'fiscalQuarter':r['fiscalQuarter'],'field':'epsGaapDiluted','priorValue':None,'sourceUrl':r['secUrl'],'sourceSha256':hashlib.sha256(b).hexdigest(),'evidence':e})
  else:skipped.append({'ticker':r['ticker'],'periodEnd':r['periodEnd'],'field':'epsGaapDiluted','reason':reason})
 except Exception as exc:skipped.append({'ticker':r['ticker'],'periodEnd':r['periodEnd'],'reason':type(exc).__name__})
 if i%25==0:commit_progress('EPS',i,len(eps_targets))
commit_progress('EPS',len(eps_targets),len(eps_targets))

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
  eps_group=False;excluded_eps=False
  for row,label in zip(grid[boundary:],labels[boundary:]):
   metric=None
   if BAD.search(label):continue
   if re.search(r'(?i)weighted|shares (?:outstanding|used)',label):eps_group=False
   if re.search(r'(?i)(?:earnings|income|loss).*per (?:common )?share|per (?:common )?share.*(?:earnings|income|loss)',label):
    eps_group=True;excluded_eps=bool(re.search(r'(?i)continuing|discontinued',label))
   if re.search(r'(?i)continuing|discontinued',label) and eps_group:excluded_eps=True
   if re.search(r'(?i)net (?:income|earnings|loss).*per (?:common )?share',label):excluded_eps=False
   if eligible_label(label) or re.fullmatch(r'(?i)sales and other operating revenues',label):metric='revenue'
   elif not excluded_eps and not re.search(r'(?i)\bclass\s+[a-z0-9]',label) and ((eps_group and re.fullmatch(r'(?i)(?:diluted|basic\s*(?:and|&)\s*diluted)',label)) or re.search(r'(?i)diluted.*per.*share|per.*diluted.*share|per.*share.*diluted',label)):metric='epsGaapDiluted'
   if metric is None or r.get(metric) is not None:continue
   if metric=='revenue' and mapping[r['ticker']].get('sector')=='Financials' and r['ticker'] not in {'ARES','BEN','ERIE','FISV','IVZ','MSCI','SPGI'}:continue
   if metric=='epsGaapDiluted' and not re.search(r'(?i)except.{0,120}per.{0,30}share|per.{0,30}share.{0,50}(?:data|amounts|except)',unit_text):continue
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
    values[metric].append({'value':v,'rawValue':raw,'scale':scale if metric=='revenue' else 0,'unitMeasure':'USD' if metric=='revenue' else 'USD/shares','statementHeading':heading,'statementText':text(table)[:20000],'rowLabel':label,'rowText':' | '.join(row),'header':column_headers[x],'unitCaption':unit_text[:3000],'tableIndex':ti,'columnIndex':x,'signFromSplitParentheses':left.strip() in {'(','$(','($'},'rowHtml':html.tostring(table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr')[boundary+grid[boundary:].index(row)],encoding='unicode')[:18000] if False else None})
 return {f:vs[0] for f,vs in values.items() if vs and len({v['value'] for v in vs})==1}
release_targets=sorted([r for r in records if r.get('releaseSourceUrl','').startswith('https://www.sec.gov/Archives/edgar/data/') and (r.get('revenue') is None or r.get('epsGaapDiluted') is None)],key=lambda r:(-date.fromisoformat(r['periodEnd']).toordinal(),r['ticker']))
for i,r in enumerate(release_targets,1):
 try:
  cik=mapping[r['ticker']]['cik'];url=r['releaseSourceUrl']
  if int(url.split('/data/')[1].split('/')[0])!=int(cik):raise ValueError('Release archive issuer mismatch')
  body=getbody(url);found=release_metrics(r,body,url,cik)
  if not found:
   root=html.fromstring(body);links=[]
   for a in root.xpath('//a[@href]'):
    h=a.get('href');t=text(a)
    if re.search(r'(?i)99[._-]?1|press.?release|earnings.?release',t+' '+h) and re.search(r'(?i)\.html?$',h):
     u=urljoin(url,h)
     if u.startswith(url.rsplit('/',1)[0]+'/') and u!=url:links.append(u)
   if len(set(links))==1:
    url=links[0];body=getbody(url);found=release_metrics(r,body,url,cik)
  items=[]
  for field,e in found.items():
   item={'ticker':r['ticker'],'periodEnd':r['periodEnd'],'fiscalYear':r['fiscalYear'],'fiscalQuarter':r['fiscalQuarter'],'field':field,'priorValue':None,'sourceUrl':url,'parentReleaseUrl':r['releaseSourceUrl'],'sourceSha256':hashlib.sha256(body).hexdigest(),'sourceKind':'explicit_quarter_release_table','evidence':e}
   items.append(item);release_selected.append(item)
  if items:(out/'releases'/(r['ticker']+'-'+r['periodEnd']+'.json')).write_text(json.dumps(items,indent=2)+'\n')
 except Exception as exc:skipped.append({'ticker':r['ticker'],'periodEnd':r['periodEnd'],'source':'release','reason':type(exc).__name__})
 if i%35==0:commit_progress('releases',i,len(release_targets))
 print(json.dumps({'phase':'releases','done':i,'total':len(release_targets),'fields':len(release_selected)}),flush=True)
commit_progress('releases',len(release_targets),len(release_targets))
