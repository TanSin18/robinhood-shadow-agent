"""Where the Codex executable is found. Path resolution only: no process is started and no trading rule is involved."""
import pytest

from agents import isolated_session
from agents.isolated_session import CODEX_LOCATIONS, find_codex, require_codex

OLD, NEW = CODEX_LOCATIONS


def _world(monkeypatch, files=(), on_path=None):
    monkeypatch.setattr(isolated_session.shutil, 'which', lambda name: on_path if name == 'codex' else None)
    monkeypatch.setattr(isolated_session.Path, 'is_file', lambda self: str(self) in files)


def test_path_wins_then_the_known_locations_in_order(monkeypatch):
    _world(monkeypatch, files={'/opt/homebrew/bin/codex', OLD, NEW}, on_path='/opt/homebrew/bin/codex')
    assert find_codex() == require_codex() == '/opt/homebrew/bin/codex'
    _world(monkeypatch, files={OLD, NEW})
    assert find_codex() == OLD                                   # the layout before the 2026-10-02 app update still resolves first
    _world(monkeypatch, files={'/explicit/codex'})
    assert find_codex('/explicit/codex') == require_codex('/explicit/codex') == '/explicit/codex'      # an explicit path is used as given


def test_the_relocated_executable_is_found_when_the_old_location_is_gone(monkeypatch):
    _world(monkeypatch, files={NEW})                             # this Mac since the app update: not on PATH, old file gone
    assert find_codex() == require_codex() == NEW
    assert NEW.endswith('/Resources/codex-cli/bin/codex') and OLD.endswith('/Resources/codex')


def test_a_clear_failure_when_it_is_nowhere(monkeypatch, tmp_path):
    _world(monkeypatch)
    assert find_codex() is None
    with pytest.raises(FileNotFoundError, match='CODEX_EXECUTABLE_NOT_FOUND: not on PATH and not at'):
        require_codex()
    with pytest.raises(FileNotFoundError, match='CODEX_EXECUTABLE_NOT_FOUND'):
        isolated_session.cli_identity()
    with pytest.raises(FileNotFoundError, match='CODEX_EXECUTABLE_NOT_FOUND'):
        require_codex('/stale/path/codex')                       # a path that is not a file is not accepted either


def test_a_missing_executable_is_not_recorded_as_a_safety_incident(monkeypatch, tmp_path):
    from agents import safety_events
    from agents.codex_bridge import PRICING, CodexBridge
    _world(monkeypatch)
    incidents = []
    monkeypatch.setattr(safety_events, 'record_incident', lambda *a, **k: incidents.append(a))
    bridge = CodexBridge(tmp_path / 'ledger.db')                 # constructing the bridge does not need the executable ...
    assert bridge.executable is None
    with pytest.raises(FileNotFoundError, match='CODEX_EXECUTABLE_NOT_FOUND'):
        bridge.run(next(iter(PRICING)), 'instructions', {'type': 'object', 'properties': {}})      # ... running it does, before any process starts
    assert incidents == [] and bridge.last_result is None and bridge.isolation_evidence == []
