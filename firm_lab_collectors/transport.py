"""The one place a Firm Lab collector opens a network connection.

HTTPS GET only (plain HTTP is allowed solely for a vendor terminal on 127.0.0.1), to hosts named in advance,
with a minimum interval between requests, a size cap, no retry and no redirect to another host. A failure is
returned as a response with its status; it is never retried in a loop.
"""
from __future__ import annotations

import gzip
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone


class TransportRefused(Exception):
    """The request was not sent: wrong scheme, a host that was not named in advance, or a missing User-Agent."""


@dataclass(frozen=True)
class Response:
    status: int                 # HTTP status, or 0 when no answer was received
    body: bytes
    url: str                    # as requested, with any secret query value removed
    fetched_at: str             # when the answer arrived (UTC)
    error: str = ''
    headers: dict = None

    @property
    def ok(self) -> bool:
        return self.status == 200


SECRET_PARAMETERS = ('api_key', 'apikey', 'apiKey', 'token', 'key')


def redact(url: str) -> str:
    """The URL with secret query values replaced, safe to store as a source id."""
    parts = urllib.parse.urlsplit(url)
    query = [(k, 'REDACTED' if k in SECRET_PARAMETERS else v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(query), ''))


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            raise urllib.error.HTTPError(req.full_url, code, 'redirect to another host refused', headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpTransport:
    def __init__(self, allowed_hosts, *, user_agent=None, min_interval=0.25, timeout=20, max_bytes=25_000_000, opener=None,
                 clock=time.monotonic, sleep=time.sleep, wall=None):
        self.allowed_hosts = frozenset(allowed_hosts)
        self.user_agent = user_agent
        self.min_interval, self.timeout, self.max_bytes = float(min_interval), timeout, int(max_bytes)
        self._opener = opener or urllib.request.build_opener(_SameHostRedirects)
        self._clock, self._sleep = clock, sleep
        self._wall = wall or (lambda: datetime.now(timezone.utc))
        self._last = None
        self.requests = 0

    def _check(self, url):
        parts = urllib.parse.urlsplit(url)
        local = parts.hostname == '127.0.0.1'
        if parts.scheme != 'https' and not (parts.scheme == 'http' and local):
            raise TransportRefused('only https is allowed (http only for a terminal on 127.0.0.1)')
        if parts.netloc not in self.allowed_hosts:
            raise TransportRefused(f'host not named in advance: {parts.netloc}')

    def get(self, url, headers=None) -> Response:
        self._check(url)
        if self._last is not None:
            wait = self.min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        send = {'Accept-Encoding': 'gzip', **(headers or {})}
        if self.user_agent:
            send['User-Agent'] = self.user_agent
        request = urllib.request.Request(url, headers=send, method='GET')
        self.requests += 1
        try:
            with self._opener.open(request, timeout=self.timeout) as reply:
                raw = reply.read(self.max_bytes + 1)
                status, reply_headers = reply.status, {str(k).lower(): v for k, v in reply.headers.items()}
        except urllib.error.HTTPError as error:
            self._last = self._clock()
            body = b''
            try:
                body = error.read(4096)
            except Exception:
                pass
            return Response(error.code, body, redact(url), self._wall().isoformat(), f'HTTP {error.code}', {})
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self._last = self._clock()
            return Response(0, b'', redact(url), self._wall().isoformat(), type(error).__name__, {})
        self._last = self._clock()
        if len(raw) > self.max_bytes:
            return Response(0, b'', redact(url), self._wall().isoformat(), 'RESPONSE_TOO_LARGE', {})
        if reply_headers.get('content-encoding', '').lower() == 'gzip' or raw[:2] == b'\x1f\x8b':
            try:
                raw = gzip.decompress(raw)
            except OSError:
                return Response(0, b'', redact(url), self._wall().isoformat(), 'BAD_GZIP', {})
        return Response(status, raw, redact(url), self._wall().isoformat(), '', reply_headers)
