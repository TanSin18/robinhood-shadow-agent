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
    "CREATE TABLE IF NOT EXISTS ingest_runs (id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, source TEXT NOT NULL, "
    "source_hash TEXT, status TEXT NOT NULL, detail_json TEXT NOT NULL DEFAULT '{}')",
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, payload_json TEXT NOT NULL)",
)
# Raw provider data (Checkpoint 3). Rows are only ever inserted. The UNIQUE key includes the content hash, so an identical
# record is ignored (resumable ingestion) and a changed record is kept as a new row beside the old one.
_PROV = ("provider TEXT NOT NULL, source_id TEXT NOT NULL, source_timestamp TEXT NOT NULL, known_at TEXT NOT NULL, ingested_at TEXT NOT NULL, "
         "schema_version TEXT NOT NULL, content_hash TEXT NOT NULL, run_id INTEGER NOT NULL")
RAW_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS provider_runs (id INTEGER PRIMARY KEY, batch TEXT NOT NULL, provider TEXT NOT NULL, domain TEXT NOT NULL, method TEXT NOT NULL, "
    "instrument TEXT, started_at TEXT NOT NULL, finished_at TEXT NOT NULL, status TEXT NOT NULL, reason TEXT, received INTEGER NOT NULL, "
    "stored INTEGER NOT NULL, duplicates INTEGER NOT NULL, issues_json TEXT NOT NULL DEFAULT '[]', diagnostics_json TEXT NOT NULL DEFAULT '{}', "
    "provenance_json TEXT)",
    "CREATE TABLE IF NOT EXISTS provider_connections (provider TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT, checked_at TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS filing_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, cik TEXT NOT NULL, accession_number TEXT NOT NULL, "
    "form_type TEXT NOT NULL, filing_date TEXT NOT NULL, report_date TEXT, accepted_timestamp TEXT NOT NULL, accepted_timestamp_raw TEXT NOT NULL, "
    "accepted_timestamp_basis TEXT NOT NULL, header_acceptance_raw TEXT, url TEXT NOT NULL, primary_document TEXT, items TEXT, entity_name TEXT, "
    "series_id TEXT, class_id TEXT, accepted_timestamp_header TEXT, accepted_timestamp_json TEXT, acceptance_time_conflict TEXT, "
    "acceptance_time_json_offset_seconds TEXT, " + _PROV + ", UNIQUE (accession_number, instrument, content_hash))",
    "CREATE TABLE IF NOT EXISTS intraday_bar_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, bar_start TEXT NOT NULL, "
    "bar_start_raw TEXT NOT NULL, interval TEXT NOT NULL, open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL, close TEXT NOT NULL, "
    "volume TEXT NOT NULL, vwap TEXT, trade_count TEXT, session TEXT NOT NULL, exchange_session_date TEXT NOT NULL, adjusted TEXT NOT NULL, "
    "feed TEXT NOT NULL, " + _PROV + ", UNIQUE (provider, instrument, bar_start, interval, adjusted, content_hash))",
    "CREATE TABLE IF NOT EXISTS trade_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, trade_timestamp TEXT NOT NULL, "
    "trade_timestamp_raw TEXT NOT NULL, participant_timestamp_raw TEXT, price TEXT NOT NULL, size TEXT NOT NULL, decimal_size TEXT, exchange TEXT NOT NULL, "
    "conditions_json TEXT, trade_id TEXT NOT NULL, sequence_number TEXT, tape TEXT, trf_id TEXT, correction TEXT, feed TEXT NOT NULL, " + _PROV
    + ", UNIQUE (provider, instrument, exchange, trade_id, trade_timestamp_raw, content_hash))",
    "CREATE TABLE IF NOT EXISTS quote_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, quote_timestamp TEXT NOT NULL, "
    "quote_timestamp_raw TEXT NOT NULL, participant_timestamp_raw TEXT, bid TEXT NOT NULL, bid_size TEXT NOT NULL, bid_exchange TEXT, ask TEXT NOT NULL, "
    "ask_size TEXT NOT NULL, ask_exchange TEXT, conditions_json TEXT, indicators_json TEXT, sequence_number TEXT, tape TEXT, feed TEXT NOT NULL, "
    + _PROV + ", UNIQUE (provider, instrument, quote_timestamp_raw, sequence_number, content_hash))",
    "CREATE TABLE IF NOT EXISTS fundamental_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, provider_instrument_id TEXT, "
    "dimension TEXT NOT NULL, reporting_basis TEXT NOT NULL, fiscal_period TEXT, period_end TEXT NOT NULL, calendar_date TEXT, filing_date TEXT NOT NULL, "
    "filing_timestamp TEXT NOT NULL, provider_datekey TEXT, last_updated TEXT NOT NULL, metric TEXT NOT NULL, provider_metric TEXT, value TEXT NOT NULL, "
    "units TEXT NOT NULL, currency TEXT, is_delisted TEXT, " + _PROV
    + ", UNIQUE (provider, instrument, dimension, period_end, filing_date, metric, content_hash))",
    "CREATE TABLE IF NOT EXISTS corporate_action_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, action_type TEXT NOT NULL, "
    "provider_action TEXT NOT NULL, effective_date TEXT NOT NULL, effective_date_basis TEXT, announcement_timestamp TEXT NOT NULL, value TEXT, "
    "value_meaning TEXT, currency TEXT, contra_instrument TEXT, contra_name TEXT, name TEXT, record_date TEXT, pay_date TEXT, distribution_type TEXT, "
    "source_record TEXT, " + _PROV
    + ", UNIQUE (provider, instrument, provider_action, effective_date, contra_instrument, content_hash))",
    # Greeks and implied volatility are stored only as provider values, with who computed them and under which model.
    "CREATE TABLE IF NOT EXISTS option_chain_observations (id INTEGER PRIMARY KEY, contract_id TEXT NOT NULL, underlying TEXT NOT NULL, "
    "expiration TEXT NOT NULL, strike TEXT NOT NULL, option_type TEXT NOT NULL, quote_timestamp TEXT NOT NULL, quote_timestamp_raw TEXT, bid TEXT NOT NULL, "
    "bid_size TEXT, ask TEXT NOT NULL, ask_size TEXT, volume TEXT NOT NULL, open_interest TEXT NOT NULL, open_interest_timestamp TEXT, "
    "provider_implied_volatility TEXT, provider_delta TEXT, provider_gamma TEXT, provider_theta TEXT, provider_vega TEXT, provider_rho TEXT, "
    "greeks_provider TEXT, greeks_model TEXT, greeks_model_version TEXT, greeks_timestamp TEXT, underlying_price TEXT, underlying_timestamp TEXT, "
    + _PROV + ", UNIQUE (provider, contract_id, quote_timestamp, content_hash))",
    # Treasury bill auction results exactly as published (text), for the 70/30 ruler's bill leg. A republished record with
    # different values is a second row; the index then stops instead of choosing between them.
    "CREATE TABLE IF NOT EXISTS treasury_auction_observations (id INTEGER PRIMARY KEY, cusip TEXT NOT NULL, security_type TEXT NOT NULL, "
    "security_term TEXT NOT NULL, auction_date TEXT NOT NULL, issue_date TEXT NOT NULL, maturity_date TEXT NOT NULL, high_discount_rate TEXT NOT NULL, "
    "price_per100 TEXT NOT NULL, closing_time_comp TEXT, reopening TEXT, original_security_term TEXT, record_date TEXT, result_known_at TEXT NOT NULL, "
    "feed TEXT, " + _PROV + ", UNIQUE (provider, cusip, auction_date, content_hash))",
    # Company facts from SEC XBRL data, one row per appearance of a fact in a filing. `accepted_timestamp` (the filing-header
    # time) is when the fact became known. A later filing with a different value for the same period is a new row with a
    # higher `version`; an earlier row is never changed.
    "CREATE TABLE IF NOT EXISTS fundamental_fact_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, cik TEXT NOT NULL, taxonomy TEXT NOT NULL, "
    "concept TEXT NOT NULL, normalized_field TEXT NOT NULL, mapping_rule TEXT NOT NULL, agreeing_concepts TEXT, unit TEXT NOT NULL, value TEXT NOT NULL, "
    "period_type TEXT NOT NULL, period_start TEXT, period_end TEXT NOT NULL, relation_to_filing TEXT NOT NULL, filing_fiscal_year TEXT, "
    "filing_fiscal_period TEXT, form TEXT NOT NULL, accession_number TEXT NOT NULL, filing_date TEXT NOT NULL, frame TEXT, accepted_timestamp TEXT NOT NULL, "
    "accepted_timestamp_json TEXT, acceptance_time_conflict TEXT, version INTEGER NOT NULL, is_restatement TEXT NOT NULL, prior_value TEXT, "
    "confirmed_in_filing TEXT NOT NULL, source_url TEXT NOT NULL, filing_document_url TEXT, entity_name TEXT, " + _PROV
    + ", UNIQUE (provider, instrument, normalized_field, period_end, accession_number, content_hash))",      # the hash covers the whole record
    # Earnings-release filings (8-K, Item 2.02): what was filed and when the SEC accepted it. Facts only; no sentiment, score or signal column.
    "CREATE TABLE IF NOT EXISTS earnings_event_observations (id INTEGER PRIMARY KEY, instrument TEXT NOT NULL, cik TEXT NOT NULL, accession_number TEXT NOT NULL, "
    "form TEXT NOT NULL, items TEXT NOT NULL, event_date TEXT NOT NULL, filing_date TEXT NOT NULL, accepted_timestamp TEXT NOT NULL, "
    "accepted_timestamp_header TEXT NOT NULL, accepted_timestamp_json TEXT NOT NULL, acceptance_time_conflict TEXT NOT NULL, acceptance_session TEXT NOT NULL, "
    "filing_url TEXT NOT NULL, primary_document_url TEXT, release_document_url TEXT NOT NULL, release_document_type TEXT, fiscal_period_end TEXT NOT NULL, "
    "fiscal_period_basis TEXT, periodic_accession_number TEXT, transcript_available TEXT NOT NULL, entity_name TEXT, " + _PROV
    + ", UNIQUE (provider, instrument, accession_number, content_hash))",
)
ADDED_COLUMNS = {'filing_observations': ('accepted_timestamp_header', 'accepted_timestamp_json', 'acceptance_time_conflict',
                                         'acceptance_time_json_offset_seconds'),
                 'corporate_action_observations': ('record_date', 'pay_date', 'distribution_type', 'source_record')}
