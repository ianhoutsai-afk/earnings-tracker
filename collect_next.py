"""Locate directly reported original SEC quarterly metrics."""
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

from official_sources import parse_earnings_release
from official_sync import _exhibit_links
from datetime import datetime
from zoneinfo import ZoneInfo

today=datetime.now(ZoneInfo('America/New_York')).date()
ranks={t:sum(r.get('revenue') is not None and r.get('epsGaapDiluted') is not None
             for r in records if r['ticker']==t) for t in mapping}

def quarter_columns(grid,boundary,end,year,quarter):
    headers=grid[:boundary]
    columns={}
    months={end.strftime('%B'),end.strftime('%b')}
    if end.month==9:
        months.add('Sept')
    date_pattern=r'(?i)(?:\b(?:'+'|'.join(months)+r')\.?\s+'+str(end.day)+r'\b|\b0?'+str(end.month)+r'/0?'+str(end.day)+r'/'+str(end.year)+r'\b)'
    ordinal=('first','second','third','fourth')[quarter-1]
    explicit=r'(?i)\b(?:'+ordinal+r'[\s-]+quarter|'+str(quarter)+r'(?:st|nd|rd|th)[\s-]+quarter|q'+str(quarter)+r'|'+str(quarter)+r'q)\b'
    for index in range(1,max(map(len,grid),default=0)):
        label=' '.join(dict.fromkeys(r[index] for r in headers if index<len(r) and r[index]))
        label=re.sub(r'(?i)\bFY\s*(\d{2})\b',r'20\1',label)
        if re.search(r'(?i)(?:six|nine|twelve)\s+months|years?\s+ended|full[\s-]*year|annual|percent\s+change',label):
            continue
        years=set(re.findall(r'\b20\d{2}\b',label))
        date_match=(years=={str(end.year)} and re.search(date_pattern,label)
                    and re.search(r'(?i)\b(?:(?:three|3)[\s-]+months|quarters?|(?:twelve|thirteen|fourteen|12|13|14)[\s-]+weeks)\s+ended\b',label))
        ordinal_match=years=={str(year)} and re.search(explicit,label)
        other_ordinals=('first','second','third','fourth')
        if ordinal_match and any(re.search(r'(?i)\b'+x+r'\s+quarter\b',label) for x in other_ordinals if x!=ordinal):
            ordinal_match=False
        if date_match or ordinal_match:
            columns[index]=(label,'explicit-date' if date_match else 'fiscal-quarter-column')
    return columns

label_pattern=re.compile(r'(?i)(?:GAAP\s+(?:diluted\s+(?:EPS|(?:earnings|net income|net loss)(?:\s*\(loss\))?\s+per\s+(?:common\s+)?share)|(?:earnings|net income|net loss)(?:\s*\(loss\))?\s+per\s+diluted\s+(?:common\s+)?share)|(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+diluted\s+(?:common\s+)?share|diluted\s+(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+)?share)')
section_pattern=re.compile(r'(?i)(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+)?share')

total_eps=re.compile(r'''(?ix)(?:gaap\s+)?(?:
    diluted\s+(?:eps|(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+|ordinary\s+)?share)
    |(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:diluted\s+(?:common\s+|ordinary\s+)?share|(?:common\s+|ordinary\s+)?share\s*[-–—:,]\s*diluted)
    |(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+|ordinary\s+)?share\s*\(\s*diluted\s*\)
    |(?:net\s+)?(?:income|earnings|loss)\s+attributable\s+to\s+[\w.' ,&-]{2,90}\s+(?:per\s+diluted\s+(?:common\s+)?share)
)(?:\s*\(\s*EPS\s*\))?''')
attributed_caption=re.compile(r'''(?ix)(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:loss|income|earnings)\))?\s+per\s+(?:common\s+)?share\s+attributable\s+to\s+[\w.' ,&-]{2,95}''')
reviewed_total_sections={
    'APP':('Diluted net income per share',r'Net income \(loss\) per share attributed to Class A and Class B common stockholders\s*[-–—]\s*Diluted'),
    'DVA':('Diluted net income',r'Earnings per share attributable to DaVita Inc\.'),
    'EFX':('Net income attributable to Equifax',r'Diluted earnings per common share'),
    'CARR':('Net earnings per share',r'Diluted'),
}


