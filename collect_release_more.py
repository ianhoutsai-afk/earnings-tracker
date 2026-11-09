"""Locate directly reported original SEC quarterly metrics."""
import json,re,hashlib,time,threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import date
from decimal import Decimal
from lxml import html
from official_sync import fetch_sec as raw_fetch_sec,decode_sec_body

sec_lock=threading.Lock()
next_request=0.0
def fetch_sec(url):
 global next_request
 with sec_lock:
  delay=max(0,next_request-time.monotonic())
  time.sleep(delay)
  next_request=time.monotonic()+0.23
 return raw_fetch_sec(url)
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
 return bool(re.fullmatch(r'(?i)(?:total\s+)?(?:GAAP\s+)?(?:consolidated\s+)?(?:net\s+)?(?:operating\s+)?(?:revenues?|sales)(?:\s*,\s*net|\s+from\s+operations|,?\s+net\s+of\s+interest\s+expense)?',label))

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
    date_pattern=r'(?i)(?:\b(?:'+'|'.join(months)+r')\.?\s+'+r'0?'+str(end.day)+r'\b|\b0?'+str(end.month)+r'/0?'+str(end.day)+r'/'+str(end.year)+r'\b)'
    ordinal=('first','second','third','fourth')[quarter-1]
    explicit=r'(?i)\b(?:'+ordinal+r'[\s-]+quarter|'+str(quarter)+r'(?:st|nd|rd|th)[\s-]+quarter|q'+str(quarter)+r'|'+str(quarter)+r'q|'+str(quarter)+r'Q)\b'
    for index in range(1,max(map(len,grid),default=0)):
        label=' '.join(dict.fromkeys(r[index] for r in headers if index<len(r) and r[index]))
        label=re.sub(r"(?i)\bQ([1-4])\s*(?:FY\s*)?[’']?(\d{2})\b",r"Q\1 20\2",label)
        label=re.sub(r"(?i)\b([1-4])Q\s*[’']?(\d{2})\b",r"Q\1 20\2",label)
        label=re.sub(r'(?i)\bFY\s*(\d{2})\b',r'20\1',label)
        label=re.sub(r'(?i)\bFY(20\d{2})\b',r'\1',label)
        if re.search(r'(?i)(?:six|nine|twelve|6|9|12)[\s-]+months|(?:fifty(?:[\s-]+(?:two|three))?|52|53)[\s-]+weeks|years?\s+ended|full[\s-]*year|annual|percent\s+change|year.to.date|\bYTD\b',label):
            continue
        years=set(re.findall(r'\b20\d{2}\b',label))
        date_match=(years=={str(end.year)} and re.search(date_pattern,label)
                    and re.search(r'(?i)\b(?:(?:three|3)[\s-]+months|quarters?|(?:twelve|thirteen|fourteen|12|13|14)[\s-]+weeks|(?:fiscal\s+)?quarter)\s+end(?:ed|ing)\b',label))
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
# Require financial-statement structure when an issuer uses a split heading.
def statement_context(table,issuer,grid,labels):
    recognized=scope(table,issuer)
    prior=[]
    current=table
    for _ in range(3):
        previous=current.getprevious()
        for _ in range(10):
            if previous is None or _local(previous)=='table' or previous.xpath('.//table'):
                break
            sample=text(previous)
            if len(sample)>330:
                break
            if sample:
                prior.append(sample)
            previous=previous.getprevious()
        p=current.getparent()
        if p is None or len(p.xpath('.//table'))!=1:
            break
        current=p
    significant=[]
    for row,label in zip(grid,labels):
        if sum(num(v) is not None for v in row)>=2 and label:
            significant.append(label)
    actual_rev=any(eligible_label(label) for label in significant)
    actual_exp=any(re.match(r'(?i)^(?:cost of (?:revenues?|sales|goods|services)|(?:total )?operating (?:costs|expenses|income|profit|loss)|(?:income|earnings|loss) from operations|total (?:costs and )?expenses|(?:income|earnings|loss) before (?:income )?tax|provision for income taxes)',label) for label in significant)
    actual_net=any(re.fullmatch(r'(?i)(?:total\s+)?net (?:income|loss|earnings)(?:\s*\((?:income|loss|earnings)\))?(?:\s+attributable to [\w .,&\'-]{2,115})?',label) for label in significant)
    total_eps_row=any(extended_eps.fullmatch(l) or label_pattern.fullmatch(l) or total_eps.fullmatch(l) or l.lower()=='diluted' for l in significant)
    expanded_heading=next((value for value in prior[:5] if re.fullmatch(r'(?i)(?:unaudited\s+)?(?:condensed\s+)?(?:consolidated|combined)\s+(?:statements?\s+of\s+(?:operations|earnings|(?:comprehensive\s+)?income)(?:\s*\(loss\))?|income\s+statements?)',value)),None)
    recognized=recognized or expanded_heading
    initial=' '.join(' '.join(row) for row in grid[:5])
    prior_scope=' '.join([initial,*prior[:4]])
    flags=re.search(r'(?i)(?:non[\s-]*gaap|adjusted financial|reconciliation|pro forma|segment (?:results|performance|information)|unaudited supplemental operating data)',prior_scope)
    has_structure=actual_rev and actual_exp and actual_net and total_eps_row and not flags
    # An explicit title can cover an EPS-only statement section. Structural
    # inference requires revenue, costs, net result and EPS in this same table.
    heading=recognized or ('Income statement structure with revenue, costs, net result, and diluted EPS' if has_structure else None)
    return heading,prior,significant,has_structure

