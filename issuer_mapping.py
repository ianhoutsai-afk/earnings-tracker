"""Fill only missing CIKs using official SEC issuer identity evidence."""
import copy
import json
import re
from urllib.parse import urlparse

REGISTRY_URL='https://www.sec.gov/files/company_tickers.json'


def fill_missing_ciks(companies,history,mapping,fetch):
    result=copy.deepcopy(mapping)
    missing=[c for c in companies if not result.get(c['ticker'],{}).get('cik')]
    if not missing:return result
    try:
        rows=json.loads(fetch(REGISTRY_URL))
        lookup={r['ticker']:r for r in rows.values() if isinstance(r,dict) and isinstance(r.get('cik_str'),int)}
    except Exception:
        lookup={}
    for company in missing:
        ticker=company['ticker']
        source=None;cik=None;fy_end=None;identity_fields={}
        official=lookup.get(ticker) or lookup.get(ticker.replace('-','.'))
        if official:
            cik=str(official['cik_str']).zfill(10);source=REGISTRY_URL
        else:
            candidates=set()
            for row in history.get(ticker,[]):
                url=row.get('secUrl') or ''
                if urlparse(url).hostname=='www.sec.gov':
                    match=re.search(r'/Archives/edgar/data/(\d+)/',url)
                    if match:candidates.add(match[1].zfill(10))
            if len(candidates)==1:
                candidate=candidates.pop();url=f'https://data.sec.gov/submissions/CIK{candidate}.json'
                try:
                    submission=json.loads(fetch(url))
                    aliases={v.replace('.','-') for v in submission.get('tickers',[])}
                    normalized=lambda value:re.sub(r'[^a-z0-9]','',value.lower())
                    official_names=[submission.get('name','')]+[r.get('name','') for r in submission.get('formerNames',[])]
                    same_name=bool(company.get('name')) and normalized(company['name']) in {normalized(name) for name in official_names}
                    if str(submission.get('cik')).zfill(10)==candidate and (ticker.replace('.','-') in aliases or same_name):
                        cik=candidate;source=url
                        current_tickers=submission.get('tickers',[])
                        identity_fields={'officialName':submission.get('name'),'officialTickers':current_tickers,
                            'tickerStatus':'current' if ticker.replace('.','-') in aliases else 'historical_alias' if current_tickers else 'unconfirmed'}
                        end=submission.get('fiscalYearEnd','')
                        if re.fullmatch(r'\d{4}',end) and 1<=int(end[:2])<=12:fy_end=int(end[:2])
                except Exception:
                    pass
        if cik:
            result[ticker]={**result.get(ticker,{}),'name':company.get('name',ticker),
                            'cik':cik,'cikSourceUrl':source,**identity_fields,'filings':result.get(ticker,{}).get('filings',{})}
            if fy_end:result[ticker]['fy_end']=fy_end
    return result
