"""Verify quarterly values against SEC Company Facts and known reporting bases."""
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from official_sync import fetch_sec

records=json.loads(Path('official_history.json').read_text())
mapping=json.loads(Path('sp500_mapping.json').read_text())
today=datetime.now(ZoneInfo('America/New_York')).date()
spans={}
for row in records:
    spans.setdefault(row['ticker'],[]).append(row)
tags=('Revenues','SalesRevenueNet','RevenueFromContractWithCustomerExcludingAssessedTax',
      'RevenueFromContractWithCustomerIncludingAssessedTax','RevenuesNetOfInterestExpense',
      'RegulatedAndUnregulatedOperatingRevenue','InterestAndDividendIncomeOperating')
tags=tags[:-1]
lock=threading.Lock()
next_request=0.0

def fetch(url):
    global next_request
    with lock:
        time.sleep(max(0,next_request-time.monotonic()))
        next_request=time.monotonic()+0.27
    return fetch_sec(url)

def duration(f):
    try:
        return (date.fromisoformat(f['end'])-date.fromisoformat(f['start'])).days+1
    except (KeyError,TypeError,ValueError):
        return 0

def eligible_facts(values):
    return [f for f in values if isinstance(f.get('val'),(int,float)) and not isinstance(f['val'],bool)
            and f.get('form') in ('10-K','10-Q','10-K/A','10-Q/A') and f.get('accn')
            and f.get('filed','')<=today.isoformat() and duration(f)>0]

def unique(facts):
    return facts[0] if facts and len({f['val'] for f in facts})==1 else None

def for_row(facts,row,lower=70,upper=116,matching_filing=True):
    return [f for f in facts if f.get('end')==row['periodEnd'] and lower<=duration(f)<=upper
            and (not matching_filing or f['accn']==row.get('accessionNumber'))
            and (not row.get('periodStart') or lower>116 or f.get('start')==row['periodStart'])]

def observed_basis(facts,ticker,target):
    matches=[]
    for row in spans[ticker]:
        if row['periodEnd']==target['periodEnd'] or row['revenue'] is None or row.get('currency')!='USD':
            continue
        possible=for_row(facts,row)
        if not possible:
            possible=[f for f in for_row(facts,row,matching_filing=False)
                        if f.get('filed','')<=(row.get('filingDate') or target.get('filingDate') or today.isoformat())]
        pick=unique(possible)
        if pick and pick['val']==row['revenue']:
            matches.append({'periodEnd':row['periodEnd'],'baselineValue':row['revenue'],'fact':pick})
    return matches

def supports_quarters(facts,annual,nine):
    items=[f for f in facts if 70<=duration(f)<=116 and annual['start']<=f['start']<=f['end']<=nine['end']
           and f.get('filed','')<=annual['filed'] and f.get('form') in ('10-Q','10-Q/A')]
    windows={}
    for f in items:
        windows.setdefault((f['start'],f['end']),[]).append(f)
    certain=[unique(v) for v in windows.values()]
    certain=[f for f in certain if f]
    chains=[]
    for q1 in certain:
        if q1['start']!=annual['start']:
            continue
        for q2 in certain:
            if (date.fromisoformat(q2['start'])-date.fromisoformat(q1['end'])).days!=1:
                continue
            for q3 in certain:
                if q3['end']!=nine['end'] or (date.fromisoformat(q3['start'])-date.fromisoformat(q2['end'])).days!=1:
                    continue
                if q1['val']+q2['val']+q3['val']==nine['val']:
                    chains.append([q1,q2,q3])
    return chains[0] if chains else None