extended_eps=re.compile(r'''(?ix)(?:GAAP\s+)?(?:
    (?:(?:total|reported)\s+)?diluted\s+(?:GAAP\s+)?(?:net\s+)?(?:EPS|(?:income|earnings|loss)(?:\s*\((?:income|loss|earnings)\))?\s+per\s+(?:(?:common|ordinary)\s+)?share)
    |(?:EPS|(?:(?:total|net)\s+)?(?:income|earnings|loss)(?:\s*\((?:income|loss|earnings)\))?\s+per\s+(?:(?:common|ordinary)\s+)?share)(?:\s+attributable to [\w. ,'&-]{2,105})?\s*[-–—,:]?\s*(?:\(\s*)?(?:basic\s+and\s+)?diluted(?:\s*\))?
    |(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:income|loss|earnings)\))?\s+per\s+(?:(?:common|ordinary)\s+)?share\s*[-–—:,]?\s*assuming dilution
    |(?:diluted\s+)?(?:net\s+)?(?:income|earnings|loss)\s+per\s+diluted\s+(?:(?:common|ordinary)\s+)?share
)(?:\s*\(\s*EPS\s*\))?''')
eps_caption=re.compile(r'''(?ix)(?:diluted\s+)?(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:income|earnings|loss)\))?\s+per\s+(?:(?:common|ordinary)\s+)?share(?:\s+(?:attributable to|of)\s+[\w. ,'&-]{2,120})?''')
def eps_scope(labels,grid,i,boundary):
    for j in range(i-1,max(boundary-1,i-5),-1):
        label=labels[j].strip(' :')
        if eps_caption.fullmatch(label) and all(not v or eps_caption.fullmatch(v.strip(' :')) for v in grid[j]):
            if all(re.fullmatch(r'(?i)(?:class [A-Z] )?basic(?: EPS)?',label) for label in labels[j+1:i] if label):
                return j
        if label and not re.fullmatch(r'(?i)(?:class [A-Z] )?basic(?: EPS)?',label):
            break
    return None

def revenue_scale(unit_text):
    patterns={
       3:r'(?i)(?:\$\s*(?:in\s+)?thousands?\b|\$\s*0{3}\b|\bthousands?\s+of\s+(?:U\.?S\.?\s+)?dollars\b|(?:in|dollars\s+in)\s+(?:U\.?S\.?\s+dollars?\s+in\s+|\$\s*)?thousands?\b)',
       6:r'(?i)(?:\$\s*(?:in\s+)?millions?\b|\bmillions?\s+of\s+(?:U\.?S\.?\s+)?dollars\b|(?:in|dollars\s+in)\s+(?:U\.?S\.?\s+dollars?\s+in\s+|\$\s*)?millions?\b)',
       9:r'(?i)(?:\$\s*(?:in\s+)?billions?\b|\bbillions?\s+of\s+(?:U\.?S\.?\s+)?dollars\b|(?:in|dollars\s+in)\s+(?:U\.?S\.?\s+dollars?\s+in\s+|\$\s*)?billions?\b)',
    }
    exact={scale for scale,pattern in patterns.items() if re.search(pattern,unit_text)}
    return next(iter(exact)) if len(exact)==1 else None

def formatted_number(row,col):
    raw=row[col]
    raw=raw.replace('−','-')
    signed_raw=raw
    if raw.startswith('(') and not raw.endswith(')') and col+1<len(row) and row[col+1]==')':
        signed_raw=raw+')'
    elif raw.startswith('$(') and not raw.endswith(')') and col+1<len(row) and row[col+1]==')':
        signed_raw=raw+')'
    value=num(signed_raw)
    split=col>0 and col+1<len(row) and row[col-1] in ('(','$(','($') and row[col+1]==')'
    if value is None:
        return None
    if split:
        value=-abs(value)
    elif col+1<len(row) and row[col+1]==')' and signed_raw==raw and not raw.endswith(')'):
        return None
    return value,signed_raw,split

