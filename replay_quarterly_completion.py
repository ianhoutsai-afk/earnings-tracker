"""Replay the critical issuers after backfill without publishing any data."""
import json
import tempfile
from pathlib import Path
from official_sync import sync_all
from validate_quarterly_data import validate

root=Path('.')
tickers={'TSLA','META','MSFT'}
history=json.loads((root/'historical_data.json').read_text())
docs={
 'data.json':[r for r in json.loads((root/'data.json').read_text()) if r['ticker'] in tickers],
 'historical_data.json':{k:v for k,v in history.items() if k in tickers},
 'official_history.json':[r for r in json.loads((root/'official_history.json').read_text()) if r['ticker'] in tickers],
 'history_status.json':{k:v for k,v in json.loads((root/'history_status.json').read_text()).items() if k in tickers},
 'sp500_mapping.json':{k:v for k,v in json.loads((root/'sp500_mapping.json').read_text()).items() if k in tickers},
}
with tempfile.TemporaryDirectory() as tmp:
    stage=Path(tmp)
    for name,value in docs.items():
        (stage/name).write_text(json.dumps(value))
    result=sync_all(stage,full=True)
    assert result['sourceHealthy'], 'Critical issuer source unavailable during replay'
    validate(stage)
    after=json.loads((stage/'historical_data.json').read_text())
    assert after==docs['historical_data.json'], 'Replay changed the verified five-quarter windows'
    print(json.dumps({'idempotent':True, 'tickers':sorted(tickers),'summary':result}))
