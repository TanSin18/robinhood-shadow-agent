"""Minimal credential-bearing read-only Robinhood proxy."""
from __future__ import annotations

import hashlib
import ctypes
import json
import os
import argparse
import grp
import signal
import socket
import stat
import sys
import threading
from pathlib import Path
from typing import Any, Callable

from broker.read_contracts import READ_METHODS, SCHEMAS, structural
from broker_proxy.protocol import ProtocolError, receive_json, send_json


def _tool_value(tool: Any, name: str) -> Any:
    if isinstance(tool, dict):
        return tool.get(name)
    return getattr(tool, name, None)


def _peer_uid(connection: socket.socket) -> int:
    getter = getattr(connection, "getpeereid", None)
    if getter is not None:
        uid, _gid = getter()
        return int(uid)
    # CPython on macOS does not expose socket.getpeereid. Use the native
    # kernel-backed libc API; never trust a UID supplied by the client.
    if sys.platform == "darwin":
        try:
            native = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True).getpeereid
            native.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint),
                               ctypes.POINTER(ctypes.c_uint)]
            native.restype = ctypes.c_int
            uid, gid = ctypes.c_uint(), ctypes.c_uint()
            if native(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) == 0:
                return int(uid.value)
        except (AttributeError, OSError):
            pass
    # Linux: the kernel's SO_PEERCRED (pid, uid, gid) for the connected Unix socket.
    if sys.platform.startswith("linux") and hasattr(socket, "SO_PEERCRED"):
        try:
            import struct
            _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
            return int(uid)
        except (OSError, struct.error):
            pass
    raise ProtocolError("PEER_ID_UNAVAILABLE", "peer identity is unavailable")


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    return value


def _validate_arguments(method: str, arguments: Any) -> dict:
    if not isinstance(arguments, dict):
        raise ProtocolError("INVALID_ARGUMENTS", "arguments must be an object")
    schema = SCHEMAS[method]
    properties = schema.get("properties", {})
    if set(arguments) - set(properties):
        raise ProtocolError("INVALID_ARGUMENTS", "unexpected argument")
    if set(schema.get("required", [])) - set(arguments):
        raise ProtocolError("INVALID_ARGUMENTS", "missing required argument")
    for key, value in arguments.items():
        expected = properties[key].get("type")
        allowed = expected if isinstance(expected, list) else [expected]
        if value is None and "null" in allowed:
            continue
        if "string" in allowed:
            if not isinstance(value, str) or not 1 <= len(value) <= 1024:
                raise ProtocolError("INVALID_ARGUMENTS", f"invalid {key}")
            continue
        if "array" in allowed:
            maximum = 10 if method == "get_equity_historicals" else 20
            if (
                not isinstance(value, list)
                or not 1 <= len(value) <= maximum
                or any(not isinstance(item, str) or not 1 <= len(item) <= 1024 for item in value)
            ):
                raise ProtocolError("INVALID_ARGUMENTS", f"invalid {key}")
            continue
        raise ProtocolError("INVALID_ARGUMENTS", f"unsupported schema for {key}")
    return dict(arguments)


