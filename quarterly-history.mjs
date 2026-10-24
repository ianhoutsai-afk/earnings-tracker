// Defensive five-quarter presentation, shared by every issuer.
export function selectHistory(ticker, rows) {
  const unique = new Map();
  for (const row of rows) {
    const key = row.periodEnd ? `period:${row.periodEnd}` : `legacy:${row.date}`;
    const previous = unique.get(key);
    const priority = item => `${item.verificationStatus === 'official_verified' ? 1 : 0}:${item.verifiedAt || ''}`;
    if (!previous || priority(row) > priority(previous)) unique.set(key, row);
  }
  const order=(a,b)=>(b.periodEnd || b.date || '').localeCompare(a.periodEnd || a.date || '');
  const trusted=[...unique.values()].filter(r=>r.verificationStatus==='official_verified'&&r.periodScope==='quarter'&&r.periodEnd).sort(order).slice(0,5);
  const legacy=[...unique.values()].filter(r=>r.verificationStatus!=='official_verified').sort(order);
  return [...trusted,...legacy.slice(0,5-trusted.length)].sort(order);
}

export function fiscalQuarterLabel(row) {
  if (Number.isInteger(row.fiscalYear) && [1,2,3,4].includes(row.fiscalQuarter)) {
    return `FY${row.fiscalYear} Q${row.fiscalQuarter}`;
  }
  if (row.verificationStatus === 'official_verified' && row.periodScope === 'quarter') {
    const match = /^(?:FY)?(\d{4}) Q([1-4])$/.exec(row.quarter || '');
    if (match) return `FY${match[1]} Q${match[2]}`;
  }
  return null;
}

export function newYorkDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone:'America/New_York', year:'numeric', month:'2-digit', day:'2-digit',
  }).formatToParts(now);
  const value = Object.fromEntries(parts.map(part=>[part.type,part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function calendarCountdown(date,now=new Date()) {
  if (!date) return null;
  const result = Math.round((Date.parse(`${date}T00:00:00Z`)-Date.parse(`${newYorkDate(now)}T00:00:00Z`))/86400000);
  return Number.isFinite(result) ? result : null;
}

export function quarterEstimates(company) {
  // A future provider must supply per-metric quarter, source and currency before enabling estimates.
  return {eps:'-',revenue:'-'};
}

export function nextCompanyEvent(company,today=newYorkDate()) {
  const valid = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && value >= today;
  if (valid(company.reportDate) && company.reportDateSource === 'official' && company.reportDateSourceUrl) {
    return {date:company.reportDate,kind:'official',url:company.reportDateSourceUrl};
  }
  if (valid(company.nextEarningsCallDate) && company.nextEarningsCallSourceUrl) {
    return {date:company.nextEarningsCallDate,kind:'call',url:company.nextEarningsCallSourceUrl};
  }
  if (valid(company.reportDate)) {
    return {date:company.reportDate,kind:'estimate',url:company.reportDateSourceUrl || null};
  }
  return {date:null,kind:'unannounced',url:null};
}

export const nextNvdaEvent = nextCompanyEvent;

export function quarterlyMetrics(row) {
  const verified = row.verificationStatus === 'official_verified' && row.periodScope === 'quarter' && row.currency === 'USD';
  return {
    eps: verified && !['conflict','pending'].includes(row.epsVerificationStatus) && row.epsBasis === 'GAAP diluted' ? row.eps_reported || '-' : '-',
    revenue: verified && !['conflict','pending'].includes(row.revenueVerificationStatus) ? row.revenue_reported || '-' : '-',
  };
}

export function sourceIsStale(source={},now=new Date()) {
  const success=Date.parse(source.lastSuccessfulDiscoveryAt || '');
  return !Number.isFinite(success) || now.getTime()-success>30*3600*1000;
}

export function coverageSummary(companies,statuses,now=new Date()) {
  const summary={count:companies.length,failed:0,stale:0,latestPending:0,fiveVerified:0,fiveComplete:0};
  for(const company of companies) {
    const s=statuses[company.ticker] || {};
    const stale=sourceIsStale(s.sourceCheck,now);
    summary.failed+=Number(s.sourceCheck?.state==='failed' || s.status==='official_mapping_missing');
    summary.stale+=Number(stale);
    summary.latestPending+=Number(stale || s.latestQuarter?.state!=='identified');
    summary.fiveVerified+=Number((s.coverage?.verifiedQuarters ?? s.officialQuarterCount)===5);
    summary.fiveComplete+=Number((s.coverage?.completeMetrics ?? s.metricsVerifiedQuarterCount)===5);
  }
  return summary;
}