def discover(ticker,rows):
    cik=int(mapping[ticker]['cik'])
    source=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
    try:
        body=fetch(source)
        payload=json.loads(body)
        if int(payload['cik'])!=cik:
            return [],[[ticker,'issuer mismatch']]
        us_gaap=payload['facts']['us-gaap']
    except (OSError,ValueError,TypeError,KeyError) as error:
        return [],[[ticker,type(error).__name__]]
    fields={}
    for tag in (*tags,'EarningsPerShareDiluted'):
        units='USD/shares' if tag=='EarningsPerShareDiluted' else 'USD'
        fields[tag]=eligible_facts(us_gaap.get(tag,{}).get('units',{}).get(units,[]))
    accepted=[]
    for row in rows:
        prefix=f'https://www.sec.gov/Archives/edgar/data/{cik}/'
        filing=row.get('secUrl') or ''
        if not filing.startswith(prefix) or row.get('form') not in ('10-Q','10-K'):
            continue
        common={'entity':cik,'sourceSha256':hashlib.sha256(body).hexdigest(),'companyFactsUrl':source,
                'filingForm':row['form']}
        def package(field,e,kind):
            return {'ticker':ticker,'periodEnd':row['periodEnd'],'fiscalYear':row['fiscalYear'],'fiscalQuarter':row['fiscalQuarter'],
                    'field':field,'value':e['value'],'sourceUrl':filing,'parentReleaseUrl':row['releaseSourceUrl'],
                    'sourceKind':kind,'evidence':e}
        if row['epsGaapDiluted'] is None:
            fact=unique(for_row(fields['EarningsPerShareDiluted'],row))
            if fact:
                proof={**common,'value':fact['val'],'unitMeasure':'USD/shares',
                    'factTag':'us-gaap:EarningsPerShareDiluted','rowLabel':'Reported GAAP diluted EPS',
                    'start':fact['start'],'end':fact['end'],'companyfactsFact':fact}
                accepted.append(package('epsGaapDiluted',proof,'companyfacts_direct'))
        if row['revenue'] is not None:
            continue
        direct={}
        estimates={}
        for tag in tags:
            facts=fields[tag]
            if not facts:
                continue
            basis=observed_basis(facts,ticker,row)
            if len(basis)<2:
                continue
            proof={**common,'unitMeasure':'USD','factTag':'us-gaap:'+tag,'rowLabel':us_gaap[tag]['label'],'basisMatches':basis}
            fact=unique(for_row(facts,row))
            if fact and fact['val']>=0:
                direct.setdefault(fact['val'],{**proof,'value':fact['val'],'start':fact['start'],'end':fact['end'],'companyfactsFact':fact})
                continue
            if row['fiscalQuarter']!=4 or row['form']!='10-K':
                continue
            q3=next((x for x in spans[ticker] if x['fiscalYear']==row['fiscalYear'] and x['fiscalQuarter']==3 and x.get('form')=='10-Q' and x.get('secUrl')),None)
            if not q3:
                continue
            annual=unique(for_row(facts,row,350,380))
            interim=unique(for_row(facts,q3,253,290))
            if not annual or not interim or annual['start']!=interim['start'] or not 70<=(date.fromisoformat(annual['end'])-date.fromisoformat(interim['end'])).days<=116:
                continue
            if annual['val']<=interim['val'] or int(annual['val'])!=annual['val'] or int(interim['val'])!=interim['val']:
                continue
            chain=supports_quarters(facts,annual,interim)
            if not chain and not any(x['periodEnd']==q3['periodEnd'] for x in basis):
                continue
            # If an exact whole-issuer Q4 fact is present in a comparative
            # filing, it must agree with the additive result.
            amount=annual['val']-interim['val']
            q4=[f for f in for_row(facts,row,matching_filing=False)
                if (date.fromisoformat(f['start'])-date.fromisoformat(interim['end'])).days==1]
            if q4 and any(f['val']!=amount for f in q4):
                continue
            estimates.setdefault(amount,{**proof,'value':amount,'annual':annual,'nineMonths':interim,
                'annualUrl':filing,'nineMonthsUrl':q3['secUrl'],'interimQuarterFacts':chain,
                'corroboratingQuarterFacts':q4[:4]})
        if len(direct)==1:
            accepted.append(package('revenue',next(iter(direct.values())),'companyfacts_direct'))
        elif not direct and len(estimates)==1:
            accepted.append(package('revenue',next(iter(estimates.values())),'companyfacts_quarter_revenue'))
    return accepted,[]

targets={}
for row in records:
    t=row['ticker']
    if row.get('currency')!='USD' or (row['epsGaapDiluted'] is not None and row['revenue'] is not None):
        continue
    if mapping[t].get('tickerStatus') in ('historical_alias','unconfirmed') or (t=='KDP' and row['periodEnd']=='2026-03-31'):
        continue
    if not row.get('secUrl'):
        continue
    targets.setdefault(t,[]).append(row)
chosen=[]
errors=[]
with ThreadPoolExecutor(max_workers=7) as pool:
    for batch,failures in pool.map(lambda pair:discover(*pair),targets.items()):
        chosen.extend(batch)
        errors.extend(failures)
        for x in batch:
            print(x['ticker'],x['periodEnd'],x['field'],x['value'],x['sourceKind'],flush=True)
out={'visited':len(targets),'companies':len({int(mapping[x['ticker']]['cik']) for x in chosen}),'failures':errors,'selected':chosen}
Path('further-companyfacts-candidates.json').write_text(json.dumps(out,indent=2)+'\n')
print('Verified SEC facts for',out['companies'],'issuers',len(chosen),'fields',flush=True)
