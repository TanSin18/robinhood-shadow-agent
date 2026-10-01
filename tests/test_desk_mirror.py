"""Public read-only mirror: only review pages, no actions, private links scrubbed, snapshot rate-limited."""
import http.client
import threading
from datetime import datetime, timezone

from agents.desk import mirror


def _serve(monkeypatch, calls):
    def fake_snapshot(db, now=None):
        calls.append(now)
        return {'preview': True, 'updated_at': '2026-10-01T16:00:00+00:00', 'history': [], 'cards': [],
                'decision_room': [{'review_id': 'r', 'stages': [], 'outcome': {'reason': 'see https://box.tail1.ts.net:8443/trace/x'}}]}
    monkeypatch.setattr(mirror, 'snapshot', fake_snapshot)
    server = mirror.make_server('unused.db', 0, allowed_hosts=['box.tail1.ts.net:10000'])
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


def _get(port, path, host=None, method='GET'):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    c.request(method, path, headers={'Host': host or f'127.0.0.1:{port}'})
    r = c.getresponse()
    return r.status, r.read().decode(errors='replace'), dict(r.getheaders())


def test_mirror_serves_review_pages_only_and_never_accepts_writes(monkeypatch):
    calls = []
    server, port = _serve(monkeypatch, calls)
    try:
        status, body, headers = _get(port, '/architecture', host='box.tail1.ts.net:10000')
        assert status == 200 and 'Shared read-only view' in body and 'noindex' in headers['X-Robots-Tag']
        assert 'href="/legacy' not in body and 'href="/inbox"' not in body and 'href="/controls"' not in body
        for path in ('/inbox', '/firm', '/controls', '/health', '/legacy'):
            assert _get(port, path)[0] == 404
        assert _get(port, '/', method='POST')[0] == 405
        assert _get(port, '/', host='evil.example')[0] == 403
        assert _get(port, '/', host='box.tail1.ts.net')[0] == 200
        status, body, _ = _get(port, '/room')
        assert 'ts.net' not in body
        assert len(calls) == 1                       # one snapshot for all requests inside 30 s
    finally:
        server.shutdown()
