"""Firm Lab foundation: the no-fill barrier and the read-only wall around the Official database.

These tests were written before any other Firm Lab feature and must pass before anything is wired into
the Mac's dashboard."""
import ast
import hashlib
import sqlite3
from pathlib import Path

import pytest

import firm_lab
from firm_lab import boundary, official, store as store_mod
from firm_lab.errors import (IsolationError, NoExecutionEngine, NoFillInBuildObserve, RealExecutionDisabled,
                             TrialActivationNotAvailable)
from firm_lab.store import FirmLabStore

ROOT = Path(__file__).resolve().parents[1]


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _official(tmp_path):
    """A stand-in for the registered database, with a paper account, a fill and a decision record."""
    path = tmp_path / 'runtime' / 'data' / 'agent.db'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE paper_accounts (lane TEXT, track TEXT, payload TEXT, PRIMARY KEY(lane, track));
        CREATE TABLE fills (id INTEGER PRIMARY KEY, created_at TEXT, payload_json TEXT);
        CREATE TABLE decision_records (id INTEGER PRIMARY KEY, created_at TEXT, payload_json TEXT);
        CREATE TABLE decision_capsules (hash TEXT PRIMARY KEY, cycle_id TEXT, created_at TEXT, payload TEXT);
        INSERT INTO paper_accounts VALUES ('A', 'agent_alone', '{"settled_cash": "25000", "positions": {"SOXX": {"quantity": "2"}}}');
        INSERT INTO fills (created_at, payload_json) VALUES ('2026-10-01T14:02:11+00:00', '{"ticker": "SOXX"}');
        INSERT INTO decision_records (created_at, payload_json) VALUES ('2026-10-01T14:02:11+00:00', '{}');
    """)
    db.commit(); db.close()
    return path


def _lab(tmp_path, official_db=None):
    return FirmLabStore(tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db', official_db)


# ---------------------------------------------------------------- isolation (required tests 1-5)
def test_firm_lab_database_is_not_the_official_database(tmp_path):
    off = _official(tmp_path)
    lab = _lab(tmp_path, off)
    assert lab.path.resolve() != off.resolve() and lab.path.parent.resolve() != off.parent.resolve()
    assert store_mod.default_path(off) == tmp_path / 'robinhood-diagnostics' / 'firm_lab' / 'firm_lab.db'
    with pytest.raises(IsolationError):
        FirmLabStore(off, off)
    with pytest.raises(IsolationError):
        FirmLabStore(off.parent / 'firm_lab.db', off)
    assert not (off.parent / 'firm_lab.db').exists()


@pytest.mark.parametrize('statement', [
    "INSERT INTO fills (created_at, payload_json) VALUES ('x', '{}')",
    "UPDATE paper_accounts SET payload='{}'",
    "DELETE FROM decision_records",
    "CREATE TABLE firm_lab_was_here (x)",
    "DROP TABLE fills",
])
def test_firm_lab_cannot_write_the_official_database(tmp_path, statement):
    off = _official(tmp_path)
    before = _sha(off)
    with official.open_official(off) as db:
        assert db.execute('SELECT COUNT(*) FROM fills').fetchone()[0] == 1          # reading works
        with pytest.raises(sqlite3.Error):
            db.execute(statement)
        with pytest.raises(sqlite3.Error):
            db.executescript(statement)
    assert _sha(off) == before


def test_each_read_only_barrier_holds_on_its_own(tmp_path):
    off = _official(tmp_path)
    ro = sqlite3.connect(f'file:{off}?mode=ro', uri=True)                           # barrier 1 alone
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM fills")
    ro.close()
    rw = sqlite3.connect(off)                                                       # barrier 3 alone, on a writable connection
    rw.set_authorizer(official._authorize)
    with pytest.raises(sqlite3.DatabaseError):
        rw.execute("DELETE FROM fills")
    rw.close()
    assert sqlite3.connect(off).execute('SELECT COUNT(*) FROM fills').fetchone()[0] == 1


def test_a_firm_lab_database_failure_leaves_the_official_database_alone(tmp_path):
    off = _official(tmp_path)
    before = _sha(off)
    broken = tmp_path / 'diag' / 'firm_lab' / 'firm_lab.db'
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b'this is not a sqlite database, it is a broken file')
    with pytest.raises(sqlite3.DatabaseError):
        FirmLabStore(broken, off)
    assert _sha(off) == before and official.capsules(off) == []


# ---------------------------------------------------------------- no fills (required tests 6-12)
@pytest.mark.parametrize('order', [
    {'instrument': 'NVDA', 'asset_class': 'stock', 'side': 'buy', 'quantity': '1'},
    {'instrument': 'SOXX', 'asset_class': 'etf', 'side': 'buy', 'quantity': '2.5'},
    {'instrument': 'NVDA 2026-12-18 C 200', 'asset_class': 'option', 'side': 'buy', 'quantity': '1'},
    {'instrument': 'SOXX', 'asset_class': 'etf', 'side': 'sell', 'quantity': '2'},
])
def test_build_observe_refuses_every_order_and_changes_nothing(tmp_path, order):
    off = _official(tmp_path)
    lab = _lab(tmp_path, off)
    assert lab.mode() == firm_lab.MODE_BUILD_OBSERVE
    official_before, counts_before = _sha(off), lab.counts()
    with pytest.raises(NoFillInBuildObserve):
        boundary.ExecutionBoundary(lab).submit(**order)
    counts_after = lab.counts()
    assert counts_after.pop('events') == counts_before.pop('events') + 1            # the refusal itself is recorded
    assert counts_after == counts_before                                            # no other row anywhere
    assert _sha(off) == official_before                                             # Control A's cash, positions and fills untouched
    with lab.connect() as db:
        assert db.execute("SELECT kind FROM events ORDER BY id DESC LIMIT 1").fetchone()[0] == 'FILL_REFUSED'


def test_firm_lab_has_no_table_that_could_hold_an_order_a_fill_a_position_or_cash(tmp_path):
    lab = _lab(tmp_path)
    for table in lab.tables():
        assert not any(word in table for word in store_mod.FORBIDDEN_TABLE_WORDS), table
    with lab.connect() as db:
        columns = [r[1] for r in db.execute('PRAGMA table_info(counterfactual_decisions)')]
    assert not any(word in c for c in columns for word in ('fill', 'quantity', 'price', 'cash', 'account', 'order'))


def test_real_orders_are_refused_in_every_mode_and_the_mode_cannot_be_changed(tmp_path):
    lab = _lab(tmp_path)
    gate = boundary.ExecutionBoundary(lab)
    with pytest.raises(RealExecutionDisabled):
        gate.real_order(instrument='NVDA', side='buy', quantity='1')
    with pytest.raises(TrialActivationNotAvailable):
        lab.set_meta('mode', firm_lab.MODE_REGISTERED_PAPER_TRIAL)
    with pytest.raises(TrialActivationNotAvailable):
        lab.request_trial_mode('trial-x')
    assert lab.mode() == firm_lab.MODE_BUILD_OBSERVE and lab.active_experiments() == []
    # Even if the stored mode were altered by hand, nothing fills: there is no engine behind the boundary.
    with lab.connect() as db:
        db.execute("UPDATE firm_meta SET value='REGISTERED_PAPER_TRIAL' WHERE key='mode'")
    with pytest.raises(NoExecutionEngine):
        gate.submit(instrument='NVDA', asset_class='stock', side='buy', quantity='1')
    with lab.connect() as db:
        db.execute("DELETE FROM firm_meta WHERE key='mode'")
    with pytest.raises(NoExecutionEngine):                                          # a missing mode is not permission either
        gate.submit(instrument='NVDA', asset_class='stock', side='buy', quantity='1')


# ---------------------------------------------------------------- structure: Firm Lab cannot reach the trading code
TRADING_MODULES = ('agents', 'broker', 'risk', 'data', 'research', 'eval', 'scripts', 'config', 'broker_proxy')
TRADING_NAMES = ('PaperBroker', 'PaperInbox', '_execute', 'RiskEngine', 'issue_desk_entry', 'submit_order', 'place_order')


def test_firm_lab_imports_nothing_from_the_trading_system():
    files = sorted((ROOT / 'firm_lab').glob('*.py'))
    assert files
    for path in files:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or '']
            for name in names:
                assert name.split('.')[0] not in TRADING_MODULES, f'{path.name} imports {name}'
            if isinstance(node, (ast.Name, ast.Attribute)):
                ident = node.id if isinstance(node, ast.Name) else node.attr
                assert ident not in TRADING_NAMES, f'{path.name} refers to {ident}'
    third_party = {'yaml', 'pydantic', 'jsonschema', 'openai', 'numpy', 'requests'}
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                assert not {a.name.split('.')[0] for a in node.names} & third_party, path.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                assert (node.module or '').split('.')[0] not in third_party, path.name
