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


# ---------------------------------------------------------------- codex-cli 0.159.0 compatibility: hardening is unchanged in effect
HARDENING = ['features.apps=false', 'features.plugins=false', 'features.shell_tool=false', 'features.unified_exec=false',
             'features.multi_agent=false', 'features.tool_suggest=false', 'project_doc_max_bytes=0', 'features.view_image=false',
             'web_search="disabled"', 'model_reasoning_effort="low"']


def _settings(argv):
    return [argv[i + 1] for i, a in enumerate(argv) if a == '-c']


def test_image_viewing_is_disabled_with_the_key_the_current_cli_recognises(monkeypatch, tmp_path):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))                 # no inherited user configuration
    argv = isolated_session.command('/x/codex')
    assert argv[:3] == ['/x/codex', 'app-server', '--strict-config']
    settings = _settings(argv)
    assert settings[:len(HARDENING)] == HARDENING                    # every earlier control is still sent, in the same order
    assert 'features.view_image=false' in settings and not [s for s in settings if s.startswith('tools.view_image')]
    assert settings[len(HARDENING):] == ['mcp_servers.robinhood-trading.enabled=false']
    with_model = _settings(isolated_session.command('/x/codex', model='gpt-5.4'))
    assert with_model[:len(HARDENING)] == HARDENING and with_model[-1] == 'model="gpt-5.4"'


def test_inherited_tool_servers_are_still_disabled_one_by_one(monkeypatch, tmp_path):
    (tmp_path / 'config.toml').write_text('[mcp_servers.notes]\ncommand = "x"\n[mcp_servers.calendar]\ncommand = "y"\n')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    settings = _settings(isolated_session.command('/x/codex'))
    assert settings[len(HARDENING):] == ['mcp_servers.calendar.enabled=false', 'mcp_servers.notes.enabled=false',
                                         'mcp_servers.robinhood-trading.enabled=false']
    (tmp_path / 'config.toml').write_text('[mcp_servers."bad name"]\ncommand = "x"\n')
    with pytest.raises(isolated_session.CapabilityError):
        isolated_session.command('/x/codex')


def test_a_config_warning_is_never_tolerated(monkeypatch):
    """The fix is to send a setting the CLI understands, not to accept the warning. Any configWarning still stops the session."""
    assert 'configWarning' not in isolated_session.BENIGN_NOTIFICATIONS
    assert isolated_session.BENIGN_NOTIFICATIONS == {'thread/started', 'thread/status/changed', 'turn/started', 'item/agentMessage/delta',
                                                     'item/reasoning/summaryTextDelta', 'item/reasoning/summaryPartAdded',
                                                     'item/reasoning/textDelta', 'account/rateLimits/updated', 'deprecationNotice', 'warning'}
    warning = {'method': 'configWarning', 'params': {'summary': 'Codex is ignoring 1 unrecognized configuration setting.', 'details': None}}
    for collector in (False, True):
        with pytest.raises(isolated_session.CapabilityError, match='configWarning'):
            isolated_session.validate_notification(warning, collector=collector)
    for method in ('mcpServer/startupStatus/updated', 'item/commandExecution/outputDelta', 'tool/requestUserInput', 'somethingNew'):
        with pytest.raises(isolated_session.CapabilityError):
            isolated_session.validate_notification({'method': method, 'params': {}})
    with pytest.raises(isolated_session.CapabilityError, match='Unexpected server request'):
        isolated_session.validate_notification({'id': 7, 'method': 'item/tool/call', 'params': {}})


def test_an_unexpected_tool_capability_is_still_refused():
    class Transport:
        notifications = []

        def __init__(self, servers):
            self.servers = servers

        def request(self, method, params=None, timeout=None):
            return {'data': self.servers, 'nextCursor': None}

    listed = [{'name': 'robinhood-trading', 'tools': {}, 'runtimeStatus': 'disabled'}]
    clean = isolated_session.verify_inference_inventory(Transport(listed), 't')
    assert clean['tools'] == []                                  # nothing is available to inference
    for bad in ([{'name': 'robinhood-trading', 'tools': {}, 'runtimeStatus': 'ready'}],          # a server that is not disabled
                [{'name': 'robinhood-trading', 'tools': {'get_quote': {}}, 'runtimeStatus': 'disabled'}]):
        with pytest.raises(isolated_session.CapabilityError, match='unexpected MCP capability'):
            isolated_session.verify_inference_inventory(Transport(bad), 't')
    with pytest.raises(isolated_session.CapabilityError):
        isolated_session.verify_inference_inventory(Transport([{'name': 'extra', 'tools': {'place_order': {}}, 'runtimeStatus': 'ready'}]), 't')