def original_exhibits(body,url):
    if not re.search(r'(?i)\bItem\s*2\.02\b',text(html.fromstring(body))[:20000]):
        return [url]
    base=url.rsplit('/',1)[0]+'/'
    links=_exhibit_links(body,base)
    for anchor in html.fromstring(body).xpath('//a[@href]'):
        description=clean(text(anchor)+' '+anchor.get('href',''))
        if not re.search(r'(?i)\b(?:EX[- ]?)?99[._-]?[23]\b|financial supplement|financial tables',description):
            continue
        target=urljoin(base,anchor.get('href')).split('#')[0]
        if target.startswith(base) and re.search(r'(?i)\.html?$',target):
            links.append(target)
    return list(dict.fromkeys(links))[:6] or [url]

def quarter_attestation(body,record):
    end=date.fromisoformat(record['periodEnd'])
    intro=text(html.fromstring(body))[:6000]
    words=r'(?i)\b(?:quarter|three months|(?:12|13|14|twelve|thirteen|fourteen)[\s-]+weeks|period)\s+end(?:ed|ing)(?:\s+on)?\s+'
    months='|'.join({end.strftime('%B'),end.strftime('%b')})
    literal=re.search(words+r'(?:'+months+r')\.?\s+0?'+str(end.day)+r',?\s+'+str(end.year)+r'\b',intro)
    return literal[0] if literal else None

