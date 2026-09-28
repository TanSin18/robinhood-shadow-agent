"""Standard-library-only local-file guard, run before application imports."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import runpy
import stat
import sys


class LocalFilesError(RuntimeError):
    pass


def require_local_files(roots):
    visited = set()
    count = 0
    def check(path):
        nonlocal count
        path = Path(path)
        try:
            details = path.stat()
            if getattr(details, 'st_flags', 0) & 0x40000000:
                raise LocalFilesError('REQUIRED_FILE_CLOUD_ONLY: ' + str(path))
            resolved = path.resolve(strict=True)
            if resolved in visited:
                return
            visited.add(resolved)
            count += 1
            if stat.S_ISDIR(details.st_mode):
                for child in path.iterdir():
                    check(child)
        except OSError as error:
            raise LocalFilesError('REQUIRED_FILE_UNAVAILABLE: ' + str(path)) from error
    for root in roots:
        check(root)
    return count


def required_roots(root):
    root = Path(root)
    return [root / name for name in (
        'agents', 'broker', 'broker_proxy', 'config', 'data', 'eval', 'prompts',
        'risk', 'research', 'scripts', 'tests', '.venv', 'preregistration.yaml', 'pyproject.toml',
    )]


def launch(roots, module, arguments):
    require_local_files(roots)
    sys.argv = [module, *arguments]
    runpy.run_module(module, run_name='__main__')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--python', type=Path)
    parser.add_argument('module', nargs='?')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        roots = required_roots(args.root)
        if args.module:
            if args.python:
                require_local_files([*roots, args.python])
                os.chdir(args.root)
                os.execv(str(args.python), [str(args.python), '-m', args.module, *args.arguments])
            os.chdir(args.root)
            sys.path.insert(0, str(args.root))
            launch(roots, args.module, args.arguments)
        else:
            print(json.dumps({'status': 'LOCAL_FILES_VERIFIED', 'checked': require_local_files(roots)}))
    except LocalFilesError as error:
        print(json.dumps({'status': 'HOLD_OPERATIONAL', 'reason': str(error)}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
