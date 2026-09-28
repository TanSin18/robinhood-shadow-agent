from __future__ import annotations

import json
import os
import socket
import stat
import struct
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest


class FakeUpstream:
    def __init__(self) -> None:
        from broker.read_contracts import SCHEMAS

        self.calls: list[tuple[str, dict]] = []
        self.tools = [
            {"name": name, "inputSchema": schema} for name, schema in SCHEMAS.items()
        ] + [{"name": "place_equity_order", "inputSchema": {"type": "object"}}]

    def list_remote_tools(self):
        return self.tools

    def authorization_evidence(self):
        return {
            "selected_path": "full_scope_bounded_cash_fallback",
            "granted_scope_names": ["internal"],
            "keychain_retrieval": "available",
        }

    def call_read(self, name, arguments):
        self.calls.append((name, arguments))
        data = {"accounts": [
            {"account_number": "agentic-test", "rhs_account_number": "crypto-test", "agentic_allowed": True},
            {"account_number": "personal-test", "rhs_account_number": "personal-crypto", "agentic_allowed": False},
        ]} if name == "get_accounts" else {}
        return {"structuredContent": {"data": data}}


@contextmanager
def running_proxy(tmp_path, *, peer_uid=None, native_identity=False, operator_uid=None):
    from broker_proxy.server import BrokerProxyServer
    from broker_proxy.server import _peer_uid

    upstream = FakeUpstream()
    # macOS limits AF_UNIX paths to roughly 104 bytes; pytest's descriptive
    # temporary paths regularly exceed it.
    short_runtime = Path(tempfile.gettempdir()) / f"rh-proxy-{uuid.uuid4().hex[:12]}"
    server = BrokerProxyServer(
        socket_path=short_runtime / "robinhood-read.sock",
        operator_uid=os.getuid() if operator_uid is None else operator_uid,
        upstream=upstream,
        preregistration_hash="a" * 64,
        config_hash="b" * 64,
        peer_uid_resolver=(_peer_uid if native_identity else
                           lambda _connection: os.getuid() if peer_uid is None else peer_uid),
    )
    server.start()
    try:
        yield server, upstream
    finally:
        server.close()
        short_runtime.rmdir()


def _send_frame(connection: socket.socket, payload: bytes) -> None:
    connection.sendall(struct.pack("!I", len(payload)))
    try:
        connection.sendall(payload)
    except BrokenPipeError:
        # A bounded server may reject from the length prefix alone.
        pass


def _receive_frame(connection: socket.socket) -> dict:
    size = struct.unpack("!I", connection.recv(4))[0]
    body = bytearray()
    while len(body) < size:
        body.extend(connection.recv(size - len(body)))
    return json.loads(body)


def raw_request(socket_path, payload: dict | bytes) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(socket_path))
        greeting = _receive_frame(connection)
        if "error" in greeting:
            return greeting
        encoded = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        _send_frame(connection, encoded)
        return _receive_frame(connection)


def test_proxy_accepts_operator_using_real_kernel_identity(tmp_path):
    with running_proxy(tmp_path, native_identity=True) as (server, upstream):
        response = raw_request(server.socket_path,
                               {"id": "native", "method": "get_accounts", "arguments": {}})
    assert "error" not in response
    assert upstream.calls == [("get_accounts", {})]


def test_proxy_rejects_real_peer_when_operator_is_a_different_uid(tmp_path):
    with running_proxy(tmp_path, native_identity=True,
                       operator_uid=os.getuid() + 1000) as (server, upstream):
        response = raw_request(server.socket_path,
                               {"id": "native", "method": "get_accounts", "arguments": {}})
    assert response["error"]["code"] == "PEER_NOT_ALLOWED"
    assert upstream.calls == []


@pytest.mark.parametrize(
    "method",
    [
        "place_equity_order",
        "preview_crypto_order",
        "review_option_order",
        "cancel_option_order",
        "exercise_option",
        "transfer_money",
        "deposit_funds",
        "withdraw_funds",
        "update_account_settings",
        "mcp__robinhood_trading__get_accounts",
        "get_accounts.extra",
        " get_accounts",
        "GET_ACCOUNTS",
        "get_accounts\N{FULLWIDTH LOW LINE}extra",
    ],
)
def test_proxy_rejects_every_nonallowlisted_method_before_upstream(tmp_path, method):
    with running_proxy(tmp_path) as (server, upstream):
        response = raw_request(
            server.socket_path,
            {"id": "1", "method": method, "arguments": {}},
        )

    assert response["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert upstream.calls == []


def test_main_proxy_client_completes_without_reading_keyring(tmp_path, monkeypatch):
    from broker.proxy_client import BrokerProxyClient
    import keyring

    monkeypatch.setattr(
        keyring,
        "get_password",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("main process attempted to read proxy keychain")
        ),
    )

    with running_proxy(tmp_path) as (server, _upstream):
        client = BrokerProxyClient(server.socket_path).open()
        try:
            result = client.call_read("get_accounts", {})
        finally:
            client.close()

    assert result["structuredContent"]["data"]["accounts"]


