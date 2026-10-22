"""Shared five-quarter policy for every active issuer; no source discovery here."""
import copy
import re
from datetime import date

HISTORY_LIMIT = 5


def _day(value):
    return date.fromisoformat(value) if isinstance(value, str) else None


def fiscal_identity(row):
    year, quarter = row.get('fiscalYear'), row.get('fiscalQuarter')
    if isinstance(year, int) and quarter in (1, 2, 3, 4):
        return year, quarter
    if row.get('verificationStatus') == 'official_verified' and row.get('periodScope') == 'quarter':
        match = re.fullmatch(r'(?:FY)?(\d{4}) Q([1-4])', row.get('quarter', ''))
        if match:
            return int(match[1]), int(match[2])
    return None


def period_key(row):
    if row.get('periodEnd'):
        return 'period', row['periodEnd']
    # Unverified duplicate labels may themselves be wrong; only the stored date can group them.
    return 'legacy', row.get('date')


def retain_history(history, today=None):
    result = {}
    for ticker, rows in history.items():
        unique = {}
        for original in rows:
            row = copy.deepcopy(original)
            released = _day(row.get('date'))
            end = _day(row.get('periodEnd'))
            if not released or (today and released > today) or (end and end > released):
                raise ValueError(f'Invalid historical dates for {ticker}')
            identity = fiscal_identity(row)
            if identity:
                row['fiscalYear'], row['fiscalQuarter'] = identity
            if row.get('verificationStatus') != 'official_verified' or not row.get('periodEnd') or row.get('periodScope')!='quarter':
                row['verificationStatus'] = 'legacy_unverified'
            key = period_key(row)
            previous = unique.get(key)
            priority = lambda item: (item.get('verificationStatus') == 'official_verified', item.get('verifiedAt', ''), item.get('date', ''))
            if previous is None or priority(row) > priority(previous):
                unique[key] = row
        # Original/revised filings for a verified period share periodEnd and never reorder on amendment date.
        order=lambda item:item.get('periodEnd') or item['date']
        trusted=sorted((r for r in unique.values() if r.get('verificationStatus')=='official_verified' and r.get('periodScope')=='quarter' and r.get('periodEnd')),key=order,reverse=True)[:HISTORY_LIMIT]
        legacy=sorted((r for r in unique.values() if r.get('verificationStatus')!='official_verified'),key=order,reverse=True)
        selected=trusted+legacy[:HISTORY_LIMIT-len(trusted)]
        result[ticker]=sorted(selected,key=order,reverse=True)
    return result


def retain_manifest(records):
    grouped = {}
    for original in records:
        record = copy.deepcopy(original)
        key = (record['ticker'], record['periodEnd'])
        previous = grouped.get(key)
        if previous is None or record.get('verifiedAt', '') >= previous.get('verifiedAt', ''):
            grouped[key] = record
    result = []
    for ticker in sorted({key[0] for key in grouped}):
        result.extend(sorted((r for (t, _), r in grouped.items() if t == ticker), key=lambda r: r['periodEnd'], reverse=True)[:HISTORY_LIMIT])
    return result


def company_fields(company, history, today):
    result = dict(company)
    # Existing forward estimates have no auditable next-quarter period/source.
    result['eps'] = '-'
    result['revenue'] = '-'
    if result.get('tickerIdentityStatus') in ('historical_alias','unconfirmed') and result.get('reportDateSource')!='official':
        result['reportDate']=None
        result['reportDateSource']=None
        result['reportDateSourceUrl']=None
    rows = history.get(result['ticker'], [])
    verified = [r for r in rows if r.get('verificationStatus') == 'official_verified' and fiscal_identity(r)]
    result.pop('latestPublishedQuarter', None)
    result.pop('latestPublishedDate', None)
    if verified:
        latest = max(verified, key=lambda r: r.get('periodEnd') or r['date'])
        result['latestPublishedQuarter'] = latest['quarter']
        result['latestPublishedDate'] = latest['date']
    for field, dependent in [('reportDate', ('reportDateSource', 'reportDateSourceUrl', 'bmo_amc')),
                              ('nextEarningsCallDate', ('nextEarningsCallSourceUrl',))]:
        try:
            event_day = _day(result.get(field))
        except ValueError:
            event_day = None
        if event_day is None or event_day < today:
            if field == 'reportDate':
                result[field] = None
                for name in dependent:
                    result[name] = None
            else:
                result.pop(field, None)
                for name in dependent:
                    result.pop(name, None)
    return result


def preserve_release_provenance(updated, previous):
    """Keep the earliest confirmed release date and its source identifiers together."""
    if not previous.get('date') or previous['date'] > updated.get('date',''):
        return updated
    same_day=previous['date']==updated.get('date')
    for field in ('date','releaseSourceUrl','releaseFilingDate','releaseAccession'):
        if previous.get(field) is not None:
            updated[field]=previous[field]
        elif not same_day:
            updated.pop(field,None)
    return updated


def merge_manifest_record(previous, incoming):
    if previous.get('verifiedAt','') > incoming.get('verifiedAt',''):
        return copy.deepcopy(previous)
    result=copy.deepcopy(incoming)
    for field, source_field in [('epsGaapDiluted','epsSourceUrl'),('revenue','revenueSourceUrl')]:
        if result.get(field) is None and previous.get(field) is not None:
            result[field]=previous[field]
            result[source_field]=previous.get(source_field) or previous.get('metricSourceUrl') or previous['releaseSourceUrl']
        elif result.get(field) is not None:
            result[source_field]=incoming.get(source_field) or incoming.get('metricSourceUrl') or incoming['releaseSourceUrl']
    if result.get('epsGaapDiluted') is not None:
        result['epsBasis']='GAAP diluted'
    if incoming.get('epsGaapDiluted') is None and incoming.get('revenue') is None and previous:
        result['metricSourceUrl']=previous.get('metricSourceUrl') or previous['releaseSourceUrl']
    return preserve_release_provenance(result,previous)
