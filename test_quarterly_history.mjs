import test from 'node:test';
import assert from 'node:assert/strict';
import { selectHistory, fiscalQuarterLabel, calendarCountdown, quarterEstimates, nextNvdaEvent } from './quarterly-history.mjs';

test('NVDA shows five distinct periods newest first while other companies keep their history', () => {
  const rows = [
    { periodEnd: '2025-04-27', quarter: '2026 Q1' },
    { periodEnd: '2025-07-27', quarter: '2026 Q2' },
    { periodEnd: '2025-10-26', quarter: '2026 Q3' },
    { periodEnd: '2026-01-25', quarter: '2026 Q4' },
    { periodEnd: '2026-04-26', quarter: '2027 Q1' },
    { periodEnd: '2026-07-26', quarter: '2027 Q2' },
  ];
  assert.deepEqual(selectHistory('NVDA', rows).map(row => row.quarter),
    ['2027 Q2', '2027 Q1', '2026 Q4', '2026 Q3', '2026 Q2']);
  assert.equal(rows.length, 6);
  assert.deepEqual(selectHistory('MSFT', rows), selectHistory('NVDA', rows));
  assert.equal(selectHistory('NVDA', [...rows, { ...rows[5] }]).length, 5);
});

test('company fiscal labels do not use the publication year', () => {
  assert.equal(fiscalQuarterLabel({ fiscalYear: 2027, fiscalQuarter: 2, date: '2026-08-26' }), 'FY2027 Q2');
});

test('countdown uses the New York calendar across Asian midnight and DST', () => {
  assert.equal(calendarCountdown('2026-10-22', new Date('2026-10-22T17:00:00Z')), 0);
  assert.equal(calendarCountdown('2026-11-02', new Date('2026-11-01T04:30:00Z')), 1);
});

test('NVDA hides estimates lacking a quarterly basis without affecting other companies', () => {
  const row = { ticker: 'NVDA', eps: '$15.91', revenue: '$253.49B' };
  assert.deepEqual(quarterEstimates(row), { eps: '-', revenue: '-' });
  assert.deepEqual(quarterEstimates({ ...row, ticker: 'MSFT' }), { eps: '-', revenue: '-' });
});

test('an official call is distinct from an estimated release and expires on the US calendar', () => {
  const row = { reportDate: '2026-11-17', reportDateSource: 'third_party_estimate',
    nextEarningsCallDate: '2026-11-17', nextEarningsCallSourceUrl: 'https://investor.nvidia.com/official' };
  assert.equal(nextNvdaEvent(row, '2026-10-22').kind, 'call');
  assert.deepEqual(nextNvdaEvent(row, '2026-11-18'), { date: null, kind: 'unannounced', url: null });
});

test('all companies now use the same five-quarter window and leave source arrays intact', () => {
  const rows=Array.from({length:6},(_,i)=>({date:`2026-0${i+1}-15`,quarter:`legacy-${i}`}));
  for(const ticker of ['AAPL','JPM','ACN','GOOGL','NEW']) {
    const result=selectHistory(ticker,rows);
    assert.equal(result.length,5);
    assert.equal(result[0].date,'2026-06-15');
    assert.equal(rows.length,6);
  }
});

test('legacy FY and legacy dates never masquerade as verified Q4 and release dates', () => {
  assert.equal(fiscalQuarterLabel({quarter:'2025 FY'}),null);
  assert.equal(fiscalQuarterLabel({quarter:'2026 Q2',verificationStatus:'legacy_unverified'}),null);
});

test('unscoped estimates are suppressed for every company', () => {
  assert.deepEqual(quarterEstimates({ticker:'AAPL',eps:'$9.57',revenue:'$451.44B'}),{eps:'-',revenue:'-'});
});

test('repeated unverified labels cannot delete a distinct stored period',()=>{
  assert.equal(selectHistory('JBL',[{date:'2026-01-10',quarter:'2026 Q1'},{date:'2026-04-10',quarter:'2026 Q1'}]).length,2);
});

test('five verified periods cannot be displaced by an uncertain later legacy date',()=>{
 const rows=Array.from({length:5},(_,i)=>({date:`2026-0${i+1}-15`,periodEnd:`2026-0${i+1}-01`,periodScope:'quarter',verificationStatus:'official_verified'}));
 rows.push({date:'2026-06-15',quarter:'legacy pending'});
 assert.ok(selectHistory('ABC',rows).every(r=>r.verificationStatus==='official_verified'));
});
