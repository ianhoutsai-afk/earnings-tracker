"""Shared five-quarter policy for every active issuer; no source discovery here."""
import copy
import re
from datetime import date

HISTORY_LIMIT = 5

# Reviewed fiscal-year changes: intervening transition reports are not quarters.
# FDX: https://www.sec.gov/Archives/edgar/data/1048911/000104891126000131/fdx-20260930.htm
# FERG: https://www.sec.gov/Archives/edgar/data/2011641/000201164126000044/ferg-20260930.htm
_FISCAL_TRANSITIONS = {
    ('FDX', '2026-09-30', '2026-05-31'): ((2026, 3), (2026, 4)),
    ('FERG', '2026-03-31', '2025-10-31'): ((2026, 1), (2026, 1)),
}


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


def history_continuity_issues(history):
    """Flag skipped or inconsistent quarters without guessing calendar identities."""
    result = {}
    for ticker, rows in history.items():
        ordered = sorted(rows, key=lambda row: row.get('periodEnd') or '', reverse=True)
        for newer, older in zip(ordered, ordered[1:]):
            first, second = fiscal_identity(newer), fiscal_identity(older)
            ends = (newer.get('periodEnd'), older.get('periodEnd'))
            if first and second:
                if _FISCAL_TRANSITIONS.get((ticker, *ends)) == (first, second):
                    continue
                serial = lambda identity: identity[0] * 4 + identity[1]
                if serial(first) - serial(second) == 1 and all(ends):
                    if 0 < (_day(ends[0]) - _day(ends[1])).days <= 140:
                        continue
            result.setdefault(ticker, []).append({
                'newerPeriodEnd': ends[0], 'olderPeriodEnd': ends[1],
                'newerFiscalQuarter': f'{first[0]} Q{first[1]}' if first else None,
                'olderFiscalQuarter': f'{second[0]} Q{second[1]}' if second else None,
            })
    return result


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


def official_source_url(row):
    return row.get('secUrl') if row.get('dateSource') == 'sec_filing' else row.get('releaseSourceUrl')


def filing_dated_quarters(history):
    return sum(row.get('verificationStatus') == 'official_verified' and row.get('dateSource') == 'sec_filing'
               for rows in history.values() for row in rows)


def pending_history_companies(history):
    continuity_pending = history_continuity_issues(history)
    return sum(
        ticker in continuity_pending or len(rows) < HISTORY_LIMIT or any(
            row.get('verificationStatus') != 'official_verified'
            or row.get('periodScope') != 'quarter'
            or not row.get('periodEnd')
            or row.get('currency') != 'USD'
            or row.get('epsBasis') != 'GAAP diluted'
            or not row.get('eps_reported') or row['eps_reported'] == '-'
            or not row.get('revenue_reported') or row['revenue_reported'] == '-'
            or row.get('dateSource') not in (None, 'recast')
            for row in rows
        )
        for ticker, rows in history.items()
    )


def all_release_dates_verified(history):
    return all(len(rows) == HISTORY_LIMIT and all(
        row.get('verificationStatus') == 'official_verified' and row.get('dateSource') is None
        for row in rows
    ) for rows in history.values())


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
    verified = [r for r in rows if r.get('verificationStatus') == 'official_verified'
                and r.get('dateSource') is None and fiscal_identity(r)]
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
    previous_source = previous.get('dateSource')
    updated_source = updated.get('dateSource')
    if not previous.get('date') or previous_source == 'sec_filing':
        return updated
    if previous_source == 'recast' and updated_source is None:
        return updated
    if previous_source == updated_source and previous['date'] > updated.get('date', ''):
        return updated
    if previous_source == 'recast':
        updated['dateSource'] = 'recast'
    else:
        updated.pop('dateSource', None)
    same_day=previous['date']==updated.get('date')
    for field in ('date','releaseSourceUrl','releaseFilingDate','releaseAccession'):
        if previous.get(field) is not None:
            updated[field]=previous[field]
        elif not same_day:
            updated.pop(field,None)
    return updated


def merge_manifest_record(previous, incoming):
    previous_is_newer = previous.get('verifiedAt', '') > incoming.get('verifiedAt', '')
    newer, older = (previous, incoming) if previous_is_newer else (incoming, previous)
    result = copy.deepcopy(newer)
    if (result.get('periodScope') == older.get('periodScope') == 'quarter'
            and all(result.get(field) and result[field] == older.get(field)
                    for field in ('ticker', 'periodEnd', 'fiscalYear', 'fiscalQuarter'))):
        if result.get('periodStart') is None and older.get('periodStart'):
            result['periodStart'] = older['periodStart']
        filing_fields = ('secUrl', 'accessionNumber', 'filingDate', 'form')
        if not any(result.get(field) for field in filing_fields) and all(older.get(field) for field in filing_fields):
            result.update({field: older[field] for field in filing_fields})
        # A later scan of the original filing has a fresh check timestamp but
        # still predates a reviewed comparative disclosure for the same quarter.
        if (older.get('metricRevisionFilingDate') or '') > (result.get('metricRevisionFilingDate') or ''):
            revision_fields = ('metricRevisionFilingDate', 'revenue', 'epsGaapDiluted', 'epsBasis',
                               'metricSourceUrl', 'revenueSourceUrl', 'epsSourceUrl',
                               'metricNote', 'metricNoteSourceUrl')
            for field in revision_fields:
                if field in older:
                    result[field] = copy.deepcopy(older[field])
                else:
                    result.pop(field, None)
            return preserve_release_provenance(result, older)
    if previous_is_newer:
        return preserve_release_provenance(result, incoming)
    for field, source_field in [('epsGaapDiluted','epsSourceUrl'),('revenue','revenueSourceUrl')]:
        if result.get(field) is None and previous.get(field) is not None:
            result[field]=previous[field]
            result[source_field]=previous.get(source_field) or previous.get('metricSourceUrl') or official_source_url(previous)
        elif result.get(field) is not None:
            result[source_field]=incoming.get(source_field) or incoming.get('metricSourceUrl') or official_source_url(incoming)
    if result.get('epsGaapDiluted') is not None:
        result['epsBasis']='GAAP diluted'
    if incoming.get('epsGaapDiluted') is None and incoming.get('revenue') is None and previous:
        result['metricSourceUrl']=previous.get('metricSourceUrl') or official_source_url(previous)
    if incoming.get('metricNote') is None and previous.get('metricNote') is not None:
        result['metricNote'] = copy.deepcopy(previous['metricNote'])
        if previous.get('metricNoteSourceUrl'):
            result['metricNoteSourceUrl'] = previous['metricNoteSourceUrl']
    return preserve_release_provenance(result,previous)
