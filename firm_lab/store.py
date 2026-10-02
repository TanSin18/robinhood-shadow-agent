"""The Firm Lab database: isolated, append-only where history matters, no portfolio state of any kind."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from . import MODE_BUILD_OBSERVE, SCHEMA_VERSION
from .errors import FirmLabError, IsolationError, TrialActivationNotAvailable

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS data_capabilities (capability TEXT PRIMARY KEY, status TEXT NOT NULL, provider TEXT, detail TEXT, "
    "updated_at TEXT NOT NULL)",
    # Point-in-time feature store. Rows are only ever inserted; a changed value is a new row with a higher revision.
    "CREATE TABLE IF NOT EXISTS feature_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, feature_name TEXT NOT NULL, "
    "value TEXT, source TEXT NOT NULL, source_timestamp TEXT, known_at TEXT NOT NULL, ingested_at TEXT NOT NULL, "
    "exchange_session_date TEXT NOT NULL, feature_version TEXT NOT NULL, provider TEXT, revision INTEGER NOT NULL DEFAULT 0, "
    "metadata_json TEXT NOT NULL DEFAULT '{}')",
    "CREATE INDEX IF NOT EXISTS feature_lookup ON feature_observations (instrument, feature_name, exchange_session_date, feature_version, id)",
    "CREATE TABLE IF NOT EXISTS universe_snapshots (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, source TEXT NOT NULL, "
    "symbols_json TEXT NOT NULL, source_hash TEXT, mode TEXT NOT NULL)",
    # Counterfactual decisions: what a rule would have selected. Deliberately no quantity, price, fill or account columns.
    "CREATE TABLE IF NOT EXISTS counterfactual_decisions (id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL, exchange_session_date TEXT NOT NULL, "
    "strategy_id TEXT NOT NULL, candidates_json TEXT NOT NULL, selected_instrument TEXT, features_used_json TEXT NOT NULL, "
    "provenance_json TEXT NOT NULL, label TEXT NOT NULL CHECK (label = 'DEVELOPMENT_ONLY'), record_hash TEXT NOT NULL UNIQUE)",
    "CREATE TABLE IF NOT EXISTS benchmark_definitions (benchmark_id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL, "
    "definition_json TEXT, defined_at TEXT, defined_by TEXT, note TEXT, implementation_status TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS benchmark_observations (id INTEGER PRIMARY KEY, benchmark_id TEXT NOT NULL, exchange_session_date TEXT NOT NULL, "
    "value TEXT NOT NULL, kind TEXT NOT NULL, source TEXT NOT NULL, known_at TEXT NOT NULL, ingested_at TEXT NOT NULL, "
    "UNIQUE (benchmark_id, exchange_session_date, kind, value, source))",
    "CREATE TABLE IF NOT EXISTS experiment_registry (experiment_id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL, "
    "registered_at TEXT, recipe_hash TEXT, start_at TEXT, end_at TEXT, status TEXT NOT NULL, notes TEXT)",
    # Raw option-chain facts if a provider ever supplies them. Storage schema only: nothing reads this to recommend a trade.
    "CREATE TABLE IF NOT EXISTS option_chain_observations (id INTEGER PRIMARY KEY, contract_id TEXT NOT NULL, underlying TEXT NOT NULL, "
    "expiry TEXT, strike TEXT, option_type TEXT, bid TEXT, ask TEXT, volume TEXT, open_interest TEXT, provider_implied_volatility TEXT, "
    "provider_delta TEXT, provider_gamma TEXT, provider_theta TEXT, provider_vega TEXT, provider TEXT NOT NULL, as_of TEXT NOT NULL, "
    "ingested_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ingest_runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, source TEXT NOT NULL, "
    "source_hash TEXT, status TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}')",
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)",
)
# Names that must never appear as Firm Lab tables while the mode is BUILD_OBSERVE (checked by a test).
FORBIDDEN_TABLE_WORDS = ('order', 'fill', 'position', 'paper_account', 'cash', 'portfolio')


def default_path(official_db) -> Path:
    """robinhood-diagnostics/firm_lab/firm_lab.db beside the runtime checkout (same convention as the analyst desk)."""
    return Path(official_db).resolve().parents[2] / 'robinhood-diagnostics' / 'firm_lab' / 'firm_lab.db'


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)


class FirmLabStore:
    def __init__(self, path, official_db=None, *, create=True):
        self.path = Path(path)
        if official_db is not None:
            official = Path(official_db).resolve()
            if self.path.resolve() == official or self.path.resolve().parent == official.parent:
                raise IsolationError('FIRM_LAB_DB_MUST_NOT_SHARE_THE_OFFICIAL_DIRECTORY')
        if not create and not self.path.is_file():
            raise FirmLabError('NOT_INITIALISED')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            for stmt in SCHEMA:
                db.execute(stmt)
            now = now_utc().isoformat()
            # The mode is set once, at creation. Nothing in this package can move it away from BUILD_OBSERVE.
            db.execute('INSERT OR IGNORE INTO firm_meta VALUES (?,?,?)', ('mode', MODE_BUILD_OBSERVE, now))
            db.execute('INSERT OR IGNORE INTO firm_meta VALUES (?,?,?)', ('schema_version', str(SCHEMA_VERSION), now))
            db.execute('INSERT OR IGNORE INTO firm_meta VALUES (?,?,?)', ('created_at', now, now))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------ mode
    def meta(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM firm_meta WHERE key=?', (key,)).fetchone()
        return row[0] if row else default

    def set_meta(self, key, value, now=None):
        if key == 'mode':
            raise TrialActivationNotAvailable('The Firm Lab mode cannot be changed here. Starting a trial is a separate operator decision.')
        at = (now or now_utc()).isoformat()
        with self.connect() as db:
            db.execute('INSERT INTO firm_meta VALUES (?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
                       (key, str(value), at))

    def mode(self) -> str:
        """Fails closed: a missing or unknown value is never read as permission."""
        value = self.meta('mode')
        if value is None:
            raise FirmLabError('MODE_MISSING')
        return value

    def request_trial_mode(self, *_, **__):
        raise TrialActivationNotAvailable('No registered Firm Lab trial exists. A hashed recipe, an explicit operator start and a '
                                          'resolution of the October research stop come first; none is built at this checkpoint.')

    # ------------------------------------------------------------------ audit
    def event(self, kind, payload, now=None):
        with self.connect() as db:
            db.execute('INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)', ((now or now_utc()).isoformat(), kind, canonical(payload)))

    def tables(self):
        with self.connect() as db:
            return sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))

    def counts(self):
        with self.connect() as db:
            return {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in
                    sorted(r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'"))}

    # ------------------------------------------------------------------ capabilities
    def set_capability(self, capability, status, provider=None, detail=None, now=None):
        from .capabilities import STATUSES
        if status not in STATUSES:
            raise FirmLabError(f'UNKNOWN_CAPABILITY_STATUS:{status}')
        with self.connect() as db:
            db.execute('INSERT INTO data_capabilities VALUES (?,?,?,?,?) ON CONFLICT(capability) DO UPDATE SET status=excluded.status, '
                       'provider=excluded.provider, detail=excluded.detail, updated_at=excluded.updated_at',
                       (capability, status, provider, detail, (now or now_utc()).isoformat()))

    def capability(self, capability) -> str:
        with self.connect() as db:
            row = db.execute('SELECT status FROM data_capabilities WHERE capability=?', (capability,)).fetchone()
        return row[0] if row else 'UNAVAILABLE'          # unknown capabilities are unavailable, never assumed

    def capabilities(self):
        with self.connect() as db:
            return [{'capability': c, 'status': s, 'provider': p, 'detail': d, 'updated_at': u} for c, s, p, d, u in
                    db.execute('SELECT capability, status, provider, detail, updated_at FROM data_capabilities ORDER BY rowid')]

    # ------------------------------------------------------------------ features (append-only)
    def add_feature(self, *, instrument, feature_name, value, source, source_timestamp, known_at, exchange_session_date,
                    feature_version, provider=None, metadata=None, now=None) -> str:
        """Inserts one observation unless the identical value from the same source is already the latest one.
        A different value for the same (instrument, feature, session, version) is appended as the next revision."""
        text = None if value is None else str(value)
        with self.connect() as db:
            last = db.execute('SELECT value, revision, source FROM feature_observations WHERE instrument=? AND feature_name=? AND '
                              'exchange_session_date=? AND feature_version=? ORDER BY id DESC LIMIT 1',
                              (instrument, feature_name, exchange_session_date, feature_version)).fetchone()
            if last is not None and last[0] == text and last[2] == source:
                return 'UNCHANGED'
            revision = 0 if last is None else int(last[1]) + 1
            db.execute('INSERT INTO feature_observations (instrument, feature_name, value, source, source_timestamp, known_at, ingested_at, '
                       'exchange_session_date, feature_version, provider, revision, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (instrument, feature_name, text, source, source_timestamp, known_at, (now or now_utc()).isoformat(),
                        exchange_session_date, feature_version, provider, revision, canonical(metadata or {})))
        return 'INSERTED' if revision == 0 else 'REVISED'

    def feature_history(self, instrument, feature_name, feature_version, *, known_by=None):
        """Latest revision per session, oldest session first, using only rows known at or before ``known_by``."""
        q = ('SELECT exchange_session_date, value, revision, source, source_timestamp, known_at FROM feature_observations '
             'WHERE instrument=? AND feature_name=? AND feature_version=?' + (' AND known_at<=?' if known_by else '') + ' ORDER BY id')
        args = (instrument, feature_name, feature_version) + ((known_by,) if known_by else ())
        latest = {}
        with self.connect() as db:
            for session, value, revision, source, stamp, known in db.execute(q, args):
                latest[session] = {'exchange_session_date': session, 'value': value, 'revision': revision, 'source': source,
                                   'source_timestamp': stamp, 'known_at': known}
        return [latest[k] for k in sorted(latest)]

    # ------------------------------------------------------------------ universe, counterfactuals, benchmarks, experiments
    def add_universe_snapshot(self, *, timestamp, source, symbols, source_hash):
        with self.connect() as db:
            db.execute('INSERT INTO universe_snapshots (timestamp, source, symbols_json, source_hash, mode) VALUES (?,?,?,?,?)',
                       (timestamp, source, canonical(sorted(symbols)), source_hash, self.mode()))

    def add_counterfactual(self, *, timestamp, exchange_session_date, strategy_id, candidates, selected_instrument, features_used, provenance):
        from . import DEVELOPMENT_ONLY
        record_hash = hashlib.sha256(canonical({'t': timestamp, 's': exchange_session_date, 'id': strategy_id, 'c': candidates,
                                                'sel': selected_instrument, 'p': provenance}).encode()).hexdigest()
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO counterfactual_decisions (timestamp, exchange_session_date, strategy_id, candidates_json, '
                             'selected_instrument, features_used_json, provenance_json, label, record_hash) VALUES (?,?,?,?,?,?,?,?,?)',
                             (timestamp, exchange_session_date, strategy_id, canonical(candidates), selected_instrument,
                              canonical(features_used), canonical(provenance), DEVELOPMENT_ONLY, record_hash))
        return {'record_hash': record_hash, 'inserted': cur.rowcount == 1}

    def latest_counterfactual(self, strategy_id):
        with self.connect() as db:
            row = db.execute('SELECT timestamp, exchange_session_date, strategy_id, candidates_json, selected_instrument, features_used_json, '
                             'provenance_json, label, record_hash FROM counterfactual_decisions WHERE strategy_id=? ORDER BY id DESC LIMIT 1',
                             (strategy_id,)).fetchone()
        if not row:
            return None
        return {'timestamp': row[0], 'exchange_session_date': row[1], 'strategy_id': row[2], 'candidates': json.loads(row[3]),
                'selected_instrument': row[4], 'features_used': json.loads(row[5]), 'provenance': json.loads(row[6]), 'label': row[7],
                'record_hash': row[8]}

    def active_experiments(self):
        with self.connect() as db:
            return [r[0] for r in db.execute("SELECT experiment_id FROM experiment_registry WHERE status='ACTIVE'")]
