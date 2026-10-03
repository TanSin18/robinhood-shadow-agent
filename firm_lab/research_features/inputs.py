"""Pure local reads. Source knowledge/acceptance precedes revision selection."""
from decimal import Decimal, InvalidOperation
import json
from .calendar import session_close, session_dates
from .types import SourceRef, content_hash, timestamp
from firm_lab.usage import require_feature_source_allowed


def eligible_rows(rows, cutoff):
    cutoff = timestamp(cutoff)
    out = []
    for row in rows:
        try:
            times = [timestamp(row['known_at'])]
            times += [timestamp(row[k]) for k in ('accepted_timestamp', 'published_at') if row.get(k)]
            if max(times) <= cutoff:
                out.append(row)
        except (ValueError, KeyError):
            continue
    return out


def _rows(db, table):
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if table not in names:
        return []
    cursor = db.execute(f'SELECT * FROM {table}')
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, r)) for r in cursor]


def _ref(table, row):
    return SourceRef(table, str(row['id']), content_hash(row), timestamp(row['known_at']))


def load_snapshot(connection, request):
    # No query may mutate anything even when the caller accidentally supplies rw.
    connection.execute('PRAGMA query_only=ON')
    names = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if names & {'paper_accounts', 'cycle_runs', 'orders', 'fills', 'positions', 'accounts'} or 'firm_meta' not in names:
        raise ValueError('OFFICIAL_OR_UNIDENTIFIED_DATABASE')
    mode = connection.execute("SELECT value FROM firm_meta WHERE key='mode'").fetchone()
    if mode != ('BUILD_OBSERVE',):
        raise ValueError('BUILD_OBSERVE_REQUIRED')
    snapshot = {k: [] for k in ('closes', 'ohlcv', 'facts', 'filings', 'earnings',
                                'macro', 'macro_events', 'mappings', 'source_refs', 'missing_reasons')}
    raw = eligible_rows(_rows(connection, 'feature_observations'), request.knowledge_cutoff)
    selected = {}
    bases = set()
    for row in raw:
        if row['instrument'] != request.instrument or row['feature_name'] != 'close':
            continue
        day = row['exchange_session_date']
        if day > request.as_of_session:
            continue
        try:
            close_at = session_close(day)
            if close_at > request.knowledge_cutoff:
                continue
            meta = json.loads(row['metadata_json'])
            require_feature_source_allowed(source=row['source'], provider=row['provider'], metadata=meta, feature_name='close')
            value = Decimal(row['value'])
            if not value.is_finite() or value <= 0:
                raise ValueError('INVALID_CLOSE')
            basis = (row['provider'], meta.get('currency', 'UNSPECIFIED'), meta.get('adjusted', 'UNSPECIFIED'))
            bases.add(basis)
            key = (timestamp(row['known_at']), int(row['revision']))
            previous = selected.get(day)
            if previous and key == previous[0] and (row['value'], row['source']) != (previous[1]['value'], previous[1]['source']):
                raise ValueError('CONFLICTING_SOURCE_REVISION')
            if previous is None or key > previous[0]:
                selected[day] = (key, row, close_at)
        except Exception as e:
            # Malformed/unusable source rows are explicit missing evidence, never silently repaired.
            snapshot['missing_reasons'].append(str(e).split(':')[0])
    if len(bases) > 1:
        snapshot['missing_reasons'].append('MIXED_PRICE_BASIS')
    if selected:
        days = sorted(selected)
        if tuple(days) != session_dates(days[0], request.as_of_session):
            snapshot['missing_reasons'].append('INCOMPLETE_WINDOW')
    for row in eligible_rows(_rows(connection, 'corporate_action_observations'), request.knowledge_cutoff):
        if row.get('instrument') == request.instrument and row.get('action_type') in ('split', 'reverse_split', 'ticker_change'):
            effective = row.get('effective_date') or row.get('ex_date')
            if selected and (not effective or min(selected) <= effective <= request.as_of_session):
                snapshot['missing_reasons'].append('CORPORATE_ACTION_UNRESOLVED')
    if not snapshot['missing_reasons']:
        for day in sorted(selected):
            _, row, close_at = selected[day]
            ref = _ref('feature_observations', row)
            snapshot['closes'].append({'session': day, 'value': row['value'], 'ref': ref,
                'known_at': max(ref.known_at, close_at), 'price_basis': 'provider_reported_close'})
            snapshot['source_refs'].append(ref)
    for key, table in (('facts', 'fundamental_fact_observations'), ('filings', 'filing_observations'),
                        ('earnings', 'earnings_event_observations'), ('macro', 'macro_observations'), ('macro_events', 'macro_events')):
        rows = eligible_rows(_rows(connection, table), request.knowledge_cutoff)
        for row in rows:
            if row.get('instrument', request.instrument) != request.instrument:
                continue
            if key == 'facts' and row.get('confirmed_in_filing') != 'CONFIRMED':
                continue
            if row.get('period_end', row.get('period', request.as_of_session)) > request.as_of_session:
                continue
            ref = _ref(table, row)
            payload = json.loads(row['payload_json']) if 'payload_json' in row else dict(row)
            payload.update({'ref': ref, 'known_at': ref.known_at})
            snapshot[key].append(payload)
            snapshot['source_refs'].append(ref)
    snapshot['missing_reasons'] = sorted(set(snapshot['missing_reasons']))
    return snapshot