amount=r'(?:\(\s*\$?\s*[\d,]+\.\d{1,4}\s*\)|[-−]?\s*\$\s*[\d,]+\.\d{1,4}|\$\s*[-−]\s*[\d,]+\.\d{1,4})'
direct_eps=re.compile(r'(?i)\bGAAP\s+(?:diluted\s+(?:EPS|(?:earnings|net income|net loss)\s+per\s+(?:common\s+)?share(?:\s*\(EPS\))?)|(?:earnings|net income|net loss)\s+per\s+diluted\s+(?:common\s+)?share)\s+(?:was|were|of|totaled|was a loss of)\s+(?P<eps>'+amount+r')')
paired_eps=re.compile(r'(?i)\b(?:GAAP\s+)?net\s+(?P<kind>income|earnings|loss)(?:\s+attributable to\s+[a-z0-9 .,\'&-]{1,75}?)?\s+(?:of|was|were|totaled)\s+\$?\s*\(?[\d,.]+\)?\s+(?:billion|million|thousand)\s*\)?\s*,?\s+(?:or|and)\s+(?P<eps>'+amount+r')\s+per\s+diluted\s+(?:common\s+)?share\b')

def narrative_values(root,r,identity,cik):
    year,quarter=r['fiscalYear'],r['fiscalQuarter']
    if (identity['fiscalYear'],identity['fiscalQuarter'])!=(year,quarter):
        return {}
    word=('first','second','third','fourth')[quarter-1]
    end=date.fromisoformat(r['periodEnd'])
    quarter_mark=r'(?i)\b(?:'+word+r'\s+quarter|'+str(quarter)+r'(?:st|nd|rd|th)\s+quarter|Q'+str(quarter)+r')\b'
    result={}
    for node in root.xpath('//p|//div|//li'):
        if node.xpath('.//p|.//div|.//li|.//table|ancestor::table'):
            continue
        paragraph=text(node)
        if len(paragraph)>1000:
            continue
        current=re.split(r'(?i)\b(?:compared (?:with|to)|versus|vs\.?|prior year|year ago|compared with)\b',paragraph,maxsplit=1)[0]
        if re.search(r'(?i)non[\s-]*gaap|adjusted|continuing|discontinued|forecast|outlook|expect|(?:full|fiscal)\s+year\s+(?:ended|results)|Class\s+[A-Z]\b',current):
            continue
        has_end=bool(re.search(r'(?i)\b(?:quarter|three months)\s+ended\s+'+end.strftime('%B')+r'\s+'+str(end.day)+r',?\s+'+str(end.year)+r'\b',current))
        has_q=bool(re.search(quarter_mark,current)) and not (set(re.findall(r'\b20\d{2}\b',current))-{str(year),str(end.year)})
        if not (has_end or has_q):
            continue
        if any(re.search(r'(?i)\b'+other+r'\s+quarter\b',current) for other in ('first','second','third','fourth') if other!=word):
            continue
        for pattern in (direct_eps,paired_eps):
            for match in pattern.finditer(current):
                if re.search(r'(?i)\b(?:full[ -]year|annual|fiscal\s+20\d\d\s+GAAP)\b',current):
                    continue
                if len(re.findall(r'(?<=[a-z\d])\.\s+(?=[A-Z•])',current[:match.start()])):
                    continue
                raw=match['eps'].replace('−','-')
                value=num(raw)
                if value is None:
                    continue
                loss=match.groupdict().get('kind','').lower()=='loss' or bool(re.search(r'(?i)loss of|diluted net loss',match[0]))
                if loss:
                    value=-abs(value)
                e={'value':value,'rawValue':raw,'scale':0,'signFromLossWording':loss,'unitMeasure':'USD/shares','entity':cik,
                   'rowLabel':'Explicit GAAP diluted EPS' if pattern is direct_eps else 'Net result per diluted share',
                   'releaseIdentity':identity,'paragraph':paragraph,'matchedText':match[0],'headerBasis':'explicit-quarter-paragraph'}
                result.setdefault(value,e)
    return result
