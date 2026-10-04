"""Research-only ingestion of files the operator downloaded. No network, no key, no schedule.

Every file becomes one capture with a receipt, and a capture is stored whole or not at all: if reading the file fails
part-way, nothing of it remains. Rows are checked one by one; a failing row is stored as a rejection with its reasons
and never as a bar. Two rows for one security and session that differ are both rejected. Valid rows are stored per
security and year as the vendor printed them (surrounding white space removed, nothing else).

Capture times are UTC, must carry an offset, and never go backwards: a capture cannot be dated before one already stored.
Without a supplied time the capture is stamped by this machine's clock (SYSTEM). A supplied time (SUPPLIED) may not lie
in the future, and a bar stored under it never counts as held at the time: a time someone typed is a claim, not a clock.

Rows wait in a private temporary database that the operating system removes when it is closed or when the process
dies; nothing licensed is left beside the history database by a run that was cut short.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from . import BAR_KNOWN_AT_BASIS, BAR_KNOWN_AT_VERSION, POLICY_VERSION, SPLIT_ADJUSTED, TOTAL_RETURN_ADJUSTED, UNADJUSTED
from .store import BAR_COLUMNS, content_hash, file_sha256, now_utc, utc_time
from .validate import bar_reasons

ROW_FIELDS = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return', 'provider_updated')
SECURITY_CORE = ('source', 'security_id', 'symbol', 'name', 'exchange', 'category', 'currency', 'is_delisted', 'first_price_date', 'last_price_date', 'price_table',
                 'cik', 'sector_current', 'industry_current', 'sic_code_current', 'provider_updated', 'related_symbols')
ACTION_TYPES = ('split', 'cash_dividend', 'spin_off', 'symbol_change', 'merger', 'delisting', 'listing', 'other')
BASIS = {'open': SPLIT_ADJUSTED, 'high': SPLIT_ADJUSTED, 'low': SPLIT_ADJUSTED, 'close': SPLIT_ADJUSTED, 'volume': SPLIT_ADJUSTED,
         'close_unadjusted': UNADJUSTED, 'close_total_return': TOTAL_RETURN_ADJUSTED}


def describe_file(path) -> dict:
    """Name, hash and size of a vendor file. A vendor file inside a Git work tree is refused: it could be committed."""
    path = Path(path)
    if any((parent / '.git').exists() for parent in path.resolve().parents):
        raise ValueError('VENDOR_FILE_INSIDE_A_REPOSITORY')
    return {'file': path.name, 'sha256': file_sha256(path), 'bytes': path.stat().st_size}


def capture_time(at=None) -> str:
    return utc_time(at) if at else now_utc()


def _begin(store, at) -> tuple:
    """(capture time, clock), checked once for the whole file. See ``HistoryStore.begin_capture``."""
    return store.begin_capture(at)


def _capture_id(store, kind, source, file, adapter, at) -> str:
    return content_hash([kind, source, file['sha256'], adapter, at, store.count('history_captures')])


def _receipt(store, capture_id, kind, source, file, adapter, counts, at, clock):
    """One capture record per ingestion run: the validation receipt. Every run leaves its own."""
    store.put('history_captures', {'capture_id': capture_id, 'kind': kind, 'source': source, **file, 'adapter': adapter, 'captured_at': at, 'clock': clock,
                                   'policy_version': POLICY_VERSION, **counts}, identity=capture_id, at=at)


def current_securities(store, *, source=None) -> dict:
    """{security_id: the security-master row of the latest capture that changed it}."""
    out = {}
    for _, payload, _ in store.rows('history_securities'):
        if source is None or payload['source'] == source:
            out[payload['security_id']] = payload
    return out


def ingest_securities(store, rows, *, source, file, adapter, at=None) -> dict:
    at, clock = _begin(store, at)
    rows = list(rows)
    seen = {}
    for row in rows:
        seen.setdefault(row.get('security_id'), set()).add(tuple(sorted((k, str(row.get(k))) for k in SECURITY_CORE if k != 'source')))
    current = {sid: {k: sec.get(k) for k in SECURITY_CORE} for sid, sec in current_securities(store, source=source).items()}
    versions = {}
    for _, payload, _ in store.rows('history_securities'):
        if payload['source'] == source:
            versions[payload['security_id']] = versions.get(payload['security_id'], 0) + 1
    read = stored = duplicate = 0
    problems = {}
    with store.transaction():
        cid = _capture_id(store, 'securities', source, file, adapter, at)
        for row in rows:
            read += 1
            core = {k: row.get(k) for k in SECURITY_CORE}
            core['source'] = source
            sid = core['security_id']
            if not sid or not core['symbol'] or core['price_table'] not in ('stocks', 'funds') or not isinstance(core['is_delisted'], bool):
                problems['MALFORMED_SECURITY'] = problems.get('MALFORMED_SECURITY', 0) + 1
            elif len(seen[sid]) > 1:
                problems['CONFLICTING_SECURITY_IDENTITY'] = problems.get('CONFLICTING_SECURITY_IDENTITY', 0) + 1      # one identifier, two descriptions, in one file
            elif current.get(sid) == core:
                duplicate += 1
            else:
                # a description the vendor returns to is stored again: "current" follows the latest capture, not the first sighting
                stored += store.put('history_securities', {**core, 'capture_id': cid}, identity=content_hash([core, versions.get(sid, 0)]), at=at)
                current[sid] = core
                versions[sid] = versions.get(sid, 0) + 1
        counts = {'rows_read': read, 'rows_stored': stored, 'rows_duplicate': duplicate, 'rows_rejected': sum(problems.values()), 'rejections_by_reason': problems}
        _receipt(store, cid, 'securities', source, file, adapter, counts, at, clock)
    return {'capture_id': cid, **counts}


def _ingest_events(store, table, kind, core_fields, rows, *, source, file, adapter, at, allowed=None):
    at, clock = _begin(store, at)
    by_symbol = {}
    for sid, sec in current_securities(store, source=source).items():
        by_symbol.setdefault(sec['symbol'], []).append(sid)
    read = stored = 0
    problems = {}

    def refuse(reason):
        problems[reason] = problems.get(reason, 0) + 1

    with store.transaction():
        cid = _capture_id(store, kind, source, file, adapter, at)
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
        _receipt(store, cid, kind, source, file, adapter, counts, at, clock)
    return {'capture_id': cid, **counts}


def ingest_actions(store, rows, *, source, file, adapter, at=None) -> dict:
    """Corporate actions as the provider reports them. The provider gives a date and no announcement time."""
    return _ingest_events(store, 'history_actions', 'actions', ('source', 'security_id', 'symbol', 'type', 'provider_code', 'effective_date', 'value', 'contra_symbol',
                                                               'contra_name', 'name', 'announcement_timestamp'),
                          rows, source=source, file=file, adapter=adapter, at=at, allowed=ACTION_TYPES)


def ingest_index_events(store, rows, *, source, file, adapter, at=None) -> dict:
    return _ingest_events(store, 'history_index_events', 'index_events', ('source', 'security_id', 'symbol', 'index', 'type', 'effective_date', 'name', 'note'),
                          rows, source=source, file=file, adapter=adapter, at=at, allowed=('added', 'removed', 'current', 'historical'))


def ingest_bars(store, rows, *, source, file, adapter, price_table='stocks', at=None, batch=50_000, sparse=False) -> dict:
    """Streams bar rows into the store. ``rows`` yields dicts with ``symbol``, ``session`` and the fields in ROW_FIELDS.

    A stored session that lies inside the span of sessions this file holds for a security and year, and that the file
    does not mention, is removed from the new version: the vendor took the bar out. ``sparse`` says the file lists only
    scattered rows (for example those changed since a date); then nothing is removed."""
    capture = _begin(store, at)
    at, clock = capture
    securities = current_securities(store, source=source)
    by_symbol = {}
    for sid, sec in securities.items():
        if sec['price_table'] == price_table:
            by_symbol.setdefault(sec['symbol'], []).append(sid)
    counts = {'rows_read': 0, 'rows_stored': 0, 'rows_duplicate_identical': 0, 'rows_rejected': 0, 'rows_in_unchanged_blocks': 0, 'blocks_stored': 0, 'blocks_duplicate': 0,
              'sessions_removed': 0}
    by_reason, by_change, rejections = {}, {}, []
    span = [None, None]
    stage = sqlite3.connect('')                                             # a private temporary database; it is gone when closed or when the process dies
    try:
        with store.transaction():
            cid = _capture_id(store, 'bars', source, file, adapter, at)

            def reject(symbol, sid, row, reasons):
                counts['rows_rejected'] += 1
                for r in reasons:
                    by_reason[r] = by_reason.get(r, 0) + 1
                rejections.append({'capture_id': cid, 'symbol': symbol, 'security_id': sid, 'session': row.get('session'), 'reasons': reasons,
                                   'row': {k: row.get(k) for k in ROW_FIELDS}})
                if len(rejections) >= batch:
                    store.put_many('history_bar_rejections', rejections, at=at)
                    rejections.clear()

            stage.execute('CREATE TABLE stage (security_id TEXT, session TEXT, n INTEGER, symbol TEXT, ' + ', '.join(f'{f} TEXT' for f in ROW_FIELDS) + ')')
            marks = ','.join('?' * (4 + len(ROW_FIELDS)))
            pending = []
            for n, raw in enumerate(rows):
                counts['rows_read'] += 1
                row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
                symbol = row.get('symbol')
                ids = by_symbol.get(symbol, [])
                reasons = bar_reasons(row, captured_at=at)
                if len(ids) != 1:
                    reasons.append('UNKNOWN_SECURITY' if not ids else 'AMBIGUOUS_SECURITY')
                elif securities[ids[0]].get('currency') != 'USD':
                    reasons.append('CURRENCY_NOT_USD')                     # a currency that is not stated is not assumed
                if reasons:
                    reject(symbol, ids[0] if len(ids) == 1 else None, row, reasons)
                    continue
                pending.append((ids[0], row['session'], n, symbol) + tuple('' if row.get(f) is None else str(row[f]) for f in ROW_FIELDS))
                if len(pending) >= batch:
                    stage.executemany(f'INSERT INTO stage VALUES ({marks})', pending)
                    pending.clear()
            stage.executemany(f'INSERT INTO stage VALUES ({marks})', pending)
            stage.execute('CREATE INDEX stage_key ON stage(security_id, session, n)')
            stage.commit()

            state = {'block': None, 'key': None}

            def flush():
                block, key = state['block'], state['key']
                if not block or not block['sessions']:
                    return
                result = store.put_bars(source, key[0], key[1], block, cid, price_table=price_table, capture=capture, sparse=sparse)
                if result['stored']:
                    counts['blocks_stored'] += 1
                    counts['rows_stored'] += len(block['sessions'])
                    counts['sessions_removed'] += result.get('sessions_removed', 0)
                    by_change[result['change']] = by_change.get(result['change'], 0) + 1
                else:
                    counts['blocks_duplicate'] += 1
                    counts['rows_in_unchanged_blocks'] += len(block['sessions'])
                span[0] = block['sessions'][0] if span[0] is None else min(span[0], block['sessions'][0])
                span[1] = block['sessions'][-1] if span[1] is None else max(span[1], block['sessions'][-1])

            def settle(group):
                """One security and session: a single row, identical copies, or a conflict."""
                values = {g[4:] for g in group}
                sid, session, symbol = group[0][0], group[0][1], group[0][3]
                if len(values) > 1:
                    for g in group:
                        reject(symbol, sid, {'session': session, **dict(zip(ROW_FIELDS, g[4:]))}, ['CONFLICTING_DUPLICATE'])
                    return
                counts['rows_duplicate_identical'] += len(group) - 1
                target = (sid, int(session[:4]))
                if target != state['key']:
                    flush()
                    state['key'], state['block'] = target, {c: [] for c in BAR_COLUMNS}
                state['block']['sessions'].append(session)
                for name, value in zip(ROW_FIELDS, group[0][4:]):
                    state['block'][name].append(value)

            group = []
            for item in stage.execute('SELECT * FROM stage ORDER BY security_id, session, n'):
                if group and (item[0], item[1]) != (group[0][0], group[0][1]):
                    settle(group)
                    group = []
                group.append(item)
            if group:
                settle(group)
            flush()
            if rejections:
                store.put_many('history_bar_rejections', rejections, at=at)
            receipt = {**counts, 'rejections_by_reason': by_reason, 'blocks_by_change': by_change, 'first_session': span[0], 'last_session': span[1],
                       'price_table': price_table, 'sparse': bool(sparse), 'basis': BASIS, 'known_at_version': BAR_KNOWN_AT_VERSION, 'known_at_basis': BAR_KNOWN_AT_BASIS}
            _receipt(store, cid, 'bars', source, file, adapter, receipt, at, clock)
    finally:
        stage.close()
    return {'capture_id': cid, **receipt}
