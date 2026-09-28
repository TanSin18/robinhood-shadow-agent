"""Secret-free authorization warnings projected into the operator outbox."""
from __future__ import annotations

import re
import hashlib
from uuid import uuid4
from pathlib import Path

from agents.notification_outbox import enqueue
from agents.safety_events import ensure_operations_schema
from data.connections import connection


def check_authorization(database, socket_path, *, now, dashboard_base_url, client_factory=None):
    """Read secret-free socket metadata only; no market or model calls."""
    if client_factory is None:
        from broker.proxy_client import BrokerProxyClient
        client_factory = lambda path: BrokerProxyClient(path, timeout=5)
    failure = False
    try:
        with client_factory(socket_path) as client:
            status = client.authorization_evidence()['authorization']
        if (not isinstance(status, dict)
            or not isinstance(status.get('authorization_id'), str)
            or not re.fullmatch(r'[0-9a-f]{32}', status['authorization_id'])
            or status.get('status') not in {'VALID','WARNING_3_DAYS','WARNING_1_DAY','EXPIRED','REFRESH_FAILED'}):
            raise ValueError('invalid authorization state')
    except Exception as error:
        failure = True
        status = {'status': {'AUTH_EXPIRED':'EXPIRED','AUTH_REFRESH_FAILED':'REFRESH_FAILED'}.get(str(error),'PROXY_UNAVAILABLE')}
    # Deduplicate each outage, but rearm after an observed healthy connection.
    service_id = hashlib.sha256(str(socket_path).encode()).hexdigest()
    with connection(Path(database)) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('CREATE TABLE IF NOT EXISTS authorization_monitor_state (service_id TEXT PRIMARY KEY, incident_id TEXT)')
        row = db.execute('SELECT incident_id FROM authorization_monitor_state WHERE service_id=?',(service_id,)).fetchone()
        incident = (row[0] if row and row[0] else uuid4().hex) if failure else None
        db.execute('INSERT OR REPLACE INTO authorization_monitor_state VALUES (?,?)',(service_id,incident))
    if failure:
        status['authorization_id'] = incident
    queued = record_authorization_status(database, status, now=now,
                                          dashboard_base_url=dashboard_base_url)
    return {'status': status['status'], 'page_queued': queued}


def record_authorization_status(database, status: dict, *, now, dashboard_base_url: str) -> bool:
    authorization_id = status.get('authorization_id')
    state = status.get('status')
    if not isinstance(authorization_id, str) or not re.fullmatch(r'[0-9a-f]{32}', authorization_id):
        raise ValueError('invalid authorization status')
    messages = {
        'PROXY_UNAVAILABLE': ('unavailable', 'Robinhood read-only connection unavailable',
                             'The isolated Robinhood proxy is unavailable. Live reviews remain blocked; check the proxy service and authorization.'),
        'WARNING_3_DAYS': ('3-days', 'Robinhood authorization expires soon',
                           'Robinhood authorization expires within 3 days. Re-authorize from the dedicated proxy account.'),
        'WARNING_1_DAY': ('1-day', 'Robinhood authorization expires soon',
                          'Robinhood authorization expires within 1 day. Re-authorize from the dedicated proxy account.'),
        'REFRESH_FAILED': ('refresh-failed', 'Robinhood authorization refresh failed',
                           'Robinhood authorization could not refresh. Live reviews are held until re-authorization.'),
        'EXPIRED': ('expired', 'Robinhood authorization expired',
                    'Robinhood authorization expired. Live reviews are held until re-authorization.'),
    }
    if state not in messages:
        return False
    suffix, title, body = messages[state]
    event_id = f'robinhood-auth-{authorization_id}-{suffix}'
    with connection(Path(database)) as db:
        ensure_operations_schema(db)
        before = db.execute('SELECT 1 FROM notification_outbox WHERE event_id=?', (event_id,)).fetchone()
        enqueue(
            db, event_id, title, body, now, priority=1,
            url=dashboard_base_url.rstrip('/') + '/#controls',
        )
    return before is None
