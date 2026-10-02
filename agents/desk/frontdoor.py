"""Dashboard-only front door. Existing operational handlers remain unchanged."""
from urllib.parse import urlsplit

from agents.inbox_web import make_server as operational_server
from .preview import snapshot, ASSETS
from .router import render
from .components import ROUTES, nav_links, brand, truth_bar


def make_server(inbox, port=8765, **options):
    server = operational_server(inbox, port, **options)
    base = server.RequestHandlerClass
    import secrets
    inbox_csrf = secrets.token_urlsafe(32)   # form token for the desk pages' own forms (Inbox answers, Ask Bubbles)
    from threading import Lock
    from urllib.parse import urlparse
    ask_lock = Lock()                        # one question at a time
    external = urlparse(inbox.config.notifications.dashboard_base_url)
    external_origin = f'{external.scheme}://{external.netloc}'   # the private (tailnet) address, same as the operational page allows

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
                # Truthful names on the operational page too. Text replacement only: the page's own source is not edited.
                for old, new in (('Agent + my approvals', 'Approval arm'), ('With your approvals', 'Approval arm'), ('Agent alone', 'Automatic arm'),
                                 ('Defined-risk options', 'Options (PAUSED)')):
                    content = content.replace(old, new)
                import re as _re
                content = _re.sub(r'(<main\b[^>]*>)', lambda m: m.group(1) + truth_bar(), content, count=1)
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
                                 brand().replace('class="desk-brand', 'class="brand desk-brand', 1), content, count=1, flags=re.S)
                content = re.sub(r'<nav class="desktop-nav"[^>]*>.*?</nav>',
                                 '<nav class="desktop-nav" aria-label="Sections">' + nav_links('') + '</nav>', content, count=1, flags=re.S)
                content = re.sub(r'<nav class="phone-nav"[^>]*>.*?</nav>(?=</body>)',
                                 '<nav class="phone-nav" aria-label="Sections">' + nav_links('') + '</nav>', content, count=1, flags=re.S)
                if '<body class="legacy-skin"' in content:
                    from .ask_page import floating
                    content = content.replace('</body>', floating(inbox_csrf, 'Approvals, History and Controls page') + '</body>', 1)
            super().send(status, content, content_type)

        def do_POST(self):
            self.desk_response = False
            self.desk_forms = False
            target = urlsplit(self.path).path
            if target == '/ask/question':
                return self.ask_question()
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

        def ask_question(self):
            """Ask Bubbles. Same-origin form with the desk token; the runtime (a separate process) calls the model."""
            import hmac
            from urllib.parse import parse_qs
            from . import ask_page

            def back(notice=''):
                self.send_response(303)
                self.send_header('Location', '/ask' + (f'?notice={notice}' if notice else '') + '#latest')
                self.send_header('Content-Length', '0')
                self.end_headers()
            origin = self.headers.get('Origin')
            local = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}', external_origin}
            if not self.allowed() or (origin is not None and origin not in local):
                return self.send(403, 'Invalid request origin')
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                length = 0
            if not 0 < length <= 4096:
                return self.send(400, 'Invalid request')
            try:
                form = parse_qs(self.rfile.read(length).decode(), max_num_fields=6)
            except (ValueError, UnicodeDecodeError):
                return self.send(400, 'Invalid request')
            if any(len(v) != 1 for v in form.values()) or not hmac.compare_digest(form.get('csrf', [''])[0], inbox_csrf):
                return self.send(403, 'Invalid request token')
            question = ' '.join(form.get('question', [''])[0].split())
            context = ' '.join(form.get('context', [''])[0].split())[:120]
            run, step = form.get('run', [''])[0][:64], form.get('step', [''])[0][:20]
            if not question:
                return back('EMPTY_QUESTION')
            if len(question) > 500:
                return back('QUESTION_TOO_LONG')
            if not ask_lock.acquire(blocking=False):
                return back('BUSY')
            try:
                try:
                    packet = ask_page.build_packet(snapshot(inbox.path), question, context, run or None, step or None)
                except Exception:
                    return back('RECORDS_UNAVAILABLE')
                status = ask_page.submit(inbox.path, question, context, packet)
            finally:
                ask_lock.release()
            return back('' if status == 'ANSWERED' or status.startswith('FAILED_') else status if status in ask_page.NOTICES else 'RUNTIME_NOT_READY')

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
                self.desk_forms = True      # every desk page carries the Ask Bubbles form (same-origin only)
                try:
                    try:
                        state = snapshot(inbox.path)
                    except Exception:
                        if path != '/guide':
                            raise
                        state = {'preview': True}   # the walkthrough needs no records
                    state = {**state, 'inbox_csrf': inbox_csrf}
                    if path == '/ask':
                        from urllib.parse import parse_qs
                        from . import ask_page
                        notice = parse_qs(parsed.query).get('notice', [''])[0]
                        state = {**state, 'ask': ask_page.load(inbox.path), 'ask_notice': notice if notice in ask_page.NOTICES else None}
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
