"""Public read-only mirror of the Agent Desk, for sharing with a reviewer through Tailscale Funnel.

    python -m agents.desk.mirror --database <agent.db> --port 8767 --allow-host <name>.ts.net:10000

What it is: the same view-only renderer as the local preview (SQLite opened mode=ro, query-only
authorizer, no broker, no models, no POST of any kind), plus:
  * only the review pages are served; Inbox, Approvals, Controls, Health, History and the AI-trader
    page are not routed at all, and links to them are removed from the navigation;
  * private dashboard links (*.ts.net) are scrubbed from page text; account identifiers are already
    stripped by the snapshot;
  * at most one database snapshot every 30 seconds, whatever the request rate;
  * search engines asked not to index (X-Robots-Tag) and no referrer sent onward.
It binds to 127.0.0.1 only; Funnel is what makes it reachable, and stopping Funnel closes it.
"""
import argparse
import re
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit

from .preview import ASSETS, snapshot
from .router import render

PUBLIC = ('/', '/portfolio', '/room', '/checks', '/money', '/scoreboard', '/guide', '/rules', '/architecture', '/analyst')
HIDDEN_LINKS = re.compile(r'<a href="/(legacy[^"]*|inbox|firm|controls|health|ask)"[^>]*>.*?</a>', re.S)
TS_LINK = re.compile(r'https://[a-z0-9.-]+\.ts\.net[^"<\s]*')
BANNER = 'Preview — view only · No approvals, controls or broker connection'
CSP = ("default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; "
       "form-action 'none'; frame-ancestors 'none'; base-uri 'none'")
TYPES = {'.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.woff2': 'font/woff2'}


def public_html(html, stamp):
    html = HIDDEN_LINKS.sub('', html)
    html = TS_LINK.sub('(private link removed)', html)
    return html.replace(BANNER, f'Shared read-only view · records as of {stamp} · paper trading only, real orders blocked · '
                                'nothing on this site can change anything')


def make_server(database, port=8767, *, allowed_hosts=(), clock=None, ttl=30.0, monotonic=time.monotonic):
    clock = clock or (lambda: datetime.now(timezone.utc))
    lock = Lock()
    cache = {'at': None, 'state': None}
    hosts = {*allowed_hosts, *(h.rsplit(':', 1)[0] for h in allowed_hosts)}

    def state():
        with lock:
            if cache['state'] is None or monotonic() - cache['at'] >= ttl:
                cache['state'] = snapshot(database, now=clock())
                cache['state']['analyst'] = cache['state'].get('analyst') or {'exists': False}
                cache['at'] = monotonic()
            return cache['state']

    class Handler(BaseHTTPRequestHandler):
        timeout = 10
        server_version = 'AgentDeskMirror'
        sys_version = ''

        def log_message(self, *args):
            pass

        def send(self, status, body, kind='text/html; charset=utf-8'):
            body = body.encode() if isinstance(body, str) else body
            self.send_response(status)
            for k, v in {'Content-Type': kind, 'Content-Length': str(len(body)), 'Cache-Control': 'no-store',
                         'X-Content-Type-Options': 'nosniff', 'X-Robots-Tag': 'noindex, nofollow', 'Referrer-Policy': 'no-referrer',
                         'Content-Security-Policy': CSP}.items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def do_POST(self):
            self.send(405, 'Read-only view. Nothing here can be changed.')
        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_POST

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            local = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in hosts | local:
                return self.send(403, 'Unknown host')
            path = urlsplit(self.path).path
            if path.startswith('/assets/'):
                asset = (ASSETS / path.removeprefix('/assets/')).resolve()
                if not asset.is_relative_to(ASSETS) or asset.suffix not in TYPES or not asset.is_file():
                    return self.send(404, 'Not found')
                return self.send(200, asset.read_bytes(), TYPES[asset.suffix])
            if path not in PUBLIC:
                return self.send(404, 'Not found on the shared view')
            try:
                st = state()
                stamp = datetime.fromisoformat(st['updated_at']).astimezone().strftime('%a %b %-d, %-I:%M %p %Z')
                body = public_html(render(path, st, None, ''), stamp)
            except Exception:
                return self.send(503, 'Records temporarily unavailable. Try again in a minute.')
            self.send(200, body)

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--database', required=True)
    p.add_argument('--port', type=int, default=8767)
    p.add_argument('--allow-host', action='append', default=[], help='Host header to accept, e.g. name.ts.net:10000')
    a = p.parse_args(argv)
    snapshot(a.database)
    with make_server(a.database, a.port, allowed_hosts=a.allow_host) as server:
        print(f'Read-only mirror: http://127.0.0.1:{server.server_port}', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
