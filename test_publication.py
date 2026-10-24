"""Publication behavior against real repositories, with external data generation injected."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / 'origin.git'
        self.repo = self.root / 'job'
        self.other = self.root / 'other'
        subprocess.run(['git', 'init', '--bare', '--initial-branch=main', str(self.remote)], check=True, capture_output=True)
        subprocess.run(['git', 'clone', str(self.remote), str(self.repo)], check=True, capture_output=True)
        for key, value in [('user.name', 'Test'), ('user.email', 'test@example.invalid')]:
            git(self.repo, 'config', key, value)
        try:
            from publication import DATA_FILES
        except ModuleNotFoundError:
            self.fail('Reliable publication helper is not implemented')
        for name in DATA_FILES:
            (self.repo / name).write_text(json.dumps({'baseline': 1}) + '\n')
        (self.repo / 'generator.py').write_text('# version one\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'baseline')
        git(self.repo, 'push', 'origin', 'HEAD:main')
        self.initial = git(self.repo, 'rev-parse', 'HEAD')
        subprocess.run(['git', 'clone', str(self.remote), str(self.other)], check=True, capture_output=True)
        for key, value in [('user.name', 'Other'), ('user.email', 'other@example.invalid')]:
            git(self.other, 'config', key, value)

    def advance(self, name='history_status.json', value=None):
        (self.other / name).write_text(json.dumps(value or {'other': 2}) + '\n')
        git(self.other, 'add', name)
        git(self.other, 'commit', '-m', 'another writer')
        git(self.other, 'push', 'origin', 'HEAD:main')
        return git(self.other, 'rev-parse', 'HEAD')

    def test_queued_job_reads_current_main_before_generating(self):
        from publication import publish
        newer = self.advance()
        observed = []
        def generate(stage, remaining):
            observed.append(json.loads((stage / 'history_status.json').read_text()))
            (stage / 'data.json').write_text('{"generated": true}\n')
            return True
        result = publish(self.repo, generate=generate, validate=lambda stage: None)
        self.assertEqual(observed, [{'other': 2}])
        self.assertEqual(result['baseSha'], newer)
        self.assertEqual(result['publication'], 'published')
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), result['pushedSha'])

    def test_remote_data_advancement_regenerates_instead_of_merging_json(self):
        from publication import publish
        observed = []
        def generate(stage, remaining):
            observed.append(json.loads((stage / 'history_status.json').read_text()))
            if len(observed) == 1:
                self.advance(value={'newer_baseline': 3})
            (stage / 'data.json').write_text(json.dumps({'attempt': len(observed)}) + '\n')
            return True
        result = publish(self.repo, generate=generate, validate=lambda stage: None)
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(observed, [{'baseline': 1}, {'newer_baseline': 3}])
        self.assertEqual(json.loads((self.repo / 'data.json').read_text()), {'attempt': 2})
        self.assertEqual(json.loads((self.repo / 'history_status.json').read_text()), {'newer_baseline': 3})

    def test_code_advancement_stops_old_generator_without_pushing(self):
        from publication import publish
        newer = []
        def generate(stage, remaining):
            (stage / 'data.json').write_text('{"generated": true}\n')
            newer.append(self.advance('generator.py', {'new_code': True}))
            return True
        result = publish(self.repo, generate=generate, validate=lambda stage: None)
        self.assertEqual(result['publication'], 'superseded')
        self.assertEqual(result['reason'], 'non_data_change')
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), newer[0])

    def test_code_advancing_before_publisher_entry_also_supersedes_old_process(self):
        from publication import publish
        newer = self.advance('generator.py', {'new_code': True})
        calls = []
        result = publish(self.repo, generate=lambda stage, left: calls.append(stage),
                         validate=lambda stage: None)
        self.assertEqual(result['publication'], 'superseded')
        self.assertEqual(result['reason'], 'non_data_change')
        self.assertEqual(calls, [])
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), newer)

    def test_validation_failure_never_changes_remote(self):
        from publication import publish
        def generate(stage, remaining):
            (stage / 'data.json').write_text('{"bad": true}\n')
            return True
        def invalid(stage):
            raise ValueError('inconsistent bundle')
        result = publish(self.repo, generate=generate, validate=invalid)
        self.assertEqual(result['publication'], 'failed')
        self.assertEqual(result['reason'], 'validation_failed')
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), self.initial)

    def test_safe_source_error_bundle_is_published_with_failed_source_verdict(self):
        from publication import publish
        def generate(stage, remaining):
            (stage / 'history_status.json').write_text('{"source_failed": true}\n')
            return False
        result = publish(self.repo, generate=generate, validate=lambda stage: None)
        self.assertEqual(result['publication'], 'published')
        self.assertFalse(result['sourceHealthy'])
        self.assertEqual(git(self.remote, 'rev-parse', 'main'), result['pushedSha'])

    def test_unchanged_run_authorizes_deployment_reconciliation(self):
        from publication import publish
        result = publish(self.repo, generate=lambda stage, remaining: True, validate=lambda stage: None)
        self.assertEqual(result['publication'], 'unchanged')
        self.assertEqual(result['pushedSha'], self.initial)
        self.assertEqual(len(result['hashes']), 6)

    def test_three_races_exhaust_attempts_without_overwriting_other_writer(self):
        from publication import publish
        calls = []
        def generate(stage, remaining):
            calls.append(1)
            git(self.other, 'pull', '--ff-only')
            self.advance(value={'writer': len(calls)})
            (stage / 'data.json').write_text('{"never_publish": true}\n')
            return True
        result = publish(self.repo, generate=generate, validate=lambda stage: None)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result['publication'], 'failed')
        self.assertEqual(result['reason'], 'retry_exhausted')
        self.assertEqual(json.loads(git(self.remote, 'show', 'main:data.json')), {'baseline': 1})

    def test_unrelated_dirty_checkout_is_rejected_without_discarding_work(self):
        from publication import publish
        (self.repo / 'generator.py').write_text('# user work\n')
        result = publish(self.repo, generate=lambda stage, remaining: True, validate=lambda stage: None)
        self.assertEqual(result['publication'], 'failed')
        self.assertEqual(result['reason'], 'dirty_checkout')
        self.assertEqual((self.repo / 'generator.py').read_text(), '# user work\n')


if __name__ == '__main__':
    unittest.main()
