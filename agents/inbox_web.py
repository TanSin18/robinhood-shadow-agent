"""Loopback-only paper dashboard. No route invokes a model or real broker."""
import argparse
import hmac
import html
import json
import secrets
import sqlite3
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from agents.dashboard import dashboard_snapshot, set_paused
from agents.dashboard_view import parse_filters, render_control, render_dashboard, shell
from agents.inbox import PaperInbox
from config.loader import load_config
from agents.desk.router import render as render_desk
from agents.desk.components import ROUTES
from agents.desk.team import TEAM


def scheduler_loaded():
    try:
        result = subprocess.run(['/bin/launchctl', 'list', 'com.openai.robinhood-daily'],
                                capture_output=True, timeout=2, check=False)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return None


def make_server(inbox, port=8765, *, proof=None, service_check=None, notification_channels=None):
    csrf = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name('static')
    external = urlparse(inbox.config.notifications.dashboard_base_url)
    external_host = external.netloc
    external_origin = f'{external.scheme}://{external.netloc}'

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            return self.headers.get('Host') in {
                f'127.0.0.1:{self.server.server_port}',
                f'localhost:{self.server.server_port}',
                external_host,
            }

        def send(self, status, content, content_type='text/html; charset=utf-8'):
            account = inbox.config.risk.agentic_account_id
            if account and isinstance(content, str):
                content = content.replace(account, '***' + account[-4:])
            body = content.encode() if isinstance(content, str) else content
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            # Keep a usable Origin on same-origin form POSTs; disclose nothing cross-origin.
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'; img-src 'self'; font-src 'self'")
            self.end_headers()
            self.wfile.write(body)

        def problem(self, status, message):
            return self.send(status, shell('Action not completed', '<main id="main" class="confirmation"><h1>Action not completed</h1><p>' + html.escape(message) + '</p><a class="button" href="/">Back to dashboard</a></main>'))

        def do_GET(self):
            if not self.allowed():
                return self.send(403, 'Local access only')
            parsed = urlparse(self.path)
            path = parsed.path
            desk_assets = {'/assets/agent-desk.css': 'text/css; charset=utf-8',
                           '/assets/agent-desk.js': 'text/javascript; charset=utf-8',
                           '/assets/fonts/Geist.woff2': 'font/woff2',
                           '/assets/fonts/GeistMono.woff2': 'font/woff2'}
            desk_assets.update({f'/assets/avatars/{entry[2]}': 'image/svg+xml' for entry in TEAM.values() if entry[2]})
            if path in desk_assets:
                return self.send(200, (assets / path.removeprefix('/assets/')).read_bytes(), desk_assets[path])
            if path in {'/assets/dashboard.css', '/assets/dashboard.js', '/assets/decision-room.js'}:
                kind = 'text/css' if path.endswith('.css') else 'text/javascript'
                return self.send(200, (assets / path.rsplit('/', 1)[1]).read_text(), kind + '; charset=utf-8')
            try:
                query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
                if path == '/control':
                    return self.send(200, render_control(query.get('action', [''])[0], csrf))
                if path.startswith('/trace/'):
                    key = unquote(path.removeprefix('/trace/'))
                    card = next((c for c in inbox.cards() if c['id'] == key), None)
                    if not card:
                        return self.problem(404, 'Decision record not found.')
                    card['proposal']['account_id'] = '***' + card['proposal']['account_id'][-4:]
                    return self.send(200, shell('Decision record', '<main id="main"><h1>Decision record</h1><a href="/">Back to dashboard</a><pre>' + html.escape(json.dumps(card, indent=2)) + '</pre></main>'))
                if path.startswith('/report/'):
                    key = path.removeprefix('/report/')
                    report = next((r for r in dashboard_snapshot(inbox)['reports'] if r['week'] == key), None)
                    if not report:
                        return self.problem(404, 'Weekly report not found.')
                    return self.send(200, shell('Weekly report', '<main id="main"><h1>Weekly report</h1><a href="/">Back to dashboard</a><pre>' + html.escape(report['body']) + '</pre></main>'))
                if path not in dict(ROUTES):
                    return self.problem(404, 'Page not found.')
                filters = parse_filters(query)
                inbox.expire()
                state = dashboard_snapshot(inbox)
                readiness = proof.assess() if proof else None
                service = service_check() if service_check else None
                content=render_desk(path, state, inbox.config, csrf, filters)
                return self.send(200, content)
            except ValueError as error:
                return self.problem(400, str(error))
            except Exception:
                return self.problem(503, 'Local records could not be loaded. No healthy status is assumed. Refresh or check the inbox service log.')

        def do_POST(self):
            origin = self.headers.get('Origin')
            local_origins = {
                f'http://127.0.0.1:{self.server.server_port}',
                f'http://localhost:{self.server.server_port}',
            }
            if not self.allowed() or (origin is not None and origin not in local_origins | {external_origin}):
                return self.problem(403, 'Invalid request origin')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096 or self.path not in {'/decision', '/control', '/views', '/notifications/test', '/tripwire/acknowledge'}:
                    return self.problem(400, 'Invalid request')
                form = parse_qs(self.rfile.read(length).decode(), max_num_fields=8)
                if any(len(values) != 1 for values in form.values()):
                    return self.problem(400, 'Duplicate form fields')
                if not hmac.compare_digest(form.get('csrf', [''])[0], csrf):
                    return self.problem(403, 'Invalid request token')
                if self.path == '/views':
                    ids = json.loads(form.get('ids', ['[]'])[0])
                    if not isinstance(ids, list) or len(ids) > 30 or any(not isinstance(key, str) for key in ids):
                        raise ValueError('Invalid card display receipt')
                    known = {card['id'] for card in inbox.cards()}
                    if not set(ids) <= known:
                        raise ValueError('Unknown card in display receipt')
                    from agents.notification_outbox import record_views
                    from datetime import datetime, timezone
                    record_views(inbox.path, ids, datetime.now(timezone.utc))
                    return self.send(204, '')
                elif self.path == '/notifications/test':
                    from datetime import datetime, timezone
                    from uuid import uuid4
                    from agents.notification_outbox import deliver_pending, enqueue
                    now = datetime.now(timezone.utc)
                    with inbox.connect() as db:
                        enqueue(db, 'pushover-test-' + uuid4().hex, 'Shadow notification test',
                                'Pushover is connected. Paper trading only; real orders remain blocked.',
                                now, priority=0, url=inbox.config.notifications.dashboard_url('controls'),
                                channels=('pushover',))
                    delivery = deliver_pending(inbox.path, notification_channels or {}, now)
                    if delivery['channels']['pushover']['delivered'] != 1:
                        raise ValueError('Pushover test was not delivered. Check Keychain credentials and the maintenance log.')
                elif self.path == '/tripwire/acknowledge':
                    from agents.account_tripwire import acknowledge_change
                    from datetime import datetime, timezone
                    if form.get('confirm') != ['yes']:
                        return self.problem(400, 'Confirm this broker-state acknowledgement.')
                    expires_at = datetime.fromisoformat(form['expires_at'][0])
                    acknowledge_change(
                        inbox.path,
                        incident_id=form['incident_id'][0],
                        expected_snapshot_hash=form['snapshot_hash'][0],
                        change_class=form['change_class'][0],
                        expires_at=expires_at,
                        csrf_confirmed=True,
                        now=datetime.now(timezone.utc),
                    )
                elif self.path == '/control':
                    if form.get('confirm') != ['yes']:
                        return self.problem(400, 'Confirm this change before applying it.')
                    set_paused(inbox, form['action'][0])
                else:
                    decision = form['decision'][0]
                    if decision not in {'YES', 'NO'}:
                        raise ValueError('Choose YES or NO')
                    inbox.decide(form['id'][0], decision)
            except (ValueError, KeyError) as error:
                return self.problem(409, str(error))
            except (OSError, sqlite3.Error):
                if self.path == '/views':
                    return self.send(503, 'Optional card display receipt unavailable', 'text/plain; charset=utf-8')
                return self.problem(503, 'The control could not be saved. Refresh to check the actual pause state.')
            self.send_response(303)
            self.send_header('Location', '/#decisions' if self.path == '/decision' else '/#controls')
            self.end_headers()

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config/settings.local.yaml')
    parser.add_argument('--database', default='data/agent.db')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    from agents.readiness import OperationalProof
    root = Path(__file__).resolve().parents[1]
    proof = OperationalProof(root=root, config_path=Path(args.config).resolve(), database=Path(args.database).resolve(),
                             test_report=root/'outputs/operational-test-results.xml', test_manifest=root/'outputs/operational-test-run.json')
    config=load_config(args.config)
    from agents.notifications import configured_notifiers
    make_server(PaperInbox(args.database, config), args.port, proof=proof, service_check=scheduler_loaded,
                notification_channels=configured_notifiers(config,include_macos=False)).serve_forever()


if __name__ == '__main__':
    main()
