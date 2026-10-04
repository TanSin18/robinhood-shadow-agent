"""The modeling database: a session-time copy of the research sources, kept apart from the live research database.

The live research database is opened read-only and is never written. The modeling database is a new file. It holds a
copy of the source rows the Checkpoint 6 calculators read, with one deliberate, recorded change: each row's
``known_at`` is replaced by the time the fact became public (see ``firm_lab.modeling``), so that the unchanged
calculators, asked "what was known at the close of session T", answer from what the market could have known then.
Every relabelled row is listed in ``modeling_time_view`` with its original value, so nothing is hidden.

No order, fill, position, account or cash table is created here, and none may be.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from firm_lab.research_features.calendar import session_close
from firm_lab.research_features.store import CANONICAL_OFFICIAL, validate_path
from firm_lab.research_features.types import content_hash, timestamp

from . import DATABASE_ROLE, TIME_POLICY

# source table -> the column that says when the publisher made the row public (None: the exchange session close)
SESSION_TIME = {'feature_observations': None, 'fundamental_fact_observations': 'accepted_timestamp', 'filing_observations': 'accepted_timestamp',
                'earnings_event_observations': 'accepted_timestamp', 'macro_observations': 'published_at', 'macro_events': 'published_at'}
# copied exactly as stored: their own known-at already keeps them out of every earlier session
UNCHANGED = ('research_sector_mappings', 'corporate_action_observations', 'research_feature_definitions')
FORBIDDEN_TABLE_WORDS = ('order', 'fill', 'position', 'account', 'cash', 'portfolio', 'broker')
APPEND_ONLY = ('modeling_time_view', 'modeling_feature_results', 'modeling_feature_inputs', 'modeling_runs', 'modeling_datasets', 'modeling_models',
               'modeling_predictions', 'modeling_reports')


def file_sha256(path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_tables(db):
    """The modeling tables: content-addressed, append-only. Nothing here can hold a trade."""
    for table in APPEND_ONLY:
        db.execute(f'CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL)')
        for action in ('UPDATE', 'DELETE'):
            db.execute(f'CREATE TRIGGER IF NOT EXISTS {table}_{action.lower()} BEFORE {action} ON {table} BEGIN '
                       "SELECT RAISE(ABORT, 'APPEND_ONLY'); END")


def build(source, target, *, official_db=CANONICAL_OFFICIAL, now=None) -> dict:
    """Creates the modeling database at ``target`` from the research database at ``source``. Refuses to overwrite."""
    source = validate_path(source, official_db)
    target = Path(target)
    if target.exists():
        raise ValueError('MODELING_DATABASE_EXISTS')
    if target.resolve() == source.resolve() or Path(official_db).resolve().parent in target.resolve().parents:
        raise ValueError('MODELING_DATABASE_MUST_BE_SEPARATE')
    at = (now or datetime.now(timezone.utc)).isoformat()
    src = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    out = sqlite3.connect(target)
    counts, dropped = {}, {}
    try:
        present = {r[0]: r[1] for r in src.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")}
        with out:
            create_tables(out)
            out.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
            for table in tuple(SESSION_TIME) + UNCHANGED:
                if table not in present:
                    continue
                out.execute(present[table])
                columns = [r[1] for r in src.execute(f'PRAGMA table_info({table})')]
                marks = ','.join('?' * len(columns))
                column = SESSION_TIME.get(table, 'UNCHANGED')
                where = " WHERE feature_name='close'" if table == 'feature_observations' else ''
                kept = 0
                for values in src.execute(f'SELECT * FROM {table}{where}'):
                    row = dict(zip(columns, values))
                    if table in UNCHANGED:
                        out.execute(f'INSERT INTO {table} VALUES ({marks})', values)
                        kept += 1
                        continue
                    try:
                        public = session_close(row['exchange_session_date']) if column is None else timestamp(row[column])
                    except (ValueError, KeyError, TypeError):
                        dropped[table] = dropped.get(table, 0) + 1          # no public time: the row cannot be dated, so it is left out
                        continue
                    original = {'known_at': row['known_at'], 'row_hash': content_hash(row)}
                    row['known_at'] = public
                    if 'payload_json' in row:                               # macro rows repeat their known-at inside the payload
                        payload = json.loads(row['payload_json'])
                        if 'known_at' in payload:
                            payload['known_at'] = public
                            row['payload_json'] = json.dumps(payload, sort_keys=True, separators=(',', ':'))
                    out.execute(f'INSERT INTO {table} VALUES ({marks})', [row[c] for c in columns])
                    entry = {'table': table, 'row_id': str(row['id']), 'original_known_at': original['known_at'], 'original_row_hash': original['row_hash'],
                             'session_time_known_at': public, 'basis': 'exchange session close' if column is None else column}
                    out.execute('INSERT INTO modeling_time_view VALUES (?,?,?)', (content_hash([table, str(row['id'])]),
                                                                                   json.dumps(entry, sort_keys=True, separators=(',', ':')), at))
                    kept += 1
                counts[table] = kept
            policy = {'policy': TIME_POLICY, 'session_time_columns': {k: v or 'exchange session close' for k, v in SESSION_TIME.items()},
                      'unchanged': list(UNCHANGED), 'rows': counts, 'rows_without_a_public_time_left_out': dropped,
                      'source_sha256': file_sha256(source), 'built_at': at,
                      'statement': 'Retrospective research view. Not evidence that Firm Lab held any of this at the time.'}
            for key, value in (('mode', 'BUILD_OBSERVE'), ('database_role', DATABASE_ROLE), ('time_policy', json.dumps(policy, sort_keys=True))):
                out.execute('INSERT INTO firm_meta VALUES (?,?,?)', (key, value, at))
    finally:
        src.close()
        out.close()
    check(target)
    return policy


def check(path) -> dict:
    """Raises unless ``path`` is a modeling database: the right role, BUILD_OBSERVE, and no table that could hold a trade."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        if any(word in name for name in names for word in FORBIDDEN_TABLE_WORDS):
            raise ValueError('EXECUTION_TABLE_FORBIDDEN')
        meta = dict(db.execute('SELECT key, value FROM firm_meta')) if 'firm_meta' in names else {}
        if meta.get('mode') != 'BUILD_OBSERVE' or meta.get('database_role') != DATABASE_ROLE:
            raise ValueError('NOT_A_MODELING_DATABASE')
        return json.loads(meta['time_policy'])
    finally:
        db.close()
