"""Bounded, duplicate-key-safe framing for the local broker proxy."""
from __future__ import annotations

import json
import socket
import struct
from typing import Any

from broker.read_contracts import REQUEST_MAX_BYTES, RESPONSE_MAX_BYTES


class ProtocolError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("INVALID_REQUEST", "duplicate JSON key")
        result[key] = value
    return result


def _receive_exact(connection: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = connection.recv(size - len(result))
        if not chunk:
            raise ProtocolError("INVALID_REQUEST", "truncated frame")
        result.extend(chunk)
    return bytes(result)


def receive_json(connection: socket.socket, *, maximum: int = REQUEST_MAX_BYTES) -> dict:
    header = _receive_exact(connection, 4)
    size = struct.unpack("!I", header)[0]
    if size > maximum:
        raise ProtocolError("FRAME_TOO_LARGE", "frame exceeds configured limit")
    if size == 0:
        raise ProtocolError("INVALID_REQUEST", "empty frame")
    try:
        value = json.loads(
            _receive_exact(connection, size), object_pairs_hook=_reject_duplicate_keys
        )
    except ProtocolError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ProtocolError("INVALID_REQUEST", "invalid JSON") from None
    if not isinstance(value, dict):
        raise ProtocolError("INVALID_REQUEST", "request must be an object")
    return value


def send_json(
    connection: socket.socket, value: dict, *, maximum: int = RESPONSE_MAX_BYTES
) -> None:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if len(encoded) > maximum:
        raise ProtocolError("FRAME_TOO_LARGE", "response exceeds configured limit")
    connection.sendall(struct.pack("!I", len(encoded)) + encoded)

