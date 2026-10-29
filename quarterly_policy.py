"""Shared five-quarter policy for every active issuer; no source discovery here."""
import copy
import re
from datetime import date
from decimal import Decimal, InvalidOperation

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
    ftv_base='https://www.sec.gov/Archives/edgar/data/1659166/'
    ftv_filing=ftv_base+'000165916625000120/ftv-20250627.htm'
    ftv_release=ftv_base+'000165916625000119/q22025-ex991.htm'
    ftv_locator=previous.get('metricLocators',{}).get('revenue',{})
    ftv_exclusions=incoming.get('metricExclusionEvidence',[])
    ftv_conflicts=previous.get('metricConflicts',{}).get('revenue',[])
    if (previous.get('ticker') == 'FTV' and incoming.get('ticker','FTV') == 'FTV'
            and previous.get('periodEnd') == incoming.get('periodEnd') == '2025-06-27'
            and (incoming.get('fiscalYear'),incoming.get('fiscalQuarter')) == (2025,2)
            and previous.get('revenue') == 1016400000 and incoming.get('revenue') == 1518800000
            and previous.get('revenueSourceUrl') == ftv_release and incoming.get('revenueSourceUrl') == ftv_filing
            and previous.get('secUrl') == incoming.get('secUrl') == ftv_filing
            and previous.get('releaseSourceUrl') == incoming.get('releaseSourceUrl') == ftv_release
            and incoming.get('revenueVerificationStatus') == 'verified'
            and not incoming.get('metricConflicts',{}).get('revenue')
            and (ftv_locator.get('table'),ftv_locator.get('row'),ftv_locator.get('column'),ftv_locator.get('label')) == (8,5,5,'Sales')
            and any(e.get('table') == 8 and e.get('reason') == 'supplemental_recast_statement'
                    and e.get('sourceUrl') == ftv_release for e in ftv_exclusions)
            and all((e.get('value'),e.get('sourceUrl')) in ((1016400000,ftv_release),(1518800000,ftv_release),(1518800000,ftv_filing)) for e in ftv_conflicts)):
        result=copy.deepcopy(incoming)
        result.setdefault('metricRevision',{})['revenue']='2026-10-28-reviewed-recast-table-correction'
        result.setdefault('metricCorrectionEvidence',{})['revenue']={
            'reason':'supplemental_discontinued_operations_recast_was_not_original_consolidated_revenue',
            'oldValue':1016400000,'oldSourceUrl':ftv_release,'oldLocator':copy.deepcopy(ftv_locator),
            'newValue':1518800000,'newSourceUrl':ftv_filing,'excludedTables':copy.deepcopy(ftv_exclusions),
            'previousEvidence':copy.deepcopy(ftv_conflicts)}
        return result
    if (previous.get('ticker') == 'PNR' and incoming.get('ticker','PNR') == 'PNR'
            and previous.get('periodEnd') == incoming.get('periodEnd') == '2026-06-30'
            and (previous.get('fiscalYear'),previous.get('fiscalQuarter')) == (2026,2)
            and (incoming.get('fiscalYear'),incoming.get('fiscalQuarter')) == (2026,2)
            and previous.get('date') in ('2026-07-10','2026-07-14') and incoming.get('date') == '2026-07-28'
            and previous.get('releaseSourceUrl') == 'https://www.sec.gov/Archives/edgar/data/77360/000007736026000039/july2026pre-earningsexhibit.htm'
            and incoming.get('releaseSourceUrl') == 'https://www.sec.gov/Archives/edgar/data/77360/000007736026000042/q22026pressrelease.htm'):
        result=copy.deepcopy(incoming)
        result['releaseCorrectionEvidence']={'reason':'preliminary_results_and_personnel_event_were_not_completed_earnings',
            'oldDate':previous['date'],'oldSourceUrl':previous['releaseSourceUrl'],
            'newDate':incoming['date'],'newSourceUrl':incoming['releaseSourceUrl']}
        return result
    kdp_base='https://www.sec.gov/Archives/edgar/data/1418135/'
    wrong_quarter_source=kdp_base+'000141813526000048/ex991-keurigdrpepperreport.htm'
    correct_filing=kdp_base+'000141813526000026/kdp-20260331.htm'
    correct_release=kdp_base+'000141813526000020/ex991-keurigdrpepperreport.htm'
    if (previous.get('ticker') == 'KDP' and incoming.get('ticker','KDP') == 'KDP'
            and previous.get('periodEnd') == incoming.get('periodEnd') == '2026-03-31'
            and previous.get('fiscalYear') == 2026 and previous.get('fiscalQuarter') in (1,2)
            and (incoming.get('fiscalYear'),incoming.get('fiscalQuarter')) == (2026,1)
            and incoming.get('secUrl') == correct_filing
            and incoming.get('releaseSourceUrl') == correct_release and incoming.get('date') == '2026-04-23'):
        result=copy.deepcopy(incoming)
        corrected=False
        for field,source_field,state_field,old_value,new_value in (
                ('epsGaapDiluted','epsSourceUrl','epsVerificationStatus',0.04,0.20),
                ('revenue','revenueSourceUrl','revenueVerificationStatus',7309000000,3976000000)):
            evidence=previous.get('metricConflicts',{}).get(field,[])
            known_evidence=all((e.get('value'),e.get('sourceUrl')) in (
                (old_value,wrong_quarter_source),(new_value,correct_filing)) for e in evidence)
            if (previous.get(field) == old_value and previous.get(source_field) == wrong_quarter_source
                    and incoming.get(field) == new_value and incoming.get(source_field) == correct_filing
                    and incoming.get(state_field) == 'verified'
                    and not incoming.get('metricConflicts',{}).get(field) and known_evidence):
                result.setdefault('metricRevision',{})[field]='2026-10-28-reviewed-quarter-association-correction'
                result.setdefault('metricCorrectionEvidence',{})[field]={
                    'reason':'second_quarter_values_were_assigned_to_first_quarter',
                    'oldValue':old_value,'oldSourceUrl':wrong_quarter_source,
                    'newValue':new_value,'newSourceUrl':correct_filing,
                    'supportingReleaseUrl':correct_release,'previousEvidence':copy.deepcopy(evidence)}
                corrected=True
        if corrected:
            # These describe the original misassociation, including when a prior
            # partial run already changed the identity but quarantined its values.
            result['fiscalIdentityCorrectionEvidence']={'reason':'second_quarter_source_was_attached_to_first_quarter_period',
                'oldFiscalYear':2026,'oldFiscalQuarter':2,'newFiscalYear':2026,'newFiscalQuarter':1,
                'oldSourceUrl':wrong_quarter_source,'newSourceUrl':correct_release,'supportingFilingUrl':correct_filing}
            result['releaseCorrectionEvidence']={'reason':'second_quarter_release_was_attached_to_first_quarter_period',
                'oldDate':'2026-08-06','oldSourceUrl':wrong_quarter_source,
                'newDate':'2026-04-23','newSourceUrl':correct_release,'supportingFilingUrl':correct_filing}
            return result
    # A newly parsed SEC record receives its ticker only after the inner merge.
    schw_source='https://www.sec.gov/Archives/edgar/data/316709/000031670926000035/a3q26exhibit991.htm'
    if (previous.get('ticker') == 'SCHW' and incoming.get('ticker', 'SCHW') == 'SCHW'
            and incoming.get('periodEnd') == previous.get('periodEnd') == '2026-09-30'
            and (previous.get('fiscalYear'),previous.get('fiscalQuarter')) == (2025,3)
            and (incoming.get('fiscalYear'),incoming.get('fiscalQuarter')) == (2026,3)
            and previous.get('releaseSourceUrl') == incoming.get('releaseSourceUrl') == schw_source):
        result=copy.deepcopy(incoming)
        result['fiscalIdentityCorrectionEvidence']={'reason':'prior_year_comparison_was_not_current_quarter',
            'oldFiscalYear':2025,'newFiscalYear':2026,'fiscalQuarter':3,'releaseSourceUrl':schw_source}
        return result
    br_source='https://www.sec.gov/Archives/edgar/data/1383312/000138331225000024/br-20250804.htm'
    if (previous.get('ticker') == 'BR' and incoming.get('ticker', 'BR') == 'BR'
            and incoming.get('periodEnd') == previous.get('periodEnd') == '2025-06-30'
            and previous.get('date') == '2025-08-04' and incoming.get('date') == '2025-08-05'
            and previous.get('releaseSourceUrl') == incoming.get('releaseSourceUrl') == br_source):
        result=copy.deepcopy(incoming)
        result['releaseCorrectionEvidence']={'reason':'earliest_board_event_was_not_earnings_release',
            'oldDate':'2025-08-04','oldSourceUrl':br_source,'newDate':'2025-08-05','newSourceUrl':br_source,
            'supportingExhibitUrl':'https://www.sec.gov/Archives/edgar/data/1383312/000138331225000024/ex991earningsrelease4q2025.htm'}
        return result
    base='https://www.sec.gov/Archives/edgar/data/1748790/'
    old_source=base+'000174879026000014/amcr-20260506.htm'
    new_source=base+'000174879026000004/amcr-20260203.htm'
    if (previous.get('ticker') == 'AMCR' and incoming.get('ticker', 'AMCR') == 'AMCR'
            and incoming.get('periodEnd') == previous.get('periodEnd') == '2025-12-31'
            and previous.get('date') == '2026-05-06' and incoming.get('date') == '2026-02-03'
            and previous.get('releaseSourceUrl') == old_source and incoming.get('releaseSourceUrl') == new_source):
        result=copy.deepcopy(incoming)
        result['releaseCorrectionEvidence']={'reason':'later_quarter_cautionary_reference_was_not_this_release',
            'oldDate':'2026-05-06','oldSourceUrl':old_source,'newDate':'2026-02-03','newSourceUrl':new_source,
            'supportingExhibitUrl':base+'000174879026000004/exhibit991q22026.htm'}
        return result
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
    correction=updated.get('releaseCorrectionEvidence',{})
    if (correction.get('oldDate') == previous.get('date') and correction.get('oldSourceUrl') == previous.get('releaseSourceUrl')
            and correction.get('newDate') == updated.get('date') and correction.get('newSourceUrl') == updated.get('releaseSourceUrl')):
        return updated
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
    # A repeated scan can obtain the same identity from a matching filing
    # instead of reparsing the exhibit's period header. Keep its original
    # proof only while both document associations and fiscal identity agree.
    same_association = (bool(incoming.get('periodEnd'))
        and fiscal_identity(previous) == fiscal_identity(incoming)
        and all(previous.get(key) == incoming.get(key) for key in
            ('periodEnd','releaseSourceUrl','releaseAccession','secUrl','accessionNumber')))
    if same_association:
        for field in ('periodEndEvidence','metricStatementEvidence','metricInputExclusionEvidence'):
            if not result.get(field) and previous.get(field):
                result[field]=copy.deepcopy(previous[field])
    for evidence_field in ('releaseCorrectionEvidence','fiscalIdentityCorrectionEvidence'):
        if incoming.get(evidence_field) or previous.get(evidence_field):
            result[evidence_field]=copy.deepcopy(incoming.get(evidence_field) or previous[evidence_field])
    result['metricRevision'] = copy.deepcopy(previous.get('metricRevision', {}))
    result['metricCorrectionEvidence'] = copy.deepcopy(previous.get('metricCorrectionEvidence', {})) | copy.deepcopy(incoming.get('metricCorrectionEvidence', {}))
    if previous.get('metricConflictResolutionEvidence') or incoming.get('metricConflictResolutionEvidence'):
        result['metricConflictResolutionEvidence'] = copy.deepcopy(previous.get('metricConflictResolutionEvidence', {})) | copy.deepcopy(incoming.get('metricConflictResolutionEvidence', {}))
    if previous.get('metricPrecisionEvidence') or incoming.get('metricPrecisionEvidence'):
        result['metricPrecisionEvidence'] = copy.deepcopy(previous.get('metricPrecisionEvidence', {})) | copy.deepcopy(incoming.get('metricPrecisionEvidence', {}))
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
        rounded_match=False
        locator=incoming.get('metricLocators',{}).get(field,{})
        if (old_value is not None and new_value is not None and old_value != new_value
                and previous.get(state_field) == incoming.get(state_field) == 'verified'
                and previous.get('periodEnd') == incoming.get('periodEnd')
                and previous.get('secUrl') == incoming.get('secUrl')
                and str(incoming.get('secUrl','')).startswith('https://www.sec.gov/Archives/edgar/data/')
                and previous.get('accessionNumber') == incoming.get('accessionNumber')
                and incoming.get('accessionNumber')):
            try:
                precision=Decimal(str(locator.get('precision','0')))
                rounded_match=precision.is_finite() and precision>0 and abs(Decimal(str(old_value))-Decimal(str(new_value)))<precision/2
            except (InvalidOperation,ValueError):
                pass
        if old_revision and new_revision < old_revision:
            result[field], result[source_field] = old_value, old_source
            result[state_field] = previous.get(state_field, 'verified')
            continue
        if new_revision and new_revision > old_revision and new_value is not None:
            result['metricRevision'][field] = new_revision
            result['metricConflicts'].pop(field, None)
            result[state_field] = incoming.get(state_field, 'verified')
        elif rounded_match:
            result[field],result[source_field],result[state_field]=old_value,old_source,'verified'
            evidence={'preciseValue':old_value,'preciseSourceUrl':old_source,'roundedValue':new_value,
                      'roundedSourceUrl':new_source,'locator':copy.deepcopy(locator),'filingSourceUrl':incoming['secUrl']}
            saved=result.setdefault('metricPrecisionEvidence',{}).setdefault(field,[])
            if evidence not in saved:saved.append(evidence)
            continue
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
            previous_evidence=previous.get('metricConflicts',{}).get(field,[])
            input_exclusions=incoming.get('metricInputExclusionEvidence',[])
            def same_row(a,b):
                return all(a.get(k)==b.get(k) and a.get(k) is not None for k in ('table','row','column','label'))
            def proven_context(item,unit,*,proof=False):
                expected={k:incoming.get(k) for k in ('periodStart','periodEnd','fiscalYear','fiscalQuarter')}
                expected.update(periodScope='quarter',currency='USD',unit=unit)
                for entry,structural in ((item,{'value','precision','sourceUrl','locator'}|({'reason'} if proof else set())),
                                          (item.get('locator',{}),{'table','row','column','label','precision'})):
                    if set(entry)-structural-set(expected):return False
                    if any(k in entry and (expected[k] is None or entry[k]!=expected[k]) for k in expected):return False
                return True
            def excluded_input(item):
                from official_metrics import _eps_calculation_input
                return proven_context(item,'USD') and item.get('sourceUrl')==new_source and any(
                    e.get('reason')=='eps_calculation_input' and e.get('sourceUrl')==new_source
                    and proven_context(e,'USD',proof=True)
                    and e.get('periodEnd')==incoming.get('periodEnd')
                    and e.get('value')==item.get('value') and item.get('value')!=new_value
                    and same_row(e.get('locator',{}),item.get('locator',{}))
                    and _eps_calculation_input(e.get('locator',{}).get('label','')) for e in input_exclusions)
            def selected_actual(item):
                return (proven_context(item,'USD/shares') and proven_context({'locator':locator},'USD/shares')
                        and item.get('sourceUrl')==new_source and item.get('value')==new_value
                        and same_row(item.get('locator',{}),locator))
            if (field=='epsGaapDiluted' and (old_value is None or old_value==new_value) and new_value is not None
                    and incoming.get(state_field)=='verified' and not incoming.get('metricConflicts',{}).get(field)
                    and fiscal_identity(incoming) is not None and same_association
                    and incoming.get('periodScope')=='quarter' and incoming.get('currency')=='USD'
                    and previous.get('periodScope')=='quarter' and previous.get('currency')=='USD'
                    and (not previous.get('periodStart') or previous['periodStart']==incoming.get('periodStart'))
                    and new_source==incoming.get('releaseSourceUrl')
                    and str(new_source).startswith('https://www.sec.gov/Archives/edgar/data/')
                    and previous_evidence and any(excluded_input(e) for e in previous_evidence)
                    and any(selected_actual(e) for e in previous_evidence)
                    and all(excluded_input(e) or selected_actual(e) for e in previous_evidence)):
                result.setdefault('metricConflictResolutionEvidence',{})[field]={
                    'reason':'eps_numerator_was_not_a_per_share_value','actualValue':new_value,
                    'actualSourceUrl':new_source,'actualLocator':copy.deepcopy(locator),
                    'previousEvidence':copy.deepcopy(previous_evidence),'excludedInputs':copy.deepcopy(input_exclusions)}
                result['metricConflicts'].pop(field,None)
                result[field],result[source_field],result[state_field]=new_value,new_source,'verified'
                result['metricLocators'][field]=copy.deepcopy(locator)
                continue
            definition=incoming.get('metricDefinitionEvidence',{}).get(field,{})
            cik_match=re.match(r'https://www\.sec\.gov/Archives/edgar/data/(\d+)/',str(new_source))
            facts_url=f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik_match[1]):010d}.json' if cik_match else None
            def same_definition_fact(item):
                loc=item.get('locator',{})
                if (item.get('sourceUrl') != facts_url or loc.get('accession') != incoming.get('accessionNumber')
                        or loc.get('periodStart') != incoming.get('periodStart')
                        or loc.get('periodEnd') != incoming.get('periodEnd') or loc.get('unit') != 'USD'):
                    return False
                return ((loc.get('tag') == 'RevenuesNetOfInterestExpense' and item.get('value') == new_value)
                        or (loc.get('tag') == 'Revenues' and item.get('value') != new_value
                            and item.get('value') in definition.get('otherTaggedValues',[])))
            if (field == 'revenue' and (old_value is None or old_value == new_value) and new_value is not None
                    and incoming.get(state_field) == 'verified' and not incoming.get('metricConflicts',{}).get(field)
                    and previous.get('secUrl') == incoming.get('secUrl') == new_source and cik_match
                    and previous.get('accessionNumber') == incoming.get('accessionNumber') and incoming.get('accessionNumber')
                    and previous.get('periodEnd') == incoming.get('periodEnd')
                    and definition.get('definition') == 'consolidated_revenue_net_of_interest_expense'
                    and definition.get('selectedTag') == 'RevenuesNetOfInterestExpense'
                    and definition.get('selectedValue') == new_value and definition.get('sourceUrl') == new_source
                    and re.fullmatch(r'(?i)total net revenues?|(?:total )?revenues?,? net of interest expense',
                                     definition.get('statementLocator',{}).get('label',''))
                    and previous_evidence and all(same_definition_fact(e) for e in previous_evidence)
                    and any(e.get('locator',{}).get('tag') == 'Revenues' for e in previous_evidence)
                    and any(e.get('locator',{}).get('tag') == 'RevenuesNetOfInterestExpense' for e in previous_evidence)):
                result.setdefault('metricConflictResolutionEvidence',{})[field]={
                    'reason':'gross_and_net_revenue_were_different_statement_definitions','actualValue':new_value,
                    'actualSourceUrl':new_source,'definitionEvidence':copy.deepcopy(definition),
                    'previousEvidence':copy.deepcopy(previous_evidence)}
                result['metricConflicts'].pop(field,None)
                result[source_field],result[state_field]=new_source,'verified'
                continue
            release_base=str(previous.get('releaseSourceUrl','')).rsplit('/',1)[0]+'/'
            def excluded_adjustment(item):
                return (field == 'epsGaapDiluted' and item.get('value') != new_value and str(item.get('sourceUrl','')).startswith(release_base)
                        and bool(re.search(r'(?i)excluding\s+(?:specified|special|certain)\s+(?:items|charges)',
                                           item.get('locator',{}).get('label',''))))
            excluded_tables=incoming.get('metricExclusionEvidence',[])
            def excluded_scope(item):
                return item.get('value') != new_value and any(e.get('reason') == 'nonconsolidated_statement'
                    and isinstance(e.get('table'),int) and e['table']>0
                    and e.get('sourceUrl') == item.get('sourceUrl') and e.get('table') == item.get('locator',{}).get('table')
                    and re.search(r'(?i)\bjoint[ -]ventures?\b|\bunconsolidated\b|\bsegments?\b',e.get('heading',''))
                    for e in excluded_tables)
            def excluded(item):return excluded_adjustment(item) or excluded_scope(item)
            if ((old_value is None or old_value == new_value) and new_value is not None
                    and incoming.get(state_field) == 'verified' and not incoming.get('metricConflicts',{}).get(field)
                    and previous.get('periodEnd') == incoming.get('periodEnd')
                    and previous.get('secUrl') == incoming.get('secUrl')
                    and str(new_source).startswith('https://www.sec.gov/Archives/edgar/data/')
                    and (new_source == previous.get('secUrl') or str(new_source).startswith(release_base))
                    and release_base == str(incoming.get('releaseSourceUrl','')).rsplit('/',1)[0]+'/'
                    and previous_evidence and any(excluded(e) for e in previous_evidence)
                    and all(excluded(e) or (e.get('value') == new_value
                        and (e.get('sourceUrl') == old_source or str(e.get('sourceUrl','')).startswith(release_base)))
                        for e in previous_evidence)):
                result.setdefault('metricConflictResolutionEvidence',{})[field]={
                    'reason':'excluded_nonconsolidated_statement_rows' if any(excluded_scope(e) for e in previous_evidence) else 'excluded_adjustment_rows_were_not_gaap_actuals',
                    'actualValue':new_value,'actualSourceUrl':new_source,'previousEvidence':copy.deepcopy(previous_evidence),
                    'excludedTables':copy.deepcopy(excluded_tables)}
                result['metricConflicts'].pop(field,None)
                result[state_field]='verified'
                continue
            filing='https://www.sec.gov/Archives/edgar/data/712515/000071251525000030/ea-20250630.htm'
            exhibit='https://www.sec.gov/Archives/edgar/data/712515/000071251525000027/earningspressrelease2025_0.htm'
            evidence=previous.get('metricConflicts',{}).get(field,[])
            def reviewed_ea_item(item):
                loc=item.get('locator',{})
                if item.get('value') == 0.79 and item.get('sourceUrl') == filing:
                    return not loc
                if item.get('sourceUrl') != exhibit or loc.get('label') != 'Diluted':
                    return False
                return ((item.get('value') == 0.58 and (loc.get('table'),loc.get('row'),loc.get('column')) in {(7,35,4),(7,35,5)})
                        or (item.get('value') == 0.79 and (loc.get('table'),loc.get('row'),loc.get('column')) in {(6,36,4),(6,36,5),(7,35,16),(7,35,17)}))
            if (previous.get('ticker') == 'EA' and incoming.get('ticker','EA') == 'EA'
                    and previous.get('periodEnd') == incoming.get('periodEnd') == '2025-06-30'
                    and field == 'epsGaapDiluted' and old_value == new_value == 0.79
                    and old_source == new_source == filing and incoming.get(state_field) == 'verified'
                    and not incoming.get('metricConflicts',{}).get(field) and evidence
                    and any(e.get('value') == 0.58 for e in evidence) and all(reviewed_ea_item(e) for e in evidence)):
                result.setdefault('metricConflictResolutionEvidence',{})[field]={'reason':'guidance_column_was_not_actual_earnings',
                    'actualValue':0.79,'actualSourceUrl':filing,'supportingExhibitUrl':exhibit,
                    'previousEvidence':copy.deepcopy(evidence)}
                result['metricConflicts'].pop(field,None)
                result[state_field]='verified'
                continue
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
