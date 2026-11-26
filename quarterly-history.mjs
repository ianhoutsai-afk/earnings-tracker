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

export function matchesEarningsWindow(company, window, today = newYorkDate()) {
  if (window === 'all') return true;
  const day = value => Date.parse(`${value}T00:00:00Z`) / 86400000;
  const todayDay = day(today);
  if (window === 'published') {
    const age = todayDay - day(company.latestVerifiedReleaseDate);
    return age >= 0 && age < 7;
  }
  const event = nextCompanyEvent(company, today);
  const until = day(event.date) - todayDay;
  if (window === 'today') return until === 0;
  if (window === 'thisWeek') {
    const weekday = new Date(todayDay * 86400000).getUTCDay() || 7;
    return until >= 0 && until <= 7 - weekday;
  }
  return until >= 0 && until <= (window === 'week' ? 7 : 30);
}

function numericMetric(value) {
  const text = String(value).replace(/[$,\s]/g, '');
  const match = /^([+-]?\d+(?:\.\d+)?)([KMBT]?)$/.exec(text);
  if (!match) return null;
  return Number(match[1]) * ({ '': 1, K: 1e3, M: 1e6, B: 1e9, T: 1e12 }[match[2]]);
}

export function quarterSeries(rows, metric) {
  return rows.filter(row => row.verificationStatus === 'official_verified'
    && row.periodScope === 'quarter' && fiscalQuarterLabel(row)).map(row => {
    const label = fiscalQuarterLabel(row);
    const [, year, quarter] = /^FY(\d+) Q([1-4])$/.exec(label);
    const displayValue = quarterlyMetrics(row)[metric];
    return {
      label, ordinal: Number(year) * 4 + Number(quarter),
      value: numericMetric(displayValue), displayValue,
    };
  }).sort((a, b) => a.ordinal - b.ordinal);
}

export function quarterGrowth(series) {
  const latest = series.at(-1);
  const growth = lag => {
    const previous = series.find(row => row.ordinal === latest.ordinal - lag);
    if (latest.value === null || !previous || previous.value === null || previous.value <= 0) return null;
    return latest.value / previous.value - 1;
  };
  return latest ? { qoq: growth(1), yoy: growth(4) } : { qoq: null, yoy: null };
}
