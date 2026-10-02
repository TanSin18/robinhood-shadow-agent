"""The Codex executable: actual discovery, detection of Control A's stale fallback, and a clear failure when it is nowhere.
Nothing here starts a process; the file system is replaced by small stand-ins."""
import re
from pathlib import Path

import pytest

from agents.desk import codex_locator
from agents.desk.codex_locator import CONTROL_A_FALLBACK, KNOWN_LOCATIONS, CodexNotFound, locate, require

ROOT = Path(__file__).resolve().parents[1]
NEW = '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex'


def _probes(files=(), on_path=None, not_executable=()):
    return {'which': lambda name: on_path if name == 'codex' else None, 'is_file': lambda p: p in files,
            'is_executable': lambda p: p in files and p not in not_executable}


def test_the_executable_is_found_on_path_first_then_at_the_known_locations():
    state = locate(**_probes(files={'/opt/homebrew/bin/codex', NEW}, on_path='/opt/homebrew/bin/codex'))
    assert state['actual_executable'] == '/opt/homebrew/bin/codex' and state['verdict'] == 'RESOLVES' and state['control_a_resolves'] is True
    state = locate(**_probes(files={CONTROL_A_FALLBACK}))                                    # the layout before the 2026-10-02 app update
    assert state['actual_executable'] == CONTROL_A_FALLBACK and state['verdict'] == 'RESOLVES' and state['fallback_is_file'] is True
    assert require(**_probes(files={NEW})) == NEW                                            # the layout after it
    assert KNOWN_LOCATIONS == (CONTROL_A_FALLBACK, NEW)


def test_a_stale_fallback_is_detected_when_the_executable_moved():
    state = locate(**_probes(files={NEW}))                                                   # this Mac on 2026-10-02: not on PATH, old file gone
    assert state['verdict'] == 'STALE_FALLBACK' and state['control_a_resolves'] is False and state['fallback_is_file'] is False
    assert state['control_a_would_use'] == CONTROL_A_FALLBACK and state['actual_executable'] == NEW and state['on_path'] is None
    assert state['known_locations_present'] == [NEW]
    # a PATH entry that points at nothing is not a resolution either
    broken = locate(**_probes(files={NEW}, on_path='/usr/local/bin/codex'))
    assert broken['control_a_resolves'] is False and broken['verdict'] == 'STALE_FALLBACK' and broken['actual_executable'] == NEW
    # a file that is present but not executable does not count
    assert locate(**_probes(files={CONTROL_A_FALLBACK, NEW}, not_executable={CONTROL_A_FALLBACK}))['verdict'] == 'STALE_FALLBACK'


def test_a_clear_failure_when_neither_path_nor_any_known_location_resolves():
    state = locate(**_probes())
    assert state['verdict'] == 'NOT_INSTALLED' and state['actual_executable'] is None and state['control_a_resolves'] is False
    with pytest.raises(CodexNotFound) as error:
        require(**_probes())
    text = str(error.value)
    assert text.startswith('CODEX_EXECUTABLE_NOT_FOUND') and 'not on PATH' in text and all(p in text for p in KNOWN_LOCATIONS)


def test_the_diagnostic_mirrors_control_a_and_starts_nothing():
    for name in ('codex_bridge.py', 'isolated_session.py'):                                  # the rule this diagnostic reproduces
        source = (ROOT / 'agents' / name).read_text()
        assert f"shutil.which('codex') or '{CONTROL_A_FALLBACK}'" in source, name
    source = Path(codex_locator.__file__).read_text()
    assert not re.search(r'\bsubprocess\b|\bPopen\b|os\.system|\.read_bytes\(|open\(', source)   # it only looks; it runs and reads nothing
