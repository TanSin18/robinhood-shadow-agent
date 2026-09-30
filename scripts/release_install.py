"""Manifest-pinned after-close release installer (operator runs it in Terminal).

Usage (only after the operator's explicit go, after the close, after the drill):

  .venv/bin/python <dev-checkout>/scripts/release_install.py \
      --primary /Users/.../robinhood-shadow-agent --source <dev-checkout> \
      --manifest <dev-checkout>/docs/review/release-2026-09-30-manifest.json --install

Without --install it only verifies (dry run). It never touches the proxy, the
inbox/dashboard service, config, credentials or the official database, and it
never clears a safety stop. Any mismatch aborts before a byte is changed; any
failure after changes rolls back automatically from a verified backup.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SERVICES = ('com.openai.robinhood-daily', 'com.openai.robinhood-maintenance')
NEVER_TOUCH = ('config/settings.local.yaml', 'config/broker-proxy.local.yaml', 'data/agent.db',
               'preregistration.yaml')


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def fingerprint(root: Path) -> str:
    sys.path.insert(0, str(root))
    try:
        from agents.readiness import source_fingerprint
        return source_fingerprint(root)
    finally:
        sys.path.pop(0)


def verify(primary: Path, source: Path, manifest: dict) -> list[str]:
    problems = []
    for rel, entry in manifest['files'].items():
        if rel in NEVER_TOUCH or '..' in Path(rel).parts or Path(rel).is_absolute():
            problems.append(f'forbidden path {rel}')
            continue
        if sha(primary / rel) != entry['before_sha256']:
            problems.append(f'installed drift {rel}')
        if sha(source / rel) != entry['after_sha256']:
            problems.append(f'source mismatch {rel}')
    for rel, entry in manifest.get('root_files', {}).items():
        if sha(source / entry['from']) != entry['after_sha256']:
            problems.append(f'source mismatch {rel}')
        if sha(primary / rel) not in {None, entry['after_sha256']}:
            problems.append(f'unexpected existing {rel}')
    if sha(primary / 'preregistration.yaml') != manifest['active_preregistration_sha256']:
        problems.append('active registration changed')
    if fingerprint(primary) != manifest['before_source_fingerprint']:
        problems.append('installed source fingerprint drift')
    return problems


def launchctl(action, label, uid, runner=subprocess.run):
    target = f'gui/{uid}/{label}'
    if action == 'bootout':
        runner(['/bin/launchctl', 'bootout', target], capture_output=True)
    else:
        plist = Path.home() / 'Library/LaunchAgents' / f'{label}.plist'
        result = runner(['/bin/launchctl', 'bootstrap', f'gui/{uid}', str(plist)], capture_output=True)
        if result.returncode not in (0, 5):
            raise RuntimeError(f'bootstrap failed for {label}')


def install(primary: Path, source: Path, manifest: dict, *, runner=subprocess.run, uid=None,
            run_suite=None, backup_parent=None) -> dict:
    uid = os.getuid() if uid is None else uid
    problems = verify(primary, source, manifest)
    if problems:
        return {'status': 'ABORTED_BEFORE_CHANGES', 'problems': problems}
    backup = Path(tempfile.mkdtemp(prefix='release-rollback.', dir=backup_parent or primary.parent))
    os.chmod(backup, 0o700)
    touched = list(manifest['files']) + list(manifest.get('root_files', {}))
    absent = []
    for rel in touched:
        if (primary / rel).is_file():
            (backup / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(primary / rel, backup / rel)
            if sha(backup / rel) != sha(primary / rel):
                return {'status': 'ABORTED_BACKUP_UNVERIFIED', 'backup': str(backup)}
        else:
            absent.append(rel)
    (backup / 'rollback.json').write_text(json.dumps({'absent_before': absent, 'files': touched}, indent=2))
    for label in SERVICES:
        launchctl('bootout', label, uid, runner)

    def rollback(reason):
        for rel in touched:
            if rel in absent:
                (primary / rel).unlink(missing_ok=True)
            else:
                shutil.copy2(backup / rel, primary / rel)
        restored = fingerprint(primary) == manifest['before_source_fingerprint']
        for label in SERVICES:
            launchctl('bootstrap', label, uid, runner)
        return {'status': 'ROLLED_BACK', 'reason': reason, 'fingerprint_restored': restored,
                'backup': str(backup)}

    try:
        for rel, entry in manifest['files'].items():
            (primary / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / rel, primary / rel)
            if sha(primary / rel) != entry['after_sha256']:
                return rollback(f'post-copy hash mismatch {rel}')
        for rel, entry in manifest.get('root_files', {}).items():
            shutil.copy2(source / entry['from'], primary / rel)
            if sha(primary / rel) != entry['after_sha256']:
                return rollback(f'post-copy hash mismatch {rel}')
        after = fingerprint(primary)
        if manifest.get('expected_after_source_fingerprint') and after != manifest['expected_after_source_fingerprint']:
            return rollback('after fingerprint mismatch')
        suite = (run_suite or default_suite)(primary)
        if suite.get('failed') != 0 or suite.get('errors') != 0 or not suite.get('passed'):
            return rollback(f'installed suite failed: {suite}')
        if fingerprint(primary) != after:
            return rollback('tests modified installed source')
    except Exception as error:  # any unexpected failure restores the previous state
        return rollback(f'{type(error).__name__}')
    for label in SERVICES:
        launchctl('bootstrap', label, uid, runner)
    return {'status': 'INSTALLED', 'backup': str(backup), 'after_source_fingerprint': after,
            'suite': suite, 'at': datetime.now(timezone.utc).isoformat()}


def default_suite(primary: Path) -> dict:
    out = primary / 'outputs' / ('release-' + datetime.now().strftime('%Y-%m-%d'))
    out.mkdir(parents=True, exist_ok=True)
    report = out / 'tests.xml'
    subprocess.run([str(primary / '.venv/bin/python'), '-m', 'scripts.verify_operations', '--run-tests',
                    '--output-dir', str(out), '--test-report', str(report),
                    '--test-manifest', str(out / 'test-run.json')], cwd=primary)
    import xml.etree.ElementTree as ET
    root = ET.parse(report).getroot()
    suite = root if root.tag == 'testsuite' else root.find('testsuite')
    tests, failures, errors, skipped = (int(suite.get(k, 0)) for k in ('tests', 'failures', 'errors', 'skipped'))
    return {'passed': tests - failures - errors - skipped, 'failed': failures, 'errors': errors, 'skipped': skipped}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--primary', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--install', action='store_true')
    args = parser.parse_args()
    primary, source = Path(args.primary).resolve(), Path(args.source).resolve()
    manifest = json.loads(Path(args.manifest).read_text())
    if not args.install:
        problems = verify(primary, source, manifest)
        print(json.dumps({'status': 'VERIFIED' if not problems else 'NOT_READY', 'problems': problems}, indent=2))
        return 0 if not problems else 2
    result = install(primary, source, manifest)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'INSTALLED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
