"""Shared five-quarter policy for every active issuer; no source discovery here."""
import copy
import re
from datetime import date

HISTORY_LIMIT = 5

# Each pair was checked against the original SEC gross-revenue tag and the
# consolidated net-revenue line in that quarter's earnings exhibit.
_RSG_NET_REVENUE_CORRECTIONS = {
    '2026-06-30': (5076000000, 4430000000, '000106039126000275/rsg-20260630.htm', '000106039126000273/exhibit991q22026.htm'),
    '2025-09-30': (4827000000, 4212000000, '000162828025047655/rsg-20250930.htm', '000162828025047534/exhibit991q32025.htm'),
    '2025-06-30': (4882000000, 4235000000, '000106039125000216/rsg-20250630.htm', '000106039125000215/exhibit991q22025.htm'),
    '2025-03-31': (4593000000, 4009000000, '000106039125000170/rsg-20250331.htm', '000106039125000169/exhibit991q12025.htm'),
}


def _reviewed_baseline_correction(previous, incoming):
    # A newly parsed SEC record receives its ticker only after the inner merge.
    if previous.get('ticker') == 'MSCI' and incoming.get('ticker', previous.get('ticker')) == 'MSCI':
        source='https://www.sec.gov/Archives/edgar/data/1408198/000140819826000005/exhibit991earningsrelease-.htm'
        old_locator=previous.get('metricLocators',{}).get('epsGaapDiluted',{})
        new_locator=incoming.get('metricLocators',{}).get('epsGaapDiluted',{})
        if (incoming.get('periodEnd') == '2025-12-31'
                and previous.get('epsGaapDiluted') == 74697
                and incoming.get('epsGaapDiluted') == 3.81
                and previous.get('epsSourceUrl') == source
                and incoming.get('epsSourceUrl') == source
                and old_locator.get('label') == 'Diluted'
                and old_locator.get('precision') == '1'
                and new_locator.get('label') == 'Earnings per diluted common share'
                and incoming.get('epsVerificationStatus','verified') == 'verified'):
            result=copy.deepcopy(incoming)
            result.setdefault('metricRevision',{})['epsGaapDiluted']='2026-10-26-reviewed-share-count-correction'
            result.setdefault('metricCorrectionEvidence',{})['epsGaapDiluted']={
                'reason':'previous_diluted_share_count_was_not_earnings_per_share',
                'oldValue':74697,'oldSourceUrl':source,'oldLocator':copy.deepcopy(old_locator),
                'newValue':3.81,'newSourceUrl':source,'newLocator':copy.deepcopy(new_locator)}
            return result
    if previous.get('ticker') != 'RSG' or incoming.get('ticker', previous.get('ticker')) != 'RSG':
        return incoming
    review = _RSG_NET_REVENUE_CORRECTIONS.get(incoming.get('periodEnd'))
    if not review:
        return incoming
    old_value,new_value,old_path,new_path=review
    base='https://www.sec.gov/Archives/edgar/data/1060391/'
    if (previous.get('revenue') != old_value or incoming.get('revenue') != new_value
            or previous.get('revenueSourceUrl') != base+old_path
            or incoming.get('revenueSourceUrl') != base+new_path
            or incoming.get('revenueVerificationStatus','verified') != 'verified'):
        return incoming
    result=copy.deepcopy(incoming)
    result.setdefault('metricRevision',{})['revenue']='2026-10-26-reviewed-gross-to-net-correction'
    result.setdefault('metricCorrectionEvidence',{})['revenue']={
        'reason':'previous_gross_tag_was_not_consolidated_net_revenue',
        'oldValue':old_value,'oldSourceUrl':base+old_path,
        'newValue':new_value,'newSourceUrl':base+new_path}
    return result


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
    incoming=_reviewed_baseline_correction(previous,incoming)
    result=copy.deepcopy(incoming)
    result['metricRevision'] = copy.deepcopy(previous.get('metricRevision', {}))
    result['metricCorrectionEvidence'] = copy.deepcopy(previous.get('metricCorrectionEvidence', {})) | copy.deepcopy(incoming.get('metricCorrectionEvidence', {}))
    result['metricConflicts'] = copy.deepcopy(previous.get('metricConflicts', {}))
    for field,evidence in incoming.get('metricConflicts',{}).items():
        saved = result['metricConflicts'].setdefault(field,[])
        for item in evidence:
            if item not in saved:
                saved.append(copy.deepcopy(item))
    result['metricLocators'] = copy.deepcopy(previous.get('metricLocators', {}))
    for field, source_field in [('epsGaapDiluted','epsSourceUrl'),('revenue','revenueSourceUrl')]:
        state_field = 'epsVerificationStatus' if field == 'epsGaapDiluted' else 'revenueVerificationStatus'
        old_revision = previous.get('metricRevision', {}).get(field, '')
        new_revision = incoming.get('metricRevision', {}).get(field, '')
        old_value, new_value = previous.get(field), incoming.get(field)
        old_source = previous.get(source_field) or previous.get('metricSourceUrl') or previous.get('releaseSourceUrl')
        new_source = incoming.get(source_field) or incoming.get('metricSourceUrl') or incoming.get('releaseSourceUrl')
        if old_revision and new_revision < old_revision:
            result[field], result[source_field] = old_value, old_source
            result[state_field] = previous.get(state_field, 'verified')
            continue
        if new_revision and new_revision > old_revision and new_value is not None:
            result['metricRevision'][field] = new_revision
            result['metricConflicts'].pop(field, None)
            result[state_field] = incoming.get(state_field, 'verified')
        elif (old_value is not None and new_value is not None and old_value != new_value) or incoming.get(state_field) == 'conflict':
            evidence = result['metricConflicts'].setdefault(field, [])
            for value, source in ((old_value, old_source), (new_value, new_source)):
                if value is None:
                    continue
                item = {'value': value, 'sourceUrl': source}
                if item not in evidence:
                    evidence.append(item)
            result[field], result[source_field] = (old_value,old_source) if old_value is not None else (new_value,new_source)
            result[state_field] = 'conflict'
            continue
        elif previous.get(state_field) == 'conflict':
            result[field], result[source_field] = old_value, old_source
            result[state_field] = 'conflict'
            continue
        else:
            result[state_field] = 'verified' if new_value is not None or old_value is not None else 'pending'
        if result.get(field) is None and previous.get(field) is not None:
            result[field]=previous[field]
            result[source_field]=previous.get(source_field) or previous.get('metricSourceUrl') or previous['releaseSourceUrl']
        elif result.get(field) is not None:
            result[source_field]=incoming.get(source_field) or incoming.get('metricSourceUrl') or incoming['releaseSourceUrl']
            if field in incoming.get('metricLocators', {}):
                result['metricLocators'][field] = copy.deepcopy(incoming['metricLocators'][field])
    if result.get('epsGaapDiluted') is not None:
        result['epsBasis']='GAAP diluted'
    if incoming.get('epsGaapDiluted') is None and incoming.get('revenue') is None and previous:
        result['metricSourceUrl']=previous.get('metricSourceUrl') or previous['releaseSourceUrl']
    return preserve_release_provenance(result,previous)
