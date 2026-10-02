"""Where is the Codex command-line executable, and would Control A find it? A read-only diagnostic.

Control A (unchanged by this file) resolves the executable in two steps: ``codex`` on PATH, else one fixed location
inside the ChatGPT app. On 2026-10-02 an app update moved the executable, so that fixed location went stale. This
module answers three questions without starting anything:

  * where the executable actually is now,
  * what Control A's own two-step rule would pick, and whether that is a real file,
  * whether the fixed fallback is stale (missing while the executable exists elsewhere).

Run it by hand:  python -m agents.desk.codex_locator
"""
from __future__ import annotations

import json
import os
import shutil

# The fallback written into Control A's agents/codex_bridge.py and agents/isolated_session.py (a test keeps this in step).
CONTROL_A_FALLBACK = '/Applications/ChatGPT.app/Contents/Resources/codex'
# Places the ChatGPT app has shipped the executable. Newest layout last.
KNOWN_LOCATIONS = (CONTROL_A_FALLBACK, '/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
RESOLVES, STALE_FALLBACK, NOT_INSTALLED = 'RESOLVES', 'STALE_FALLBACK', 'NOT_INSTALLED'


class CodexNotFound(RuntimeError):
    """No Codex executable on PATH or at any known location."""


def _usable(path, is_file, is_executable) -> bool:
    return bool(path) and is_file(path) and is_executable(path)


def locate(*, which=shutil.which, is_file=os.path.isfile, is_executable=lambda p: os.access(p, os.X_OK)) -> dict:
    """What exists and what Control A would use. Starts no process and reads no file content."""
    on_path = which('codex')
    found = [p for p in KNOWN_LOCATIONS if _usable(p, is_file, is_executable)]
    control_a_uses = on_path or CONTROL_A_FALLBACK                       # exactly Control A's rule
    control_a_resolves = _usable(control_a_uses, is_file, is_executable)
    actual = on_path if _usable(on_path, is_file, is_executable) else (found[0] if found else None)
    if control_a_resolves:
        verdict = RESOLVES
    elif actual:
        verdict = STALE_FALLBACK                                         # the executable exists, but not where Control A looks
    else:
        verdict = NOT_INSTALLED
    return {'on_path': on_path, 'known_locations_present': found, 'actual_executable': actual, 'control_a_would_use': control_a_uses,
            'control_a_resolves': control_a_resolves, 'fallback_is_file': _usable(CONTROL_A_FALLBACK, is_file, is_executable), 'verdict': verdict}


def require(**probes) -> str:
    """The executable that actually exists (PATH first, then the known locations), or a clear error naming what was checked."""
    state = locate(**probes)
    if state['actual_executable']:
        return state['actual_executable']
    raise CodexNotFound('CODEX_EXECUTABLE_NOT_FOUND: "codex" is not on PATH and none of these is an executable file: ' + ', '.join(KNOWN_LOCATIONS))


if __name__ == '__main__':
    print(json.dumps(locate(), indent=1))
