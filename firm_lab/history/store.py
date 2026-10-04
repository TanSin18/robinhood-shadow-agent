"""The historical research database: one separate file, append-only, versioned, holding no trade.

Licensed vendor data lives only here. The file is refused inside a Git work tree, beside the registered database, in
any folder that holds an ``agent.db``, or when it already holds anything that looks like an execution table.

Versions. Bars are stored per security and calendar year. A new capture for a security and year is compared with the
current version: the same content adds nothing; anything else becomes the next version and the earlier one stays, also
when the vendor returns to content it supplied before. A capture that holds only some sessions of a year extends the
year. Inside the span of sessions a capture does hold, a stored session it no longer mentions is a removal (the vendor
took the bar out); outside that span nothing is removed. A file that lists only scattered rows (for example the rows
changed since a date) is ingested as ``sparse`` and removes nothing. "Current" is always the highest version.

Clocks. A version stored at the time this machine's clock showed is marked SYSTEM. A version stored with a time the
caller supplied is marked SUPPLIED: its time orders the versions and nothing more. Only a SYSTEM version can show that
a bar was held at the time. No supplied time may lie in the future or before a capture already stored.

What append-only means here. Every connection this package opens refuses UPDATE, DELETE and REPLACE through triggers.
That protects against the package's own mistakes. It does not protect against a person with the file and a SQL
prompt, who can drop a trigger or a table. What makes a change detectable is that every block carries the hash of its
content and every dataset names the blocks it was built from.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import DATABASE_ROLE, POLICY_VERSION
from .validate import block_reasons

CANONICAL_OFFICIAL = Path('/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db')
OFFICIAL_NAME = 'agent.db'
JSON_TABLES = ('history_captures', 'history_securities', 'history_actions', 'history_index_events', 'history_bar_rejections',
               'history_universe', 'history_datasets', 'history_reservations', 'history_reports')
BAR_TABLE = 'history_bars'
BAR_COLUMNS = ('sessions', 'open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return', 'provider_updated')
VALUE_COLUMNS = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted')
FORBIDDEN_TABLE_WORDS = ('order', 'fill', 'position', 'account', 'cash', 'portfolio', 'broker')
OFFICIAL_TABLES = {'paper_accounts', 'cycle_runs', 'orders', 'fills', 'positions', 'accounts'}
CLOCK_SKEW = timedelta(minutes=5)
FIRST, EXTENDED, SCALE_ONLY, VALUE_CHANGE = 'FIRST', 'EXTENDED', 'SCALE_ONLY', 'VALUE_CHANGE'
TOTAL_RETURN_READJUSTED, METADATA_ONLY = 'TOTAL_RETURN_READJUSTED', 'METADATA_ONLY'


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


def utc_time(value) -> str:
    """An ISO timestamp with an offset, as UTC. A time without an offset, or anything else, is refused: capture times are
    compared with exchange times, and a comparison of two different notations is not a comparison."""
    try:
        stamp = datetime.fromisoformat(str(value))
    except ValueError:
        raise ValueError('INVALID_CAPTURE_TIME') from None
    if stamp.tzinfo is None or stamp.utcoffset() is None or 'T' not in str(value):
        raise ValueError('INVALID_CAPTURE_TIME')
    return stamp.astimezone(timezone.utc).isoformat()


def refuse_private_location(path, official_db=CANONICAL_OFFICIAL) -> Path:
    """The resolved path, or an error when it is the registered database, beside it, in a folder holding an ``agent.db``,
    or inside a Git work tree. Used for the database and for every file written from it."""
    target = Path(path).resolve()
    for raw in (official_db, CANONICAL_OFFICIAL):
        official = Path(raw).resolve()
        if target == official or official.parent == target.parent or official.parent in target.parents or (target.exists() and official.exists() and target.samefile(official)):
            raise ValueError('OFFICIAL_DATABASE_FORBIDDEN')
    if target.name == OFFICIAL_NAME or (target.parent / OFFICIAL_NAME).exists():
        raise ValueError('OFFICIAL_DATABASE_FORBIDDEN')
    if any((parent / '.git').exists() for parent in target.parents):
        raise ValueError('HISTORY_DATABASE_INSIDE_A_REPOSITORY')            # licensed data must never be committable
    return target


def _same(old, i, new, j, columns) -> bool:
    return all(old[c][i] == new[c][j] for c in columns)


def when(text) -> datetime:
    """A stored or supplied timestamp as a time. Times are compared as times, never as text."""
    return datetime.fromisoformat(utc_time(text))


def _decimals(text) -> int:
    text = str(text)
    return len(text.split('.', 1)[1]) if '.' in text and 'e' not in text.lower() else 0


def _places(block) -> dict:
    """How finely each column of a block is printed: the most decimals any of its values shows. A vendor that drops
    trailing zeros prints "52" for 52.00; the column, not the single value, says how the price was rounded."""
    return {c: max((_decimals(v) for v in block[c] if v not in ('', None)), default=0) for c in ('open', 'high', 'low', 'close', 'volume')}


def _factor_range(old, i, new, j, old_places, new_places):
    """(lowest k, highest k, whether the volume could confirm it) for which this row is the old row with prices times k
    and volume divided by k, given how finely both were printed; None when no factor fits or the printed price itself
    moved. Every one of the four prices and the volume must agree on k: a different bar is not a rescale. A volume is
    taken as rounded to a whole share at best, however many decimals it is printed with ("1502.0" is 1502)."""
    try:
        if old['close_unadjusted'][i] != new['close_unadjusted'][j]:
            return None
        low, high = 0.0, float('inf')
        for c in ('open', 'high', 'low', 'close'):
            was, now = float(old[c][i]), float(new[c][j])
            a, b = 0.5 * 10.0 ** -old_places[c], 0.5 * 10.0 ** -new_places[c]
            low = max(low, (now - b) / (was + a))
            high = min(high, (now + b) / (was - a) if was - a > 0 else float('inf'))
        was, now = float(old['volume'][i]), float(new['volume'][j])
        a, b = max(0.5, 0.5 * 10.0 ** -old_places['volume']), max(0.5, 0.5 * 10.0 ** -new_places['volume'])
        says = False                                                    # whether the volume alone rules out "nothing was re-counted"
        if was > 0 or now > 0:
            least, most = (was - a) / (now + b), (was + a) / (now - b) if now - b > 0 else float('inf')
            low, high, says = max(low, least), min(high, most), not least <= 1.0 <= most
        slack = 1e-12 * max(1.0, low)
        return (low - slack, high + slack, says) if low <= high + 2 * slack else None
    except (ValueError, ZeroDivisionError):
        return None


def _common_factor(old, new, pairs):
    """The one factor every (old row, new row) pair of a block was rescaled by, or None. One is not a factor: a block
    whose rows moved by nothing more than their printing is not a rescale. At least one row's volume must itself show
    the re-count: with no volume anywhere, or volumes too small to move, nothing says that the shares were re-counted
    and not the prices changed."""
    if not pairs:
        return None
    old_places, new_places = _places(old), _places(new)
    low, high, ratios, traded = 0.0, float('inf'), [], False
    for i, j in pairs:
        found = _factor_range(old, i, new, j, old_places, new_places)
        if found is None:
            return None
        low, high, traded = max(low, found[0]), min(high, found[1]), traded or found[2]
        ratios.append(float(new['close'][j]) / float(old['close'][i]))
    if low > high or low <= 1.0 <= high or not traded:
        return None
    middle = sorted(ratios)[len(ratios) // 2]
    return min(max(middle, low), high)


def classify_change(old, new) -> dict:
    """How a new version of one security-year differs from the version before it. Never used to alter either.

    EXTENDED: only sessions after the previous last session were added. SCALE_ONLY: every session before some date was
    rescaled by one common factor (prices times k, volume divided by k, the printed price unchanged) and nothing else
    differs: a vendor re-adjusting for a later split. TOTAL_RETURN_READJUSTED: only the total-return close differs: a
    later dividend. METADATA_ONLY: only the provider's update stamp differs. VALUE_CHANGE: anything else, including a
    session that appeared in the past, a session that disappeared, one corrected print, or a "rescale" that only some
    rows or only some columns show."""
    before, after = {s: k for k, s in enumerate(old['sessions'])}, {s: k for k, s in enumerate(new['sessions'])}
    removed = [s for s in before if s not in after]
    added = [s for s in after if s not in before]
    common = [s for s in old['sessions'] if s in after]
    changed = [s for s in common if not _same(old, before[s], new, after[s], VALUE_COLUMNS)]
    total = sum(1 for s in common if old['close_total_return'][before[s]] != new['close_total_return'][after[s]])
    meta = sum(1 for s in common if old['provider_updated'][before[s]] != new['provider_updated'][after[s]])
    out = {'sessions_changed': len(changed), 'sessions_removed': len(removed), 'sessions_added': len(added), 'scale_factor': None}
    past_addition = bool(added) and bool(old['sessions']) and min(added) < old['sessions'][-1]
    if removed or past_addition:
        return {**out, 'change': VALUE_CHANGE}
    if changed:
        prefix = changed == common[:len(changed)]                           # a split re-adjusts every session before its date, and only those
        factor = _common_factor(old, new, [(before[s], after[s]) for s in changed]) if prefix else None
        if factor is not None:
            return {**out, 'change': SCALE_ONLY, 'scale_factor': round(float(factor), 6)}
        return {**out, 'change': VALUE_CHANGE}
    if added:
        return {**out, 'change': EXTENDED}
    if total:
        return {**out, 'change': TOTAL_RETURN_READJUSTED, 'sessions_changed': total}
    return {**out, 'change': METADATA_ONLY, 'sessions_changed': meta}


class HistoryStore:
    def __init__(self, path, *, official_db=CANONICAL_OFFICIAL, create=False, read_only=False):
        target = refuse_private_location(path, official_db)
        if not target.exists():
            if not create or read_only:
                raise ValueError('HISTORY_DATABASE_REQUIRED')
            target.parent.mkdir(parents=True, exist_ok=True)
        self.path = target
        self.db = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True, timeout=120) if read_only else sqlite3.connect(target, timeout=120)
        self._depth = 0
        self._capture = None                                               # the capture in progress: the (time, clock) pair ``begin_capture`` handed out
        try:
            self.db.execute('PRAGMA recursive_triggers=ON')                 # so that INSERT OR REPLACE meets the delete trigger and is refused
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
                            'change TEXT NOT NULL, content_hash TEXT NOT NULL, price_table TEXT NOT NULL, payload BLOB NOT NULL, created_at TEXT NOT NULL, '
                            'clock TEXT NOT NULL, UNIQUE(source, security_id, year, version))')
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

    @contextmanager
    def transaction(self):
        """Everything written inside is stored together or not at all."""
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.db.rollback()
                self._capture = None                                    # a capture's time is good for its own transaction only
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self.db.commit()
                self._capture = None

    # ------------------------------------------------------------------------------------------------ generic rows
    def put(self, table, payload, *, identity=None, at=None) -> bool:
        """Stores one row. True when it was new. An identity that is already stored is left exactly as it is."""
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        with self.transaction():
            return bool(self.db.execute(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)',
                                        (identity or content_hash(payload), canonical(payload), at or now_utc())).rowcount)

    def put_many(self, table, payloads, *, at=None) -> int:
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        at = at or now_utc()
        with self.transaction():
            before = self.db.total_changes
            self.db.executemany(f'INSERT OR IGNORE INTO {table} VALUES (?,?,?)', ((content_hash(p), canonical(p), at) for p in payloads))
            return self.db.total_changes - before

    def rows(self, table):
        if table not in JSON_TABLES:
            raise ValueError('UNKNOWN_TABLE')
        for identity, payload, created in self.db.execute(f'SELECT id, payload, created_at FROM {table} ORDER BY created_at, rowid'):
            yield identity, json.loads(payload), created

    def count(self, table) -> int:
        if table not in JSON_TABLES + (BAR_TABLE,):
            raise ValueError('UNKNOWN_TABLE')
        return self.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]

    def latest_capture_time(self):
        """The latest time any capture or bar version was stored under, as text in UTC; None in an empty store. Read
        from the database every time: another connection may have stored something since."""
        times = [r[0] for r in self.db.execute(f'SELECT MAX(created_at) FROM history_captures UNION ALL SELECT MAX(created_at) FROM {BAR_TABLE}') if r[0]]
        return max(times, key=when) if times else None       # every stored time is UTC in one notation, so the text maximum per table is its latest

    def capture_clock(self, at=None) -> tuple:
        """(time, clock) for a write. Without ``at`` the time is this machine's clock (SYSTEM). A supplied time is SUPPLIED:
        it may not lie in the future, and no time may be earlier than a capture already stored."""
        now = now_utc()
        stamp, clock = (utc_time(at), 'SUPPLIED') if at else (now, 'SYSTEM')
        if clock == 'SUPPLIED' and when(stamp) > when(now) + CLOCK_SKEW:
            raise ValueError('CAPTURE_TIME_IN_THE_FUTURE')
        latest = self.latest_capture_time()
        if latest and when(stamp) < when(latest):
            raise ValueError('CAPTURE_TIME_NOT_MONOTONIC')
        return stamp, clock

    def begin_capture(self, at=None) -> tuple:
        """Checks the time of a capture once and returns the (time, clock) pair every block of that capture is stored
        under. ``put_bars`` accepts only the pair handed out here, so a clock cannot be claimed, and only until the
        transaction it is used in ends, so it cannot be kept for later."""
        self._capture = self.capture_clock(at)
        return self._capture

    # ------------------------------------------------------------------------------------------------------- bars
    def sources(self) -> list:
        return [r[0] for r in self.db.execute(f'SELECT DISTINCT source FROM {BAR_TABLE} ORDER BY 1')]

    def _source(self, source):
        if source:
            return source
        found = self.sources()
        if len(found) > 1:
            raise ValueError('SOURCE_REQUIRED')                             # two vendors' bars for one identifier are two different series
        return found[0] if found else None

    def put_bars(self, source, security_id, year, columns, capture_id, *, price_table, at=None, capture=None, sparse=False) -> dict:
        """Stores one security-year block. Every row is checked again here, against the capture time too; a block holding an
        invalid row is refused whole. Stored sessions outside the span this capture holds are carried over, so a partial file
        extends a year. A stored session inside that span that the capture no longer mentions is removed from the new
        version (``sparse`` captures remove nothing). Content equal to the current version is a duplicate; anything else is
        the next version. ``capture`` is the pair ``begin_capture`` returned, passed by ``ingest`` for every block of one
        file; a direct caller leaves it out and gives ``at`` or nothing, and the time is checked here."""
        if tuple(sorted(columns)) != tuple(sorted(BAR_COLUMNS)) or len({len(columns[c]) for c in BAR_COLUMNS}) != 1 or not columns['sessions']:
            raise ValueError('MALFORMED_BAR_BLOCK')
        if list(columns['sessions']) != sorted(set(columns['sessions'])) or any(str(s)[:4] != str(year) for s in columns['sessions']):
            raise ValueError('MALFORMED_BAR_BLOCK')
        if capture is None:
            at, clock = self.capture_clock(at)
        elif capture is not self._capture or at is not None:
            raise ValueError('INVALID_CAPTURE_TIME')                        # not the pair this store handed out
        else:
            at, clock = capture
        if price_table not in ('stocks', 'funds') or block_reasons(columns, captured_at=at):
            raise ValueError('INVALID_BAR_BLOCK')
        body = {c: ['' if v is None else str(v) for v in columns[c]] for c in BAR_COLUMNS}
        previous = self.db.execute(f'SELECT version, payload, content_hash FROM {BAR_TABLE} WHERE source=? AND security_id=? AND year=? ORDER BY version DESC LIMIT 1',
                                   (source, security_id, int(year))).fetchone()
        carried = 0
        if previous:
            old = json.loads(zlib.decompress(previous[1]))
            mentioned, first, last = set(body['sessions']), body['sessions'][0], body['sessions'][-1]
            keep = [k for k, s in enumerate(old['sessions']) if s not in mentioned and (sparse or s < first or s > last)]
            if keep:
                carried = len(keep)
                merged = sorted([(old['sessions'][k], 'old', k) for k in keep] + [(s, 'new', k) for k, s in enumerate(body['sessions'])])
                body = {c: [(old if origin == 'old' else body)[c][k] for _, origin, k in merged] for c in BAR_COLUMNS}
            digest = content_hash(body)
            if digest == previous[2]:
                return {'stored': False, 'id': content_hash([source, security_id, int(year), previous[0]]), 'version': previous[0]}
            change, version = classify_change(old, body), previous[0] + 1
        else:
            digest, change, version = content_hash(body), {'change': FIRST}, 1
        change['sessions_carried_over'] = carried
        identity = content_hash([source, security_id, int(year), version])
        with self.transaction():
            self.db.execute(f'INSERT INTO {BAR_TABLE} VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (identity, source, security_id, int(year), version, len(body['sessions']), body['sessions'][0], body['sessions'][-1], capture_id,
                             canonical(change), digest, price_table, zlib.compress(canonical(body).encode(), 6), at, clock))
        return {'stored': True, 'id': identity, 'version': version, **change}

    def bar_blocks(self, security_id, *, source=None, through_capture_time=None):
        """The current block of every year of one security: the highest version (optionally, the highest stored by a time)."""
        source = self._source(source)
        through = None if through_capture_time is None else when(through_capture_time)
        latest = {}
        for year, version, identity, payload, created, capture in self.db.execute(
                f'SELECT year, version, id, payload, created_at, capture_id FROM {BAR_TABLE} WHERE security_id=? AND source=? ORDER BY year, version', (security_id, source)):
            if through is None or when(created) <= through:
                latest[year] = (version, identity, payload, capture)
        for year in sorted(latest):
            version, identity, payload, capture = latest[year]
            yield {'year': year, 'version': version, 'id': identity, 'capture_id': capture, **json.loads(zlib.decompress(payload))}

    def bars(self, security_id, **kw) -> dict:
        """{column: [values as stored]} over every stored year, plus the identities of the blocks they came from."""
        out = {c: [] for c in BAR_COLUMNS}
        blocks = []
        for block in self.bar_blocks(security_id, **kw):
            for c in BAR_COLUMNS:
                out[c].extend(block[c])
            blocks.append(block['id'])
        out['blocks'] = blocks
        return out

    def bar_history(self, security_id, *, source=None) -> dict:
        """What the versions say about each bar that is read today:

            since    {session: when the value read today was first stored}
            clock    {session: SYSTEM or SUPPLIED, the clock of that version}
            revised  the sessions whose value was changed after it was first stored
            removed  the sessions that were stored once and are not read today: the vendor took the bar out

        A pure rescale of a block for a later split (SCALE_ONLY), a re-adjusted total-return close and a new update stamp
        do not change a bar. Anything else does: in a VALUE_CHANGE version every row whose values differ from the version
        before is a revised bar, dated to that version, whether or not the row alone would pass for a rescale."""
        source = self._source(source)
        since, clock, revised, previous = {}, {}, set(), {}
        for year, payload, created, stamp in self.db.execute(f'SELECT year, payload, created_at, clock FROM {BAR_TABLE} WHERE security_id=? AND source=? ORDER BY year, version',
                                                             (security_id, source)):
            block = json.loads(zlib.decompress(payload))
            old = previous.get(year)
            if old is None:
                for session in block['sessions']:
                    since[session], clock[session] = created, stamp
            else:
                kind = classify_change(old, block)['change']
                before = {session: k for k, session in enumerate(old['sessions'])}
                now = set(block['sessions'])
                for k, session in enumerate(block['sessions']):
                    if session not in before:
                        since[session], clock[session] = created, stamp
                        if session in revised or session < old['sessions'][-1]:
                            revised.add(session)                       # it appeared in the past, or it was removed and came back
                    elif kind == VALUE_CHANGE and not _same(old, before[session], block, k, VALUE_COLUMNS):
                        since[session], clock[session] = created, stamp
                        revised.add(session)
                for session in before:
                    if session not in now:
                        since.pop(session, None)
                        clock.pop(session, None)
                        revised.add(session)                           # removed: if it returns, it returns as a revised bar
            previous[year] = block
        return {'since': since, 'clock': clock, 'revised': {session for session in revised if session in since},
                'removed': {session for session in revised if session not in since}}

    def held_since(self, security_id, *, source=None) -> dict:
        """{session: when the bar that is read today was first stored}. See ``bar_history``."""
        return self.bar_history(security_id, source=source)['since']

    def security_ids(self, *, price_table=None) -> list:
        query = f'SELECT DISTINCT security_id FROM {BAR_TABLE}' + (' WHERE price_table=?' if price_table else '') + ' ORDER BY 1'
        return [r[0] for r in self.db.execute(query, (price_table,) if price_table else ())]

    def current_blocks_hash(self, *, price_table=None) -> str:
        """One hash over the identity and content of every current block: what a universe or a dataset was built from.
        With ``price_table``: every current block of every security that has bars from that table, whichever table each
        block came from, because a security's panel is read whole."""
        query = (f'SELECT id, content_hash FROM {BAR_TABLE} b WHERE version = (SELECT MAX(version) FROM {BAR_TABLE} WHERE source=b.source AND security_id=b.security_id '
                 'AND year=b.year)' + (f' AND security_id IN (SELECT DISTINCT security_id FROM {BAR_TABLE} WHERE price_table=?)' if price_table else '') + ' ORDER BY id')
        return content_hash([list(r) for r in self.db.execute(query, (price_table,) if price_table else ())])

    def spans(self) -> list:
        """(first session, last session, bars) of every security, from its current blocks. Dates and counts only."""
        return [tuple(r) for r in self.db.execute(
            f'SELECT MIN(first_session), MAX(last_session), SUM(row_count) FROM {BAR_TABLE} b WHERE version = (SELECT MAX(version) FROM {BAR_TABLE} '
            'WHERE source=b.source AND security_id=b.security_id AND year=b.year) GROUP BY source, security_id')]

    def bar_summary(self) -> dict:
        row = self.db.execute(f'SELECT COUNT(DISTINCT source || char(31) || security_id), MIN(first_session), MAX(last_session), COUNT(*) FROM {BAR_TABLE}').fetchone()
        rows = self.db.execute(f'SELECT COALESCE(SUM(row_count), 0) FROM {BAR_TABLE} b WHERE version = (SELECT MAX(version) FROM {BAR_TABLE} '
                               'WHERE source=b.source AND security_id=b.security_id AND year=b.year)').fetchone()[0]
        changes = {}
        for (change,) in self.db.execute(f'SELECT change FROM {BAR_TABLE}'):
            kind = json.loads(change)['change']
            changes[kind] = changes.get(kind, 0) + 1
        return {'securities': row[0], 'first_session': row[1], 'last_session': row[2], 'blocks': row[3], 'bars': rows, 'block_versions': changes, 'sources': self.sources()}