def release_values(r,body,url,cik):
    try:
        identity=parse_earnings_release(body,r['date'],r.get('releaseFilingDate') or r['date'],today)
    except ValueError:
        intro=text(html.fromstring(body))[:3400]
        if not re.search(r'(?i)\b(?:reported|reporting|reports|announced|announces|release[ds])\b',intro) or not re.search(r'(?i)\b(?:results|earnings)\b',intro):
            return {}
        identity={'date':r['date'],'periodEnd':None,'fiscalYear':None,'fiscalQuarter':None,'eventSource':'same-accession actual results; period independently attested in column'}
    if identity['date']!=r['date'] or identity['periodEnd'] not in (None,r['periodEnd']):
        return {}
    if identity['fiscalYear'] is not None and (identity['fiscalYear'],identity['fiscalQuarter'])!=(r['fiscalYear'],r['fiscalQuarter']):
        return {}
    root=html.fromstring(body)
    issuer=canonical(cik) or mapping[r['ticker']].get('name','')
    end=date.fromisoformat(r['periodEnd'])
    values=narrative_values(root,r,identity,cik) if identity['periodEnd']==r['periodEnd'] else {}
    revenues={}
    for table in root.xpath('//table'):
        if table.xpath('.//table'):
            continue
        heading=scope(table,issuer)
        try:
            grid=[[clean(x) for x in row] for row in _grid(table)]
        except Exception:
            continue
        labels=[]
        for row in grid:
            label=next((x for x in row if x and not re.fullmatch(r'\d+\)|\(\d+\)',x)),'')
            labels.append(re.sub(r'(?:\s*\((?:\d+|[a-z])\))+\s*$','',label,flags=re.I).strip(' :'))
        boundary=next((i for i,l in enumerate(labels) if eligible_label(l) or label_pattern.fullmatch(l) or total_eps.fullmatch(l) or section_pattern.fullmatch(l) or attributed_caption.fullmatch(l)),None)
        if boundary is None:
            continue
        columns=quarter_columns(grid,boundary,end,r['fiscalYear'],r['fiscalQuarter'])
        if not columns:
            continue
        caption=' '.join([heading or '',*[' '.join(row) for row in grid[:boundary]]])
        if re.search(r'(?i)\b(?:EUR|GBP|CAD|AUD|JPY|CNY|euros?|renminbi|yen)\b',caption) or r.get('currency')!='USD':
            continue
        if mapping[r['ticker']].get('sector')=='Utilities' and not any(compact(n) in compact(heading or '') for n in (issuer, mapping[r['ticker']].get('name','')) if n):
            continue
        statement=text(table)
        if heading and r.get('revenue') is None and mapping[r['ticker']].get('sector') not in ('Financials','Utilities','Real Estate'):
            unit_pattern=r'(?i)\b(?:in|expressed in)\s+(?:U\.?S\.?\s+dollars?\s+in\s+|\$\s*)?(billions?|millions?|thousands?)\b'
            prior=[]
            previous=table.getprevious()
            while previous is not None and len(prior)<5:
                prior_text=text(previous)
                if previous.xpath('.//table') or _local(previous)=='table' or not (harmless(prior_text,issuer) or title(prior_text,issuer)):
                    break
                prior.append(prior_text)
                previous=previous.getprevious()
            unit_text=caption+' '+' '.join(prior)
            scales={dict(billion=9,million=6,thousand=3)[u.lower().rstrip('s')] for u in re.findall(unit_pattern,unit_text)}
            if len(scales)==1:
                scale=next(iter(scales))
                for i in range(boundary,len(grid)):
                    if not eligible_label(labels[i]):
                        continue
                    row=grid[i]
                    for col,(header,basis) in columns.items():
                        if col>=len(row) or basis!='explicit-date':
                            continue
                        raw=row[col]
                        value=num(raw,scale=scale)
                        if value is None or value<0 or (col+1<len(row) and row[col+1]==')'):
                            continue
                        revenues.setdefault(value,{'value':value,'rawValue':raw,'scale':scale,'unitMeasure':'USD',
                            'entity':cik,'rowLabel':labels[i],'rowCells':row,'columnIndex':col,'header':header,
                            'headerBasis':basis,'statementHeading':heading,'unitCaption':unit_text[:4000],
                            'releaseIdentity':identity,'tableExcerpt':statement[:8500]})
        for i in range(boundary,len(grid)):
            row,label=grid[i],labels[i]
            if re.search(r'(?i)\b(?:adjusted|non.gaap|continuing operations|discontinued operations|pro forma|class [A-Z] shares?)\b',label):
                continue
            if r.get('epsGaapDiluted') is not None:
                continue
            section=None
            trusted_section=False
            reviewed=reviewed_total_sections.get(r['ticker'])
            if reviewed and heading and label.casefold()==reviewed[0].casefold():
                start=next((j for j in range(i-1,max(boundary-1,i-6),-1) if re.fullmatch(reviewed[1],labels[j],re.I)),None)
                if start is not None:
                    section=grid[start:i+1]
                    trusted_section=True
            if trusted_section:
                pass
            elif label_pattern.fullmatch(label) or total_eps.fullmatch(label):
                if not heading and not label.lower().startswith('gaap '):
                    continue
            elif heading and re.fullmatch(r'(?i)diluted|basic\s*(?:and|&)\s*diluted',label):
                start=i-1
                if start>=0 and re.fullmatch(r'(?i)basic',labels[start]):
                    start-=1
                if start<0 or not (section_pattern.fullmatch(labels[start]) or attributed_caption.fullmatch(labels[start])):
                    continue
                if any(v and not (section_pattern.fullmatch(v.strip(' :')) or attributed_caption.fullmatch(v.strip(' :'))) for v in grid[start]):
                    continue
                section=grid[start:i+1]
            else:
                continue
            if re.search(r'(?i)\b(?:continuing|discontinued)\s+operations\b',statement) and not (trusted_section or re.match(r'(?i)(?:diluted\s+)?net\s+(?:income|earnings|loss)',labels[start] if section else label)):
                continue
            if re.search(r'(?i)non[\s-]*gaap|adjusted\s+(?:diluted|earnings|income|EPS)',statement) and not label.lower().startswith('gaap '):
                continue
            for col,(header,basis) in columns.items():
                if col>=len(row) or (basis=='fiscal-quarter-column' and (identity['periodEnd']!=r['periodEnd'] or (identity['fiscalYear'],identity['fiscalQuarter'])!=(r['fiscalYear'],r['fiscalQuarter']))):
                    continue
                raw=row[col]
                value=num(raw)
                if value is None:
                    continue
                if not ('$' in ' '.join(row) or re.search(r'(?i)per share|EPS',caption+' '+label)):
                    continue
                left=row[col-1] if col else ''
                right=row[col+1] if col+1<len(row) else ''
                split=left in {'(','$(','($'}
                if split or right==')':
                    if not split or right!=')' or (col-1 in columns and columns[col-1]!=columns[col]) or (col+1 in columns and columns[col+1]!=columns[col]):
                        continue
                    value=-abs(value)
                proof={'value':value,'rawValue':raw,'scale':0,'signFromSplitParentheses':split,'unitMeasure':'USD/shares',
                       'entity':cik,'rowLabel':label,'rowCells':row,'columnIndex':col,'sectionRows':section,
                       'header':header,'headerBasis':basis,'statementHeading':heading,'unitCaption':caption[:3000],
                       'releaseIdentity':identity,'tableExcerpt':statement[-12000:]}
                values.setdefault(value,proof)
    result={}
    if len(values)==1:
        result['epsGaapDiluted']=next(iter(values.values()))
    if len(revenues)==1:
        result['revenue']=next(iter(revenues.values()))
    return result

