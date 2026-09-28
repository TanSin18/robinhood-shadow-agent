from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from mcp.shared.auth import OAuthToken


NOW = datetime(2026, 9, 28, 14, 0, tzinfo=timezone.utc)


def test_background_monitor_pages_from_socket_metadata_without_broker_calls(tmp_path):
    from broker_proxy.auth_monitor import check_authorization
    class Client:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def authorization_evidence(self):
            return {'authorization': {'authorization_id': 'c'*32,
                'status': 'WARNING_1_DAY', 'expires_at': (NOW+timedelta(hours=12)).isoformat()}}
        def call_read(self, *args): raise AssertionError('No market calls')
    result=check_authorization(tmp_path/'agent.db', 'unused', now=NOW,
        dashboard_base_url='http://localhost', client_factory=lambda _:Client())
    assert result['status']=='WARNING_1_DAY'
    with sqlite3.connect(tmp_path/'agent.db') as db:
        assert db.execute("SELECT COUNT(*) FROM notification_deliveries WHERE channel='pushover' AND priority=1").fetchone()[0]==1


@pytest.mark.asyncio
async def test_existing_session_cannot_read_after_authorization_expires():
    from broker_proxy.mcp_client import RobinhoodMCPClient
    from broker_proxy.oauth import KeychainOAuthStorage, OAuthUnavailable
    backend=MemoryKeychain(); storage=KeychainOAuthStorage(backend=backend, clock=lambda:NOW)
    await storage.set_tokens(OAuthToken(access_token='secret',expires_in=60,scope='internal'))
    class Session:
        async def call_tool(self,*args,**kwargs): raise AssertionError('Expired token reached upstream')
    client=RobinhoodMCPClient.for_testing(Session()); client.storage=storage
    storage.clock=lambda:NOW+timedelta(seconds=60)
    with pytest.raises(OAuthUnavailable,match='AUTH_EXPIRED'):
        await client.call_read_async('get_accounts',{})


def test_proxy_greeting_rechecks_authorization_per_connection(tmp_path):
    from test_broker_proxy import running_proxy
    from broker.proxy_client import BrokerProxyClient
    with running_proxy(tmp_path) as (server,upstream):
        upstream.authorization_evidence=lambda:{'authorization':{'status':'WARNING_1_DAY'}}
        with BrokerProxyClient(server.socket_path) as client:
            assert client.authorization_evidence()['authorization']['status']=='WARNING_1_DAY'


def test_expired_proxy_greeting_blocks_connection(tmp_path):
    from test_broker_proxy import running_proxy
    from broker.proxy_client import BrokerProxyClient
    from broker.base import BrokerError
    from broker_proxy.oauth import OAuthUnavailable
    with running_proxy(tmp_path) as (server,upstream):
        def expired(): raise OAuthUnavailable('AUTH_EXPIRED')
        upstream.authorization_evidence=expired
        with pytest.raises(BrokerError,match='AUTH_EXPIRED'):
            BrokerProxyClient(server.socket_path).open()
        assert upstream.calls==[]


@pytest.mark.parametrize('code',['AUTH_EXPIRED','AUTH_REFRESH_FAILED'])
def test_open_socket_preserves_authorization_failure(tmp_path,code):
    from test_broker_proxy import running_proxy
    from broker.proxy_client import BrokerProxyClient
    from broker.base import BrokerError
    from broker_proxy.oauth import OAuthUnavailable
    with running_proxy(tmp_path) as (server,upstream):
        with BrokerProxyClient(server.socket_path) as client:
            def failed(*args): raise OAuthUnavailable(code)
            upstream.call_read=failed
            with pytest.raises(BrokerError,match=code):
                client.call_read('get_accounts',{})
        from broker_proxy.auth_monitor import check_authorization
        result=check_authorization(tmp_path/'monitor.db',server.socket_path,now=NOW,
            dashboard_base_url='http://localhost')
        assert result['status']==('EXPIRED' if code=='AUTH_EXPIRED' else 'REFRESH_FAILED')
        assert result['page_queued']


def test_authorization_monitor_recovers_then_pages_new_outage(tmp_path):
    from broker_proxy.auth_monitor import check_authorization
    state={'offline':True}
    class Client:
        def __enter__(self):
            if state['offline']: raise ConnectionRefusedError()
            return self
        def __exit__(self,*args): pass
        def authorization_evidence(self):
            return {'authorization':{'status':'VALID','authorization_id':'a'*32}}
    def check():
        return check_authorization(tmp_path/'agent.db','unused',now=NOW,
            dashboard_base_url='http://localhost',client_factory=lambda _:Client())
    assert check()['page_queued']
    assert not check()['page_queued']
    state['offline']=False; assert check()['status']=='VALID'
    state['offline']=True; assert check()['page_queued']