class BrokerProxyServer:
    """Serve the fixed read surface to one registered operator UID."""

    def __init__(
        self,
        *,
        socket_path: str | Path,
        operator_uid: int,
        upstream: Any,
        preregistration_hash: str,
        config_hash: str,
        peer_uid_resolver: Callable[[socket.socket], int] = _peer_uid,
        socket_gid: int | None = None,
    ) -> None:
        self.socket_path = Path(socket_path)
        self.operator_uid = operator_uid
        self.upstream = upstream
        self.preregistration_hash = preregistration_hash
        self.config_hash = config_hash
        self.peer_uid_resolver = peer_uid_resolver
        self.socket_gid = socket_gid
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._workers: list[threading.Thread] = []
        self._closing = threading.Event()
        self._greeting: dict[str, Any] | None = None
        self._authorization_failure: str | None = None

    def _catalog_greeting(self) -> dict[str, Any]:
        tools = self.upstream.list_remote_tools()
        catalog: list[dict[str, Any]] = []
        by_name: dict[str, dict] = {}
        for tool in tools:
            name = _tool_value(tool, "name")
            input_schema = _tool_value(tool, "inputSchema")
            if input_schema is None:
                input_schema = _tool_value(tool, "input_schema")
            if not isinstance(name, str) or not isinstance(input_schema, dict) or name in by_name:
                raise RuntimeError("UNEXPECTED_CAPABILITY")
            normalized = structural(input_schema)
            by_name[name] = normalized
            catalog.append({"name": name, "inputSchema": normalized})
        for name, expected in SCHEMAS.items():
            if by_name.get(name) != expected:
                raise RuntimeError("UNEXPECTED_CAPABILITY")
        authorization = self.upstream.authorization_evidence()
        if not isinstance(authorization, dict):
            raise RuntimeError("AUTH_EVIDENCE_INVALID")
        catalog_hash = hashlib.sha256(
            json.dumps(
                sorted(catalog, key=lambda item: item["name"]),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        return {
            **authorization,
            "protocol_version": "1",
            "remote_catalog_hash": catalog_hash,
            "remote_tool_count": len(catalog),
            "effective_read_tools": sorted(READ_METHODS),
            "effective_write_tool_count": 0,
            "preregistration_hash": self.preregistration_hash,
            "config_hash": self.config_hash,
        }

    def start(self) -> None:
        if self._socket is not None:
            return
        self._greeting = self._catalog_greeting()
        parent = self.socket_path.parent
        if parent.exists() and (parent.is_symlink() or not parent.is_dir()):
            raise RuntimeError("unsafe proxy runtime directory")
        parent.mkdir(parents=True, mode=0o770, exist_ok=True)
        os.chmod(parent, 0o770)
        if os.path.lexists(self.socket_path):
            details = self.socket_path.lstat()
            if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.getuid():
                raise RuntimeError("unsafe existing proxy socket")
            self.socket_path.unlink()
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o660)
            if self.socket_gid is not None:
                os.chown(parent, -1, self.socket_gid)
                os.chown(self.socket_path, -1, self.socket_gid)
            listener.listen(8)
            listener.settimeout(0.2)
        except BaseException:
            listener.close()
            if self.socket_path.exists():
                self.socket_path.unlink()
            raise
        self._socket = listener
        self._closing.clear()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self) -> None:
        assert self._socket is not None
        while not self._closing.is_set():
            try:
                connection, _address = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                if self._closing.is_set():
                    return
                raise
            worker = threading.Thread(
                target=self._serve_connection, args=(connection,), daemon=True
            )
            self._workers.append(worker)
            worker.start()

    def _send_error(self, connection: socket.socket, code: str, message: str) -> None:
        try:
            send_json(connection, {"error": {"code": code, "message": message}})
        except (OSError, ProtocolError):
            pass

    def _verified_agentic_account(self) -> dict:
        """Discover caller-relative eligibility; never trust the socket caller's ID."""
        result = _json_value(self.upstream.call_read("get_accounts", {}))
        if not isinstance(result, dict) or result.get("isError"):
            raise ProtocolError("ACCOUNT_NOT_ALLOWED", "account is not verified")
        payload = result.get("structuredContent", result.get("structured_content"))
        if payload is None:
            blocks = result.get("content", [])
            texts = [block.get("text") for block in blocks
                     if isinstance(block, dict) and block.get("type") == "text"]
            if len(texts) == 1:
                try:
                    payload = json.loads(texts[0])
                except (TypeError, ValueError):
                    pass
        data = payload.get("data") if isinstance(payload, dict) else None
        accounts = data.get("accounts") if isinstance(data, dict) else None
        matches = [item for item in accounts
                   if isinstance(item, dict) and item.get("agentic_allowed") is True] if isinstance(accounts, list) else []
        if len(matches) != 1 or not isinstance(matches[0].get("account_number"), str) or not matches[0]["account_number"]:
            raise ProtocolError("ACCOUNT_NOT_ALLOWED", "account is not verified")
        return matches[0]

    def _dispatch_read(self, method: str, arguments: dict) -> Any:
        account_keys = {"account_number", "rhs_account_number"} & arguments.keys()
        if method == "get_accounts" or account_keys:
            account = self._verified_agentic_account()
            for key in account_keys:
                expected = account.get(key)
                if not isinstance(expected, str) or not expected or arguments[key] != expected:
                    raise ProtocolError("ACCOUNT_NOT_ALLOWED", "account is not allowed")
            if method == "get_accounts":
                # Do not forward the provider's full account inventory or guide.
                return {"structuredContent": {"data": {"accounts": [account]}}}
        return _json_value(self.upstream.call_read(method, arguments))

    def _serve_connection(self, connection: socket.socket) -> None:
        with connection:
            try:
                peer_uid = self.peer_uid_resolver(connection)
            except BaseException:
                self._send_error(connection, "PEER_ID_UNAVAILABLE", "peer identity unavailable")
                return
            if peer_uid != self.operator_uid:
                self._send_error(connection, "PEER_NOT_ALLOWED", "peer is not registered")
                return
            assert self._greeting is not None
            if self._authorization_failure:
                self._send_error(connection, self._authorization_failure, 'authorization unavailable')
                return
            try:
                authorization = self.upstream.authorization_evidence()
            except Exception as error:
                code = str(error) if str(error) in {'AUTH_EXPIRED','AUTH_REFRESH_FAILED'} else 'AUTH_UNAVAILABLE'
                self._send_error(connection, code, 'authorization unavailable')
                return
            send_json(connection, {"greeting": {**self._greeting, **authorization}})
            while not self._closing.is_set():
                try:
                    request = receive_json(connection)
                except ProtocolError as error:
                    self._send_error(connection, error.code, str(error))
                    return
                except OSError:
                    return
                request_id = request.get("id")
                if set(request) != {"id", "method", "arguments"} or not isinstance(
                    request_id, str
                ):
                    self._send_error(connection, "INVALID_REQUEST", "invalid request envelope")
                    continue
                method = request.get("method")
                if not isinstance(method, str) or method not in READ_METHODS:
                    self._send_error(connection, "METHOD_NOT_ALLOWED", "method is not allowed")
                    continue
                try:
                    arguments = _validate_arguments(method, request.get("arguments"))
                    result = self._dispatch_read(method, arguments)
                    send_json(connection, {"id": request_id, "result": result})
                except ProtocolError as error:
                    self._send_error(connection, error.code, str(error))
                except BaseException as error:
                    code = str(error) if str(error) in {'AUTH_EXPIRED','AUTH_REFRESH_FAILED'} else 'UPSTREAM_READ_FAILED'
                    if code in {'AUTH_EXPIRED','AUTH_REFRESH_FAILED'}:
                        self._authorization_failure = code
                    self._send_error(connection, code, "read failed")

    def close(self) -> None:
        self._closing.set()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        for worker in self._workers:
            worker.join(timeout=2)
        self._workers.clear()
        if self.socket_path.exists() and self.socket_path.is_socket():
            self.socket_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/broker-proxy.local.yaml')
    parser.add_argument('--preregistration', default='preregistration.yaml')
    args = parser.parse_args()
    from broker_proxy.config import load_broker_proxy_config
    from broker_proxy.mcp_client import RobinhoodMCPClient
    from broker_proxy.oauth import KeychainOAuthStorage
    from broker_proxy.identity import require_proxy_identity
    require_proxy_identity()
    config_path = Path(args.config).resolve()
    preregistration_path = Path(args.preregistration).resolve()
    config = load_broker_proxy_config(config_path)
    if os.getuid() == config.operator_uid:
        raise RuntimeError('broker proxy must not run as the operator user')
    if grp.getgrnam(config.socket_group).gr_gid not in os.getgroups():
        raise RuntimeError('broker proxy is not in the configured socket group')
    client = RobinhoodMCPClient(
        server_url=config.server_url,
        storage=KeychainOAuthStorage(service=config.keychain_service),
    ).open(interactive=False)
    server = BrokerProxyServer(
        socket_path=config.socket_path,
        operator_uid=config.operator_uid,
        upstream=client,
        preregistration_hash=hashlib.sha256(preregistration_path.read_bytes()).hexdigest(),
        config_hash=hashlib.sha256(config_path.read_bytes()).hexdigest(),
        socket_gid=grp.getgrnam(config.socket_group).gr_gid,
    )
    stop = threading.Event()
    for event in (signal.SIGINT, signal.SIGTERM):
        signal.signal(event, lambda *_args: stop.set())
    try:
        server.start()
        stop.wait()
    finally:
        server.close()
        client.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
