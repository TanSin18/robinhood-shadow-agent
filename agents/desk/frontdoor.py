"""Dashboard-only front door. Existing operational handlers remain unchanged."""
from urllib.parse import urlsplit

from agents.inbox_web import make_server as operational_server
from .preview import snapshot, ASSETS
from .router import render
from .components import ROUTES


def make_server(inbox, port=8765, **options):
    server = operational_server(inbox, port, **options)
    base = server.RequestHandlerClass

    class Handler(base):
        desk_response = False

        def send_header(self, keyword, value):
            if keyword.lower() == 'location' and value.startswith('/#'):
                value = '/legacy' + value[1:]
            if keyword.lower() == 'content-security-policy' and not self.desk_response and "font-src" not in value:
                value = value + "; font-src 'self'"
            if keyword.lower() == 'content-security-policy' and self.desk_response:
                value = "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
            super().send_header(keyword, value)

        def send(self, status, content, content_type='text/html; charset=utf-8'):
            if not self.desk_response and content_type.startswith('text/html'):
                content = content.replace('href="/#', 'href="/legacy#').replace('action="/#', 'action="/legacy#')
                content = content.replace('action="/"', 'action="/legacy"').replace('href="/"', 'href="/legacy"')
                content = content.replace('<main ', '<a class="button" href="/">Agent Desk home</a><main ', 1)
                # Same look as Agent Desk; markup, forms and checks unchanged.
                content = content.replace('<link rel="stylesheet" href="/assets/dashboard.css">',
                    '<link rel="stylesheet" href="/assets/dashboard.css"><link rel="stylesheet" href="/assets/legacy-skin.css">', 1)
                content = content.replace('<body ', '<body class="legacy-skin" ', 1)
                content = content.replace('<p class="rail-caption">Your paper trading desk</p>',
                    '<p class="rail-caption">Approvals &amp; controls</p><a class="desk-back" href="/">← Agent Desk: Today, Decision room, Checks</a>', 1)
            super().send(status, content, content_type)

        def do_GET(self):
            self.desk_response = False
            if not self.allowed():
                return self.send(403, 'Local access only')
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == '/legacy':
                self.path = '/' + ('?' + parsed.query if parsed.query else '')
                return super().do_GET()
            if path in dict(ROUTES):
                self.desk_response = True
                try:
                    state = snapshot(inbox.path)
                    body = render(path, state, None, '')
                    body = body.replace('Preview — view only · No approvals, controls or broker connection',
                        'Agent Desk — view only · Real orders blocked · '
                        '<a href="/legacy#decisions">Approvals</a> · <a href="/legacy#controls">Live controls</a> · '
                        '<a href="/legacy#history">Full history</a>')
                    body = body.replace('http://127.0.0.1:8765/#controls', '/legacy#controls')
                    body = body.replace('Open live controls on 8765', 'Open live controls')
                except Exception:
                    return self.send(503, 'Agent Desk records unavailable. <a href="/legacy">Open operational dashboard</a>. No healthy status is assumed.')
                return self.send(200, body)
            if path.startswith('/assets/'):
                asset = (ASSETS / path.removeprefix('/assets/')).resolve()
                types = {'.css':'text/css; charset=utf-8', '.js':'text/javascript; charset=utf-8',
                         '.svg':'image/svg+xml', '.woff2':'font/woff2'}
                if asset.is_relative_to(ASSETS) and asset.is_file() and asset.suffix in types:
                    # Existing response helper is text-only; serve binary assets separately.
                    payload = asset.read_bytes()
                    self.desk_response = True
                    self.send_response(200)
                    for key,value in {'Content-Type':types[asset.suffix], 'Content-Length':str(len(payload)),
                            'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
                            'Content-Security-Policy':"default-src 'none'"}.items():
                        self.send_header(key,value)
                    self.end_headers()
                    self.wfile.write(payload)
                    return
            return super().do_GET()

    server.RequestHandlerClass = Handler
    return server
