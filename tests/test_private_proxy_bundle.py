from pathlib import Path
import json
import pytest


def test_bundle_has_no_execution_adapters_or_operator_symlinks(tmp_path):
    from scripts.build_private_proxy import build_bundle
    python = tmp_path / 'python'; (python / 'bin').mkdir(parents=True)
    (python / 'bin/python3').write_text('test interpreter')
    (python / '__pycache__').mkdir()
    (python / '__pycache__/mutable.pyc').write_bytes(b'cache')
    destination = tmp_path / 'release'
    build_bundle(Path.cwd(), python, destination)
    assert (destination / 'app/broker_proxy/server.py').is_file()
    assert not (destination / 'app/broker/robinhood.py').exists()
    assert not (destination / 'app/agents').exists()
    assert not (destination / 'app/data').exists()
    assert not list(destination.rglob('*.db'))
    assert not list(destination.rglob('*.pyc'))
    manifest = json.loads((destination / 'manifest.json').read_text())
    assert len(manifest['read_methods']) == 11
    assert 'app/preregistration.yaml' in manifest['files']
    assert 'python/bin/python3' in manifest['files']


def test_bundle_rejects_python_symlink_to_operator_home(tmp_path):
    from scripts.build_private_proxy import build_bundle
    python = tmp_path / 'python'; (python / 'bin').mkdir(parents=True)
    (python / 'bin/python3').symlink_to('/usr/bin/python3')
    with pytest.raises(ValueError, match='external symlink'):
        build_bundle(Path.cwd(), python, tmp_path / 'release')
