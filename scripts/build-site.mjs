import { mkdir, readFile, writeFile, copyFile } from 'node:fs/promises';
import { join } from 'node:path';
import { selectHistory } from '../quarterly-history.mjs';

const [root = '.', output = '_site'] = process.argv.slice(2);
const readJson = async name => JSON.parse(await readFile(join(root, name), 'utf8'));
const writeJson = (name, value) => writeFile(join(output, name), JSON.stringify(value));

const [companies, history, status, mapping, scan] = await Promise.all(
  ['data.json', 'historical_data.json', 'history_status.json', 'sp500_mapping.json', 'official_scan_state.json'].map(readJson)
);

await mkdir(join(output, 'company-history'), { recursive: true });
const summarized = await Promise.all(companies.map(async company => {
  const { ticker } = company;
  if (!/^[A-Z0-9.-]+$/.test(ticker)) throw new Error(`Invalid ticker: ${ticker}`);
  const selected = selectHistory(ticker, history[ticker]);
  await writeJson(`company-history/${ticker}.json`, { history: selected, status: status[ticker] });
  const latest = selected[0];
  const latestRecord = latest && Object.fromEntries([
    'date', 'quarter', 'verificationStatus', 'periodScope', 'fiscalYear',
    'fiscalQuarter', 'currency', 'epsBasis', 'eps_reported', 'revenue_reported',
  ].map(key => [key, latest[key]]));
  return {
    ...company,
    sector: mapping[ticker]?.sector || null,
    latestRecord: latestRecord || null,
    latestVerifiedReleaseDate: selected.find(row => row.verificationStatus === 'official_verified')?.date || null,
  };
}));

const health = {
  verified: scan.officialQuarters,
  failed: scan.sourceFailedCompanies,
  pending: scan.pendingCompanies,
};
await writeJson('site-summary.json', { companies: summarized, health });
for (const name of ['data.json', 'historical_data.json', 'history_status.json', 'official_scan_state.json', 'quarterly-history.mjs', 'i18n.mjs']) {
  await copyFile(join(root, name), join(output, name));
}

const html = await readFile(join(root, 'index.html'), 'utf8');
const sourceStyles = /<!-- tailwind-source -->[\s\S]*?<!-- \/tailwind-source -->/;
if (!sourceStyles.test(html)) throw new Error('Tailwind source block missing');
await writeFile(join(output, 'index.html'), html.replace(sourceStyles, '<link rel="stylesheet" href="./tracker.css">'));
