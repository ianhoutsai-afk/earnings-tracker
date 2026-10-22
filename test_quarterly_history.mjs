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
  assert.equal(selectHistory('MSFT', rows), rows);
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
  assert.deepEqual(quarterEstimates({ ...row, ticker: 'MSFT' }), { eps: '$15.91', revenue: '$253.49B' });
});

test('an official call is distinct from an estimated release and expires on the US calendar', () => {
  const row = { reportDate: '2026-11-17', reportDateSource: 'third_party_estimate',
    nextEarningsCallDate: '2026-11-17', nextEarningsCallSourceUrl: 'https://investor.nvidia.com/official' };
  assert.equal(nextNvdaEvent(row, '2026-10-22').kind, 'call');
  assert.deepEqual(nextNvdaEvent(row, '2026-11-18'), { date: null, kind: 'unannounced', url: null });
});
