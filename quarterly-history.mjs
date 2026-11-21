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
    eps: verified && row.epsBasis === 'GAAP diluted' ? row.eps_reported || '-' : '-',
    revenue: verified ? row.revenue_reported || '-' : '-',
  };
}

export function quarterMetricSources(row, metrics = quarterlyMetrics(row)) {
  const epsUrl = metrics.eps !== '-' ? row.epsSourceUrl || row.metricSourceUrl : null;
  const revenueUrl = metrics.revenue !== '-' ? row.revenueSourceUrl || row.metricSourceUrl : null;

  if (epsUrl && revenueUrl && epsUrl !== revenueUrl) {
    return [
      {url: epsUrl, labelKey: 'history.epsSource'},
      {url: revenueUrl, labelKey: 'history.revenueSource'},
    ];
  }

  const url = epsUrl || revenueUrl;
  if (!url || url === row.releaseSourceUrl || (row.dateSource === 'sec_filing' && url === row.secUrl)) {
    return [];
  }
  const labelKey = epsUrl && revenueUrl ? 'earnings.metricSource'
    : epsUrl ? 'history.epsSource' : 'history.revenueSource';
  return [{url, labelKey}];
}

export function historyCoverage(companies, history, sourceStatus) {
  const coverage = { count: companies.length, verified: 0, failed: 0, pending: 0, filingDated: 0, recastDated: 0 };
  for (const { ticker } of companies) {
    if (['official_source_failed', 'official_mapping_missing'].includes(sourceStatus[ticker]?.status)) {
      coverage.failed += 1;
    }

    const rows = selectHistory(ticker, history[ticker] || []);
    let pending = rows.length < 5;
    for (const row of rows) {
      if (row.verificationStatus === 'official_verified') {
        coverage.verified += 1;
        if (row.dateSource === 'sec_filing') coverage.filingDated += 1;
        if (row.dateSource === 'recast') coverage.recastDated += 1;
      }
      const { eps, revenue } = quarterlyMetrics(row);
      if (eps === '-' || revenue === '-' || (row.dateSource != null && row.dateSource !== 'recast')) {
        pending = true;
      }
    }
    if (pending) coverage.pending += 1;
  }
  return coverage;
}
