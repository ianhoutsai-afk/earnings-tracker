"""Public, backward-compatible source, identity and field-level coverage ledger."""
import copy
from datetime import datetime, timedelta

PARSER_VERSION = 21


def metric_verified(row, field):
    state = 'epsVerificationStatus' if field == 'epsGaapDiluted' else 'revenueVerificationStatus'
    value = 'eps_reported' if field == 'epsGaapDiluted' else 'revenue_reported'
    return (row.get('verificationStatus') == 'official_verified' and row.get('periodScope') == 'quarter'
            and row.get('currency') == 'USD' and row.get(state) not in ('conflict', 'pending')
            and row.get(value) not in (None, '-')
            and (field != 'epsGaapDiluted' or row.get('epsBasis') == 'GAAP diluted'))


def company_status(company, rows, previous, checked):
    result = copy.deepcopy(previous)
    trusted = [r for r in rows if r.get('verificationStatus') == 'official_verified' and r.get('periodScope') == 'quarter']
    trusted.sort(key=lambda r:r['periodEnd'], reverse=True)
    source = result.setdefault('sourceCheck', {})
    success = source.get('lastSuccessfulDiscoveryAt')
    try:
        source['stale'] = datetime.fromisoformat(checked.replace('Z','+00:00')) - datetime.fromisoformat(success.replace('Z','+00:00')) > timedelta(hours=30)
    except (TypeError, ValueError, AttributeError):
        source['stale'] = True
    source.setdefault('state', 'not_checked')
    candidates = result.setdefault('candidates', [])
    oldest = trusted[-1]['periodEnd'] if len(trusted) == 5 else None
    for candidate in candidates:
        candidate['scope'] = 'superseded' if oldest and (
            (candidate.get('periodEnd') and candidate['periodEnd'] < oldest)
            or (candidate.get('filingDate') and candidate['filingDate'] < oldest)) else 'current_or_unknown'
    active = [c for c in candidates if c['scope'] != 'superseded']
    latest = trusted[0] if trusted else {}
    ordinals = [r['fiscalYear']*4+r['fiscalQuarter'] for r in trusted
                if isinstance(r.get('fiscalYear'),int) and r.get('fiscalQuarter') in (1,2,3,4)]
    newest = max(ordinals,default=0)
    target_rows = [r for r in trusted if isinstance(r.get('fiscalYear'),int)
                   and r.get('fiscalQuarter') in (1,2,3,4)
                   and newest-4 <= r['fiscalYear']*4+r['fiscalQuarter'] <= newest]
    unknown_latest = [c for c in active if (c.get('periodEnd') or c.get('filingDate') or '9999-12-31') >= latest.get('periodEnd','')]
    state = 'pending_discovery' if not success or source['stale'] or source['state'] in ('failed','deferred','identity_pending') else 'pending_identity' if unknown_latest or not trusted else 'identified'
    if company.get('tickerIdentityStatus') in ('historical_alias', 'unconfirmed'):
        state = 'issuer_identity_pending'
    result['latestQuarter'] = {'state':state, 'periodEnd':latest.get('periodEnd'),
        'fiscalYear':latest.get('fiscalYear'), 'fiscalQuarter':latest.get('fiscalQuarter'),
        'releaseDate':latest.get('date'), 'sourceUrl':latest.get('releaseSourceUrl'),
        'discoveryAsOf':success, 'metricsComplete':state=='identified' and bool(latest) and all(metric_verified(latest,f) for f in ('epsGaapDiluted','revenue'))}
    gaps = []
    for error in result.get('sourceErrors',[]):
        gaps.append({'field':'sourceAccess','reason':'official_source_unavailable','sourceUrl':error['sourceUrl'],
                     'stage':error['stage'],'nextAction':'retry_official_source'})
    for candidate in active:
        gaps.append({'key':candidate['key'], 'periodEnd':candidate.get('periodEnd'), 'field':'quarterIdentity',
                     'reason':candidate['reason'], 'sourceUrl':candidate['sourceUrl'], 'nextAction':'review_official_announcement'})
    for row in rows:
        if row.get('verificationStatus') != 'official_verified':
            gaps.append({'periodEnd':row.get('periodEnd'), 'field':'quarterIdentity',
                         'reason':'quarter_identity_unconfirmed','sourceUrl':row.get('secUrl') or row.get('releaseSourceUrl') or source.get('sourceUrl'),
                         'nextAction':'find_original_official_release'})
            continue
        for field, state_key, source_key in [('epsGaapDiluted','epsVerificationStatus','epsSourceUrl'),('revenue','revenueVerificationStatus','revenueSourceUrl')]:
            if not metric_verified(row, field):
                reason = 'official_value_conflict' if row.get(state_key)=='conflict' else 'quarterly_metric_not_located'
                gaps.append({'periodEnd':row['periodEnd'], 'fiscalYear':row.get('fiscalYear'), 'fiscalQuarter':row.get('fiscalQuarter'),
                    'field':field, 'reason':reason, 'sourceUrl':row.get(source_key) or row.get('metricSourceUrl') or row.get('releaseSourceUrl'),
                    'nextAction':'resolve_conflicting_official_values' if reason=='official_value_conflict' else 'inspect_official_statement_or_supplement'})
    if len(target_rows) < 5:
        gaps.append({'field':'fiveQuarterHistory','reason':'insufficient_verified_history','missingPeriods':5-len(target_rows),
                     'sourceUrl':source.get('sourceUrl'), 'nextAction':'extend_official_submission_history'})
    if source['stale']:
        gaps.append({'field':'latestDiscovery','reason':'successful_discovery_older_than_30_hours' if success else 'official_discovery_not_completed',
                     'sourceUrl':source.get('sourceUrl'), 'nextAction':'resume_official_discovery'})
    if state == 'issuer_identity_pending':
        gaps.append({'field':'issuerIdentity','reason':'historical_or_unconfirmed_ticker',
                     'sourceUrl':source.get('sourceUrl'),'nextAction':'confirm_current_company_and_ticker'})
    result['gaps'] = gaps
    result['coverage'] = {'targetQuarters':5, 'verifiedQuarters':len(target_rows), 'storedVerifiedQuarters':len(trusted),
        'verifiedEps':sum(metric_verified(r,'epsGaapDiluted') for r in target_rows),
        'verifiedRevenue':sum(metric_verified(r,'revenue') for r in target_rows),
        'completeMetrics':sum(all(metric_verified(r,f) for f in ('epsGaapDiluted','revenue')) for r in target_rows)}
    result['recordCount'], result['officialQuarterCount'] = len(rows), len(trusted)
    result['metricsVerifiedQuarterCount'] = result['coverage']['completeMetrics']
    result['latestStoredDate'] = rows[0].get('date') if rows else None
    result['latestStoredOfficial'] = bool(rows and rows[0].get('verificationStatus')=='official_verified')
    result['officialSourceUrl'] = latest.get('releaseSourceUrl')
    return result