def test_proxy_socket_is_group_only_and_rejects_oversize_or_malformed_frames(tmp_path):
    from broker.read_contracts import REQUEST_MAX_BYTES

    with running_proxy(tmp_path) as (server, upstream):
        assert stat.S_IMODE(server.socket_path.stat().st_mode) == 0o660
        assert stat.S_IMODE(server.socket_path.parent.stat().st_mode) == 0o770
        oversized = raw_request(server.socket_path, b"{" * (REQUEST_MAX_BYTES + 1))
        duplicate = raw_request(
            server.socket_path,
            b'{"id":"1","method":"get_accounts","method":"get_portfolio","arguments":{}}',
        )

    assert oversized["error"]["code"] == "FRAME_TOO_LARGE"
    assert duplicate["error"]["code"] == "INVALID_REQUEST"
    assert upstream.calls == []


@pytest.mark.parametrize(
    "arguments",
    [None, [], {"symbols": [f"S{index}" for index in range(21)]}],
)
def test_proxy_rejects_invalid_or_over_cardinality_arguments_before_upstream(
    tmp_path, arguments
):
    with running_proxy(tmp_path) as (server, upstream):
        response = raw_request(
            server.socket_path,
            {"id": "1", "method": "get_equity_quotes", "arguments": arguments},
        )

    assert response["error"]["code"] == "INVALID_ARGUMENTS"
    assert upstream.calls == []


def test_proxy_rejects_unregistered_peer_uid_before_greeting_or_dispatch(tmp_path):
    with running_proxy(tmp_path, peer_uid=os.getuid() + 1000) as (server, upstream):
        response = raw_request(server.socket_path, {"id": "1", "method": "get_accounts", "arguments": {}})

    assert response["error"]["code"] == "PEER_NOT_ALLOWED"
    assert upstream.calls == []


def test_proxy_inventory_is_exactly_the_eleven_registered_reads(tmp_path):
    from broker.proxy_client import BrokerProxyClient
    from broker.read_contracts import READ_METHODS

    with running_proxy(tmp_path) as (server, _upstream):
        client = BrokerProxyClient(server.socket_path).open()
        try:
            greeting = client.authorization_evidence()
            tools = client.list_remote_tools()
        finally:
            client.close()

    assert {tool.name for tool in tools} == READ_METHODS
    assert greeting["effective_read_tools"] == sorted(READ_METHODS)
    assert greeting["effective_write_tool_count"] == 0
    assert greeting["protocol_version"] == "1"


@pytest.mark.parametrize('method,key,wrong', [
    ('get_equity_orders', 'account_number', 'personal-test'),
    ('get_option_orders', 'account_number', 'personal-test'),
    ('get_crypto_orders', 'rhs_account_number', 'agentic-test'),
    ('get_portfolio', 'account_number', 'personal-test'),
    ('get_equity_positions', 'account_number', 'personal-test'),
])
def test_proxy_denies_account_mismatch_before_scoped_read(tmp_path, method, key, wrong):
    with running_proxy(tmp_path) as (server, upstream):
        response = raw_request(server.socket_path,
                               {'id': 'scope', 'method': method, 'arguments': {key: wrong}})
    assert response['error']['code'] == 'ACCOUNT_NOT_ALLOWED'
    assert not any(name == method for name, _ in upstream.calls)


def test_proxy_returns_only_the_verified_agentic_account(tmp_path):
    with running_proxy(tmp_path) as (server, _):
        response = raw_request(server.socket_path,
                               {'id': 'scope', 'method': 'get_accounts', 'arguments': {}})
    accounts = response['result']['structuredContent']['data']['accounts']
    assert [item['account_number'] for item in accounts] == ['agentic-test']


@pytest.mark.parametrize('method,key,account', [
    ('get_equity_orders', 'account_number', 'agentic-test'),
    ('get_option_orders', 'account_number', 'agentic-test'),
    ('get_crypto_orders', 'rhs_account_number', 'crypto-test'),
])
def test_proxy_allows_histories_only_for_verified_mapping(tmp_path, method, key, account):
    with running_proxy(tmp_path) as (server, upstream):
        args = {key: account, 'created_at_gte': '2026-09-28T14:00:00+00:00'}
        response = raw_request(server.socket_path,
                               {'id': 'scope', 'method': method, 'arguments': args})
    assert 'error' not in response
    assert (method, args) in upstream.calls
