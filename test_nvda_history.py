import copy
from quarterly_policy import retain_history
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from urllib.error import HTTPError

from verified_history import apply_official_records


FIXTURES = Path(__file__).parent / 'tests' / 'fixtures' / 'nvda'
PREFIX = 'https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-'
RELEASES = [
    (2026, 2, '2025-07-27', '2025-08-27', 1.08, 46743000000, 'second-quarter-fiscal-2026'),
    (2026, 3, '2025-10-26', '2025-11-19', 1.30, 57006000000, 'third-quarter-fiscal-2026'),
    (2026, 4, '2026-01-25', '2026-02-25', 1.76, 68127000000, 'fourth-quarter-and-fiscal-2026'),
    (2027, 1, '2026-04-26', '2026-05-20', 2.39, 81615000000, 'first-quarter-fiscal-2027'),
    (2027, 2, '2026-07-26', '2026-08-26', 2.46, 96221000000, 'second-quarter-fiscal-2027'),
]


def reviewed_records():
    return [dict(ticker='NVDA', fiscalYear=fy, fiscalQuarter=q, periodEnd=end,
                 date=released, periodScope='quarter', epsGaapDiluted=eps,
                 epsBasis='GAAP diluted', revenue=revenue, currency='USD',
                 releaseSourceUrl=PREFIX + slug, verifiedAt='2026-10-22')
            for fy, q, end, released, eps, revenue, slug in RELEASES]


class NvdaRollingHistoryTests(unittest.TestCase):
    def setUp(self):
        self.companies = [{'ticker': 'NVDA'}, {'ticker': 'MSFT'}]
        self.history = {
            'NVDA': [{'date': '2025-05-28', 'quarter': '2026 Q1', 'eps_reported': '$0.81'}],
            'MSFT': [{'date': f'2025-0{n}-01', 'quarter': f'old-{n}'} for n in range(1, 7)],
        }

    def test_official_merge_keeps_only_five_nvda_quarters_newest_first(self):
        before = copy.deepcopy(self.history)
        history, _ = apply_official_records(self.companies, self.history, reviewed_records(), date(2026, 10, 22))
        self.assertEqual(len(history['NVDA']), 5)
        self.assertEqual([row['quarter'] for row in history['NVDA']],
                         ['2027 Q2', '2027 Q1', '2026 Q4', '2026 Q3', '2026 Q2'])
        self.assertEqual(history['MSFT'], retain_history(before)['MSFT'])
        self.assertEqual(self.history, before)

    def test_new_quarter_evicts_one_old_quarter_and_old_seed_cannot_resurrect_it(self):
        history, _ = apply_official_records(self.companies, self.history, reviewed_records(), date(2026, 10, 22))
        # Synthetic future-quarter fixture, not a claim of published actuals.
        next_quarter = {**reviewed_records()[-1], 'fiscalQuarter': 3,
                        'periodEnd': '2026-10-25', 'date': '2026-11-17',
                        'verifiedAt': '2026-11-18', 'epsGaapDiluted': None, 'revenue': None}
        updated, _ = apply_official_records(self.companies, history, [next_quarter], date(2026, 11, 18))
        self.assertEqual([row['quarter'] for row in updated['NVDA']],
                         ['2027 Q3', '2027 Q2', '2027 Q1', '2026 Q4', '2026 Q3'])
        replayed, _ = apply_official_records(self.companies, updated, reviewed_records(), date(2026, 11, 18))
        self.assertEqual(replayed, updated)

    def test_same_period_revision_keeps_original_release_date_and_five_positions(self):
        history, _ = apply_official_records(self.companies, self.history, reviewed_records(), date(2026, 10, 22))
        revision = {**reviewed_records()[1], 'date': '2026-10-20', 'verifiedAt': '2026-10-22', 'epsGaapDiluted': 1.31}
        updated, _ = apply_official_records(self.companies, history, [revision], date(2026, 10, 22))
        self.assertEqual(len(updated['NVDA']), 5)
        row = next(row for row in updated['NVDA'] if row['periodEnd'] == '2025-10-26')
        self.assertEqual(row['date'], '2025-11-19')
        self.assertEqual(row['eps_reported'], '$1.31')
        self.assertEqual(updated['NVDA'][0]['quarter'], '2027 Q2')

    def test_invalid_future_release_does_not_change_history(self):
        original = copy.deepcopy(self.history)
        future = {**reviewed_records()[-1], 'date': '2026-11-17'}
        with self.assertRaises(ValueError):
            apply_official_records(self.companies, self.history, [future], date(2026, 10, 22))
        self.assertEqual(self.history, original)

    def test_old_seed_does_not_overwrite_a_later_reviewed_revision(self):
        history, _ = apply_official_records(self.companies, self.history, reviewed_records(), date(2026, 10, 22))
        revision = {**reviewed_records()[1], 'verifiedAt': '2026-10-23', 'epsGaapDiluted': 1.31}
        updated, _ = apply_official_records(self.companies, history, [revision], date(2026, 10, 23))
        replayed, _ = apply_official_records(self.companies, updated, reviewed_records(), date(2026, 10, 23))
        self.assertEqual(replayed, updated)

    def test_missing_reparsed_metrics_cannot_erase_previously_verified_values(self):
        history, _ = apply_official_records(self.companies, self.history, reviewed_records(), date(2026, 10, 22))
        partial = {**reviewed_records()[-1], 'epsGaapDiluted': None, 'revenue': None}
        updated, _ = apply_official_records(self.companies, history, [partial], date(2026, 10, 22))
        self.assertEqual(updated['NVDA'][0]['eps_reported'], '$2.46')
        self.assertEqual(updated['NVDA'][0]['revenue_reported'], '$96.22B')
        self.assertEqual(updated['NVDA'][0]['epsBasis'], 'GAAP diluted')


