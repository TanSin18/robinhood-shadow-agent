"""Storage of raw, validated provider data. Only a ``ProviderResult`` whose status is OK is ever written; a rejected
or unavailable result leaves a run record (with the reasons) and no data rows.

Rows are inserted, never updated. Each row carries the full provenance and a content hash; an identical record is
ignored on a repeat run, so ingestion can be resumed safely.
"""
from __future__ import annotations

import json
import re

from .errors import FirmLabError
from .provenance import content_hash
from .providers import OK
from .schemas import BARE_GREEK_NAMES, GREEKS
from .store import RAW_TABLES, canonical, now_utc

DOMAIN_TABLE = {'filings': 'filing_observations', 'intraday_bars': 'intraday_bar_observations', 'trades': 'trade_observations',
                'quotes': 'quote_observations', 'fundamentals': 'fundamental_observations', 'corporate_actions': 'corporate_action_observations',
                'options_chain': 'option_chain_observations'}
# The column that says when the observation is about, used for "oldest" and "newest".
TIME_COLUMN = {'filing_observations': 'accepted_timestamp', 'intraday_bar_observations': 'bar_start', 'trade_observations': 'trade_timestamp',
               'quote_observations': 'quote_timestamp', 'fundamental_observations': 'period_end', 'corporate_action_observations': 'effective_date',
               'option_chain_observations': 'quote_timestamp'}
PROVENANCE_COLUMNS = ('provider', 'source_id', 'source_timestamp', 'known_at', 'ingested_at', 'schema_version', 'content_hash', 'run_id')
CONNECTION_STATES = ('NOT_SELECTED', 'NOT_CONFIGURED', 'CONFIGURED', 'ACTIVE', 'ERROR')
_VENDOR_GREEK = re.compile(r'^([a-z][a-z0-9]*)_provider_(' + '|'.join(GREEKS) + ')$')


def set_connection(store, provider, state, detail='', now=None):
    """What is known about reaching a provider. Never holds a credential, a key fragment or a contact address."""
    if state not in CONNECTION_STATES:
        raise FirmLabError(f'UNKNOWN_CONNECTION_STATE:{state}')
    with store.connect() as db:
        db.execute('INSERT INTO provider_connections VALUES (?,?,?,?) ON CONFLICT(provider) DO UPDATE SET state=excluded.state, '
                   'detail=excluded.detail, checked_at=excluded.checked_at', (provider, state, str(detail)[:300], (now or now_utc()).isoformat()))


def _columns(db, table):
    return [r[1] for r in db.execute(f'PRAGMA table_info({table})')]


def _text(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (list, tuple, dict)):
        return canonical(value)
    return str(value)


def _row(record, columns, vendor):
    """Maps one validated record onto the table's columns. Vendor-named Greeks (``thetadata_provider_delta``) go to the
    ``provider_*`` columns only together with the vendor's name in ``greeks_provider``."""
    if set(record) & BARE_GREEK_NAMES:
        raise FirmLabError('BARE_GREEK_FIELD')                 # validation refuses these earlier; storage refuses them again
    flat = dict(record)
    for key in list(flat):
        match = _VENDOR_GREEK.match(key)
        if match:
            if flat.get('greeks_provider', '').lower().replace(' ', '') != match.group(1):
                raise FirmLabError(f'GREEK_VENDOR_NOT_NAMED:{key}')
            flat['provider_' + match.group(2)] = flat.pop(key)
    for name in ('conditions', 'indicators'):
        if name in flat:
            flat[name + '_json'] = flat.pop(name)
    return [_text(flat.get(c)) for c in columns]


def new_batch(store, provider, now=None) -> str:
    """A name for one sample: every request made in it is recorded under this name, so the sample is judged as a whole."""
    with store.connect() as db:
        number = db.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM provider_runs').fetchone()[0]
    return f'{provider}#{number}@{(now or now_utc()).isoformat()}'