def release_values(r,body,url,cik):
    try:
        identity=parse_earnings_release(body,r['date'],r.get('releaseFilingDate') or r['date'],today)
    except ValueError:
        intro=text(html.fromstring(body))[:3400]
        if not re.search(r'(?i)\b(?:reported|reporting|reports|announced|announces|release[ds])\b',intro) or not re.search(r'(?i)\b(?:results|earnings)\b',intro):
            return {}
        identity={'date':r['date'],'periodEnd':None,'fiscalYear':None,'fiscalQuarter':None,'eventSource':'same-accession actual results; period independently attested in column'}
    if identity['date']!=r['date']:
        return {}
    if identity['periodEnd'] not in (None,r['periodEnd']) or identity['fiscalYear'] not in (None,r['fiscalYear']) or identity['fiscalQuarter'] not in (None,r['fiscalQuarter']):
        identity={'date':r['date'],'periodEnd':None,'fiscalYear':None,'fiscalQuarter':None,'parsedHeadline':identity}
    literal=quarter_attestation(body,r)
    if literal and identity['periodEnd'] is None:
        identity={**identity,'periodEnd':r['periodEnd'],'literalPeriodEvidence':literal}
    root=html.fromstring(body)
    issuer=canonical(cik) or mapping[r['ticker']].get('name','')
    end=date.fromisoformat(r['periodEnd'])
    values={}
    revenues={}
    for table in root.xpath('//table'):
        if table.xpath('.//table'):
            continue
        try:
            grid=[[clean(x) for x in row] for row in _grid(table)]
        except Exception:
            continue
        labels=[]
        for row in grid:
            label=next((x for x in row if x and not re.fullmatch(r'\d+\)|\(\d+\)',x)),'')
            labels.append(re.sub(r'(?:\s*\((?:\d+|[a-z])\))+\s*$','',label,flags=re.I).strip(' :'))
        heading,prior,significant,structural=statement_context(table,issuer,grid,labels)
        boundary=next((i for i,l in enumerate(labels) if eligible_label(l) or label_pattern.fullmatch(l) or total_eps.fullmatch(l) or extended_eps.fullmatch(l) or eps_caption.fullmatch(l)),None)
        if boundary is None:
            continue
        columns=quarter_columns(grid,boundary,end,r['fiscalYear'],r['fiscalQuarter'])
        if not columns:
            continue
        caption=' '.join([heading or '',*[' '.join(row) for row in grid[:boundary]]])
        if re.search(r'(?i)\b(?:EUR|GBP|CAD|AUD|JPY|CNY|euros?|renminbi|yen)\b',caption) or r.get('currency')!='USD':
            continue
        issuer_header=' '.join([heading or '',*prior[:4],*[' '.join(row) for row in grid[:3]]])
        if mapping[r['ticker']].get('sector')=='Utilities' and not any(compact(n) in compact(issuer_header) for n in (issuer, mapping[r['ticker']].get('name','')) if n):
            continue
        statement=text(table)
        if r.get('revenue') is None and (heading or any(re.fullmatch(r'(?i)(?:total\s+)?GAAP\s+(?:net\s+)?revenues?',l) for l in significant)):
            # Scales are attested by actual source caption text. Conflicting scales
            # such as dollars in millions and shares in thousands are deferred.
            unit_text=caption+' '+' '.join(prior[:6])
            scale=revenue_scale(unit_text)
            if scale is not None and not re.search(r'(?i)\b(?:EUR|GBP|CAD|AUD|JPY|CNY|euros?|renminbi|yen)\b',unit_text):
                matches=[i for i in range(boundary,len(grid)) if eligible_label(labels[i])]
                totals=[i for i in matches if re.match(r'(?i)(?:total\b|GAAP\b)',labels[i]) and sum(num(v) is not None for v in grid[i])>=2]
                for i in totals or matches:
                    label=labels[i]
                    if not heading and not re.fullmatch(r'(?i)(?:total\s+)?GAAP\s+(?:net\s+)?revenues?',label):
                        continue
                    # Financial issuers' revenue definitions vary. Require a
                    # printed total plus a consolidated statement title for these.
                    if mapping[r['ticker']].get('sector') in ('Financials','Real Estate') and (not heading or heading.startswith('Income statement structure')):
                        continue
                    row=grid[i]
                    for col,(header,basis) in columns.items():
                        if col>=len(row) or (basis=='fiscal-quarter-column' and identity['periodEnd']!=r['periodEnd']):
                            continue
                        raw=row[col]
                        value=num(raw,scale=scale)
                        if value is None or value<0 or (col+1<len(row) and row[col+1]==')'):
                            continue
                        revenues.setdefault(value,{'value':value,'rawValue':raw,'scale':scale,'unitMeasure':'USD',
                            'entity':cik,'rowLabel':label,'rowCells':row,'columnIndex':col,'header':header,
                            'headerBasis':basis,'statementHeading':heading or 'Explicit GAAP total revenue row',
                            'structuralScope':structural,'unitCaption':unit_text[:5500],
                            'releaseIdentity':identity,'tableExcerpt':statement[:7200]})
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
            elif label_pattern.fullmatch(label) or total_eps.fullmatch(label) or extended_eps.fullmatch(label):
                if not heading and not label.lower().startswith('gaap '):
                    continue
            elif heading and re.fullmatch(r'(?i)diluted|basic\s*(?:and|&)\s*diluted',label):
                start=eps_scope(labels,grid,i,boundary)
                if start is None:
                    continue
                section=grid[start:i+1]
            else:
                continue
            if re.search(r'(?i)\b(?:continuing|discontinued)\s+operations\b',statement) and not (trusted_section or re.match(r'(?i)(?:diluted\s+)?net\s+(?:income|earnings|loss)',labels[start] if section else label)):
                continue
            if re.search(r'(?i)non[\s-]*gaap|adjusted\s+(?:diluted|earnings|income|EPS)',statement) and not label.lower().startswith('gaap ') and (not heading or heading.startswith('Income statement structure')):
                continue
            for col,(header,basis) in columns.items():
                if col>=len(row) or (basis=='fiscal-quarter-column' and identity['periodEnd']!=r['periodEnd']):
                    continue
                number=formatted_number(row,col)
                if number is None:
                    continue
                value,signed_raw,split=number
                raw=row[col]
                if not ('$' in ' '.join(row) or re.search(r'(?i)per share|EPS',caption+' '+label)):
                    continue
                proof={'value':value,'rawValue':raw,'signedRawValue':signed_raw,'scale':0,'signFromSplitParentheses':split,'unitMeasure':'USD/shares',
                       'entity':cik,'rowLabel':label,'rowCells':row,'columnIndex':col,'sectionRows':section,
                       'header':header,'headerBasis':basis,'statementHeading':heading,'unitCaption':caption[:3000],
                       'releaseIdentity':identity,'structuralScope':structural,'tableExcerpt':statement[:9000]}
                values.setdefault(value,proof)
    result={}
    if len(values)==1:
        result['epsGaapDiluted']=next(iter(values.values()))
    if len(revenues)==1:
        result['revenue']=next(iter(revenues.values()))
    return result

