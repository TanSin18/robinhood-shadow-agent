"""Dashboard-only front door. Existing operational handlers remain unchanged."""
from urllib.parse import urlsplit

from agents.inbox_web import make_server as operational_server
from .preview import snapshot, ASSETS
from .router import render
from .components import ROUTES, nav_links


def make_server(inbox, port=8765, **options):
    server = operational_server(inbox, port, **options)
    base = server.RequestHandlerClass
    import secrets
    inbox_csrf = secrets.token_urlsafe(32)   # the Inbox page's own form token

    class Handler(base):
        desk_response = False

        def send_header(self, keyword, value):
            if keyword.lower() == 'location' and value.startswith('/#'):
                value = '/legacy' + value[1:]
            if keyword.lower() == 'content-security-policy' and not self.desk_response and "font-src" not in value:
                value = value + "; font-src 'self'; img-src 'self'"   # the brand logo is an image on the operational page too
            if keyword.lower() == 'content-security-policy' and self.desk_response:
                form = "'self'" if getattr(self, 'desk_forms', False) else "'none'"
                value = ("default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self'; font-src 'self'; connect-src 'none'; "
                         f"form-action {form}; frame-ancestors 'none'; base-uri 'none'")
            super().send_header(keyword, value)

        def send(self, status, content, content_type='text/html; charset=utf-8'):
            if not self.desk_response and content_type.startswith('text/html'):
                content = content.replace('href="/#', 'href="/legacy#').replace('action="/#', 'action="/legacy#')
                content = content.replace('action="/"', 'action="/legacy"').replace('href="/"', 'href="/legacy"')
                content = content.replace('<main ', '<a class="button" href="/">Botfolio home</a><main ', 1)
                # Capital wording follows the ledger (v1.6 Lane A $25,000) instead of the old fixed "$500" text.
                try:
                    from .components import capital_note
                    note = capital_note(snapshot(inbox.path))
                except Exception:
                    note = ''
                content = content.replace('<p class="muted">Two independent $500 lanes. ',
                                          note + '<p class="muted">Two independent paper lanes; each lane header shows its recorded start. ', 1)
                content = content.replace('<p>Each lane starts at $500. ', '<p>Each lane starts at its recorded capital (Lane A $25,000 from the first v1.6 run; Lane B $500). ', 1)
                # Same look as Agent Desk; markup, forms and checks unchanged.
                content = content.replace('<link rel="stylesheet" href="/assets/dashboard.css">',
                    '<link rel="stylesheet" href="/assets/dashboard.css"><link rel="stylesheet" href="/assets/legacy-skin.css">'
                    '<link rel="stylesheet" href="/assets/botfolio-theme.css"><link rel="icon" href="/assets/botfolio-logo.svg">', 1)
                content = content.replace('<body ', '<body class="legacy-skin" ', 1)
                import re
                content = re.sub(r'<a class="brand" href="/legacy"[^>]*>.*?</a>\s*<p class="rail-caption">[^<]*</p>',
                                 '<a class="brand desk-brand bf-brand" href="/"><img src="/assets/botfolio-logo.svg" width="30" height="30" alt="">Botfolio</a>', content, count=1, flags=re.S)
                content = re.sub(r'<nav class="desktop-nav"[^>]*>.*?</nav>',
                                 '<nav class="desktop-nav" aria-label="Sections">' + nav_links('') + '</nav>', content, count=1, flags=re.S)
                content = re.sub(r'<nav class="phone-nav"[^>]*>.*?</nav>(?=</body>)',
                                 '<nav class="phone-nav" aria-label="Sections">' + nav_links('') + '</nav>', content, count=1, flags=re.S)
            super().send(status, content, content_type)

        def do_POST(self):
            self.desk_response = False
            self.desk_forms = False
            target = urlsplit(self.path).path
            if target not in ('/inbox/answer', '/firm/answer'):
                return super().do_POST()
            import hmac
            from datetime import datetime, timezone
            from urllib.parse import parse_qs
            origin = self.headers.get('Origin')
            local = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
            if not self.allowed() or (origin is not None and origin not in local):
                return self.send(403, 'Invalid request origin')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2048:
                    return self.send(400, 'Invalid request')
                form = parse_qs(self.rfile.read(length).decode(), max_num_fields=4)
                if any(len(v) != 1 for v in form.values()) or not hmac.compare_digest(form.get('csrf', [''])[0], inbox_csrf):
                    return self.send(403, 'Invalid request token')
                answer = form.get('answer', [''])[0]
                if target == '/firm/answer':
                    from agents.ai_trader import cycle as firm_cycle
                    from agents.ai_trader.hook import default_path as firm_path
                    from agents.ai_trader.store import TraderStore
                    if not firm_path(inbox.path).is_file():
                        return self.send(404, 'The AI trader is not set up. <a href="/firm">Back</a>')
                    store = TraderStore(firm_path(inbox.path), inbox.path)
                    firm_cycle.decide(store, form.get('card', [''])[0], answer, now=datetime.now(timezone.utc),
                                      cut_fraction=0.5 if answer == 'CUT' else None)
                    self.send_response(303); self.send_header('Location', '/firm'); self.send_header('Content-Length', '0'); self.end_headers()
                    return
                from agents.cards import LIVE_COPY_ENABLED, CardStore, default_path
                if answer == 'may_copy_live' and not LIVE_COPY_ENABLED:
                    return self.send(409, 'Live copy is off until the account safety check accepts acknowledgements. <a href="/inbox">Back</a>')
                CardStore(default_path(inbox.path), inbox.path).answer(form.get('card', [''])[0], answer,
                                                                       at=datetime.now(timezone.utc))
            except Exception as error:
                back = '/firm' if target == '/firm/answer' else '/inbox'
                return self.send(400, f'Answer not recorded ({type(error).__name__}). <a href="{back}">Back</a>')
            self.send_response(303)
            self.send_header('Location', '/inbox')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def do_GET(self):
            self.desk_response = False
            self.desk_forms = False
            if not self.allowed():
                return self.send(403, 'Local access only')
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == '/legacy':
                self.path = '/' + ('?' + parsed.query if parsed.query else '')
                return super().do_GET()
            if path in dict(ROUTES):
                self.desk_response = True
                self.desk_forms = path in ('/inbox', '/firm')
                try:
                    try:
                        state = snapshot(inbox.path)
                    except Exception:
                        if path != '/guide':
                            raise
                        state = {'preview': True}   # the walkthrough needs no records
                    if path in ('/inbox', '/firm'):
                        state = {**state, 'inbox_csrf': inbox_csrf}
                    body = render(path, state, None, '')
                    # One navigation (sidebar) covers Approvals/History/Results/Controls; no second banner.
                    body = body.replace('<p class="desk-preview" role="status">Preview — view only · No approvals, controls or broker connection</p>', '')
                    body = body.replace('http://127.0.0.1:8765/#controls', '/legacy#controls')
                    body = body.replace('Open live controls on 8765', 'Open live controls')
                except Exception:
                    return self.send(503, 'Botfolio records unavailable. <a href="/legacy">Open operational dashboard</a>. No healthy status is assumed.')
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
