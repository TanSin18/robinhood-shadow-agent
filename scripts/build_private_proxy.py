"""Build a credential-free, explicit-source proxy release outside iCloud."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from scripts.runtime_preflight import require_local_files


SOURCES = (
    'broker/__init__.py', 'broker/base.py', 'broker/policy.py',
    'broker/read_contracts.py', 'broker/read_schemas_v1.4.2.json',
    'broker_proxy/__init__.py', 'broker_proxy/config.py', 'broker_proxy/identity.py',
    'broker_proxy/mcp_client.py', 'broker_proxy/oauth.py', 'broker_proxy/protocol.py',
    'broker_proxy/server.py', 'broker_proxy/revocation.py', 'scripts/__init__.py',
    'scripts/authorize_robinhood.py', 'scripts/runtime_preflight.py',
    'config/broker-proxy.local.yaml', 'preregistration.yaml',
)


def build_bundle(root, python, destination):
    root, python, destination = map(Path, (root, python, destination))
    if destination.exists():
        raise ValueError('release destination already exists')
    require_local_files([python, *[root / name for name in SOURCES]])
    for item in python.rglob('*'):
        if item.is_symlink() and (item.readlink().is_absolute() or
                                 not item.resolve().is_relative_to(python.resolve())):
            raise ValueError('external symlink in private Python runtime')
    for name in SOURCES:
        if (root / name).is_symlink():
            raise ValueError('source symlink is not permitted')
    destination.mkdir(parents=True)
    # Bytecode embeds its build path and is mutable on first import. Deploy
    # sources/extensions only and run the private interpreter with -B.
    shutil.copytree(python, destination / 'python', symlinks=True,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in SOURCES:
        target = destination / 'app' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    from broker.read_contracts import READ_METHODS
    files = {}
    for item in sorted(destination.rglob('*')):
        if item.is_file():
            files[str(item.relative_to(destination))] = hashlib.sha256(item.read_bytes()).hexdigest()
    manifest = {'read_methods': sorted(READ_METHODS), 'files': files,
                'credentials_in_bundle': False}
    (destination / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    manifest = build_bundle(Path(__file__).resolve().parents[1], args.python, args.destination)
    print(json.dumps({'status': 'BUNDLE_BUILT_NOT_INSTALLED', 'file_count': len(manifest['files'])}))


if __name__ == '__main__':
    main()
