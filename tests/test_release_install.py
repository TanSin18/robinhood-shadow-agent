import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import release_install as ri  # noqa: E402


def h(text): return hashlib.sha256(text.encode()).hexdigest()


class Runner:
    def __init__(self): self.calls = []
    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1]); return type('R', (), {'returncode': 0})()


@pytest.fixture
def trees(tmp_path, monkeypatch):
    primary, source = tmp_path / 'primary', tmp_path / 'source'
    for root, body in ((primary, 'old'), (source, 'new')):
        (root / 'agents').mkdir(parents=True)
        (root / 'agents/x.py').write_text(body)
        (root / 'preregistration.yaml').write_text('v142')
    (source / 'agents/new.py').write_text('added')
    (source / 'amend.yaml').write_text('signed')
    fp = {'value': 'BEFORE'}
    monkeypatch.setattr(ri, 'fingerprint', lambda root: fp['value'] if root == primary.resolve() or root == primary else 'SRC')
    manifest = {'before_source_fingerprint': 'BEFORE', 'active_preregistration_sha256': h('v142'),
                'files': {'agents/x.py': {'before_sha256': h('old'), 'after_sha256': h('new')},
                          'agents/new.py': {'before_sha256': None, 'after_sha256': h('added')}},
                'root_files': {'preregistration-amendment-v1.5.0.yaml': {'from': 'amend.yaml', 'after_sha256': h('signed')}}}
    return primary, source, manifest, fp


def test_install_success_reloads_services_and_keeps_backup(trees):
    primary, source, manifest, fp = trees
    runner = Runner()
    result = ri.install(primary, source, manifest, runner=runner, uid=501,
                        run_suite=lambda p: {'passed': 10, 'failed': 0, 'errors': 0})
    assert result['status'] == 'INSTALLED'
    assert (primary / 'agents/x.py').read_text() == 'new'
    assert (primary / 'preregistration-amendment-v1.5.0.yaml').read_text() == 'signed'
    assert (primary / 'preregistration.yaml').read_text() == 'v142'
    assert runner.calls == ['bootout', 'bootout', 'bootstrap', 'bootstrap']
    assert (Path(result['backup']) / 'agents/x.py').read_text() == 'old'


def test_failed_suite_rolls_back_everything(trees):
    primary, source, manifest, _ = trees
    result = ri.install(primary, source, manifest, runner=Runner(), uid=501,
                        run_suite=lambda p: {'passed': 9, 'failed': 1, 'errors': 0})
    assert result['status'] == 'ROLLED_BACK'
    assert (primary / 'agents/x.py').read_text() == 'old'
    assert not (primary / 'agents/new.py').exists()
    assert not (primary / 'preregistration-amendment-v1.5.0.yaml').exists()


def test_drift_aborts_before_any_change(trees):
    primary, source, manifest, _ = trees
    (primary / 'agents/x.py').write_text('someone edited')
    runner = Runner()
    result = ri.install(primary, source, manifest, runner=runner, uid=501, run_suite=lambda p: {})
    assert result['status'] == 'ABORTED_BEFORE_CHANGES' and runner.calls == []
    assert (primary / 'agents/x.py').read_text() == 'someone edited'


def test_forbidden_paths_and_registration_change_abort(trees):
    primary, source, manifest, _ = trees
    manifest['files']['config/settings.local.yaml'] = {'before_sha256': None, 'after_sha256': 'x'}
    assert any('forbidden' in p for p in ri.verify(primary, source, manifest))
    del manifest['files']['config/settings.local.yaml']
    (primary / 'preregistration.yaml').write_text('changed')
    assert 'active registration changed' in ri.verify(primary, source, manifest)
