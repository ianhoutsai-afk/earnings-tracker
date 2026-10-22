// Pilot rules apply only to NVDA; other companies retain their existing behavior.
export function selectHistory(ticker, rows) {
  if (ticker !== 'NVDA') return rows;
  const unique = new Map();
  for (const row of rows) {
    const key = row.periodEnd || row.quarter || row.date;
    if (!unique.has(key)) unique.set(key, row);
  }
  return [...unique.values()]
    .sort((a, b) => (b.periodEnd || b.date || '').localeCompare(a.periodEnd || a.date || ''))
    .slice(0, 5);
}

export function fiscalQuarterLabel(row) {
  return `FY${row.fiscalYear} Q${row.fiscalQuarter}`;
}

export function newYorkDate(now = new Date()) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now);
  const value = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${value.year}-${value.month}-${value.day}`;
}

export function calendarCountdown(date, now = new Date()) {
  if (!date) return null;
  return Math.round((Date.parse(`${date}T00:00:00Z`) - Date.parse(`${newYorkDate(now)}T00:00:00Z`)) / 86400000);
}

export function quarterEstimates(company) {
  return company.ticker === 'NVDA'
    ? { eps: '-', revenue: '-' }
    : { eps: company.eps || '-', revenue: company.revenue || '-' };
}

export function nextNvdaEvent(company, today = newYorkDate()) {
  if (company.nextEarningsCallDate >= today && company.nextEarningsCallSourceUrl) {
    return { date: company.nextEarningsCallDate, kind: 'call', url: company.nextEarningsCallSourceUrl };
  }
  if (company.reportDate >= today) {
    return { date: company.reportDate, kind: company.reportDateSource === 'official' ? 'official' : 'estimate', url: company.reportDateSourceUrl || null };
  }
  return { date: null, kind: 'unannounced', url: null };
}
