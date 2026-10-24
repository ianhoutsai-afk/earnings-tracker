"""Build and verify a Pages release for one validated main commit."""
import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from publication import DATA_FILES, _git, _sha, _stage, bundle_hashes, validate_stage

PUBLIC_ASSETS = ('index.html', 'i18n.mjs', 'quarterly-history.mjs')


def authorized_sha(result, producer_run_id):
    if (result.get('schemaVersion') != 1
            or result.get('publication') not in ('published', 'unchanged')
            or str(result.get('runId')) != str(producer_run_id)
            or not re.fullmatch(r'[a-f0-9]{40}', result.get('pushedSha', ''))
            or set(result.get('hashes', {})) != set(DATA_FILES)
            or any(not re.fullmatch(r'[a-f0-9]{64}', str(v)) for v in result['hashes'].values())):
        return None
    return result['pushedSha']


def build_release(root, output, *, sha=None, result=None, producer_run_id=None,
                  validate=validate_stage):
    root, output = Path(root).resolve(), Path(output).resolve()
    if result is not None:
        sha = authorized_sha(result, producer_run_id)
        if sha is None:
            return {'deploy': False, 'reason': 'missing_or_invalid_producer_result'}
    if not sha or not re.fullmatch(r'[a-f0-9]{40}', sha):
        return {'deploy': False, 'reason': 'invalid_commit'}
    _git(root, 'fetch', 'origin', 'main')
    if _sha(root, 'origin/main') != sha:
        return {'deploy': False, 'reason': 'superseded', 'sourceCommit': sha}
    with tempfile.TemporaryDirectory(prefix='earnings-pages-') as temp:
        stage = Path(temp)
        _stage(root, sha, stage)
        validate(stage)
        hashes = bundle_hashes(stage)
        if result is not None and hashes != result['hashes']:
            raise ValueError('Producer hashes do not match the authorized commit')
        output.mkdir(parents=True, exist_ok=True)
        for name in (*DATA_FILES, *PUBLIC_ASSETS):
            shutil.copyfile(stage / name, output / name)
        metadata = {'schemaVersion': 1, 'sourceCommit': sha, 'hashes': hashes,
                    'producerRunId': producer_run_id,
                    'builtAt': datetime.now(timezone.utc).isoformat()}
        (output / 'deployment.json').write_text(json.dumps(metadata, indent=2) + '\n')
        (output / '.nojekyll').touch()
    return {'deploy': True, 'sourceCommit': sha, 'hashes': hashes}


def _fetch(url):
    request = Request(url, headers={'Cache-Control': 'no-cache', 'User-Agent': 'EarningsTracker-Pages-Verify'})
    with urlopen(request, timeout=20) as response:
        return response.read()


def verify_publication(base, expected, *, timeout=900, fetch=_fetch,
                       clock=time.monotonic, sleep=time.sleep):
    if set(expected.get('hashes', {})) != set(DATA_FILES):
        raise ValueError('Verification requires all six data file hashes')
    if not re.fullmatch(r'[a-f0-9]{40}', expected.get('sourceCommit', '')):
        raise ValueError('Verification requires an exact source commit')
    deadline, attempt = clock() + timeout, 0
    while True:
        attempt += 1
        suffix = '?release=' + expected['sourceCommit'] + '&attempt=' + str(attempt)
        matches, mismatches = [], []
        for name in DATA_FILES:
            try:
                body = fetch(base.rstrip('/') + '/' + name + suffix)
                json.loads(body)
                matched = hashlib.sha256(body).hexdigest() == expected['hashes'][name]
            except Exception:
                matched = False
            (matches if matched else mismatches).append(name)
        try:
            metadata = json.loads(fetch(base.rstrip('/') + '/deployment.json' + suffix))
            commit_matches = metadata.get('sourceCommit') == expected['sourceCommit']
        except Exception:
            commit_matches = False
        report = {'verified': not mismatches and commit_matches, 'matches': matches,
                  'mismatches': mismatches, 'commitMatches': commit_matches,
                  'sourceCommit': expected['sourceCommit'], 'attempts': attempt}
        if report['verified'] or clock() >= deadline:
            return report
        sleep(min(10, max(0, deadline - clock())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    build = sub.add_parser('build')
    build.add_argument('--output', required=True)
    build.add_argument('--sha')
    build.add_argument('--producer-result')
    build.add_argument('--producer-run-id')
    verify = sub.add_parser('verify')
    verify.add_argument('--url', required=True)
    verify.add_argument('--expected', required=True)
    verify.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    if args.command == 'build':
        result = None
        if args.producer_result:
            path = Path(args.producer_result)
            result = json.loads(path.read_text()) if path.exists() else {}
        report = build_release(Path.cwd(), args.output, sha=args.sha, result=result,
                               producer_run_id=args.producer_run_id)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
                stream.write('deploy=' + str(report['deploy']).lower() + '\n')
                stream.write('sha=' + report.get('sourceCommit', '') + '\n')
    else:
        report = verify_publication(args.url, json.loads(Path(args.expected).read_text()),
                                    timeout=args.timeout)
    print(json.dumps(report))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('### Pages publication\n\n```json\n' + json.dumps(report, indent=2) + '\n```\n')
    if args.command == 'verify' and not report['verified']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
