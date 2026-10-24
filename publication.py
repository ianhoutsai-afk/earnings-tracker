"""Stage, validate and publish a complete earnings bundle without rebasing generated data."""
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

DATA_FILES = (
    'data.json', 'historical_data.json', 'official_history.json',
    'history_status.json', 'official_scan_state.json', 'sp500_mapping.json',
)


def _git(root, *args, check=True):
    return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                          text=True, check=check)


def _sha(root, ref='HEAD'):
    return _git(root, 'rev-parse', ref).stdout.strip()


def bundle_hashes(root):
    return {name: hashlib.sha256((Path(root) / name).read_bytes()).hexdigest()
            for name in DATA_FILES}


def _changed(root, before, after):
    return set(_git(root, 'diff', '--name-only', before, after).stdout.splitlines())


def _stage(root, revision, target):
    archive = subprocess.run(['git', '-C', str(root), 'archive', revision],
                             check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            name = Path(member.name)
            if not member.isfile() or name.is_absolute() or '..' in name.parts:
                continue
            output = target / name
            output.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as stream:
                output.write_bytes(stream.read())
    cache = root / '.sec_cache'
    cache.mkdir(exist_ok=True)
    (target / '.sec_cache').symlink_to(cache, target_is_directory=True)


def validate_stage(stage):
    subprocess.run([sys.executable, str(stage / 'validate_quarterly_data.py'),
                    '--root', str(stage)], cwd=stage, check=True, timeout=120)


def generate_bundle(stage, mode, remaining):
    """Run generators as fresh processes using code from the current staged commit."""
    started = time.monotonic()
    healthy = True
    commands = []
    if mode == 'mapping':
        commands.append(['official_sync.py', '--mapping-only'])
    else:
        if mode == 'daily':
            commands.append(['verified_history.py', '--scan'])
        commands.append(['official_sync.py'] + ([] if mode == 'window' else ['--full']))
    for command in commands:
        left = remaining - (time.monotonic() - started)
        if left < 30:
            raise TimeoutError('Source budget exhausted before next generator')
        env = {**os.environ, 'OFFICIAL_SOURCE_BUDGET_SECONDS': str(max(1, int(left - 15))),
               'PYTHONDONTWRITEBYTECODE': '1'}
        result = subprocess.run([sys.executable, *command], cwd=stage, env=env,
                                timeout=left)
        healthy = result.returncode == 0 and healthy
    return healthy


def publish(root, *, generate, validate=validate_stage, max_attempts=3,
            source_budget=2400, clock=time.monotonic):
    """Only a clean ephemeral main checkout may be reset; user work is never discarded."""
    root = Path(root).resolve()
    result = {'schemaVersion': 1, 'publication': 'failed', 'sourceHealthy': False,
              'attempts': 0, 'runId': os.environ.get('GITHUB_RUN_ID'),
              'generatedAt': datetime.now(timezone.utc).isoformat(), 'hashes': {}}
    deadline = clock() + source_budget
    if _git(root, 'status', '--porcelain', '--untracked-files=no').stdout.strip():
        return {**result, 'reason': 'dirty_checkout'}
    if _git(root, 'branch', '--show-current').stdout.strip() != 'main':
        return {**result, 'reason': 'main_checkout_required'}
    try:
        _git(root, 'fetch', 'origin', 'main')
        baseline = _sha(root, 'origin/main')
        for attempt in range(1, max_attempts + 1):
            result.update(attempts=attempt, baseSha=baseline)
            if deadline - clock() < 30:
                return {**result, 'reason': 'source_budget_exhausted'}
            _git(root, 'reset', '--hard', baseline)
            with tempfile.TemporaryDirectory(prefix='earnings-publication-') as temp:
                stage = Path(temp)
                _stage(root, baseline, stage)
                try:
                    result['sourceHealthy'] = bool(generate(stage, deadline - clock()))
                except (TimeoutError, subprocess.TimeoutExpired):
                    return {**result, 'reason': 'source_budget_exhausted'}
                except Exception as exc:
                    return {**result, 'reason': 'generation_failed', 'errorType': type(exc).__name__}
                try:
                    validate(stage)
                    hashes = bundle_hashes(stage)
                except Exception as exc:
                    return {**result, 'reason': 'validation_failed', 'errorType': type(exc).__name__}
                _git(root, 'fetch', 'origin', 'main')
                current = _sha(root, 'origin/main')
                if current != baseline:
                    if _changed(root, baseline, current) - set(DATA_FILES):
                        return {**result, 'publication': 'superseded', 'reason': 'non_data_change'}
                    baseline = current
                    continue
                for name in DATA_FILES:
                    shutil.copyfile(stage / name, root / name)
                _git(root, 'add', '--', *DATA_FILES)
                if _git(root, 'diff', '--cached', '--quiet', check=False).returncode == 0:
                    return {**result, 'publication': 'unchanged', 'pushedSha': baseline,
                            'hashes': hashes, 'reason': 'validated_for_deployment_reconciliation'}
                _git(root, 'commit', '-m', 'Update validated quarterly data and source health [skip ci]')
                pushed = _sha(root)
                response = _git(root, 'push', 'origin', 'HEAD:main', check=False)
                if response.returncode == 0:
                    return {**result, 'publication': 'published', 'pushedSha': pushed,
                            'hashes': hashes}
                # A push may have succeeded server-side before the connection failed.
                _git(root, 'fetch', 'origin', 'main')
                current = _sha(root, 'origin/main')
                if _git(root, 'merge-base', '--is-ancestor', pushed, current, check=False).returncode == 0:
                    return {**result, 'publication': 'published', 'pushedSha': pushed,
                            'hashes': hashes, 'reason': 'push_confirmed_after_transport_error'}
                if current == baseline:
                    return {**result, 'reason': 'push_failed'}
                if _changed(root, baseline, current) - set(DATA_FILES):
                    return {**result, 'publication': 'superseded', 'reason': 'non_data_change'}
                baseline = current
        return {**result, 'reason': 'retry_exhausted'}
    except subprocess.CalledProcessError as exc:
        return {**result, 'reason': 'git_operation_failed', 'errorType': type(exc).__name__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('daily', 'full', 'window', 'mapping'), required=True)
    parser.add_argument('--result', required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise SystemExit('Publication is restricted to a clean GitHub Actions main checkout')
    result = publish(Path.cwd(), generate=lambda stage, left: generate_bundle(stage, args.mode, left))
    Path(args.result).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('### Quarterly publication\n\n```json\n' + json.dumps(result, indent=2) + '\n```\n')
    if result['publication'] not in ('published', 'unchanged') or not result['sourceHealthy']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
