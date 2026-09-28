"""Catch deterministic connection leaks, including without garbage collection."""
import sqlite3
import subprocess
import sys

import pytest

from test_inbox_lanes import setup_runtime


def test_inbox_connection_commits_and_closes(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with inbox.connect() as db:
        db.execute("INSERT INTO weekly_reports VALUES ('test', '{}')")
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with inbox.connect() as reopened:
        assert reopened.execute('SELECT count(*) FROM weekly_reports').fetchone()[0] == 1


def test_inbox_connection_rolls_back_and_closes_on_error(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with pytest.raises(ValueError, match='abort'):
        with inbox.connect() as db:
            db.execute("INSERT INTO weekly_reports VALUES ('test', '{}')")
            raise ValueError('abort')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with inbox.connect() as reopened:
        assert reopened.execute('SELECT count(*) FROM weekly_reports').fetchone()[0] == 0


def test_repeated_http_refresh_keeps_data_and_assets_available_under_fd_limit(tmp_path):
    # Isolate both the FD ceiling and disabled GC from pytest and the real service.
    # A connection left to GC makes real HTTP requests fail under this workload.
    result = subprocess.run([sys.executable, '-c', r'''
import gc, resource, sys, threading
from pathlib import Path
from urllib.request import urlopen
sys.path.insert(0, 'tests')
from test_inbox_lanes import setup_runtime
from agents.inbox_web import make_server
from agents.readiness import OperationalProof
inbox, _ = setup_runtime(Path(sys.argv[1]))
root = Path.cwd()
proof = OperationalProof(root=root, config_path=root/'config/settings.yaml',
    database=inbox.path, test_report=Path(sys.argv[1])/'absent.xml',
    test_manifest=Path(sys.argv[1])/'absent.json')
gc.collect(); gc.disable()
soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
resource.setrlimit(resource.RLIMIT_NOFILE, (min(192, hard), hard))
server = make_server(inbox, port=0, proof=proof, service_check=lambda: True)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
url = f'http://127.0.0.1:{server.server_port}'
try:
    for refresh in range(150):
        for route, mime in [('/', 'text/html'), ('/assets/dashboard.css', 'text/css'), ('/assets/dashboard.js', 'text/javascript'), ('/assets/decision-room.js', 'text/javascript')]:
            with urlopen(url+route, timeout=5) as response:
                assert response.status == 200, (refresh, route)
                assert mime in response.headers['Content-Type']
                assert response.read()
    with inbox.connect() as db:
        assert db.execute('SELECT count(*) FROM cycle_runs').fetchone()[0] == 0
    print('150 refreshes plus 450 asset requests passed; zero daily claims')
finally:
    server.shutdown(); server.server_close(); thread.join()
''', str(tmp_path)], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