USD_NUMBER=r'(?:\(\s*\$?\s*[\d,]+(?:\.\d+)?\s*\)|\$?\s*\(\s*[\d,]+(?:\.\d+)?\s*\)|[-−]?\s*(?:US)?\$\s*[-−]?\s*[\d,]+(?:\.\d+)?)'
EPS_NUMBER=r'(?:\(\s*\$?\s*[\d,]+\.\d{1,4}\s*\)|\$?\s*\(\s*[\d,]+\.\d{1,4}\s*\)|[-−]?\s*(?:US)?\$\s*[-−]?\s*[\d,]+\.\d{1,4})'
PER_SHARE=r'(?:EPS|(?:net\s+)?(?:income|earnings|loss)(?:\s*\((?:income|loss)\))?\s+per\s+(?:common\s+|ordinary\s+)?share)(?:\s*\(\s*["“]?\s*EPS\s*["”]?\s*\))?'
eps_direct=re.compile(r'(?i)(?P<label>\b(?:(?:(?:U\.?S\.?\s+)?GAAP|reported)\s+diluted\s+'+PER_SHARE+r'|diluted\s+(?:GAAP|reported)\s+'+PER_SHARE+r'|(?:net\s+)?(?:income|earnings|loss)\s+per\s+diluted\s+(?:common\s+|ordinary\s+)?share|diluted\s+net\s+(?:income|loss)\s+per\s+(?:common\s+)?share))\s*(?:of|was|were|totaled|grew(?:\s+[\d.]+%)?\s+to|decreased(?:\s+[\d.]+%)?\s+to|increased(?:\s+[\d.]+%)?\s+to|:)\s*(?P<raw>'+EPS_NUMBER+r')')
eps_pair=re.compile(r'(?i)(?P<label>\b(?:GAAP\s+)?net\s+(?:income|earnings|loss)(?:\s+attributable\s+to\s+[\w .,&\'-]{2,70}?)?)\s+(?:of|was|were|totaled)\s+'+USD_NUMBER+r'\s*(?:billion|million|thousand)\b\s*,?\s*(?:or|and)\s+(?P<raw>'+EPS_NUMBER+r')\s+per\s+diluted\s+(?:common\s+|ordinary\s+)?share')
rev_pattern=re.compile(r'(?i)(?P<label>\b(?:(?:consolidated|total|GAAP|reported)\s+)*(?:net\s+)?(?:operating\s+)?(?:revenues?|sales(?:\s+and\s+revenues?)*))\s*(?:for\s+(?:the\s+)?(?:fiscal\s+)?(?:first|second|third|fourth|current)\s+quarter(?:\s+of\s+(?:fiscal\s+(?:year\s+)?)?20\d{2})?\s+)?(?:were|was|totaled|of|increased(?:\s+[\d.]+%)?\s+to|decreased(?:\s+[\d.]+%)?\s+to|grew(?:\s+[\d.]+%)?\s+to|:)\s*(?P<raw>'+USD_NUMBER+r')\s*(?P<unit>billion|million|thousand)\b')
section_break=re.compile(r'(?i)^(?:fiscal\s+(?:year\s+)?20\d{2}\b|full[\s-]*year\b|annual\b|[a-z ]{0,30}\b(?:outlook|guidance|segment performance|segment results|business segment|operating segments|financial statements|reconciliation|non[\s-]*gaap)\b)')
bad_scope=re.compile(r'(?i)\b(?:non[\s-]*gaap|adjusted|ongoing|pro forma|organic|continuing operations|discontinued operations|constant currency|approximately|expects?|estimated?|projected|forecast|outlook|segment|full[\s-]*year|twelve months|annual|prior year|year ago|next quarter)\b')
comparison=re.compile(r'(?i)\b(?:as compared|compared\s+(?:with|to)|versus|vs\.?|in the prior year|prior-year quarter|year ago)\b')
def blocks(root):
    for node in root.xpath('//p|//div|//li|//tr|//h1|//h2|//h3|//h4'):
        if _local(node)=='tr':
            if node.xpath('.//table|.//p|.//li|.//div'):
                continue
        elif node.xpath('.//p|.//div|.//li|.//table|.//h1|.//h2|.//h3|.//h4'):
            continue
        label=text(node).strip(' ·•●▪◦-')
        if label:
            yield label
def clean_start(s):
    return s.replace('’',"'").replace('−','-')