class NvdaOfficialSourceTests(unittest.TestCase):
    def test_transient_newsroom_failure_is_retried_before_marking_source_failed(self):
        from unittest.mock import patch
        from official_sync import sync_all
        from nvda_history import FEED_URL,release_url
        records=reviewed_records();companies=[{'ticker':'NVDA'}]
        history,_=apply_official_records(companies,{'NVDA':[]},records,date(2026,10,22))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,value in {'data.json':companies,'historical_data.json':history,
                               'official_history.json':records,'history_status.json':{},
                               'sp500_mapping.json':{'NVDA':{'cik':'0001045810'}}}.items():
                (root/name).write_text(json.dumps(value))
            attempts=[]
            def source(url):
                attempts.append(url)
                if url==FEED_URL and attempts.count(url)==1:raise OSError('temporary transport failure')
                if url==FEED_URL:return '<rss><channel/></rss>'
                if url==release_url(2027,2):return (FIXTURES/'fy2027-q2.html').read_text()
                if url==release_url(2027,3):raise HTTPError(url,404,'not published',{},None)
                raise AssertionError(url)
            with patch('nvda_history.fetch_official',side_effect=source),patch('official_sync.time.sleep'):
                result=sync_all(root,today=date(2026,10,22),fetch=lambda url:None,full=True)
            self.assertTrue(result['healthy'])
            self.assertEqual(attempts.count(FEED_URL),2)
            self.assertEqual(attempts.count(release_url(2027,3)),1)

    def test_sync_preserves_metric_sources_when_a_reparse_has_no_metrics(self):
        from nvda_history import sync_nvda, FEED_URL, release_url
        from lxml import html
        records = reviewed_records()
        source_url = 'https://nvidianews.nvidia.com/news/quarterly-statements'
        records[-1]['metricSourceUrl'] = source_url
        companies = [{'ticker': 'NVDA'}]
        history, _ = apply_official_records(companies, {'NVDA': []}, records, date(2026, 10, 22))
        tree = html.fromstring((FIXTURES / 'fy2027-q2.html').read_text())
        for table in tree.xpath('//table'):
            table.getparent().remove(table)
        def fetch(url):
            if url == FEED_URL:
                return '<rss><channel/></rss>'
            if url == release_url(2027, 2):
                return html.tostring(tree, encoding='unicode')
            raise HTTPError(url, 404, 'not published', {}, None)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in {'data.json': companies, 'historical_data.json': history,
                                'official_history.json': records, 'history_status.json': {}}.items():
                (root / name).write_text(json.dumps(value))
            sync_nvda(root, today=date(2026, 10, 22), fetch=fetch)
            latest = json.loads((root / 'historical_data.json').read_text())['NVDA'][0]
            manifest = json.loads((root / 'official_history.json').read_text())
            self.assertEqual(latest['eps_reported'], '$2.46')
            self.assertEqual(latest['metricSourceUrl'], source_url)
            self.assertEqual(next(row for row in manifest if row['periodEnd'] == '2026-07-26')['metricSourceUrl'], source_url)

    def test_successful_official_sync_changes_only_nvda_and_is_idempotent(self):
        from nvda_history import sync_nvda, FEED_URL, release_url
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            msft = {'ticker': 'MSFT', 'reportDate': '2026-10-28', 'eps': '$1', 'revenue': '$2B'}
            msft_history = [{'date': '2026-07-29', 'quarter': '2026 Q4'}]
            msft_status = {'status': 'pending_official', 'checkedAt': 'unchanged'}
            documents = {
                'data.json': [{'ticker': 'NVDA', 'eps': '$15.91', 'revenue': '$253.49B'}, msft],
                'historical_data.json': {'NVDA': [{'date': '2025-05-28', 'quarter': '2026 Q1'}], 'MSFT': msft_history},
                'official_history.json': reviewed_records(),
                'history_status.json': {'MSFT': msft_status},
            }
            for name, value in documents.items():
                (root / name).write_text(json.dumps(value))
            def fetch(url):
                if url == FEED_URL:
                    return '<rss><channel/></rss>'
                if url == release_url(2027, 2):
                    return (FIXTURES / 'fy2027-q2.html').read_text()
                if url == release_url(2027, 3):
                    return '<html><title>News Archive | NVIDIA Newsroom</title><h1>News Archive</h1></html>'
                raise AssertionError(f'Unexpected request: {url}')
            sync_nvda(root, today=date(2026, 10, 22), fetch=fetch)
            companies = json.loads((root / 'data.json').read_text())
            history = json.loads((root / 'historical_data.json').read_text())
            self.assertEqual(companies[1], msft)
            self.assertEqual(history['MSFT'], retain_history({'MSFT': msft_history})['MSFT'])
            self.assertEqual(json.loads((root / 'history_status.json').read_text())['MSFT'], msft_status)
            self.assertEqual(companies[0]['eps'], '-')
            self.assertEqual(companies[0]['latestPublishedQuarter'], '2027 Q2')
            self.assertEqual([row['quarter'] for row in history['NVDA']],
                             ['2027 Q2', '2027 Q1', '2026 Q4', '2026 Q3', '2026 Q2'])
            sync_nvda(root, today=date(2026, 10, 22), fetch=fetch)
            self.assertEqual(json.loads((root / 'historical_data.json').read_text()), history)

    def test_real_official_quarterly_tables_parse_gaap_instead_of_adjusted_or_annual(self):
        from nvda_history import parse_release
        for expected in reviewed_records():
            tag = f"fy{expected['fiscalYear']}-q{expected['fiscalQuarter']}.html"
            with self.subTest(tag=tag):
                record = parse_release((FIXTURES / tag).read_text(), expected['releaseSourceUrl'], date(2026, 10, 22))
                for field in ('ticker', 'date', 'periodEnd', 'fiscalYear', 'fiscalQuarter',
                              'epsGaapDiluted', 'revenue', 'epsBasis', 'periodScope'):
                    self.assertEqual(record[field], expected[field], field)

    def test_parser_rejects_future_releases_and_unofficial_hosts(self):
        from nvda_history import parse_release
        source = (FIXTURES / 'fy2027-q2.html').read_text()
        with self.assertRaises(ValueError):
            parse_release(source, PREFIX + 'second-quarter-fiscal-2027', date(2026, 8, 25))
        with self.assertRaises(ValueError):
            parse_release(source, 'https://example.com/copied-release', date(2026, 10, 22))

    def test_blank_current_quarter_cells_never_fall_back_to_comparison_values(self):
        from nvda_history import parse_release
        from lxml import html
        tree = html.fromstring((FIXTURES / 'fy2027-q2.html').read_text())
        table = tree.xpath('//table')[0]
        for tr in table.xpath('.//tr'):
            cells = tr.xpath('./td|./th')
            if cells and cells[0].text_content().strip() in ('Revenue', 'Diluted earnings per share'):
                for child in list(cells[1]):
                    cells[1].remove(child)
                cells[1].text = ''
        record = parse_release(html.tostring(tree, encoding='unicode'), PREFIX + 'second-quarter-fiscal-2027', date(2026, 10, 22))
        self.assertIsNone(record['epsGaapDiluted'])
        self.assertIsNone(record['revenue'])

    def test_metrics_follow_the_matching_quarter_column_not_the_first_number(self):
        from nvda_history import parse_release
        source = '''<h1 class="article-title">NVIDIA Announces Financial Results for Second Quarter Fiscal 2027</h1>
        <div class="article-date">August 26, 2026</div><div class="article-body">
        <p>The second quarter ended July 26, 2026.</p><table><tr><td>GAAP</td></tr>
        <tr><td>($ in millions, except per share)</td><td>Q1 FY27</td><td>Q2 FY27</td></tr>
        <tr><td>Revenue</td><td>$81,615</td><td>$96,221</td></tr>
        <tr><td>Diluted earnings per share</td><td>$2.39</td><td>$2.46</td></tr></table></div>'''
        record = parse_release(source, PREFIX + 'second-quarter-fiscal-2027', date(2026, 10, 22))
        self.assertEqual(record['epsGaapDiluted'], 2.46)
        self.assertEqual(record['revenue'], 96221000000)

    def test_sync_failure_keeps_all_existing_files_byte_identical(self):
        from nvda_history import sync_nvda
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            documents = {'data.json': [{'ticker': 'NVDA'}], 'historical_data.json': {'NVDA': []},
                         'official_history.json': reviewed_records(), 'history_status.json': {}}
            for name, value in documents.items():
                (root / name).write_text(json.dumps(value))
            before = {name: (root / name).read_bytes() for name in documents}
            def failure(_):
                raise RuntimeError('source unavailable')
            with self.assertRaises(RuntimeError):
                sync_nvda(root, today=date(2026, 10, 22), fetch=failure)
            self.assertEqual(before, {name: (root / name).read_bytes() for name in documents})


if __name__ == '__main__':
    unittest.main()
