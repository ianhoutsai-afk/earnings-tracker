"""Only an explicit scheduled financial-results release is a future earnings date."""
import unittest
from datetime import date
TODAY=date(2026,10,29)

class ExpectedReleaseTests(unittest.TestCase):
    def parse(self, text):
        from official_events import parse_expected_release
        return parse_expected_release('<html><body><p>'+text+'</p></body></html>',TODAY)

    def test_explicit_release_date_and_after_close_timing(self):
        result=self.parse('Example will post its financial results for the third quarter of 2026 after market close on Wednesday, November 4, 2026.')
        self.assertEqual(result,{'date':'2026-11-04','bmo_amc':'AMC','eventType':'earnings_release'})

    def test_call_date_does_not_become_release_date(self):
        self.assertIsNone(self.parse('Example will host its third quarter 2026 earnings conference call on November 4, 2026.'))

    def test_past_and_ambiguous_dates_remain_unknown(self):
        self.assertIsNone(self.parse('Example will release financial results on October 21, 2026.'))
        self.assertIsNone(self.parse('Example will release financial results on November 4, 2026. Example will release financial results on November 5, 2026.'))

    def test_today_and_unconfirmed_timing_are_supported(self):
        result=self.parse('Example will report financial results on October 29, 2026.')
        self.assertEqual(result['date'],'2026-10-29')
        self.assertIsNone(result['bmo_amc'])

    def test_before_open_and_different_following_call_date(self):
        result=self.parse('Example will release its financial results before the market opens on November 4, 2026. A conference call will be held on November 5, 2026.')
        self.assertEqual(result['date'],'2026-11-04')
        self.assertEqual(result['bmo_amc'],'BMO')

    def test_generic_product_release_and_preliminary_metrics_are_excluded(self):
        for text in ['Example will release a product and discuss financial results on November 4, 2026.','Example will report preliminary financial results on November 4, 2026.']:
            self.assertIsNone(self.parse(text))

    def test_same_sentence_call_date_is_not_attached_to_release_without_its_own_date(self):
        self.assertIsNone(self.parse('Example will release financial results and hold a conference call on November 4, 2026.'))

    def test_sync_records_official_event_source_without_adding_future_history(self):
        import copy
        from official_sync import check_issuer
        from test_official_sync import SUBMISSIONS,fetch
        sub=copy.deepcopy(SUBMISSIONS)
        primary='<h2>Item 2.02 Results of Operations</h2><a href="ex991.htm">99.1</a>'
        release='<h1>Production update</h1><p>Example will post its financial results for the third quarter of 2026 after market close on November 4, 2026.</p>'
        def source(url):
            if url.endswith('results.htm'):return primary
            if url.endswith('ex991.htm'):return release
            return fetch(url)
        rows,details=check_issuer('0000000001',sub,source,TODAY)
        self.assertEqual(rows,[])
        self.assertEqual(details['nextEarningsEvent']['date'],'2026-11-04')
        self.assertTrue(details['nextEarningsEvent']['sourceUrl'].endswith('/ex991.htm'))
