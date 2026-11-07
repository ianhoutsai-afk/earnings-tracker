"""Collect directly reported quarterly facts, checking each against its source iXBRL."""
import hashlib,json,re,time
from collections import defaultdict
from datetime import date,timedelta,datetime
from decimal import Decimal,InvalidOperation
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo
from lxml import html
from official_sources import _local,_desc,_unique_text,_contract_revenue_total
from official_sync import _filings,fetch_sec,decode_sec_body

today=datetime.now(ZoneInfo('America/New_York')).date()
records=json.loads(Path('official_history.json').read_text())
mapping=json.loads(Path('sp500_mapping.json').read_text())
target={}
for row in records:
    target.setdefault(row['ticker'],[]).append(row)

concepts={
    'epsGaapDiluted':('USD/shares',('EarningsPerShareDiluted',)),
    'revenue':('USD',('Revenues','SalesRevenueNet','RevenueFromContractWithCustomerExcludingAssessedTax',
                       'RevenueFromContractWithCustomerIncludingAssessedTax',
                       'RegulatedAndUnregulatedOperatingRevenue'))
}

@lru_cache(maxsize=8)
def get(url):
    cache=Path('.sec_cache/official')/(hashlib.sha256(url.encode()).hexdigest()+'.body')
    if cache.exists():
        return decode_sec_body(cache.read_bytes())
    body=fetch_sec(url)
    time.sleep(.14)
    return body

def expected_start(row,quarters):
    end=date.fromisoformat(row['periodEnd'])
    previous_year=row['fiscalYear']-(row['fiscalQuarter']==1)
    previous_quarter=(row['fiscalQuarter']-2)%4+1
    preceding=[x for x in quarters if (x['fiscalYear'],x['fiscalQuarter'])==(previous_year,previous_quarter)]
    derived=(date.fromisoformat(preceding[0]['periodEnd'])+timedelta(days=1)).isoformat() if len(preceding)==1 else None
    start=row.get('periodStart') or derived
    if not start or (derived and derived!=start):
        return None
    return start if 70<=(end-date.fromisoformat(start)).days+1<=110 else None

@lru_cache(maxsize=3)
def statement(url,cik):
    body=get(url)
    tree=html.fromstring(body)
    nodes=[n for n in tree.iter() if isinstance(n.tag,str)]
    contexts={}
    units={}
    numeric=[]
    for n in nodes:
        kind=_local(n)
        if kind=='context':
            owner=_unique_text(_desc(n,'identifier'))
            if not owner or not owner.isdigit() or int(owner)!=cik or _desc(n,'segment') or _desc(n,'scenario'):
                continue
            start,end=(_unique_text(_desc(n,k)) for k in ('startdate','enddate'))
            if start and end:
                contexts[n.get('id')]=(start,end)
        elif kind=='unit':
            top=_desc(n,'unitnumerator')
            bottom=_desc(n,'unitdenominator')
            if top and bottom:
                if (_unique_text(_desc(top[0],'measure')) or '').lower()=='iso4217:usd' and (_unique_text(_desc(bottom[0],'measure')) or '').lower()=='xbrli:shares':
                    units[n.get('id')]='USD/shares'
            elif (_unique_text(_desc(n,'measure')) or '').lower()=='iso4217:usd':
                units[n.get('id')]='USD'
        elif kind=='nonfraction':
            numeric.append(n)
    return body,contexts,units,numeric

def confirm(url,cik,start,end,unit,tag,expected):
    body,contexts,units,numeric=statement(url,cik)
    values=[]
    for node in numeric:
        if node.get('name','').lower()!=('us-gaap:'+tag).lower():
            continue
        if contexts.get(node.get('contextref'))!=(start,end) or units.get(node.get('unitref'))!=unit:
            continue
        if node.get('format','').split(':')[-1].lower() not in ('','num-dot-decimal','numdotdecimal'):
            continue
        if unit=='USD':
            if not _contract_revenue_total(node):
                continue
            if 'revenuefromcontract' in tag.lower() and any(
                x.get('name','').lower()=='us-gaap:revenuenotfromcontractwithcustomer'
                and contexts.get(x.get('contextref'))==(start,end) for x in numeric
            ):
                continue
        raw=''.join(''.join(node.itertext()).split()).replace(',','')
        if not re.fullmatch(r'(?:\d+(?:\.\d+)?|\.\d+)',raw):
            continue
        scale=int(node.get('scale','0'))
        if not -12<=scale<=15:
            continue
        v=Decimal(raw)*Decimal(10)**scale
        sign=node.get('sign')
        if sign=='-':
            v=-v
        values.append((v,node,raw,scale,sign))
    if {v[0] for v in values}!={expected}:
        return None
    _,node,raw,scale,sign=values[0]
    row=next((n for n in node.iterancestors() if _local(n)=='tr'),None)
    return {'contextId':node.get('contextref'),'unitId':node.get('unitref'),'rawValue':raw,
            'scale':scale,'sign':sign,'rowText':' '.join(' '.join(row.itertext()).split())[:900] if row is not None else None,
            'sourceSha256':hashlib.sha256(body).hexdigest()}

