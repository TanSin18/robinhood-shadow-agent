"""Unprivileged application client for the local read-only broker proxy."""
from __future__ import annotations

import socket
import threading
import uuid
from pathlib import Path

from broker.base import BrokerError
from broker.read_contracts import REQUEST_MAX_BYTES, RESPONSE_MAX_BYTES, SCHEMAS, ToolView
from broker_proxy.protocol import receive_json, send_json


class BrokerProxyClient:
    def __init__(self, socket_path: str | Path, *, timeout: float = 30) -> None:
        self.socket_path = Path(socket_path)
        self.timeout = timeout
        self._socket: socket.socket | None = None
        self._greeting: dict | None = None
        self._lock = threading.Lock()

    def open(self) -> "BrokerProxyClient":
        if self._socket is not None:
            return self
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(str(self.socket_path))
            message = receive_json(connection, maximum=RESPONSE_MAX_BYTES)
            if "error" in message:
                raise BrokerError(message["error"].get("code", "proxy rejected connection"))
            greeting = message.get("greeting")
            if not isinstance(greeting, dict):
                raise BrokerError("invalid broker proxy greeting")
        except BaseException:
            connection.close()
            raise
        self._socket = connection
        self._greeting = greeting
        return self

    def authorization_evidence(self) -> dict:
        if self._greeting is None:
            raise BrokerError("broker proxy client is not open")
        return dict(self._greeting)

    def list_remote_tools(self) -> list[ToolView]:
        return [ToolView(name, schema) for name, schema in SCHEMAS.items()]

    def call_read(self, name: str, arguments: dict) -> dict:
        if self._socket is None:
            raise BrokerError("broker proxy client is not open")
        request_id = str(uuid.uuid4())
        with self._lock:
            send_json(
                self._socket,
                {"id": request_id, "method": name, "arguments": arguments},
                maximum=REQUEST_MAX_BYTES,
            )
            response = receive_json(self._socket, maximum=RESPONSE_MAX_BYTES)
        error = response.get("error")
        if isinstance(error, dict):
            raise BrokerError(str(error.get("code", "broker proxy read failed")))
        if response.get("id") != request_id or "result" not in response:
            raise BrokerError("invalid broker proxy response")
        result = response["result"]
        if not isinstance(result, dict):
            raise BrokerError("invalid broker proxy result")
        return result

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        self._greeting = None

    def __enter__(self) -> "BrokerProxyClient":
        return self.open()

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
