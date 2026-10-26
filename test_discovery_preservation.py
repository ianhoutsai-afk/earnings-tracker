import json
import tempfile
import unittest
from pathlib import Path
from datetime import date
from verified_history import refresh_site_data


class DiscoveryPreservationTests(unittest.TestCase):
    def test_daily_date_discovery_preserves_official_progress_and_freshness(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            prior={'ABC':{'status':'official_parse_pending','sourceCheck':{'lastSuccessfulDiscoveryAt':'2026-10-23T00:00:00Z'},
                'backfillProgress':{'auditAsOf':'2026-10-22T00:00:00Z','completedAccessions':['original']},
                'candidates':[{'key':'official-candidate'}]}}
            for name,value in {'data.json':[{'ticker':'ABC'}],'historical_data.json':{'ABC':[]},
                'official_history.json':[],'history_status.json':prior}.items():(root/name).write_text(json.dumps(value))
            refresh_site_data(root,date(2026,10,24),scan=True,fetch=lambda _:None,sleep=lambda _:None)
            result=json.loads((root/'history_status.json').read_text())['ABC']
            for key in ('sourceCheck','backfillProgress','candidates'):
                self.assertEqual(result[key],prior['ABC'][key])


if __name__=='__main__':unittest.main()
