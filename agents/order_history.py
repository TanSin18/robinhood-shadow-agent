"""Code-only order monitoring. Never return these records to model evidence."""
from datetime import datetime, timedelta
import hashlib
import json

from broker.base import BrokerError
from data.connections import connection

ORDER_TOOLS = frozenset({'get_equity_orders', 'get_option_orders', 'get_crypto_orders'})
MAX_PAGES = 20
MAX_RECORDS = 1000
MAX_CALLS = 1060


def _items(response):
    data = response.get('data') if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise BrokerError('ORDER_HISTORY_INCOMPLETE')
    keys = [key for key in ('orders', 'results') if key in data]
    if len(keys) != 1 or not isinstance(data[keys[0]], list):
        raise BrokerError('ORDER_HISTORY_INCOMPLETE')
    records = data[keys[0]]
    if any(not isinstance(item, dict) or not isinstance(item.get('id'), str)
           or not item['id'] or not isinstance(item.get('state'), str) or not item['state']
           for item in records):
        raise BrokerError('ORDER_HISTORY_INCOMPLETE')
    cursor = data.get('next')
    if cursor is not None and not isinstance(cursor, str):
        raise BrokerError('ORDER_HISTORY_INCOMPLETE')
    return records, cursor or None


def collect_histories(read, account, *, now, since, tracked):
    """Complete bootstrap; then new orders plus fresh reads of every known ID.

    Even terminal IDs are refreshed: no unverified terminal-immutability assumption.
    No successful checkpoint is advanced by this function.
    """
    if (not isinstance(account, dict) or account.get('agentic_allowed') is not True
            or any(not isinstance(account.get(key), str) or not account[key]
                   for key in ('account_number', 'rhs_account_number'))):
        raise BrokerError('ORDER_HISTORY_ACCOUNT_UNVERIFIED')
    if now.tzinfo is None or (since is not None and (since.tzinfo is None or since > now)):
        raise BrokerError('ORDER_HISTORY_COVERAGE_UNVERIFIED')
    calls = 0
    total = 0
    histories = {}

    def fetch(tool, args):
        nonlocal calls
        calls += 1
        if calls > MAX_CALLS:
            raise BrokerError('ORDER_HISTORY_INCOMPLETE')
        return _items(read(tool, args))

    for kind in ('equity', 'option', 'crypto'):
        tool = f'get_{kind}_orders'
        key = 'rhs_account_number' if kind == 'crypto' else 'account_number'
        scope = {key: account[key]}
        args = dict(scope)
        if since is not None:
            args['created_at_gte'] = (since - timedelta(seconds=60)).isoformat()
        found = {}
        cursors = set()
        for _ in range(MAX_PAGES):
            records, cursor = fetch(tool, args)
            for item in records:
                identifier = item['id']
                if identifier in found and found[identifier] != item:
                    raise BrokerError('ORDER_HISTORY_INCOMPLETE')
                found[identifier] = item
                if len(found) + total > MAX_RECORDS:
                    raise BrokerError('ORDER_HISTORY_INCOMPLETE')
            if cursor is None:
                break
            if cursor in cursors:
                raise BrokerError('ORDER_HISTORY_INCOMPLETE')
            cursors.add(cursor)
            args = {**args, 'cursor': cursor}
        else:
            raise BrokerError('ORDER_HISTORY_INCOMPLETE')
        for old in tracked.get(kind, []):
            identifier = old['id']
            if identifier in found:
                continue
            records, cursor = fetch(tool, {**scope, 'order_id': identifier})
            if cursor is not None or len(records) != 1 or records[0]['id'] != identifier:
                raise BrokerError('ORDER_HISTORY_INCOMPLETE')
            found[identifier] = records[0]
        total += len(found)
        if total > MAX_RECORDS:
            raise BrokerError('ORDER_HISTORY_INCOMPLETE')
        histories[kind] = [found[key] for key in sorted(found)]
    return histories


def _ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS order_monitor_checkpoint (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), account_hash TEXT NOT NULL,
      checked_at TEXT NOT NULL, tracked_json TEXT NOT NULL)''')


def account_fingerprint(account):
    return hashlib.sha256(json.dumps({key: account[key] for key in
        ('account_number', 'rhs_account_number')}, sort_keys=True).encode()).hexdigest()


def load_checkpoint(path, account):
    with connection(path) as db:
        _ensure(db)
        row = db.execute('SELECT account_hash,checked_at,tracked_json FROM order_monitor_checkpoint WHERE singleton=1').fetchone()
    if row is None:
        return None, {}
    if row[0] != account_fingerprint(account):
        raise BrokerError('ORDER_HISTORY_ACCOUNT_UNVERIFIED')
    return datetime.fromisoformat(row[1]), json.loads(row[2])


def save_checkpoint(path, account, now, histories):
    # Only identities are needed for targeted refresh; prices/quantities stay out.
    tracked = {kind: [{'id': item['id']} for item in items] for kind, items in histories.items()}
    with connection(path) as db:
        _ensure(db)
        db.execute('INSERT OR REPLACE INTO order_monitor_checkpoint VALUES (1,?,?,?)',
                   (account_fingerprint(account), now.isoformat(), json.dumps(tracked, sort_keys=True)))
