import test from 'node:test';
import assert from 'node:assert/strict';
import {quarterlyMetrics,coverageSummary,sourceIsStale} from './quarterly-history.mjs';

test('conflicting EPS is suppressed independently of verified revenue',()=>{
  const row={verificationStatus:'official_verified',periodScope:'quarter',currency:'USD',
    epsBasis:'GAAP diluted',eps_reported:'$1.50',revenue_reported:'$1B',epsVerificationStatus:'conflict'};
  assert.deepEqual(quarterlyMetrics(row),{eps:'-',revenue:'$1B'});
});
test('freshness ages in the browser without a new publication',()=>{
  assert.equal(sourceIsStale({lastSuccessfulDiscoveryAt:'2026-10-24T00:00:00Z'},new Date('2026-10-25T06:00:01Z')),true);
  assert.equal(sourceIsStale({lastSuccessfulDiscoveryAt:'2026-10-24T00:00:00Z'},new Date('2026-10-24T23:00:00Z')),false);
});
test('source, latest identity and metric coverage are separate counters',()=>{
  const statuses={A:{sourceCheck:{state:'checked',lastSuccessfulDiscoveryAt:'2026-10-24T00:00:00Z'},
    latestQuarter:{state:'pending_identity'},coverage:{verifiedQuarters:5,completeMetrics:4}},
    B:{sourceCheck:{state:'failed'},latestQuarter:{state:'pending_discovery'},coverage:{verifiedQuarters:3,completeMetrics:2}}};
  const summary=coverageSummary([{ticker:'A'},{ticker:'B'}],statuses,new Date('2026-10-24T01:00:00Z'));
  assert.deepEqual(summary,{count:2,failed:1,stale:1,latestPending:2,fiveVerified:1,fiveComplete:0});
});
