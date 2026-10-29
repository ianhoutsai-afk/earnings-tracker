"""Check branch backfill coverage and replay without production writes."""
import json
from pathlib import Path
from official_sync import sync_all

root = Path('.')
before_history = json.loads((root/'historical_data.json').read_text())
before_status = json.loads((root/'history_status.json').read_text())
summary = sync_all(root, full=True)
print('BACKFILL_SUMMARY', json.dumps(summary), flush=True)
assert summary['sourceHealthy'], 'Official source unavailable; keep results on this branch for inspection'
after_history = json.loads((root/'historical_data.json').read_text())
after_status = json.loads((root/'history_status.json').read_text())
assert set(before_history) == set(after_history)
assert all(len(rows) <= 5 for rows in after_history.values())
assert summary['officialQuarters'] >= sum(s.get('officialQuarterCount',0) for s in before_status.values())
assert summary['completeMetricQuarters'] >= sum(s.get('metricsVerifiedQuarterCount',0) for s in before_status.values())
changes = []
for ticker in after_history:
    old = before_history[ticker]
    new = after_history[ticker]
    if old != new:
        changes.append({'ticker':ticker, 'oldLatest': old[0].get('date') if old else None, 'newLatest': new[0].get('date') if new else None, 'oldMetrics':before_status.get(ticker,{}).get('metricsVerifiedQuarterCount',0),'newMetrics':after_status[ticker]['metricsVerifiedQuarterCount']})
Path('docs/quarterly-completion-results.json').write_text(json.dumps({'summary':summary,'changes':changes},indent=2)+'\n')
print('CHANGED_TICKERS', json.dumps(changes),flush=True)
for ticker in ('TSLA','META'):
    assert after_history[ticker][0]['date'] >= '2026-10-21', ticker+' latest quarter missing after backfill'