chosen=[]
visited=0
errors=[]
issuers=set()
excluded=set([773840,51434,1034054,1393818,217346,16732,65984,75362,72903,1037540,906345,1755672,1297996,1501585,77360,2041610,1063761,1393052,1097149,64803,1093557,1352010,1324424,1035983,882095,1652044,1543151,796343,6281,47217,857005,814547,910606,1014473,711404,21076,943819,320187,5272,1374310,895126,97210,1113169,86312,1555280,1094285,72741,1123360,1571949,865752])
order=sorted([r for r in records if r.get('epsGaapDiluted') is None or r.get('revenue') is None],key=lambda r:(-ranks.get(r['ticker'],0),-date.fromisoformat(r['periodEnd']).toordinal(),r['ticker']))
for r in order:
    if len(issuers)>=68:
        break
    ticker=r['ticker']
    cik=int(mapping[ticker]['cik'])
    if cik in issuers or cik in excluded or mapping[ticker].get('tickerStatus') in ('historical_alias','unconfirmed'):
        continue
    url=r['releaseSourceUrl']
    prefix=f'https://www.sec.gov/Archives/edgar/data/{cik}/'
    if not url.startswith(prefix):
        continue
    visited+=1
    if r.get('revenue') is None and r.get('secUrl','').startswith(prefix) and r.get('form') in ('10-Q','10-K'):
        try:
            filing=r['secUrl']
            content=getbody(filing)
            e,_=inspect(r,content,cik,canonical(cik))
            if e:
                e.update({'sourceSha256':hashlib.sha256(content).hexdigest(),'unitMeasure':'USD','entity':cik,
                          'start':e['context']['start'],'end':e['context']['end'],'filingForm':r['form']})
                chosen.append({'ticker':ticker,'periodEnd':r['periodEnd'],'fiscalYear':r['fiscalYear'],
                    'fiscalQuarter':r['fiscalQuarter'],'field':'revenue','value':e['value'],'sourceUrl':filing,
                    'sourceKind':'inline_statement_revenue','evidence':e})
                issuers.add(cik)
                print(ticker,r['periodEnd'],'inline revenue',e['value'],len(issuers),flush=True)
                continue
        except (OSError,ValueError,KeyError,TypeError) as exc:
            errors.append({'ticker':ticker,'type':'inline:'+type(exc).__name__})
    try:
        body=getbody(url)
        if re.search(r'(?i)\bItem\s*2\.02\b',text(html.fromstring(body))[:20000]):
            sources=_exhibit_links(body,url.rsplit('/',1)[0]+'/') or [url]
        else:
            sources=[url]
        facts={}
        for source in sources:
            content=body if source==url else getbody(source)
            try:
                found=release_values(r,content,source,cik)
            except (ValueError,TypeError):
                continue
            for field,e in found.items():
                e['sourceSha256']=hashlib.sha256(content).hexdigest()
                facts.setdefault(field,[]).append({'ticker':ticker,'periodEnd':r['periodEnd'],'fiscalYear':r['fiscalYear'],
                              'fiscalQuarter':r['fiscalQuarter'],'field':field,'value':e['value'],'sourceUrl':source,
                              'parentReleaseUrl':url,'sourceKind':'explicit_release_eps' if field=='epsGaapDiluted' else 'explicit_release_revenue',
                              'evidence':e})
        selected=[proofs[0] for proofs in facts.values() if len({x['value'] for x in proofs})==1]
        if selected:
            chosen.extend(selected)
            issuers.add(cik)
            print(ticker,r['periodEnd'],[(x['field'],x['value']) for x in selected],len(issuers),flush=True)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        errors.append({'ticker':ticker,'type':'release:'+type(exc).__name__})
    if visited%30==0:
        print('Progress',visited,len(issuers),flush=True)
Path('next-candidates.json').write_text(json.dumps({'visited':visited,'companies':len(issuers),'failures':errors,'selected':chosen},indent=2)+'\n')
print('Verified additional candidates',len(issuers),flush=True)