def store_result(store, provider, result, *, started_at, batch=None, instrument=None, received=None, diagnostics=None, now=None) -> dict:
    """Records the run, and stores the records only when the result is OK. Returns counts."""
    at = (now or now_utc()).isoformat()
    table = DOMAIN_TABLE.get(result.domain)
    if table is None:
        raise FirmLabError(f'NO_RAW_TABLE_FOR_DOMAIN:{result.domain}')
    records = list(result.records()) if result.status == OK else []
    issues = [{'code': i.code, 'detail': i.detail[:200], 'index': i.index, 'field': i.field} for i in result.issues][:60]
    prov = result.provenance
    if result.status == OK and (prov is None or prov.missing()):
        raise FirmLabError('PROVENANCE_INCOMPLETE')            # cannot happen for a validated result; refuse rather than store
    stored = duplicates = 0
    with store.connect() as db:
        if batch is None:
            batch = f'{provider}#{db.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM provider_runs").fetchone()[0]}@{started_at}'
        cur = db.execute('INSERT INTO provider_runs (batch, provider, domain, method, instrument, started_at, finished_at, status, reason, received, '
                         'stored, duplicates, issues_json, diagnostics_json, provenance_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                         (batch, provider, result.domain, result.method, instrument, started_at, at, result.status, result.reason,
                          len(records) if received is None else int(received), 0, 0, canonical(issues), canonical(diagnostics or {}),
                          canonical(prov.as_dict()) if prov else None))
        run_id = cur.lastrowid
        if records:
            columns = [c for c in _columns(db, table) if c not in ('id',) + PROVENANCE_COLUMNS]
            names = columns + list(PROVENANCE_COLUMNS)
            sql = f'INSERT OR IGNORE INTO {table} ({", ".join(names)}) VALUES ({", ".join("?" * len(names))})'
            for record in records:
                values = _row(record, columns, provider) + [provider, prov.source_id, prov.source_timestamp, prov.known_at, at, prov.schema_version,
                                                           content_hash(record), run_id]
                inserted = db.execute(sql, values).rowcount
                stored += inserted
                duplicates += 1 - inserted
            db.execute('UPDATE provider_runs SET stored=?, duplicates=? WHERE id=?', (stored, duplicates, run_id))
    return {'run_id': run_id, 'status': result.status, 'domain': result.domain, 'received': len(records) if received is None else int(received),
            'stored': stored, 'duplicates': duplicates, 'issues': sorted({i['code'] for i in issues}), 'reason': result.reason}


def latest_batch(db, provider, domain) -> list:
    """Every run of the provider's most recent sample for the domain (runs of one sample share ``batch``).
    One run per instrument: the sample passes only when all of them did."""
    row = db.execute('SELECT batch FROM provider_runs WHERE provider=? AND domain=? ORDER BY id DESC LIMIT 1', (provider, domain)).fetchone()
    if row is None:
        return []
    return [{'run_id': i, 'instrument': inst, 'status': status, 'reason': reason, 'issues': sorted({x['code'] for x in json.loads(issues or '[]')}),
             'provenance': json.loads(prov) if prov else None, 'finished_at': finished, 'stored': stored, 'duplicates': duplicates,
             'batch': row[0]}
            for i, inst, status, reason, issues, prov, finished, stored, duplicates in db.execute(
                'SELECT id, instrument, status, reason, issues_json, provenance_json, finished_at, stored, duplicates FROM provider_runs '
                'WHERE provider=? AND domain=? AND batch=? ORDER BY id', (provider, domain, row[0]))]


def summary(store) -> dict:
    with store.connect() as db:
        return summary_db(db)


def summary_db(db) -> dict:
    """Per raw table: rows, oldest and newest observation, last successful run and the validation record. Reads only."""
    out = {}
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='provider_runs'").fetchone():
        return out                                              # a database from before Checkpoint 3: nothing is stored
    if True:
        for table in RAW_TABLES:
            column = TIME_COLUMN[table]
            rows, oldest, newest = db.execute(f'SELECT COUNT(*), MIN({column}), MAX({column}) FROM {table}').fetchone()
            domains = [d for d, t in DOMAIN_TABLE.items() if t == table]
            marks = ','.join('?' * len(domains))
            last_ok = db.execute(f"SELECT finished_at, provider FROM provider_runs WHERE domain IN ({marks}) AND status='OK' AND stored + duplicates > 0 "
                                 'ORDER BY id DESC LIMIT 1', domains).fetchone()
            last = db.execute(f'SELECT status, reason, issues_json, finished_at, provider FROM provider_runs WHERE domain IN ({marks}) '
                              'ORDER BY id DESC LIMIT 1', domains).fetchone()
            counts = dict(db.execute(f'SELECT status, COUNT(*) FROM provider_runs WHERE domain IN ({marks}) GROUP BY status', domains).fetchall())
            failures = {}
            for (text,) in db.execute(f"SELECT issues_json FROM provider_runs WHERE domain IN ({marks}) AND status='REJECTED'", domains):
                for issue in json.loads(text or '[]'):
                    failures[issue['code']] = failures.get(issue['code'], 0) + 1
            instruments = db.execute(f'SELECT COUNT(DISTINCT {"contract_id" if table == "option_chain_observations" else "instrument"}) '
                                     f'FROM {table}').fetchone()[0]
            batch = []
            if last:
                for domain in domains:
                    batch += [{k: v for k, v in run.items() if k != 'provenance'} | {'domain': domain} for run in latest_batch(db, last[4], domain)]
            out[table] = {'rows': rows, 'instruments': instruments, 'oldest': oldest, 'newest': newest, 'last_batch': batch,
                          'last_successful_ingest': last_ok[0] if last_ok else None,
                          'last_run': None if not last else {'status': last[0], 'reason': last[1], 'finished_at': last[3], 'provider': last[4],
                                                             'issues': sorted({i['code'] for i in json.loads(last[2] or '[]')})},
                          'runs': counts, 'rejected_issue_counts': failures}
        out['connections'] = {p: {'state': s, 'detail': d, 'checked_at': c} for p, s, d, c in
                              db.execute('SELECT provider, state, detail, checked_at FROM provider_connections')}
    return out
