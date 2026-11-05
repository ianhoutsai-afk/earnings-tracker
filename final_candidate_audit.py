"""Report exact retained-value and quarter-window changes before publication."""
import json,subprocess
from pathlib import Path
def prior(name):
 return json.loads(subprocess.check_output(['git','show','origin/main:'+name],text=True))
def current(name):return json.loads(Path(name).read_text())
before=prior('official_history.json');after=current('official_history.json')
old={(r['ticker'],r['periodEnd']):r for r in before};new={(r['ticker'],r['periodEnd']):r for r in after}
bh=prior('historical_data.json');ah=current('historical_data.json');status=current('history_status.json')
assert set(bh)==set(ah),'Company universe changed'
fills=[];replacements=[];lost=[];advances=[];date_changes=[]
for key,row in new.items():
 prev=old.get(key,{})
 for field,source in [('revenue','revenueSourceUrl'),('epsGaapDiluted','epsSourceUrl')]:
  if prev.get(field) is not None:
   if row.get(field) is None:lost.append({'ticker':key[0],'periodEnd':key[1],'field':field})
   elif row[field]!=prev[field]:replacements.append({'ticker':key[0],'periodEnd':key[1],'field':field,'before':prev[field],'after':row[field],'sourceUrl':row.get(source) or row.get('metricSourceUrl')})
  elif row.get(field) is not None:
   fills.append({'ticker':key[0],'periodEnd':key[1],'field':field,'value':row[field],'sourceUrl':row.get(source) or row.get('metricSourceUrl') or row['releaseSourceUrl'],'newPeriod':key not in old})
 if prev.get('date') and row['date']!=prev['date']:date_changes.append({'ticker':key[0],'periodEnd':key[1],'before':prev['date'],'after':row['date'],'sourceUrl':row['releaseSourceUrl']})
for ticker,rows in ah.items():
 assert len(rows)<=5 and status[ticker]['recordCount']==len(rows),ticker
 verified=[r for r in rows if r.get('verificationStatus')=='official_verified']
 assert len({r['periodEnd'] for r in verified})==len(verified),ticker+' duplicate periods'
 old_end=max((r.get('periodEnd','') for r in bh[ticker] if r.get('verificationStatus')=='official_verified'),default='')
 end=max((r['periodEnd'] for r in verified),default='')
 assert end>=old_end,ticker+' regressed latest official period'
 if end>old_end:
  row=next(r for r in verified if r['periodEnd']==end)
  advances.append({'ticker':ticker,'before':old_end or None,'after':end,'date':row['date'],'sourceUrl':row['releaseSourceUrl']})
assert not lost,'Previously retained numeric values were lost'
report={'baselineMainCommit':subprocess.check_output(['git','rev-parse','origin/main'],text=True).strip(),'baseline':prior('official_scan_state.json'),'candidate':current('official_scan_state.json'),'populatedFields':fills,'retainedValueReplacements':replacements,'lostRetainedValues':lost,'latestPeriodAdvances':advances,'releaseDateChanges':date_changes,'newOfficialPeriods':[list(k) for k in new.keys()-old.keys()],'removedOldOfficialPeriods':[list(k) for k in old.keys()-new.keys()],'remainingMetricGaps':2514-current('official_scan_state.json')['completeMetricQuarters'],'unverifiedLatestTickers':[t for t,rs in ah.items() if rs and rs[0].get('verificationStatus')!='official_verified']}
Path('docs/quarterly-completion-final-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:len(report[k]) for k in ('populatedFields','retainedValueReplacements','latestPeriodAdvances','unverifiedLatestTickers')}))
