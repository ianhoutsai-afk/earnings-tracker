import hashlib
import json
import tempfile
import unittest
from pathlib import Path


class PagesReleaseTests(unittest.TestCase):
    def setUp(self):
        try:
            import pages_release
        except ModuleNotFoundError:
            self.fail('Exact-commit Pages release verification is not implemented')
        self.api = pages_release

    def expected(self):
        from publication import DATA_FILES
        bodies = {name: ('{"file":"' + name + '"}\n').encode() for name in DATA_FILES}
        manifest = {'sourceCommit': 'a' * 40, 'hashes': {
            name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()}}
        bodies['deployment.json'] = json.dumps(manifest).encode()
        return manifest, bodies

    def test_all_six_hashes_and_exact_commit_are_required(self):
        expected, bodies = self.expected()
        report = self.api.verify_publication('https://example.invalid/', expected,
                                             timeout=0, fetch=lambda url, **kwargs: bodies[url.rsplit('/', 1)[-1].split('?')[0]])
        self.assertTrue(report['verified'])
        self.assertEqual(len(report['matches']), 6)

    def test_one_stale_json_does_not_pass_a_successful_http_response(self):
        expected, bodies = self.expected()
        bodies['history_status.json'] = b'{"stale":true}'
        report = self.api.verify_publication('https://example.invalid/', expected,
                                             timeout=0, fetch=lambda url, **kwargs: bodies[url.rsplit('/', 1)[-1].split('?')[0]])
        self.assertFalse(report['verified'])
        self.assertIn('history_status.json', report['mismatches'])

    def test_same_data_with_wrong_deployment_commit_remains_unverified(self):
        expected, bodies = self.expected()
        bodies['deployment.json'] = json.dumps({**expected, 'sourceCommit': 'b' * 40}).encode()
        report = self.api.verify_publication('https://example.invalid/', expected,
                                             timeout=0, fetch=lambda url, **kwargs: bodies[url.rsplit('/', 1)[-1].split('?')[0]])
        self.assertFalse(report['verified'])
        self.assertFalse(report['commitMatches'])

    def test_missing_json_is_not_zero_filled_or_ignored(self):
        expected, bodies = self.expected()
        def unavailable(url, **kwargs):
            name = url.rsplit('/', 1)[-1].split('?')[0]
            if name == 'official_history.json':
                raise OSError('not deployed')
            return bodies[name]
        report = self.api.verify_publication('https://example.invalid/', expected, timeout=0, fetch=unavailable)
        self.assertFalse(report['verified'])
        self.assertIn('official_history.json', report['mismatches'])

    def test_slow_responses_cannot_extend_fifteen_minute_verification_deadline(self):
        expected, _ = self.expected()
        now = [0]
        def slow(url, *, timeout):
            now[0] += min(20, timeout)
            return b'{}'
        report = self.api.verify_publication('https://example.invalid/', expected,
            timeout=900, fetch=slow, clock=lambda: now[0],
            sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertFalse(report['verified'])
        self.assertLessEqual(now[0], 900)

    def test_source_error_does_not_invalidate_successful_producer_authorization(self):
        from publication import DATA_FILES
        result = {'schemaVersion': 1, 'publication': 'published', 'sourceHealthy': False,
                  'runId': '123', 'pushedSha': 'a' * 40, 'hashes': {name: '0' * 64 for name in DATA_FILES}}
        self.assertEqual(self.api.authorized_sha(result, producer_run_id='123'), 'a' * 40)
        self.assertIsNone(self.api.authorized_sha({**result, 'publication': 'failed'}, producer_run_id='123'))
        self.assertIsNone(self.api.authorized_sha(result, producer_run_id='456'))

    def test_unchanged_validated_result_can_reconcile_a_previous_missing_artifact(self):
        from publication import DATA_FILES
        result = {'schemaVersion': 1, 'publication': 'unchanged', 'runId': '124',
                  'pushedSha': 'a' * 40, 'hashes': {name: '0' * 64 for name in DATA_FILES}}
        self.assertEqual(self.api.authorized_sha(result, producer_run_id='124'), 'a' * 40)

    def test_bounded_wait_retries_until_a_consistent_public_bundle_arrives(self):
        expected, bodies = self.expected()
        now = [0]
        def fetch(url, **kwargs):
            name = url.rsplit('/', 1)[-1].split('?')[0]
            return b'{}' if now[0] == 0 and name == 'data.json' else bodies[name]
        report = self.api.verify_publication('https://example.invalid/', expected,
                                             timeout=15, fetch=fetch, clock=lambda: now[0],
                                             sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        self.assertTrue(report['verified'])
        self.assertEqual(report['attempts'], 2)

    def test_build_excludes_repository_private_files_and_pins_commit(self):
        from test_publication import PublicationTests, git
        from publication import DATA_FILES
        fixture = PublicationTests('test_queued_job_reads_current_main_before_generating')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        for name in self.api.PUBLIC_ASSETS:
            (fixture.repo / name).write_text('public asset\n')
        (fixture.repo / 'private-audit.txt').write_text('must not be deployed\n')
        git(fixture.repo, 'add', '.')
        git(fixture.repo, 'commit', '-m', 'site files')
        git(fixture.repo, 'push', 'origin', 'HEAD:main')
        sha = git(fixture.repo, 'rev-parse', 'HEAD')
        output = fixture.root / 'public'
        report = self.api.build_release(fixture.repo, output, sha=sha, validate=lambda stage: None)
        self.assertTrue(report['deploy'])
        self.assertEqual(set(p.name for p in output.iterdir()),
                         set(DATA_FILES) | set(self.api.PUBLIC_ASSETS) | {'deployment.json', '.nojekyll'})
        self.assertEqual(json.loads((output / 'deployment.json').read_text())['sourceCommit'], sha)
        old = self.api.build_release(fixture.repo, output, sha=fixture.initial, validate=lambda stage: None)
        self.assertFalse(old['deploy'])
        self.assertEqual(old['reason'], 'superseded')


if __name__ == '__main__':
    unittest.main()