RAW_TABLES = ('filing_observations', 'intraday_bar_observations', 'trade_observations', 'quote_observations', 'fundamental_observations',
              'corporate_action_observations', 'option_chain_observations', 'treasury_auction_observations',
              'fundamental_fact_observations', 'earnings_event_observations')
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
            # Checkpoint 1 created an option table that never held a row; its Checkpoint 3 shape adds provenance and model fields.
            old = [r[1] for r in db.execute('PRAGMA table_info(option_chain_observations)')]
            if old and 'run_id' not in old:
                if db.execute('SELECT COUNT(*) FROM option_chain_observations').fetchone()[0]:
                    raise FirmLabError('OPTION_TABLE_HAS_ROWS_IN_THE_OLD_SHAPE: refusing to replace it')
                db.execute('DROP TABLE option_chain_observations')
                db.execute('INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)',
                           (now, 'SCHEMA_CHANGE', canonical({'table': 'option_chain_observations', 'change': 'empty table recreated with '
                                                             'provenance and model columns', 'rows_before': 0})))
            for stmt in RAW_SCHEMA:
                db.execute(stmt)
            # Columns added after a table was first created. Existing rows are left exactly as they were stored (the new
            # columns stay empty on them); nothing is back-filled.
            for table, columns in ADDED_COLUMNS.items():
                have = {r[1] for r in db.execute(f'PRAGMA table_info({table})')}
                missing = [c for c in columns if c not in have]
                for column in missing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {column} TEXT')
                if missing:
                    db.execute('INSERT INTO events(at, kind, payload_json) VALUES (?,?,?)',
                               (now, 'SCHEMA_CHANGE', canonical({'table': table, 'change': 'columns added; existing rows not rewritten',
                                                                 'columns': missing, 'rows_before': db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]})))
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
    def set_capability(self, capability, status, provider=None, detail=None, now=None, *, evidence=None, reason=''):
        """Kept for callers; the rule lives in capabilities.set_status (AVAILABLE needs a validated source)."""
        from . import capabilities
        capabilities.set_status(self, capability, status, provider, detail, now, evidence=evidence, reason=reason)

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