def support_values(r,body,cik):
    try:
        identity=parse_earnings_release(body,r['date'],r.get('releaseFilingDate') or r['date'],today)
    except ValueError:
        return {}
    if identity['periodEnd']!=r['periodEnd'] or identity['fiscalYear'] not in (None,r['fiscalYear']) or identity['fiscalQuarter'] not in (None,r['fiscalQuarter']):
        return {}
    root=html.fromstring(body)
    quarter=r['fiscalQuarter']
    ordinal=('first','second','third','fourth')[quarter-1]
    end=date.fromisoformat(r['periodEnd'])
    qlabel=r'(?i)\b(?:'+ordinal+r'[\s-]+quarter|'+str(quarter)+r'(?:st|nd|rd|th)[\s-]+quarter|Q'+str(quarter)+r')\b'
    exact=r'(?i)\b(?:quarter|three months)\s+ended(?:\s+on)?\s+'+end.strftime('%B')+r'\s+'+str(end.day)+r',?\s+'+str(end.year)+r'\b'
    section=''
    remaining=0
    options={}
    for whole in list(blocks(root))[:360]:
        if re.search(section_break,whole) and len(whole)<125:
            section=''
            remaining=0
        headings=bool(re.search(qlabel,whole)) and len(whole)<108 and bool(re.search(r'(?i)\b(?:results|highlights|overview|performance|summary|quarter)\b',whole)) and not bool(re.search(r'\$\s*\d',whole)) and not bool(re.search(bad_scope,whole))
        if headings:
            years=set(re.findall(r'\b20\d{2}\b',whole))
            if (not years or years<={str(r['fiscalYear']),str(end.year)}) and (years or identity['fiscalQuarter']==quarter or re.search(exact,whole)):
                section=whole
                remaining=5
                continue
        remaining-=1
        if len(whole)>900:
            continue
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z•●])',whole):
            current=comparison.split(sentence,maxsplit=1)[0]
            local=bool(re.search(exact,current) or re.search(qlabel,current))
            recent=remaining>=0 and bool(section)
            if not local and not recent:
                continue
            other=set(re.findall(r'\b20\d{2}\b',current))-{str(r['fiscalYear']),str(end.year)}
            if other:
                continue
            if any(re.search(r'(?i)\b'+w+r'[\s-]+quarter\b',current) for w in ('first','second','third','fourth') if w!=ordinal):
                continue
            for field,patterns in [('epsGaapDiluted',(eps_direct,eps_pair)),('revenue',(rev_pattern,))]:
                if r.get(field) is not None:
                    continue
                if field=='revenue' and mapping[r['ticker']].get('sector') in ('Financials','Real Estate','Utilities'):
                    continue
                for pattern in patterns:
                    for m in pattern.finditer(current):
                        before=current[:m.start()]
                        if re.search(bad_scope,before) or re.search(bad_scope,m['label']) or re.search(r'(?i)(?:\bnon[-\s]*|\badjusted\s*)$',before) or re.search(r'(?i)(?:\bfrom\s+continuing|\bfrom\s+discontinued|\bto\s+\$|\bper\s+cent|\bper\s+share)\b',current[m.end():m.end()+36]) and field=='revenue':
                            continue
                        after=current[m.end():]
                        if re.match(r'(?i)\s*(?:for\s+the\s+(?:full[\s-]*year|year\s+ended)|from\s+(?:continuing|discontinued)\s+operations|to\s+\$)',after):
                            continue
                        if re.search(r'(?i)\b(?:non[\s-]*gaap|adjusted|organic)\s*$',before):
                            continue
                        if field=='epsGaapDiluted' and not re.search(r'(?i)\b(?:gaap|reported|net)\b',m['label']):
                            continue
                        if field=='revenue' and not re.search(r'(?i)\b(?:GAAP|reported|consolidated|total)\b',m['label']):
                            prefix=before.strip(' ●•◦·–-')
                            explicit_start=not prefix or bool(re.fullmatch(r'(?i)(?:the\s+company(?:\x27s|’s)|we reported|company reported|fourth[ -]+quarter(?:\s+20\d{2})?|the company reported|for\s+the\s+(?:first|second|third|fourth)\s+quarter(?:\s+of\s+20\d{2})?,?)',prefix))
                            if not explicit_start or not (local or recent):
                                continue
                        if field=='revenue' and ('€' in current or '£' in current or re.search(r'(?i)\b(?:CAD|AUD|GBP|EUR)\b',current)):
                            continue
                        if field=='epsGaapDiluted' and re.search(r'(?i)continuing|discontinued|\b(?:was|were)\b.+\b(?:from|in)\s+the\s+prior\b',m[0]):
                            continue
                        units=m.groupdict().get('unit')
                        raw=clean_start(m['raw']).replace('US$','$')
                        factor={'billion':9,'million':6,'thousand':3}.get(units.lower() if units else '',0)
                        value=num(raw,scale=factor)
                        if value is None or (field=='revenue' and value<0):
                            continue
                        loss=field=='epsGaapDiluted' and bool(re.search(r'(?i)\b(?:net|diluted)\s+loss\b',m['label']))
                        if loss:
                            value=-abs(value)
                        proof={'value':value,'rawValue':raw,'scale':factor,'signFromLossWording':loss,
                            'unitMeasure':'USD/shares' if field=='epsGaapDiluted' else 'USD','entity':cik,'rowLabel':m['label'],
                            'releaseIdentity':identity,'paragraph':whole,'matchedText':m[0],
                            'headerBasis':'explicit-quarter-paragraph','quarterAnchor':current if local else section,
                            'sourcePrecisionUnit':units,'sourceSha256':hashlib.sha256(body).hexdigest()}
                        options.setdefault(field,{}).setdefault(value,proof)
    return {k:next(iter(v.values())) for k,v in options.items() if len(v)==1}
