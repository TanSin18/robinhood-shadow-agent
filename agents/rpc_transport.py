"""Private, bounded app-server JSON-RPC transport. Never approves server requests."""
from __future__ import annotations

import json
import os
import selectors
import signal
import subprocess
import tempfile
import threading
import time


class ProtocolError(RuntimeError):
    pass


class RpcTransport:
    def __init__(self, command, *, max_line_bytes=4*1024*1024, max_total_bytes=32*1024*1024):
        self.directory = tempfile.TemporaryDirectory(prefix='shadow-rpc-')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, cwd=self.directory.name,
                                        start_new_session=True)
        self.selector = selectors.DefaultSelector()
        self.selector.register(self.process.stdout, selectors.EVENT_READ)
        self.buffer = b''
        self.next_id = 1
        self.notifications = []
        self.lock = threading.RLock()
        self.max_line_bytes, self.max_total_bytes = max_line_bytes, max_total_bytes
        self.total_bytes = 0
        self.closed = False
        self.event_guard=None
        self.denied_requests=False

    def send(self, message):
        try:
            self.process.stdin.write((json.dumps(message, allow_nan=False)+'\n').encode())
            self.process.stdin.flush()
        except (OSError, ValueError) as error:
            self.close()
            raise ProtocolError('protocol write failed') from error

    def read_event(self, *, timeout):
        deadline = time.monotonic() + timeout
        try:
            while b'\n' not in self.buffer:
                if len(self.buffer) > self.max_line_bytes:
                    raise ProtocolError('protocol line limit exceeded')
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not self.selector.select(remaining):
                    raise ProtocolError('protocol timeout')
                chunk = os.read(self.process.stdout.fileno(), 65536)
                if not chunk:
                    raise ProtocolError('protocol ended before response')
                self.total_bytes += len(chunk)
                if self.total_bytes > self.max_total_bytes:
                    raise ProtocolError('protocol response limit exceeded')
                self.buffer += chunk
            line, self.buffer = self.buffer.split(b'\n', 1)
            if len(line) > self.max_line_bytes:
                raise ProtocolError('protocol line limit exceeded')
            event = json.loads(line)
            if not isinstance(event, dict) or not event:
                raise ProtocolError('invalid protocol event')
            return event
        except (ValueError, OSError, ProtocolError) as error:
            self.close()
            if isinstance(error, ProtocolError):
                raise
            raise ProtocolError('malformed protocol response') from error

    def accept_notification(self, event):
        if not isinstance(event.get('method'), str):
            raise ProtocolError('unrecognized protocol event')
        if 'id' in event:
            self.denied_requests=True
            self.send({'id': event['id'], 'error': {'code': -32601, 'message': 'Request denied by shadow policy'}})
        if self.event_guard is not None:
            self.event_guard(event)
        if 'id' not in event:
            self.notifications.append(event)

    def request(self, method, params, *, timeout=30):
        with self.lock:
            request_id = self.next_id
            self.next_id += 1
            self.send({'id': request_id, 'method': method, 'params': params})
            deadline = time.monotonic()+timeout
            try:
                while True:
                    event = self.read_event(timeout=max(0, deadline-time.monotonic()))
                    if 'method' in event:
                        self.accept_notification(event)
                        continue
                    if event.get('id') != request_id or 'error' in event or not isinstance(event.get('result'), dict):
                        raise ProtocolError('invalid or failed RPC response')
                    return event['result']
            except Exception:
                self.close()
                raise

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
            except ProcessLookupError:
                self.process.wait(timeout=2)
        for stream in (self.process.stdin, self.process.stdout):
            stream.close()
        self.selector.close()
        self.directory.cleanup()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
