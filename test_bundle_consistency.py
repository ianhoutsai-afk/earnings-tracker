import json
import tempfile
import unittest
from pathlib import Path
from datetime import date

class BundleConsistencyTests(unittest.TestCase):
    def setUp(self):
        import test_official_sync as fixture
        from official_sync import sync_all
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        fixture.OfficialSyncTests().setup_root(self.root)
        sync_all(self.root,fixture.TODAY,fetch=fixture.fetch,full=True)

    def validate(self):
        from validate_quarterly_data import validate
        return validate(self.root,date(2026,10,22))

    def test_malformed_mapping_is_rejected_before_publication(self):
        (self.root/'sp500_mapping.json').write_text('{invalid')
        with self.assertRaises(ValueError):self.validate()

    def test_summary_cannot_claim_more_verified_quarters_than_history(self):
        p=self.root/'official_scan_state.json';s=json.loads(p.read_text());s['officialQuarters']+=1;p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError,'summary'):self.validate()

    def test_field_coverage_cannot_count_conflicted_values_as_verified(self):
        p=self.root/'history_status.json';s=json.loads(p.read_text());s['ABC']['coverage']['verifiedEps']+=1;p.write_text(json.dumps(s))
        with self.assertRaisesRegex(ValueError,'coverage'):self.validate()

if __name__=='__main__':unittest.main()