def test_malformed_receipt_pages_instead_of_aborting_maintenance(tmp_path):
    from broker_proxy.auth_monitor import check_authorization
    class Client:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def authorization_evidence(self): return {'authorization':{'status':'VALID'}}
    result=check_authorization(tmp_path/'agent.db','unused',now=NOW,
        dashboard_base_url='http://localhost',client_factory=lambda _:Client())
    assert result['status']=='PROXY_UNAVAILABLE'


def test_proxy_client_bounds_wait_for_greeting(tmp_path):
    import socket,threading,tempfile
    from pathlib import Path
    from broker.proxy_client import BrokerProxyClient
    with tempfile.TemporaryDirectory(prefix='rh-timeout-') as directory:
        address=str(Path(directory)/'sock')
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); listener.bind(address); listener.listen(1)
        stop=threading.Event()
        def stall():
            conn,_=listener.accept()
            with conn: stop.wait(2)
        thread=threading.Thread(target=stall); thread.start()
        try:
            with pytest.raises(TimeoutError): BrokerProxyClient(address,timeout=.05).open()
        finally:
            stop.set(); thread.join(3); listener.close()


def test_background_monitor_pages_when_proxy_is_unavailable(tmp_path):
    from broker_proxy.auth_monitor import check_authorization
    def offline(_): raise ConnectionRefusedError()
    for _ in range(2):
        result=check_authorization(tmp_path/'agent.db','unused',now=NOW,
            dashboard_base_url='http://localhost',client_factory=offline)
    assert result['status']=='PROXY_UNAVAILABLE'
    with sqlite3.connect(tmp_path/'agent.db') as db:
        assert db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0]==1


class MemoryKeychain:
    def __init__(self): self.values = {}
    def get_password(self, service, account): return self.values.get((service, account))
    def set_password(self, service, account, value): self.values[(service, account)] = value


@pytest.mark.asyncio
async def test_token_timing_uses_expires_in_and_contains_no_credentials():
    from broker_proxy.oauth import KeychainOAuthStorage

    backend = MemoryKeychain()
    storage = KeychainOAuthStorage(backend=backend, clock=lambda: NOW)
    tokens = OAuthToken(access_token='access-secret', refresh_token='refresh-secret',
                        expires_in=767302, scope='internal')
    await storage.set_tokens(tokens)
    timing = json.loads(backend.values[(storage.service, 'token_timing')])

    assert timing['stored_at'] == NOW.isoformat()
    assert timing['expires_at'] == (NOW + timedelta(seconds=767302)).isoformat()
    assert len(timing['authorization_id']) == 32
    encoded = json.dumps(timing)
    assert 'access-secret' not in encoded
    assert 'refresh-secret' not in encoded


@pytest.mark.asyncio
async def test_expired_token_fails_before_remote_session_is_opened():
    from broker_proxy.oauth import KeychainOAuthStorage, OAuthUnavailable, require_noninteractive_tokens

    backend = MemoryKeychain()
    storage = KeychainOAuthStorage(backend=backend, clock=lambda: NOW)
    await storage.set_tokens(OAuthToken(access_token='secret', expires_in=60, scope='internal'))
    storage.clock = lambda: NOW + timedelta(seconds=60)

    with pytest.raises(OAuthUnavailable, match='AUTH_EXPIRED'):
        await require_noninteractive_tokens(storage)


def test_three_day_and_one_day_pages_are_deduplicated_and_redacted(tmp_path):
    from broker_proxy.auth_monitor import record_authorization_status

    path = tmp_path / 'agent.db'
    base = {
        'authorization_id': 'a' * 32,
        'expires_at': (NOW + timedelta(days=3)).isoformat(),
    }
    for status in ('WARNING_3_DAYS', 'WARNING_3_DAYS', 'WARNING_1_DAY', 'WARNING_1_DAY'):
        record_authorization_status(
            path, {**base, 'status': status}, now=NOW,
            dashboard_base_url='http://127.0.0.1:8765',
        )
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT event_id,title,body FROM notification_outbox ORDER BY event_id').fetchall()
    assert len(rows) == 2
    assert all('secret' not in ''.join(row) for row in rows)
    assert all('Robinhood authorization' in row[1] for row in rows)


def test_refresh_failure_pages_immediately_once(tmp_path):
    from broker_proxy.auth_monitor import record_authorization_status

    path = tmp_path / 'agent.db'
    status = {'authorization_id': 'b' * 32, 'status': 'REFRESH_FAILED', 'expires_at': None}
    record_authorization_status(path, status, now=NOW,
                                dashboard_base_url='http://127.0.0.1:8765')
    record_authorization_status(path, status, now=NOW,
                                dashboard_base_url='http://127.0.0.1:8765')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0] == 1
