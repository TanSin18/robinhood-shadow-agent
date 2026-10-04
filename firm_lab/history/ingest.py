"""Research-only ingestion of files the operator downloaded. No network, no key, no schedule.

Every file becomes a capture with a receipt. Rows are checked one by one; a failing row is stored as a rejection with
its reasons and never as a bar. Two rows for one security and session that differ are both rejected. Valid rows are
stored per security and year exactly as supplied.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from . import BAR_KNOWN_AT_BASIS, BAR_KNOWN_AT_VERSION, POLICY_VERSION, SPLIT_ADJUSTED, TOTAL_RETURN_ADJUSTED, UNADJUSTED
from .store import BAR_COLUMNS, content_hash, file_sha256, now_utc
from .validate import bar_reasons

ROW_FIELDS = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return', 'provider_updated')
SECURITY_CORE = ('source', 'security_id', 'symbol', 'name', 'exchange', 'category', 'currency', 'is_delisted', 'first_price_date', 'last_price_date', 'price_table',
                 'cik', 'sector_current', 'industry_current', 'sic_code_current', 'provider_updated', 'related_symbols')
ACTION_TYPES = ('split', 'cash_dividend', 'spin_off', 'symbol_change', 'merger', 'delisting', 'listing', 'other')
BASIS = {'open': SPLIT_ADJUSTED, 'high': SPLIT_ADJUSTED, 'low': SPLIT_ADJUSTED, 'close': SPLIT_ADJUSTED, 'volume': SPLIT_ADJUSTED,
         'close_unadjusted': UNADJUSTED, 'close_total_return': TOTAL_RETURN_ADJUSTED}


def describe_file(path) -> dict:
    path = Path(path)
    return {'file': path.name, 'sha256': file_sha256(path), 'bytes': path.stat().st_size}


def _receipt(store, kind, source, file, adapter, counts, at):
    """One capture record per ingestion run: the validation receipt."""
    capture_id = content_hash([kind, source, file['sha256'], adapter, at])
    store.put('history_captures', {'capture_id': capture_id, 'kind': kind, 'source': source, **file, 'adapter': adapter, 'captured_at': at,
                                   'policy_version': POLICY_VERSION, **counts}, identity=capture_id, at=at)
    return capture_id


def capture_id(kind, source, file, adapter, at) -> str:
    return content_hash([kind, source, file['sha256'], adapter, at])


def current_securities(store, *, source=None) -> dict:
    """{security_id: latest stored security-master row}."""
    out = {}
    for _, payload, _ in store.rows('history_securities'):
        if source is None or payload['source'] == source:
            out[payload['security_id']] = payload
    return out


def ingest_securities(store, rows, *, source, file, adapter, at=None) -> dict:
    at = at or now_utc()
    cid = capture_id('securities', source, file, adapter, at)
    read = stored = 0
    problems = {}
    for row in rows:
        read += 1
        core = {k: row.get(k) for k in SECURITY_CORE}
        core['source'] = source
        if not core['security_id'] or not core['symbol'] or core['price_table'] not in ('stocks', 'funds'):
            problems['MALFORMED_SECURITY'] = problems.get('MALFORMED_SECURITY', 0) + 1
            continue
        stored += store.put('history_securities', {**core, 'capture_id': cid}, identity=content_hash(core), at=at)
    counts = {'rows_read': read, 'rows_stored': stored, 'rows_duplicate': read - stored - sum(problems.values()), 'rows_rejected': sum(problems.values()),
              'rejections_by_reason': problems}
    _receipt(store, 'securities', source, file, adapter, counts, at)
    return {'capture_id': cid, **counts}


def _ingest_events(store, table, kind, core_fields, rows, *, source, file, adapter, securities, at, allowed=None):
    cid = capture_id(kind, source, file, adapter, at)
    by_symbol = {}
    for sid, sec in securities.items():
        by_symbol.setdefault(sec['symbol'], []).append(sid)
    read = stored = 0
    problems = {}

    def refuse(reason):
        problems[reason] = problems.get(reason, 0) + 1

    for row in rows:
        read += 1
        ids = by_symbol.get(row.get('symbol'), [])
        if len(ids) != 1:
            refuse('UNKNOWN_SECURITY' if not ids else 'AMBIGUOUS_SECURITY')
            continue
        core = {k: row.get(k) for k in core_fields}
        core.update(source=source, security_id=ids[0])
        if not core.get('effective_date') or (allowed and core.get('type') not in allowed):
            refuse('MALFORMED_EVENT')
            continue
        stored += store.put(table, {**core, 'capture_id': cid}, identity=content_hash(core), at=at)
    counts = {'rows_read': read, 'rows_stored': stored, 'rows_duplicate': read - stored - sum(problems.values()), 'rows_rejected': sum(problems.values()),
              'rejections_by_reason': problems}
    _receipt(store, kind, source, file, adapter, counts, at)
    return {'capture_id': cid, **counts}


def ingest_actions(store, rows, *, source, file, adapter, at=None) -> dict:
    """Corporate actions as the provider reports them. The provider gives a date and no announcement time."""
    return _ingest_events(store, 'history_actions', 'actions', ('source', 'security_id', 'symbol', 'type', 'provider_code', 'effective_date', 'value', 'contra_symbol',
                                                               'contra_name', 'name', 'announcement_timestamp'),
                          rows, source=source, file=file, adapter=adapter, securities=current_securities(store, source=source), at=at or now_utc(), allowed=ACTION_TYPES)


def ingest_index_events(store, rows, *, source, file, adapter, at=None) -> dict:
    return _ingest_events(store, 'history_index_events', 'index_events', ('source', 'security_id', 'symbol', 'index', 'type', 'effective_date', 'name', 'note'),
                          rows, source=source, file=file, adapter=adapter, securities=current_securities(store, source=source), at=at or now_utc(),
                          allowed=('added', 'removed', 'current', 'historical'))


def ingest_bars(store, rows, *, source, file, adapter, price_table='stocks', at=None, batch=50_000) -> dict:
    """Streams bar rows into the store. ``rows`` yields dicts with ``symbol``, ``session`` and the fields in ROW_FIELDS."""
    at = at or now_utc()
    cid = capture_id('bars', source, file, adapter, at)
    securities = current_securities(store, source=source)
    by_symbol = {}
    for sid, sec in securities.items():
        if sec['price_table'] == price_table:
            by_symbol.setdefault(sec['symbol'], []).append(sid)
    staging = Path(str(store.path) + f'.staging-{cid[:12]}')
    counts = {'rows_read': 0, 'rows_stored': 0, 'rows_duplicate_identical': 0, 'rows_rejected': 0, 'rows_in_unchanged_blocks': 0, 'blocks_stored': 0, 'blocks_duplicate': 0}
    by_reason, by_change, rejections = {}, {}, []
    first = last = None

    def reject(symbol, sid, row, reasons):
        counts['rows_rejected'] += 1
        for r in reasons:
            by_reason[r] = by_reason.get(r, 0) + 1
        rejections.append({'capture_id': cid, 'symbol': symbol, 'security_id': sid, 'session': row.get('session'), 'reasons': reasons,
                           'row': {k: row.get(k) for k in ROW_FIELDS}})
        if len(rejections) >= batch:
            store.put_many('history_bar_rejections', rejections, at=at)
            rejections.clear()

    stage = sqlite3.connect(staging)
    try:
        stage.execute('CREATE TABLE stage (security_id TEXT, session TEXT, n INTEGER, symbol TEXT, ' + ', '.join(f'{f} TEXT' for f in ROW_FIELDS) + ')')
        pending = []
        for n, row in enumerate(rows):
            counts['rows_read'] += 1
            symbol = row.get('symbol')
            ids = by_symbol.get(symbol, [])
            reasons = bar_reasons(row, captured_at=at)
            if len(ids) != 1:
                reasons.append('UNKNOWN_SECURITY' if not ids else 'AMBIGUOUS_SECURITY')
            elif (securities[ids[0]].get('currency') or 'USD') != 'USD':
                reasons.append('CURRENCY_NOT_USD')
            if reasons:
                reject(symbol, ids[0] if len(ids) == 1 else None, row, reasons)
                continue
            pending.append((ids[0], row['session'], n, symbol) + tuple('' if row.get(f) is None else str(row[f]).strip() for f in ROW_FIELDS))
            if len(pending) >= batch:
                stage.executemany('INSERT INTO stage VALUES (' + ','.join('?' * (4 + len(ROW_FIELDS))) + ')', pending)
                pending.clear()
        stage.executemany('INSERT INTO stage VALUES (' + ','.join('?' * (4 + len(ROW_FIELDS))) + ')', pending)
        stage.execute('CREATE INDEX stage_key ON stage(security_id, session, n)')
        stage.commit()

        block, key = None, None

        def flush():
            nonlocal first, last
            if not block or not block['sessions']:
                return
            result = store.put_bars(source, key[0], key[1], block, cid, at=at)
            if result['stored']:
                counts['blocks_stored'] += 1
                counts['rows_stored'] += len(block['sessions'])
                by_change[result['change']] = by_change.get(result['change'], 0) + 1
            else:
                counts['blocks_duplicate'] += 1
                counts['rows_in_unchanged_blocks'] += len(block['sessions'])
            first = block['sessions'][0] if first is None else min(first, block['sessions'][0])
            last = block['sessions'][-1] if last is None else max(last, block['sessions'][-1])

        group = []

        def settle(group):
            """One security and session: a single row, identical copies, or a conflict."""
            nonlocal block, key
            values = {g[4:] for g in group}
            sid, session, symbol = group[0][0], group[0][1], group[0][3]
            if len(values) > 1:
                for g in group:
                    reject(symbol, sid, {'session': session, **dict(zip(ROW_FIELDS, g[4:]))}, ['CONFLICTING_DUPLICATE'])
                return
            counts['rows_duplicate_identical'] += len(group) - 1
            target = (sid, int(session[:4]))
            if target != key:
                flush()
                key, block = target, {c: [] for c in BAR_COLUMNS}
            block['sessions'].append(session)
            for name, value in zip(ROW_FIELDS, group[0][4:]):
                block[name].append(value)

        for item in stage.execute('SELECT * FROM stage ORDER BY security_id, session, n'):
            if group and (item[0], item[1]) != (group[0][0], group[0][1]):
                settle(group)
                group = []
            group.append(item)
        if group:
            settle(group)
        flush()
    finally:
        stage.close()
        if staging.exists():
            os.unlink(staging)
    if rejections:
        store.put_many('history_bar_rejections', rejections, at=at)
    receipt = {**counts, 'rejections_by_reason': by_reason, 'blocks_by_change': by_change, 'first_session': first, 'last_session': last, 'price_table': price_table,
               'basis': BASIS, 'known_at_version': BAR_KNOWN_AT_VERSION, 'known_at_basis': BAR_KNOWN_AT_BASIS}
    _receipt(store, 'bars', source, file, adapter, receipt, at)
    return {'capture_id': cid, **receipt}
