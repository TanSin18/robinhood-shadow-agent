"""The historical research database: one separate file, append-only, versioned, holding no trade.

Licensed vendor data lives only here. The file is refused inside a Git work tree, beside the registered database, or
when it already holds anything that looks like an execution table. Rows are content-addressed: storing the same content
twice adds nothing, and different content for the same security and year becomes the next version while the earlier
one stays. UPDATE and DELETE are refused by triggers on every table.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from datetime import datetime, timezone
from pathlib import Path

from . import DATABASE_ROLE, POLICY_VERSION

CANONICAL_OFFICIAL = Path('/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db')
JSON_TABLES = ('history_sources', 'history_captures', 'history_securities', 'history_actions', 'history_index_events', 'history_bar_rejections',
               'history_quarantine', 'history_universe', 'history_datasets', 'history_reservations', 'history_reports')
BAR_TABLE = 'history_bars'
BAR_COLUMNS = ('sessions', 'open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return', 'provider_updated')
FORBIDDEN_TABLE_WORDS = ('order', 'fill', 'position', 'account', 'cash', 'portfolio', 'broker')
OFFICIAL_TABLES = {'paper_accounts', 'cycle_runs', 'orders', 'fills', 'positions', 'accounts'}
FIRST, EXTENDED, SCALE_ONLY, VALUE_CHANGE = 'FIRST', 'EXTENDED', 'SCALE_ONLY', 'VALUE_CHANGE'


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refuse_official(target, official_db):
    for raw in (official_db, CANONICAL_OFFICIAL):
        official = Path(raw).resolve()
        if target == official or official.parent in target.parents or (target.exists() and official.exists() and target.samefile(official)):
            raise ValueError('OFFICIAL_DATABASE_FORBIDDEN')


def _inside_a_repository(target) -> bool:
    return any((parent / '.git').exists() for parent in target.parents)


def classify_change(old, new) -> dict:
    """How a new version of one security-year differs from the version before it. Never used to alter either."""
    before, after = dict(zip(old['sessions'], range(len(old['sessions'])))), dict(zip(new['sessions'], range(len(new['sessions']))))
    removed = [s for s in before if s not in after]
    common = [s for s in before if s in after]
    changed, factors = 0, set()
    for s in common:
        i, j = before[s], after[s]
        same = all(old[c][i] == new[c][j] for c in ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted'))
        if same:
            continue
        changed += 1
        try:
            ratios = [float(new[c][j]) / float(old[c][i]) for c in ('open', 'high', 'low', 'close')]
            volume = float(new['volume'][j]) * ratios[3] / float(old['volume'][i]) if float(old['volume'][i]) else 1.0
            scale = max(ratios) - min(ratios) < 1e-3 * ratios[3] and abs(volume - 1) < 1e-2 and old['close_unadjusted'][i] == new['close_unadjusted'][j]
            factors.add(round(ratios[3], 4) if scale else None)
        except (ValueError, ZeroDivisionError):
            factors.add(None)
    if removed or None in factors or len(factors) > 1:
        kind = VALUE_CHANGE
    elif factors:
        kind = SCALE_ONLY
    else:
        kind = EXTENDED
    return {'change': kind, 'sessions_changed': changed, 'sessions_removed': len(removed), 'sessions_added': len(after) - len(common),
            'scale_factor': next(iter(factors)) if kind == SCALE_ONLY else None}


class HistoryStore:
    def __init__(self, path, *, official_db=CANONICAL_OFFICIAL, create=False, read_only=False):
        target = Path(path).resolve()
        _refuse_official(target, official_db)
        if _inside_a_repository(target):
            raise ValueError('HISTORY_DATABASE_INSIDE_A_REPOSITORY')                # licensed data must never be committable
        if not target.exists():
            if not create or read_only:
                raise ValueError('HISTORY_DATABASE_REQUIRED')
            target.parent.mkdir(parents=True, exist_ok=True)
        self.path = target
        self.db = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=120) if read_only else sqlite3.connect(target, timeout=120)
        try:
            names = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if names & OFFICIAL_TABLES or any(word in name for name in names for word in FORBIDDEN_TABLE_WORDS):
                raise ValueError('EXECUTION_TABLE_FORBIDDEN')
            if names and 'firm_meta' not in names:
                raise ValueError('NOT_A_HISTORY_DATABASE')
            if not names:
                if read_only:
                    raise ValueError('NOT_A_HISTORY_DATABASE')
                self._create()
            meta = dict(self.db.execute('SELECT key, value FROM firm_meta'))
            if meta.get('mode') != 'BUILD_OBSERVE' or meta.get('database_role') != DATABASE_ROLE:
                raise ValueError('NOT_A_HISTORY_DATABASE')
        except Exception:
            self.db.close()
            raise

    def _create(self):
        at = now_utc()
        with self.db:
            self.db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
            for key, value in (('mode', 'BUILD_OBSERVE'), ('database_role', DATABASE_ROLE), ('policy_version', POLICY_VERSION)):
                self.db.execute('INSERT INTO firm_meta VALUES (?,?,?)', (key, value, at))
            for table in JSON_TABLES:
                self.db.execute(f'CREATE TABLE {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
            self.db.execute(f'CREATE TABLE {BAR_TABLE} (id TEXT PRIMARY KEY, source TEXT NOT NULL, security_id TEXT NOT NULL, year INTEGER NOT NULL, '
                            'version INTEGER NOT NULL, row_count INTEGER NOT NULL, first_session TEXT NOT NULL, last_session TEXT NOT NULL, capture_id TEXT NOT NULL, '
                            'change TEXT NOT NULL, payload BLOB NOT NULL, created_at TEXT NOT NULL, UNIQUE(source, security_id, year, version))')
            self.db.execute(f'CREATE INDEX {BAR_TABLE}_security ON {BAR_TABLE}(security_id, year, version)')
            for table in JSON_TABLES + (BAR_TABLE, 'firm_meta'):
                for action in ('UPDATE', 'DELETE'):
                    self.db.execute(f'CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON {table} BEGIN '
                                    "SELECT RAISE(ABORT, 'APPEND_ONLY'); END")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.db.close()

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------------------------------------ generic rows
    def put(self, table, payload, *, identity=None, at=None) -> bool:
        """Stores one content-addressed row. True when it was new."""
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        with self.db:
            return bool(self.db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)',
                                        (identity or content_hash(payload), canonical(payload), at or now_utc())).rowcount)

    def put_many(self, table, payloads, *, at=None) -> int:
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        at = at or now_utc()
        with self.db:
            before = self.db.total_changes
            self.db.executemany(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)', ((content_hash(p), canonical(p), at) for p in payloads))
            return self.db.total_changes - before

    def rows(self, table):
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        for identity, payload, created in self.db.execute(f'SELECT id, payload, created_at FROM {table} ORDER BY created_at, id'):
            yield identity, json.loads(payload), created

    def count(self, table) -> int:
        if table not in JSON_TABLES + (BAR_TABLE,):
            raise ValueError('UNKNOWN_TABLE')
        return self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    # ------------------------------------------------------------------------------------------------------- bars
    def put_bars(self, source, security_id, year, columns, capture_id, *, at=None) -> dict:
        """Stores one security-year block exactly as supplied. Identical content is a duplicate; different content is the
        next version, with a record of how it differs. The earlier version is never touched."""
        if tuple(sorted(columns)) != tuple(sorted(BAR_COLUMNS)) or len({len(columns[c]) for c in BAR_COLUMNS}) != 1 or not columns['sessions']:
            raise ValueError('MALFORMED_BAR_BLOCK')
        if list(columns['sessions']) != sorted(set(columns['sessions'])) or any(s[:4] != str(year) for s in columns['sessions']):
            raise ValueError('MALFORMED_BAR_BLOCK')
        body = {c: list(columns[c]) for c in BAR_COLUMNS}
        identity = content_hash([source, security_id, int(year), body])
        if self.db.execute(f'SELECT 1 FROM {BAR_TABLE} WHERE id=?', (identity,)).fetchone():
            return {'stored': False, 'id': identity}
        previous = self.db.execute(f'SELECT version, payload FROM {BAR_TABLE} WHERE source=? AND security_id=? AND year=? ORDER BY version DESC LIMIT 1',
                                   (source, security_id, int(year))).fetchone()
        if previous:
            change = classify_change(json.loads(zlib.decompress(previous[1])), body)
            version = previous[0] + 1
        else:
            change, version = {'change': FIRST}, 1
        with self.db:
            self.db.execute(f'INSERT INTO {BAR_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (identity, source, security_id, int(year), version, len(body['sessions']), body['sessions'][0], body['sessions'][-1], capture_id,
                             canonical(change), zlib.compress(canonical(body).encode(), 6), at or now_utc()))
        return {'stored': True, 'id': identity, 'version': version, **change}

    def bar_blocks(self, security_id, *, source=None, through_capture_time=None):
        """The current block of every year of one security: the highest version (optionally, the highest stored by a time)."""
        query = f'SELECT year, version, id, payload, created_at, capture_id FROM {BAR_TABLE} WHERE security_id=?'
        args = [security_id]
        if source:
            query, args = query + ' AND source=?', args + [source]
        latest = {}
        for year, version, identity, payload, created, capture in self.db.execute(query + ' ORDER BY year, version', args):
            if through_capture_time is None or created <= through_capture_time:
                latest[year] = (version, identity, payload, capture)
        for year in sorted(latest):
            version, identity, payload, capture = latest[year]
            yield {'year': year, 'version': version, 'id': identity, 'capture_id': capture, **json.loads(zlib.decompress(payload))}

    def bars(self, security_id, **kw) -> dict:
        """{column: [values as supplied]} over every stored year, plus the identities of the blocks they came from."""
        out = {c: [] for c in BAR_COLUMNS}
        blocks = []
        for block in self.bar_blocks(security_id, **kw):
            for c in BAR_COLUMNS:
                out[c].extend(block[c])
            blocks.append(block['id'])
        out['blocks'] = blocks
        return out

    def first_seen(self, security_id, *, source=None) -> dict:
        """{session: the time the earliest stored block holding that session was stored}. A bar Firm Lab stored before the
        next session opened was held at the time; a bar stored later was not."""
        query = f'SELECT payload, created_at FROM {BAR_TABLE} WHERE security_id=?'
        args = [security_id]
        if source:
            query, args = query + ' AND source=?', args + [source]
        out = {}
        for payload, created in self.db.execute(query + ' ORDER BY created_at, version', args):
            for session in json.loads(zlib.decompress(payload))['sessions']:
                out.setdefault(session, created)
        return out

    def security_ids(self) -> list:
        return [r[0] for r in self.db.execute(f'SELECT DISTINCT security_id FROM {BAR_TABLE} ORDER BY 1')]

    def bar_summary(self) -> dict:
        row = self.db.execute(f'SELECT COUNT(DISTINCT security_id), MIN(first_session), MAX(last_session), COUNT(*) FROM {BAR_TABLE}').fetchone()
        rows = self.db.execute(f'SELECT COALESCE(SUM(row_count), 0) FROM {BAR_TABLE} b WHERE version = (SELECT MAX(version) FROM {BAR_TABLE} '
                               'WHERE source=b.source AND security_id=b.security_id AND year=b.year)').fetchone()[0]
        changes = {}
        for (change,) in self.db.execute(f'SELECT change FROM {BAR_TABLE}'):
            kind = json.loads(change)['change']
            changes[kind] = changes.get(kind, 0) + 1
        return {'securities': row[0], 'first_session': row[1], 'last_session': row[2], 'blocks': row[3], 'bars': rows, 'block_versions': changes}