from official_sources import _contract_revenue_total

def filing_values(row,body,cik):
    parsed=parse_inline_quarter(body,row['periodEnd'],cik)
    if (parsed['fiscalYear'],parsed['fiscalQuarter'])!=(row['fiscalYear'],row['fiscalQuarter']):
        return {}
    root=html.fromstring(body)
    nodes=[n for n in root.iter() if isinstance(n.tag,str)]
    issuer=canonical(cik) or mapping[row['ticker']]['name']
    contexts={}
    unit_nodes={}
    for n in nodes:
        kind=_local(n)
        if kind=='context':
            entity=_unique_text(_desc(n,'identifier'))
            start=_unique_text(_desc(n,'startdate'))
            end=_unique_text(_desc(n,'enddate'))
            if not entity or not entity.isdigit() or int(entity)!=cik or not start or end!=row['periodEnd'] or _desc(n,'segment') or _desc(n,'scenario'):
                continue
            if not 70<=(date.fromisoformat(end)-date.fromisoformat(start)).days+1<=110:
                continue
            if row.get('periodStart') not in (None,start):
                continue
            contexts[n.get('id')]=(start,end,n)
        if kind=='unit':
            numerator=_desc(n,'unitnumerator')
            denominator=_desc(n,'unitdenominator')
            if numerator and denominator:
                if (_unique_text(_desc(numerator[0],'measure')) or '').lower()=='iso4217:usd' and (_unique_text(_desc(denominator[0],'measure')) or '').lower()=='xbrli:shares':
                    unit_nodes[n.get('id')]=('USD/shares',n)
            elif (_unique_text(_desc(n,'measure')) or '').lower()=='iso4217:usd':
                unit_nodes[n.get('id')]=('USD',n)
    by_table={}
    facts={}
    for n in nodes:
        if _local(n)!='nonfraction':
            continue
        tag=n.get('name','')
        key=tag.lower()
        field='epsGaapDiluted' if key=='us-gaap:earningspersharediluted' else 'revenue'
        if row.get(field) is not None:
            continue
        if field=='revenue' and key not in ALLOWED_TAGS and (':' not in key or not re.search(r'revenue|sales',key.split(':',1)[-1]) or re.search(r'adjusted|nongaap|proforma|segment',key)):
            continue
        duration=contexts.get(n.get('contextref'))
        units=unit_nodes.get(n.get('unitref'))
        if duration is None or units is None or units[0]!=('USD' if field=='revenue' else 'USD/shares'):
            continue
        table=next((p for p in n.iterancestors() if _local(p)=='table'),None)
        line=next((p for p in n.iterancestors() if _local(p)=='tr'),None)
        if table is None or line is None or table.xpath('.//table'):
            continue
        if table not in by_table:
            try:
                grid=[[clean(v) for v in cells] for cells in _grid(table)]
            except (ValueError,TypeError):
                continue
            labels=[next((v for v in cells if v),'').rstrip(':') for cells in grid]
            heading,_,_,structural=statement_context(table,issuer,grid,labels)
            by_table[table]=(heading,structural)
        heading,structural=by_table[table]
        if heading is None:
            continue
        first=line.xpath('./td|./th')
        if not first:
            continue
        label=re.sub(r'(?:\s*\((?:\d+|[a-z])\))+\s*$','',text(first[0]),flags=re.I).strip(' :')
        if not label:
            label=label_before_numbers(line)
        if field=='revenue':
            if not eligible_label(label):
                continue
            if mapping[row['ticker']].get('sector') in ('Financials','Real Estate') and not re.match(r'(?i)total\s+',label):
                continue
            if mapping[row['ticker']].get('sector') in ('Financials','Real Estate','Utilities') and structural:
                continue
            if not re.match(r'(?i)(?:total\s+)?(?:net\s+)?(?:operating\s+)?(?:revenues?|sales)\b',label):
                continue
        else:
            if re.search(r'(?i)adjusted|non[\s-]*gaap|continuing|discontinued|pro forma',label):
                continue
            if not (label_pattern.fullmatch(label) or extended_eps.fullmatch(label) or total_eps.fullmatch(label) or re.fullmatch(r'(?i)diluted|basic and diluted',label)):
                continue
            if re.fullmatch(r'(?i)diluted|basic and diluted',label):
                sibling=line.getprevious()
                nearby=[]
                for _ in range(5):
                    if sibling is None:
                        break
                    nearby.append(text(sibling))
                    sibling=sibling.getprevious()
                if not any(re.search(r'(?i)\b(?:earnings|income|loss)\s+per\s+(?:common\s+)?share\b',l) and not re.search(r'(?i)continuing|discontinued|weighted.average',l) for l in nearby):
                    continue
        raw=re.sub(r'\s+','',text(n)).replace(',','')
        if not re.fullmatch(r'(?:\d+(?:\.\d+)?|\.\d+)',raw):
            continue
        if n.get('format','').split(':')[-1].lower() not in ('','num-dot-decimal','numdotdecimal'):
            continue
        scale=int(n.get('scale','0'))
        sign=n.get('sign')
        if not -12<=scale<=15 or (field=='revenue' and sign=='-'):
            continue
        value=num(raw,sign=sign,scale=scale)
        if value is None:
            continue
        start,end,context=duration
        proof={'value':value,'rawValue':raw,'scale':scale,'sign':sign,'entity':cik,'unitMeasure':units[0],
            'factTag':tag,'start':start,'end':end,'context':{'start':start,'end':end,'entity':cik},
            'contextHtml':html.tostring(context,encoding='unicode'),'unitHtml':html.tostring(units[1],encoding='unicode'),
            'rowLabel':label,'rowText':text(line)[:1800],'statementHeading':heading,'structuralScope':structural,
            'statementText':text(table)[:9500],'filingForm':row['form'],
            'sourceSha256':hashlib.sha256(body).hexdigest()}
        facts.setdefault(field,[]).append(proof)
    out={}
    for field,options in facts.items():
        totals=[e for e in options if re.match(r'(?i)total\s+',e['rowLabel'])] if field=='revenue' else []
        possible=totals or options
        if len({x['value'] for x in possible})==1:
            out[field]=possible[0]
    return out

