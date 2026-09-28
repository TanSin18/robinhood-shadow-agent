from pathlib import Path
from types import SimpleNamespace
import pytest


def test_cloud_only_dependency_fails_before_entrypoint(tmp_path, monkeypatch):
    from scripts.runtime_preflight import launch, LocalFilesError
    dependency = tmp_path / 'dependency.py'
    dependency.write_text('raise AssertionError("must not read or import")')
    original = Path.stat
    def flags(path, **kwargs):
        if path == dependency:
            return SimpleNamespace(st_flags=0x40000000, st_mode=0o100600)
        return original(path, **kwargs)
    monkeypatch.setattr(Path, 'stat', flags)
    with pytest.raises(LocalFilesError, match='REQUIRED_FILE_CLOUD_ONLY'):
        launch([tmp_path], 'not_a_real_module', [])


def test_missing_required_root_fails_closed(tmp_path):
    from scripts.runtime_preflight import require_local_files, LocalFilesError
    with pytest.raises(LocalFilesError, match='REQUIRED_FILE_UNAVAILABLE'):
        require_local_files([tmp_path / 'missing'])


def test_local_tree_and_symlink_target_are_checked(tmp_path, monkeypatch):
    from scripts.runtime_preflight import require_local_files, LocalFilesError
    root = tmp_path / 'root'; root.mkdir()
    target = tmp_path / 'target'; target.write_text('local')
    (root / 'link').symlink_to(target)
    require_local_files([root])
    target.unlink()
    with pytest.raises(LocalFilesError):
        require_local_files([root])


def test_proxy_service_does_not_depend_on_operator_checkout():
    from scripts.install_shadow_services import service_definitions
    service = service_definitions('/Users/operator/Documents/project')['com.openai.robinhood-read-proxy']
    assert '/Users/operator' not in str(service)
    assert service['WorkingDirectory'].startswith('/Users/Shared/RobinhoodShadow/private/')


def test_scheduled_preflight_bootstraps_outside_cloud_python():
    from scripts.install_shadow_services import service_definitions
    args = service_definitions('/Users/operator/Documents/project')['com.openai.robinhood-daily']['ProgramArguments']
    assert args[0] == '/opt/homebrew/opt/python@3.14/bin/python3.14'
    assert args[1] == '/Users/Shared/RobinhoodShadow/launch/runtime_preflight.py'
    assert args[args.index('--python') + 1] == '/Users/operator/Documents/project/.venv/bin/python'


@pytest.mark.parametrize('name', ['tests/test_example.py', 'pyproject.toml'])
def test_cloud_only_fingerprint_inputs_also_stop_cycle(tmp_path, monkeypatch, name):
    from scripts.runtime_preflight import required_roots, require_local_files, LocalFilesError
    for directory in ('agents','broker','broker_proxy','config','data','eval','prompts',
                      'risk','research','scripts','.venv','tests'):
        (tmp_path / directory).mkdir()
    for filename in ('preregistration.yaml','pyproject.toml','tests/test_example.py'):
        (tmp_path / filename).write_text('fixture')
    original = Path.stat
    def flags(path, **kwargs):
        if path == tmp_path / name:
            return SimpleNamespace(st_flags=0x40000000, st_mode=0o100600)
        return original(path, **kwargs)
    monkeypatch.setattr(Path, 'stat', flags)
    with pytest.raises(LocalFilesError, match='REQUIRED_FILE_CLOUD_ONLY'):
        require_local_files(required_roots(tmp_path))
