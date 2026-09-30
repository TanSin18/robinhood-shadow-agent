"""Build a pinned release manifest from git: installed-base commit -> candidate commit.

  python scripts/build_release_manifest.py --base 6e2c220 --before-fingerprint <installed> \
      --out docs/review/release-2026-09-30-manifest.json [--amendment docs/.../preregistration-amendment-v1.5.0.yaml]
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

RUNTIME = ('agents', 'broker', 'broker_proxy', 'risk', 'research', 'data', 'eval', 'prompts', 'scripts', 'tests')
EXCLUDE = set()  # tests import these scripts; ship them so the installed suite is complete


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, check=True).stdout


def blob_sha(commit, rel):
    try:
        return hashlib.sha256(git('show', f'{commit}:{rel}')).hexdigest()
    except subprocess.CalledProcessError:
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', required=True)
    p.add_argument('--head', default='HEAD')
    p.add_argument('--before-fingerprint', required=True)
    p.add_argument('--active-registration', default='39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075')
    p.add_argument('--amendment')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    head = git('rev-parse', a.head).decode().strip()
    changed = git('diff', '--name-only', a.base, head, '--', *RUNTIME).decode().split()
    files = {}
    for rel in sorted(changed):
        if rel in EXCLUDE or '__pycache__' in rel:
            continue
        after = blob_sha(head, rel)
        if after is None:
            raise SystemExit(f'deletion not supported by this installer: {rel}')
        files[rel] = {'before_sha256': blob_sha(a.base, rel), 'after_sha256': after}
    manifest = {'source_commit': head, 'installed_base_commit': a.base,
                'before_source_fingerprint': a.before_fingerprint,
                'expected_after_source_fingerprint': None,
                'active_preregistration_sha256': a.active_registration,
                'files': files, 'root_files': {}}
    if a.amendment:
        manifest['root_files']['preregistration-amendment-v1.5.0.yaml'] = {
            'from': a.amendment, 'after_sha256': hashlib.sha256(Path(a.amendment).read_bytes()).hexdigest()}
    Path(a.out).write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'files': len(files), 'source_commit': head}))


if __name__ == '__main__':
    main()