excluded=set([1564708,1397187,1535527,1403568,1002910,1410636,12927,875045,14272,1374310,277948,29905,1095073,1289490,1262039,1652044,1123360,45012,1783879,879169,1687229,51434,936468,352541,1141391,1682852,62709,898173,75677,764622,1034054,1283699,1113169,860731,1555280,1094285,77476,1140859,814547,1063761,829224,52988,898293,896878,316709,1327567,910521,1381197,10795,1341439,40533,32604,26172,1571949,1002047,1037540,764180,1164727,1024478,910606,1014473,72903,1418135,753308,100885,783325,720005,1501585,1048695,900075,1156375,713676,1389170,86312,11544,915913,820027,8818,2012383,18230,1868275,21665,1166691,4977])
def examine(r):
    ticker=r['ticker']
    cik=int(mapping[ticker]['cik'])
    parent=r['releaseSourceUrl']
    if not parent.startswith(f'https://www.sec.gov/Archives/edgar/data/{cik}/'):
        return [],[]
    try:
        source=getbody(parent)
        result={}
        for url in original_exhibits(source,parent):
            doc=source if url==parent else getbody(url)
            for field,e in support_values(r,doc,cik).items():
                kind='narrative_release_revenue' if field=='revenue' else 'explicit_release_eps'
                item={'ticker':ticker,'periodEnd':r['periodEnd'],'fiscalYear':r['fiscalYear'],'fiscalQuarter':r['fiscalQuarter'],
                    'field':field,'value':e['value'],'sourceUrl':url,'parentReleaseUrl':parent,'sourceKind':kind,'evidence':e}
                result.setdefault(field,{}).setdefault(e['value'],item)
        return [next(iter(x.values())) for x in result.values() if len(x)==1],[]
    except (OSError,ValueError,TypeError,KeyError) as error:
        return [],[[ticker,type(error).__name__]]
ordered=[r for r in records if r.get('currency')=='USD' and int(mapping[r['ticker']]['cik']) not in excluded and (r.get('revenue') is None or r.get('epsGaapDiluted') is None) and mapping[r['ticker']].get('tickerStatus') not in ('historical_alias','unconfirmed')]
ordered.sort(key=lambda r:(-ranks.get(r['ticker'],0),-date.fromisoformat(r['periodEnd']).toordinal(),r['ticker']))
chosen=[]
errors=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    for found,failures in pool.map(examine,ordered):
        chosen.extend(found)
        errors.extend(failures)
        for item in found:
            print(item['ticker'],item['periodEnd'],item['field'],item['value'],flush=True)
out={'visited':len(ordered),'companies':len({x['ticker'] for x in chosen}),'failures':errors,'selected':chosen}
Path('additional-release-figures.json').write_text(json.dumps(out,indent=2)+'\n')
print('Additional release candidates',out['companies'],len(chosen),flush=True)
