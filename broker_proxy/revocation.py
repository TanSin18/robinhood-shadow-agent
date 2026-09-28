"""Private, operator-assisted drill. No secrets or account payloads are exported."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import time


async def probe_existing_token(token):
    """Use the existing bearer only: no refresh, consent, or credential deletion."""
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client
    from broker.policy import Stage1ToolPolicy
    from broker_proxy.mcp_client import ROBINHOOD_MCP_URL
    from broker_proxy.server import BrokerProxyServer

    Stage1ToolPolicy().authorize('get_accounts')
    rejected_at_transport = False

    async def observe_response(response):
        nonlocal rejected_at_transport
        # MCP can replace HTTPStatusError with a generic MCPError. Preserve only
        # the status of this exact authenticated request, never its body/token.
        if (response.request.method == 'POST'
            and str(response.request.url) == ROBINHOOD_MCP_URL
            and response.request.headers.get('Authorization') == 'Bearer ' + token
            and response.status_code in {401, 403}):
            rejected_at_transport = True

    try:
        async with asyncio.timeout(45):
            async with create_mcp_http_client(
                headers={'Authorization': 'Bearer ' + token},
                timeout=httpx2.Timeout(20),
            ) as http:
                http.event_hooks['response'].append(observe_response)
                async with streamable_http_client(ROBINHOOD_MCP_URL, http_client=http,
                                                  terminate_on_close=False) as (reads, writes):
                    async with ClientSession(reads, writes) as session:
                        await session.initialize()
                        result = await session.call_tool('get_accounts', {},
                                                        allow_input_required=False, allow_claimed=False)
                        server = BrokerProxyServer(socket_path='unused', operator_uid=1,
                            upstream=SimpleNamespace(call_read=lambda *_: result),
                            preregistration_hash='', config_hash='')
                        server._verified_agentic_account()
                        return 'READ_SUCCEEDED'
    except Exception as error:
        if rejected_at_transport:
            return 'AUTH_REJECTED'
        return classify_probe_error(error)


def classify_probe_error(error):
    import httpx2
    if isinstance(error, BaseExceptionGroup):
        values = [classify_probe_error(child) for child in error.exceptions]
        return 'AUTH_REJECTED' if values and all(v == 'AUTH_REJECTED' for v in values) else 'INCONCLUSIVE'
    if isinstance(error, httpx2.HTTPStatusError) and error.response.status_code in {401,403}:
        return 'AUTH_REJECTED'
    return 'INCONCLUSIVE'


def _save(path, state):
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
        json.dump(state, handle, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def receipt(state):
    return {key: value for key, value in state.items() if key != 'token_fingerprint'}


async def advance(action, path, storage, probe, now, *, bindings=None, clock=None):
    started = time.monotonic()
    clock = clock or (lambda: now + timedelta(seconds=time.monotonic() - started))
    path = Path(path)
    if now.tzinfo is None:
        raise ValueError('AWARE_TIME_REQUIRED')
    if path.is_symlink():
        raise ValueError('UNSAFE_DRILL_STATE')
    state = json.loads(path.read_text()) if path.exists() else {}
    if state and state.get('bindings') != bindings:
        raise ValueError('DRILL_CONFIGURATION_CHANGED')
    if state and now < datetime.fromisoformat(state['begun_at']):
        raise ValueError('DRILL_CLOCK_INVALID')
    token = await storage.get_tokens()
    fingerprint = hashlib.sha256(token.access_token.encode()).hexdigest() if token else None
    if action == 'begin':
        if state and state.get('status') != 'COMPLETED':
            raise ValueError('DRILL_ALREADY_IN_PROGRESS')
    else:
        expected = {'verify-revoked':'AWAITING_REMOTE_REVOKE',
                    'remove-local-credentials':'REMOTE_REJECTION_VERIFIED',
                    'verify-reauthorized':'AWAITING_REAUTHORIZATION'}
        recover = action == 'remove-local-credentials' and state.get('status') == 'LOCAL_DELETION_IN_PROGRESS'
        if (state.get('status') != expected.get(action) and not recover) or action not in expected:
            raise ValueError('INVALID_DRILL_STATE')
    if action in {'begin','verify-revoked','verify-reauthorized'}:
        if token is None:
            raise ValueError('AUTHORIZATION_MISSING')
        expires = datetime.fromisoformat(storage.authorization_status()['expires_at'])
        if expires.tzinfo is None or expires <= now:
            raise ValueError('AUTH_EXPIRED_NOT_REVOCATION_PROOF')
    recovery_without_token = (action == 'remove-local-credentials'
        and state.get('status') == 'LOCAL_DELETION_IN_PROGRESS' and token is None)
    if action in {'verify-revoked','remove-local-credentials'} and not recovery_without_token and fingerprint != state['token_fingerprint']:
        raise ValueError('DRILL_CREDENTIAL_CHANGED')
    if action == 'begin':
        if await probe(token.access_token) != 'READ_SUCCEEDED':
            raise ValueError('BASELINE_READ_NOT_PROVEN')
        if expires <= clock():
            raise ValueError('AUTH_EXPIRED_NOT_REVOCATION_PROOF')
        state = {'status':'AWAITING_REMOTE_REVOKE','begun_at':now.isoformat(),
                 'token_fingerprint':fingerprint,'bindings':bindings}
    elif action == 'verify-revoked':
        if await probe(token.access_token) != 'AUTH_REJECTED':
            raise ValueError('REMOTE_REVOCATION_NOT_PROVEN')
        if expires <= clock():
            raise ValueError('AUTH_EXPIRED_NOT_REVOCATION_PROOF')
        state.update(status='REMOTE_REJECTION_VERIFIED', revoked_read_failed_at=clock().isoformat())
    elif action == 'remove-local-credentials':
        state.update(status='LOCAL_DELETION_IN_PROGRESS')
        _save(path,state)
        storage.delete_tokens_and_client_info()
        if not storage.credentials_absent():
            raise ValueError('LOCAL_DELETION_NOT_PROVEN')
        state.update(status='AWAITING_REAUTHORIZATION',local_credentials_removed_at=now.isoformat())
    else:
        if fingerprint == state['token_fingerprint']:
            raise ValueError('NEW_AUTHORIZATION_REQUIRED')
        if await probe(token.access_token) != 'READ_SUCCEEDED':
            raise ValueError('REAUTHORIZED_READ_NOT_PROVEN')
        if expires <= clock():
            raise ValueError('AUTH_EXPIRED_NOT_REVOCATION_PROOF')
        state.update(status='COMPLETED',reauthorized_read_passed_at=now.isoformat())
    _save(path,state)
    return receipt(state)


def main():
    from broker_proxy.identity import require_proxy_identity
    from broker_proxy.oauth import KeychainOAuthStorage
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['begin','verify-revoked','remove-local-credentials','verify-reauthorized'])
    args=parser.parse_args()
    try:
        require_proxy_identity()
        root=Path(__file__).resolve().parents[1]
        bindings={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
                  for name in ('preregistration.yaml','config/broker-proxy.local.yaml')}
        result=asyncio.run(advance(args.action,root.parent.parent/'state/revocation.json',
            KeychainOAuthStorage(),probe_existing_token,datetime.now(timezone.utc),bindings=bindings,
            clock=lambda:datetime.now(timezone.utc)))
    except Exception as error:
        code=str(error) if type(error) is ValueError else type(error).__name__
        print(json.dumps({'status':'DRILL_BLOCKED','code':code}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