def matches(data,start,end,unit,tags):
    out=[]
    for tag in tags:
        for fact in data.get(tag,{}).get('units',{}).get(unit,[]):
            if fact.get('start')!=start or fact.get('end')!=end or fact.get('form') not in ('10-K','10-Q'):
                continue
            if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',fact.get('accn','')):
                continue
            if not end<=fact.get('filed','')<=today.isoformat():
                continue
            if not isinstance(fact.get('val'),(int,float)) or isinstance(fact['val'],bool):
                continue
            out.append((tag,fact))
    return out

accepted=[]
visited=0
failures=[]
issuers=set()
ranked=sorted(target,key=lambda t:(-sum(x.get('revenue') is not None and x.get('epsGaapDiluted') is not None for x in target[t]),t))
for ticker in ranked:
    if len(issuers)==50:
        break
    entry=mapping.get(ticker,{})
    if not entry.get('cik') or entry.get('tickerStatus') in ('historical_alias','unconfirmed'):
        continue
    quarters=target[ticker]
    gaps=[(row,expected_start(row,quarters)) for row in quarters if row.get('currency')=='USD' and (row.get('revenue') is None or row.get('epsGaapDiluted') is None)]
    gaps=[(row,start) for row,start in gaps if start]
    if not gaps:
        continue
    cik=int(entry['cik'])
    if cik in issuers:
        continue
    visited+=1
    try:
        facts_url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010}.json'
        response=get(facts_url)
        payload=json.loads(response)
        if int(payload.get('cik',0))!=cik:
            raise ValueError('Wrong SEC companyfacts issuer')
        data=payload['facts']['us-gaap']
        filing_by_accession=None
        for row,start in sorted(gaps,key=lambda v:v[0]['periodEnd'],reverse=True):
            end=row['periodEnd']
            for field,(unit,tags) in concepts.items():
                if row.get(field) is not None or (field=='revenue' and entry.get('sector') in ('Financials','Utilities','Real Estate')):
                    continue
                options=matches(data,start,end,unit,tags)
                if field=='revenue':
                    totals=[x for x in options if x[0] in ('Revenues','SalesRevenueNet','RegulatedAndUnregulatedOperatingRevenue')]
                    options=totals or options
                if not options or len({Decimal(str(f['val'])) for _,f in options})!=1:
                    continue
                value=Decimal(str(options[0][1]['val']))
                if not value.is_finite() or (field=='revenue' and value<0):
                    continue
                if filing_by_accession is None:
                    sub=json.loads(get(f'https://data.sec.gov/submissions/CIK{cik:010}.json'))
                    if int(sub.get('cik',0))!=cik:
                        raise ValueError('Wrong SEC submissions issuer')
                    filing_by_accession={f['accessionNumber']:f for f in _filings(sub,today)}
                ordered=sorted(options,key=lambda x:(x[1]['accn']!=row.get('accessionNumber'),x[1]['filed']))
                tried=set()
                for tag,fact in ordered:
                    accession=fact['accn']
                    filing=filing_by_accession.get(accession)
                    if not filing or (tag,accession) in tried or len(tried)>=4:
                        continue
                    tried.add((tag,accession))
                    if filing['form']!=fact['form'] or filing['filingDate']!=fact['filed'] or filing['reportDate']<end:
                        continue
                    url=f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-','')}/{filing['primaryDocument']}"
                    try:
                        proof=confirm(url,cik,start,end,unit,tag,value)
                    except (ValueError,OSError,InvalidOperation):
                        continue
                    if proof is None:
                        continue
                    evidence={**proof,'entity':cik,'start':start,'end':end,'unitMeasure':unit,'factTag':'us-gaap:'+tag,
                              'companyfactsUrl':facts_url,'companyfactsSha256':hashlib.sha256(response).hexdigest(),
                              'companyfactsFact':fact,'filingReportDate':filing['reportDate']}
                    accepted.append({'ticker':ticker,'periodEnd':end,'fiscalYear':row['fiscalYear'],'fiscalQuarter':row['fiscalQuarter'],
                                     'field':field,'value':fact['val'],'sourceUrl':url,'evidence':evidence})
                    issuers.add(cik)
                    print(ticker,end,field,fact['val'],len(issuers),flush=True)
                    break
    except (OSError,ValueError,KeyError,TypeError) as exc:
        failures.append({'ticker':ticker,'type':type(exc).__name__})
    if visited%20==0:
        print('Progress',visited,len(issuers),len(accepted),flush=True)
Path('fact-candidates.json').write_text(json.dumps({'visited':visited,'companies':len(issuers),'failures':failures,'selected':accepted},indent=2)+'\n')
print('Verified companies',len(issuers),'fields',len(accepted),flush=True)
