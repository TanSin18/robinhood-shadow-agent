"""Dashboard contract: honest evidence, read-only views and scoped controls."""
import json
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pytest

from agents.inbox_web import make_server
from test_inbox_lanes import setup_runtime, issue
from test_risk_engine import NOW


@contextmanager
def serving(inbox, **server_options):
    server = make_server(inbox, port=0, **server_options)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def read(url):
    with urlopen(url) as response:
        return response.read().decode()


def post(url, **form):
    return read(Request(url, data=urlencode(form).encode()))


def put_cycle(inbox, day, status, **payload):
    with inbox.connect() as db:
        db.execute('INSERT OR REPLACE INTO cycle_runs VALUES (?,?,?)',
                   (day, status, json.dumps(payload)))


def seed_decision_room_trace(inbox, *, trace_id='cycle-room-1', card_id=None):
    common = {'trace_id': trace_id, 'data_mode': 'live_readonly'}
    events = [
        {
            **common,
            'event': 'data_collected',
            'timestamp': NOW.isoformat(),
            'quote_count': 14,
            'volatility_count': 14,
        },
        {
            **common,
            'event': 'stage_completed',
            'role': 'research',
            'timestamp': (NOW + timedelta(seconds=2)).isoformat(),
            'output': {
                'summary': 'Compared the eligible universe; <script>bad()</script>',
                'compared_symbols': ['VTI'],
                'missing_evidence': [],
            },
            'candidate_decisions': [
                {
                    'instrument': 'VTI',
                    'lane': 'A',
                    'state': 'reviewed',
                    'reason_code': 'research_compared',
                    'reason': 'Compared by Research.',
                    'source_refs': [],
                }
            ],
        },
        {
            **common,
            'event': 'stage_completed',
            'role': 'portfolio',
            'timestamp': (NOW + timedelta(seconds=4)).isoformat(),
            'output': {'reason': 'VTI advanced.', 'picks': [{'instrument': 'VTI'}]},
            'candidate_decisions': [
                {
                    'instrument': 'VTI',
                    'lane': 'A',
                    'state': 'proposed',
                    'reason_code': 'portfolio_pick',
                    'reason': 'Broad-market paper proposal.',
                    'source_refs': ['signal:VTI'],
                }
            ],
        },
        {
            **common,
            'event': 'stage_completed',
            'role': 'critic',
            'timestamp': (NOW + timedelta(seconds=5)).isoformat(),
            'output': {
                'counterargument': 'Confirm price freshness.',
                'rejected_instruments': [],
            },
        },
        {
            **common,
            'event': 'risk_evaluated',
            'timestamp': (NOW + timedelta(seconds=6)).isoformat(),
            'status': 'completed',
            'real_execution': 'blocked',
        },
        {
            **common,
            'event': 'cycle_terminal',
            'timestamp': (NOW + timedelta(seconds=7)).isoformat(),
            'payload': {
                'status': 'COMPLETED',
                'reason': 'Paper proposal created.',
                'results': [{'card_id': card_id}] if card_id else [],
            },
        },
    ]
    for event in events:
        inbox.store.append_json('local_traces', event)


def test_dashboard_has_next_history_results_and_no_fake_success(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
        for label in ('Next up', 'What happened', 'Needs your answer', 'Decision room', 'Results',
                      'No run recorded', 'Background connection not yet verified',
                      'Pause paper activity', 'Estimated AI cost'):
            assert label in page
        assert 'agentic-1' not in page
        assert 'Not available' in page  # No invented VTI return.


def test_agent_activity_shows_structured_findings_not_hidden_reasoning(tmp_path):
    from agents.dashboard import dashboard_snapshot
    from agents.dashboard_view import render_dashboard

    inbox, _ = setup_runtime(tmp_path)
    inbox.store.append_json('local_traces', {
        'trace_id': 'cycle-activity-1', 'event': 'stage_started', 'role': 'research',
        'timestamp': NOW.isoformat(), 'data_mode': 'live_readonly',
    })
    inbox.store.append_json('local_traces', {
        'trace_id': 'cycle-activity-1', 'event': 'stage_completed', 'role': 'research',
        'timestamp': (NOW + timedelta(seconds=4)).isoformat(),
        'output': {
            'summary': 'SOXX leads momentum; <script>bad()</script>',
            'compared_symbols': ['SOXX', 'VTI'],
            'news_checked': False,
            'news': [],
            'missing_evidence': ['News disabled'],
        },
    })
    inbox.store.append_json('local_traces', {
        'trace_id': 'cycle-activity-1', 'event': 'stage_completed', 'role': 'critic',
        'timestamp': (NOW + timedelta(seconds=7)).isoformat(),
        'output': {'counterargument': 'Momentum may reverse.', 'rejected_instruments': ['META']},
    })

    state = dashboard_snapshot(inbox, NOW + timedelta(minutes=1))
    assert state['activity'][0]['cycle_id'] == 'cycle-activity-1'
    assert [event['status'] for event in state['activity'][0]['events']] == [
        'completed', 'completed', 'started'
    ]
    page = render_dashboard(state, inbox.config, 'token', {'lane': '', 'status': '', 'date': ''})
    activity = page.split('data-view="activity"', 1)[1].split('data-view="results"', 1)[0]
    assert 'SOXX leads momentum' in activity
    assert 'News disabled' in activity
    assert 'Momentum may reverse' in activity
    assert 'META' in activity
    assert '<script>bad()</script>' not in activity
    assert '&lt;script&gt;bad()&lt;/script&gt;' in activity
    assert 'Structured work products are shown. Private chain-of-thought is not recorded.' in activity


def test_decision_room_renders_entities_flow_selections_and_honest_fallbacks(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)

    with serving(inbox) as url:
        page = read(url + '/#activity')

    activity = page.split('data-view="activity"', 1)[1].split(
        'data-view="history"', 1
    )[0]
    labels = ('Evidence', 'Research Agent', 'Portfolio Agent', 'Critic', 'Risk Engine', 'Final outcome')
    assert 'Decision room' in activity
    assert 'aria-label="Review flow"' in activity
    assert [activity.index(label) for label in labels] == sorted(
        activity.index(label) for label in labels
    )
    assert 'Lane A · Stocks &amp; ETFs' in activity
    assert 'Lane B · Defined-risk options' in activity
    assert 'data-decision-state="proposed"' in activity
    assert 'Structured work products are shown. Private chain-of-thought is not recorded.' in activity
    assert '<script>bad()</script>' not in activity
    assert '&lt;script&gt;bad()&lt;/script&gt;' in activity
    assert 'data-entity-kind="agent"' in activity
    assert 'data-entity-kind="deterministic"' in activity
    assert '>Completed<' in activity or '>Waiting<' in activity or '>Blocked<' in activity
    for svg in re.findall(r'<svg\b[^>]*>', activity):
        assert 'aria-hidden="true"' in svg
    assert page.count('<h1') == 1


def test_decision_room_css_has_approved_tokens_and_phone_stepper():
    css = Path('agents/static/dashboard.css').read_text()
    for token in ('--canvas:#f3f6f4', '--ink:#172a24', '--forest:#245443',
                  '--evidence:#2f668c', '--caution:#996a20', '--failure:#a33f3f'):
        assert token in css.lower()
    assert '.decision-flow' in css
    assert '[data-entity-kind="deterministic"]' in css
    assert '@media(max-width:640px)' in css.replace(' ', '')
    assert 'prefers-reduced-motion:reduce' in css.replace(' ', '')


def test_decision_rows_wrap_unbroken_identifiers():
    css = Path('agents/static/dashboard.css').read_text()
    block = css.split('.decision-row', 1)[1]
    assert 'overflow-wrap:anywhere' in block.replace(' ', '')


def test_historical_review_does_not_invent_unrecorded_selection_details(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    inbox.store.append_json(
        'local_traces',
        {
            'trace_id': 'historic',
            'event': 'stage_completed',
            'role': 'research',
            'output': {
                'summary': 'VTI mentioned in prose',
                'compared_symbols': ['VTI'],
            },
        },
    )

    with serving(inbox) as url:
        page = read(url + '/#activity')

    assert 'Detailed selection states were not recorded for this review.' in page
    assert 'data-decision-state="proposed"' not in page


def test_decision_room_links_pending_approval_and_marks_failed_boundary(tmp_path):
    inbox, _ = setup_runtime(tmp_path, expiry=10000)
    card = issue(inbox)
    seed_decision_room_trace(inbox, card_id=card['id'])
    inbox.store.append_json(
        'local_traces',
        {
            'trace_id': 'newer-failure',
            'event': 'cycle_terminal',
            'timestamp': (NOW + timedelta(seconds=9)).isoformat(),
            'data_mode': 'live_readonly',
            'payload': {
                'status': 'NOT_ISSUED_DATA',
                'reason': 'Current quotes unavailable.',
                'results': [],
            },
        },
    )

    with serving(inbox) as url:
        page = read(url + '/#activity')

    activity = page.split('data-view="activity"', 1)[1].split(
        'data-view="history"', 1
    )[0]
    assert 'Review pending approval' in activity
    assert 'Current quotes unavailable.' in activity
    assert '>Blocked<' in activity
    review_tags = re.findall(r'<article data-review="[^"]+"[^>]*>', activity)
    assert len(review_tags) == 2
    assert sum(' hidden' not in tag for tag in review_tags) == 1


def test_decision_room_keeps_security_and_accessibility_contracts(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)
    with serving(inbox) as url:
        page = read(url + '/#activity')
    room = page.split('data-view="activity"', 1)[1].split(
        'data-view="history"', 1
    )[0]
    assert 'aria-live="polite"' in room
    assert '<ol' in room and 'aria-label="Review flow"' in room
    assert 'Private chain-of-thought is not recorded.' in room
    assert 'Real orders blocked' in page
    assert 'agentic-1' not in page
    assert re.search(r'<(?:script|img|link)[^>]+(?:src|href)="https?://', room) is None


def test_malformed_trace_http_view_stays_available_and_nested_secrets_are_removed(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    for payload in (
        {'trace_id': 'broken-http', 'event': 'cycle_started', 'data_mode': {}},
        {'trace_id': 'broken-http', 'event': [], 'role': []},
        {'trace_id': 'broken-http', 'event': 'stage_completed', 'role': []},
        {'trace_id': 'broken-http', 'event': 'strategy_evaluated', 'signals': 42},
        {'trace_id': 'broken-http', 'event': 'data_collected',
         'quote_count': {'api_key': 'SYNTHETIC_SECRET_ONLY'}},
        {'trace_id': 'broken-http', 'event': 'risk_evaluated', 'status': []},
        {'trace_id': 'broken-http', 'event': 'cycle_terminal', 'payload': ['bad']},
        {
            'trace_id': 'broken-http',
            'event': 'stage_completed',
            'role': 'research',
            'output': {
                'summary': 'Safe finding.',
                'news': [{
                    'fact': 'Public fact.',
                    'source_url': 'https://example.test/source',
                    'api_key': 'do-not-render-this',
                }],
            },
            'candidate_decisions': [{'instrument': 'VTI', 'lane': [], 'state': []}],
        },
    ):
        inbox.store.append_json('local_traces', payload)

    with serving(inbox) as url:
        page = read(url + '/#activity')

    assert 'Activity record incomplete' in page
    assert 'Safe finding.' in page
    assert 'Public fact.' in page
    assert 'do-not-render-this' not in page
    assert 'SYNTHETIC_SECRET_ONLY' not in page


def test_historical_pending_proposal_never_claims_no_proposal(tmp_path):
    inbox, _ = setup_runtime(tmp_path, expiry=10000)
    card = issue(inbox)
    inbox.store.append_json('local_traces', {
        'trace_id': 'historical-card',
        'event': 'cycle_terminal',
        'timestamp': NOW.isoformat(),
        'data_mode': 'live_readonly',
        'payload': {
            'status': 'COMPLETED',
            'reason': 'Paper proposal created.',
            'decision': {'picks': [{'instrument': 'VTI'}]},
            'results': [{'status': 'PENDING', 'card_id': card['id']}],
        },
    })

    with serving(inbox) as url:
        page = read(url + '/#activity')

    review = page.split('data-review="historical-card"', 1)[1].split('</article>', 1)[0]
    assert 'Review pending approval' in review
    assert 'Proposal recorded; lane details were not recorded' in review
    assert 'No paper proposal from this review.' not in review


def test_review_header_and_stage_inspector_use_plain_language(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)
    with serving(inbox) as url:
        page = read(url + '/#activity')
    room = page.split('data-view="activity"', 1)[1].split('data-view="history"', 1)[0]
    for label in ('Outcome', 'Freshness', 'Duration', 'Estimated AI cost', 'Paper state'):
        assert f'<dt>{label}</dt>' in room
    assert 'Inputs' in room
    assert 'Findings' in room
    assert 'Sources' in room
    assert 'Blockers' in room
    assert 'Handoff' in room
    assert 'class="stage-output"' in room
    inspector = room.split('class="stage-inspector"', 1)[1].split('</aside>', 1)[0]
    assert '<pre>' not in inspector


def test_decision_rows_expose_recorded_source_references(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)
    with serving(inbox) as url:
        page = read(url + '/#activity')
    assert 'Evidence sources' in page
    assert 'signal:VTI' in page


def test_pushover_test_button_is_csrf_protected_and_records_delivery(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    calls = []

    class Pushover:
        def notify(self, title, body, *, priority, url=None):
            calls.append((title, body, priority, url))
            return {'request_id': 'test-request', 'receipt': None}

    with serving(inbox, notification_channels={'pushover': Pushover()}) as url:
        page = read(url + '/#controls')
        token = re.search('name="csrf" value="([^"]+)"', page)[1]
        with pytest.raises(HTTPError) as missing:
            post(url + '/notifications/test')
        assert missing.value.code == 400
        post(url + '/notifications/test', csrf=token)
        assert calls == [(
            'Shadow notification test',
            'Pushover is connected. Paper trading only; real orders remain blocked.',
            0,
            inbox.config.notifications.dashboard_url('controls'),
        )]
        updated = read(url + '/#controls')
        assert 'Pushover' in updated
        assert 'Delivered' in updated
        assert 'test-request' not in updated


def test_pause_requires_confirmation_and_csrf_then_blocks_paper_fills(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        confirmation = read(url + '/control?action=pause')
        token = re.search('name="csrf" value="([^"]+)"', confirmation)[1]
        assert not (tmp_path / 'STOP_TRADING').exists()
        for fields in ({'action': 'pause', 'confirm': 'yes'},
                       {'action': 'pause', 'csrf': token}):
            with pytest.raises(HTTPError):
                post(url + '/control', **fields)
        post(url + '/control', csrf=token, action='pause', confirm='yes')
        assert (tmp_path / 'STOP_TRADING').exists()
        blocked = issue(inbox)
        assert blocked['status'] == 'RISK_BLOCKED'
        assert Decimal(inbox.state('A', 'agent_alone')['settled_cash']) == 500
        post(url + '/control', csrf=token, action='resume', confirm='yes')
        assert not (tmp_path / 'STOP_TRADING').exists()
        with inbox.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM cycle_runs').fetchone()[0] == 0
        actions = [r['action'] for r in inbox.store.read_json('alerts')
                   if r.get('kind') == 'dashboard_control']
        assert actions == ['pause', 'resume']


def test_resume_never_clears_an_external_stop_or_starts_a_cycle(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    (tmp_path / 'STOP_TRADING').write_text('Manual safety stop')
    with serving(inbox) as url:
        page = read(url)
        token = re.search('name="csrf" value="([^"]+)"', page)[1]
        with pytest.raises(HTTPError) as error:
            post(url + '/control', csrf=token, action='resume', confirm='yes')
        assert error.value.code == 409
    assert (tmp_path / 'STOP_TRADING').read_text() == 'Manual safety stop'


def test_schedule_holidays_dst_claims_and_missed_window(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    # Thanksgiving Thursday -> Friday (still a 10 AM session).
    state = dashboard_snapshot(inbox, datetime(2026, 11, 26, 14, tzinfo=timezone.utc))
    assert state['next_run'] == '2026-11-27T10:00:00-05:00'
    monday = datetime(2026, 9, 28, 14, 20, tzinfo=timezone.utc)
    state = dashboard_snapshot(inbox, monday)
    assert state['today_status'] == 'NO_RUN_RECORDED'
    assert state['next_run'] == '2026-09-29T10:00:00-04:00'
    put_cycle(inbox, '2026-09-28', 'FAILED', error_type='ValueError')
    state = dashboard_snapshot(inbox, monday - timedelta(minutes=2))
    assert state['today_status'] == 'FAILED'
    assert state['next_run'] == '2026-09-29T10:00:00-04:00'


@pytest.mark.parametrize('status,payload,want', [
    ('STARTED', {}, 'RUNNING'),
    ('FAILED', {'error_type': 'TimeoutError'}, 'FAILED'),
    ('COMPLETED', {'decision': {'picks': [], 'reason': 'Nothing qualifies'}, 'results': []}, 'HOLD'),
    ('COMPLETED', {'decision': {'picks': [{'instrument': 'VTI'}]}, 'results': [{'status': 'RISK_BLOCKED'}]}, 'COMPLETED'),
])
def test_completed_hold_failure_and_running_are_distinct(tmp_path, status, payload, want):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', status, **payload)
    state = dashboard_snapshot(inbox, datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc))
    assert state['today_status'] == want
    assert state['history'][0]['kind'] == 'cycle'


def test_lingering_started_cycle_is_not_presented_as_healthy(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'STARTED')
    state = dashboard_snapshot(inbox, datetime(2026, 9, 28, 15, tzinfo=timezone.utc))
    assert state['today_status'] == 'UNCONFIRMED'


def test_costs_charge_agent_tracks_only_and_include_unsettled_reservations(tmp_path):
    from agents.dashboard import dashboard_snapshot
    from agents.codex_bridge import CostLedger
    inbox, config = setup_runtime(tmp_path)
    now = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
    inbox.store.append_json('api_costs', {'timestamp': now.isoformat(), 'cost_usd': '.20'})
    ledger = CostLedger(inbox.path, config.daily_api_budget_usd)
    ledger.reserve(now, Decimal('.14'))
    state = dashboard_snapshot(inbox, now)
    assert state['costs']['today'] == '0.20'
    assert state['costs']['held'] == '0.14'
    assert state['costs']['remaining'] == '0.06'
    for lane in state['lanes']:
        assert lane['tracks'][0]['net_value'] == '499.90'
        assert lane['tracks'][1]['net_value'] == '499.90'
        assert lane['cash_benchmark'] == '500.00'
        assert lane['vti_benchmark'] is None


def test_stale_or_missing_position_marks_are_not_current_equity(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    state = dashboard_snapshot(inbox, NOW + timedelta(days=1))
    track = state['lanes'][0]['tracks'][0]
    assert track['stale'] is True
    assert track['as_of'] is not None
    assert track['value'] is not None  # Explicitly the last known valuation.
    with inbox.connect() as db:
        account = inbox.state('A', 'agent_alone', db)
        account['marks'] = {}
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',
                   (json.dumps(account), 'A', 'agent_alone'))
    assert dashboard_snapshot(inbox, NOW)['lanes'][0]['tracks'][0]['value'] is None


def test_filters_escape_evidence_and_report_route_cannot_read_files(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED',
              decision={'picks': [], 'reason': '<script>alert(1)</script>'})
    with inbox.connect() as db:
        db.execute('INSERT INTO weekly_reports VALUES (?,?)', ('2026-10-02',
                   json.dumps({'body': 'Known report <script>bad</script>', 'generated_at': '2026-10-02T21:00:00+00:00'})))
    with serving(inbox) as url:
        page = read(url)
        assert '<script>alert(1)</script>' not in page
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page
        assert 'Nothing recorded for these filters' in read(url + '/?date=2026-09-29')
        assert 'Known report' in read(url + '/report/2026-10-02')
        for path in ('/report/../../config/settings.local.yaml', '/?lane=LIVE', '/?date=bogus'):
            with pytest.raises(HTTPError) as error:
                read(url + path)
            assert error.value.code in (400, 404)


def test_refresh_is_local_only_and_preserves_safe_csp(tmp_path, monkeypatch):
    from agents.codex_bridge import CodexBridge
    def forbidden(*args, **kwargs):
        raise AssertionError('Dashboard must not call an AI model')
    monkeypatch.setattr(CodexBridge, 'run', forbidden)
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        for _ in range(2):
            with urlopen(url) as response:
                policy = response.headers['Content-Security-Policy']
                assert "script-src 'self'" in policy
                assert "frame-ancestors 'none'" in policy
        assert 'setInterval' in read(url + '/assets/dashboard.js')
        with inbox.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM cycle_runs').fetchone()[0] == 0


def test_pending_filter_and_lane_filter_never_change_paper_accounts(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    before = inbox.state('A', 'agent_alone')
    with serving(inbox) as url:
        page = read(url + '/?lane=B&status=PENDING')
        assert 'No decisions waiting' in page
    assert inbox.state('A', 'agent_alone') == before


def test_fixture_cycles_are_visibly_labeled_and_assets_change_evidence_hash(tmp_path):
    from agents.readiness import source_fingerprint
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED', data_mode='fixture', decision={'picks': []})
    with serving(inbox) as url:
        assert 'Mock / fixture data' in read(url)
    static = tmp_path / 'agents/static'
    static.mkdir(parents=True)
    (static.parent / 'worker.py').write_text('version = 1')
    (static / 'dashboard.js').write_text('version one')
    before = source_fingerprint(tmp_path)
    (static / 'dashboard.js').write_text('version two')
    assert source_fingerprint(tmp_path) != before


def test_cost_day_is_eastern_and_vti_never_loses_ai_cost(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    inbox.store.append_json('api_costs', {'timestamp': '2026-09-29T01:00:00+00:00', 'cost_usd': '.20'})
    for day, price in [('2026-09-25', '100'), ('2026-09-28', '102')]:
        inbox.store.append_json('daily_values', {'benchmark': 'VTI', 'data_mode': 'live_readonly', 'close': {'date': day, 'price': price}})
    state = dashboard_snapshot(inbox, datetime(2026, 9, 29, 2, tzinfo=timezone.utc))
    assert state['costs']['today'] == '0.20'
    assert state['lanes'][0]['vti_benchmark'] == '510.00'
    assert state['lanes'][0]['cash_benchmark'] == '500.00'


def test_control_rejects_cross_origin_unknown_actions_and_symlink_stops(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    target = tmp_path / 'external-stop'
    target.write_text('do not delete')
    (tmp_path / 'STOP_TRADING').symlink_to(target)
    with serving(inbox) as url:
        token = re.search('name="csrf" value="([^"]+)"', read(url))[1]
        for action in ('resume', 'pause', 'live'):
            with pytest.raises(HTTPError) as error:
                post(url + '/control', csrf=token, action=action, confirm='yes')
            assert error.value.code == 409
        with pytest.raises(HTTPError) as error:
            read(Request(url + '/control', data=urlencode({'csrf': token, 'action': 'pause', 'confirm': 'yes'}).encode(), headers={'Origin': 'https://evil.test'}))
        assert error.value.code == 403
    assert target.read_text() == 'do not delete'


def test_api_pause_blocks_old_yes_page_without_changing_held_cash(tmp_path):
    from agents.dashboard import set_paused
    inbox, _ = setup_runtime(tmp_path)
    card = issue(inbox)
    set_paused(inbox, 'pause', NOW)
    outcome = inbox.decide(card['id'], 'YES', NOW + timedelta(minutes=1))
    assert outcome['approval_fill']['status'] == 'RISK_BLOCKED'
    assert Decimal(inbox.state('A', 'with_approvals')['settled_cash']) == 500


def test_get_confirmation_never_places_csrf_token_in_url(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
        form = re.search(r'<form method="get" action="/control">(.*?)</form>', page, re.S)[1]
        assert 'name="csrf"' not in form


def test_form_referrer_policy_preserves_same_origin_posts_but_rejects_null(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        with urlopen(url) as response:
            # no-referrer causes browser form POSTs to send Origin:null.
            assert response.headers['Referrer-Policy'] == 'same-origin'
            token = re.search('name="csrf" value="([^"]+)"', response.read().decode())[1]
        with pytest.raises(HTTPError) as error:
            read(Request(url + '/control', data=urlencode({'csrf': token, 'action': 'pause', 'confirm': 'yes'}).encode(), headers={'Origin': 'null'}))
        assert error.value.code == 403


@pytest.mark.parametrize('payload', [{}, {'decision': {}}, {'decision': {'picks': []}}, {'results': []}])
def test_incomplete_completion_is_not_a_successful_hold(tmp_path, payload):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED', **payload)
    state = dashboard_snapshot(inbox, datetime(2026, 9, 28, 15, tzinfo=timezone.utc))
    assert state['today_status'] == 'UNCONFIRMED'


def test_past_unrecorded_trading_day_stays_in_history(tmp_path):
    from agents.dashboard import dashboard_snapshot
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-25', 'COMPLETED', decision={'picks': []}, results=[])
    state = dashboard_snapshot(inbox, datetime(2026, 9, 29, 13, tzinfo=timezone.utc))
    missed = [h for h in state['history'] if h['status'] == 'NO_RUN_RECORDED']
    assert len(missed) == 1
    assert missed[0]['timestamp'] == '2026-09-28T10:00:00-04:00'
    assert all('2026-09-26' not in h['timestamp'] for h in missed)


def test_history_groups_recovery_day_and_marks_reviewed_incident_resolved(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED',
              cycle_id='final-cycle', timestamp='2026-09-28T14:18:13+00:00',
              completed_at='2026-09-28T14:20:17+00:00', data_mode='live_readonly',
              agents=['Research Agent', 'Portfolio Agent', 'Critic'], quote_count=14,
              volatility_count=14, market_open=True, results=[],
              decision={'picks': [], 'reason': 'The initial quotes are stale.'},
              critic={'counterargument': 'Holding cash is appropriate.'})
    inbox.store.append_json('run_states', {
        'status':'FAILED', 'timestamp':'2026-09-28T14:11:23+00:00',
        'error_type':'CapabilityError', 'remediation':'Inspect the failed attempt.'})
    with inbox.connect() as db:
        from agents.safety_events import ensure_operations_schema
        ensure_operations_schema(db)
        db.execute("INSERT INTO safety_incidents VALUES ('incident-1','UNEXPECTED_CAPABILITY',NULL,?,?)",
                   ('2026-09-28T14:11:20+00:00','2026-09-28T14:18:13+00:00'))
        db.execute("INSERT INTO notification_outbox(event_id,title,body,created_at,status,attempts) VALUES (?,?,?,?,?,?)",
                   ('incident-1','Shadow trading stopped','review','2026-09-28T14:11:20+00:00','DELIVERED',1))
        db.execute("INSERT INTO notification_outbox(event_id,title,body,created_at,status,attempts) VALUES (?,?,?,?,?,?)",
                   ('notice-2','Shadow cycle update','review','2026-09-28T14:18:13+00:00','DELIVERED',1))
    with serving(inbox) as url:
        page = read(url)
    assert page.count('data-history-day="2026-09-28"') == 1
    day = page.split('data-history-day="2026-09-28"')[1].split('</article>', 1)[0]
    summary = day.split('Technical timeline', 1)[0]
    assert '<h3>Hold cash</h3>' in summary
    assert 'Review completed' in summary
    assert 'Research, Portfolio, and Critic finished. No eligible paper trade was proposed.' in summary
    assert 'Nothing needs your approval' in summary
    assert 'Final data refresh' in summary
    assert '14 quotes returned' in summary
    assert 'No selected instrument required final freshness validation.' in summary
    assert 'Strategy signals were not recorded for this run' in summary
    assert 'The upgraded selector starts with the next eligible cycle.' in summary
    assert 'fresh quotes' not in summary
    assert all(name in summary for name in ('Research', 'Portfolio', 'Critic'))
    assert 'The initial quotes are stale.' not in summary
    assert 'Technical timeline · 2 records' in day
    assert 'System messages · 2' in day
    assert 'Resolved' in day
    assert 'The initial quotes are stale.' in page
    assert 'CapabilityError' in page


def test_history_labels_closed_market_cycle_as_after_hours_and_does_not_claim_fresh_quotes(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-27', 'COMPLETED',
              timestamp='2026-09-27T21:42:00+00:00', data_mode='live_readonly',
              agents=['Research Agent', 'Portfolio Agent', 'Critic'], quote_count=16,
              market_open=False, results=[],
              decision={'picks': [], 'reason': 'The market is closed and supplied quotes are stale.'},
              critic={'counterargument': 'Holding cash is appropriate.'})
    with serving(inbox) as url:
        page = read(url)
    day = page.split('data-history-day="2026-09-27"')[1].split('</article>', 1)[0]
    summary = day.split('Technical timeline', 1)[0]
    assert '<h3>After-hours setup run</h3>' in summary
    assert 'Market closed' in summary
    assert 'The review finished while the market was closed. No paper trade was proposed.' in summary
    assert 'Quote refresh' in summary
    assert '16 quotes returned' in summary
    assert 'Returned prices may reflect the prior trading session.' in summary
    assert 'fresh quotes' not in summary
    assert 'The market is closed and supplied quotes are stale.' not in summary
    assert 'The market is closed and supplied quotes are stale.' in day


def test_history_gives_standalone_failure_a_plain_language_fallback(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    inbox.store.append_json('run_states', {
        'status': 'FAILED', 'timestamp': '2026-09-28T14:11:23+00:00',
        'error_type': 'CapabilityError'})
    with serving(inbox) as url:
        page = read(url)
    assert 'This recovery attempt stopped before completion.' in page
    assert 'CapabilityError' in page


def test_history_explains_strategy_signal_result_and_next_trigger(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED',
              timestamp='2026-09-28T14:18:13+00:00', data_mode='live_readonly',
              agents=['Research Agent', 'Portfolio Agent', 'Critic'], quote_count=14,
              market_open=True, results=[], decision={'picks': [], 'reason': 'No signal.'},
              strategy_assessment={
                  'signals': [], 'qualification': 'DAILY_SHADOW_SIGNAL_ONLY',
                  'strategies': {
                      'momentum_rotation': {'qualifying_count': 0},
                      'mean_reversion': {'qualifying_count': 0},
                  }})
    with serving(inbox) as url:
        page = read(url)
    day = page.split('data-history-day="2026-09-28"')[1].split('</article>', 1)[0]
    summary = day.split('Technical timeline', 1)[0]
    assert 'Strategy signals' in summary
    assert '0 triggered' in summary
    assert 'Momentum 0 · Mean reversion 0' in summary
    assert 'Next trigger' in summary
    assert 'positive ETF momentum above its 200-session average' in summary


def test_history_day_surfaces_pending_action_without_duplicating_dates(tmp_path):
    from test_risk_engine import make_proposal

    from agents.dashboard import dashboard_snapshot
    from agents.dashboard_view import render_dashboard
    from broker.models import Quote
    inbox, _ = setup_runtime(tmp_path)
    cycle_now = datetime(2026, 9, 28, 14, 5, tzinfo=timezone.utc)
    card = inbox.issue(make_proposal(quantity=Decimal('.49')),
                       Quote(ticker='VTI',bid=Decimal(100),ask=Decimal('100.20'),timestamp=cycle_now),
                       Decimal('.20'),cycle_now,cycle_now)
    put_cycle(inbox, '2026-09-28', 'COMPLETED',
              timestamp=cycle_now.isoformat(), completed_at=cycle_now.isoformat(),
              data_mode='live_readonly', quote_count=1,
              agents=['Research Agent', 'Portfolio Agent', 'Critic'],
              decision={'picks':[{'instrument':'VTI'}], 'reason':'Paper proposal created.'},
              results=[{'status':'PENDING','card_id':card['id']}])
    state=dashboard_snapshot(inbox,cycle_now+timedelta(minutes=1))
    page=render_dashboard(state,inbox.config,'token',{'lane':'','status':'','date':''})
    assert page.count('data-history-day="2026-09-28"') == 1
    day = page.split('data-history-day="2026-09-28"')[1].split('</article>', 1)[0]
    assert '1 proposal needs your answer' in day
    assert 'Open approvals' in day


def test_resume_fails_closed_when_audit_cannot_be_saved(tmp_path, monkeypatch):
    import sqlite3
    from agents.dashboard import set_paused
    inbox, _ = setup_runtime(tmp_path)
    set_paused(inbox, 'pause', NOW)
    def fail_audit(*args, **kwargs):
        raise sqlite3.OperationalError('test database unavailable')
    monkeypatch.setattr(inbox.store, 'append_json', fail_audit)
    with pytest.raises(sqlite3.OperationalError):
        set_paused(inbox, 'resume', NOW)
    assert (tmp_path / 'STOP_TRADING').exists()


def test_resume_rejects_copied_external_stop_marker(tmp_path):
    from agents.dashboard import set_paused, STOP_OWNER
    inbox, _ = setup_runtime(tmp_path)
    (tmp_path / 'STOP_TRADING').write_text(json.dumps({'owner': STOP_OWNER}))
    with pytest.raises(ValueError):
        set_paused(inbox, 'resume', NOW)
    assert (tmp_path / 'STOP_TRADING').exists()


def test_fixture_balances_are_labeled_in_results_and_hold_can_be_filtered(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with inbox.connect() as db:
        state = inbox.state('A', 'agent_alone', db)
        state['data_mode'] = 'fixture'
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?', (json.dumps(state), 'A', 'agent_alone'))
    put_cycle(inbox, '2026-09-28', 'COMPLETED', decision={'picks': []}, results=[])
    with serving(inbox) as url:
        page = read(url)
        assert 'Mock / fixture marks' in page.split('<section id="results">')[1]
        assert 'Completed · No trade recommended' in read(url + '/?status=HOLD')


def test_failed_resume_completion_restores_stop_and_retains_durable_intent(tmp_path, monkeypatch):
    import sqlite3
    from agents.dashboard import set_paused
    inbox, _ = setup_runtime(tmp_path)
    set_paused(inbox, 'pause', NOW)
    original = inbox.store.append_json
    def fail_completion(table, payload):
        if payload.get('kind') == 'dashboard_control' and payload.get('action') == 'resume':
            raise sqlite3.OperationalError('test completion write failure')
        return original(table, payload)
    monkeypatch.setattr(inbox.store, 'append_json', fail_completion)
    with pytest.raises(sqlite3.OperationalError):
        set_paused(inbox, 'resume', NOW)
    assert (tmp_path / 'STOP_TRADING').exists()
    assert any(e['kind'] == 'dashboard_control_request' for e in inbox.store.read_json('alerts'))


def test_browser_refresh_and_countdown_logic_without_network():
    """Execute the actual JS with a controlled DOM/clock, no browser or API traffic."""
    import subprocess
    result = subprocess.run(['node', '-e', r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const timers = new Map(), events = {}, formEvents = {};
let now = 1000000, reloads = 0, opened = false, focused = false, activeControl = false;
const buttons = [{disabled:false}, {disabled:false}];
const toggle = {checked:true, addEventListener:(name, fn)=>events[name]=fn};
const countdown = {dataset:{expires:new Date(now+125000).toISOString()}, textContent:'',
  closest:()=>({querySelectorAll:()=>buttons})};
const location = {href:'http://127.0.0.1:8766/?lane=B',search:'?lane=B',reload:()=>reloads++};
const document = {body:{dataset:{auto:'on'}},visibilityState:'visible',
  activeElement:{closest:()=>focused ? {} : null, matches:()=>activeControl},
  querySelector:s=>s==='#auto-refresh' ? toggle : (opened ? {} : null),
  querySelectorAll:s=>s==='form' ? [{addEventListener:(name,fn)=>formEvents[name]=fn}] : [countdown]};
class Clock extends Date {static now(){return now;}}
vm.runInNewContext(fs.readFileSync('agents/static/dashboard.js','utf8'),
  {document,window:{location,history:{replaceState:(_a,_b,url)=>location.href=String(url)}},
   URL,URLSearchParams,Date:Clock,setInterval:(fn,ms)=>timers.set(ms,fn)});
timers.get(1000)(); assert.equal(countdown.textContent,'Expires in 2m 5s');
now+=125000; timers.get(1000)(); assert.ok(buttons.every(b=>b.disabled));
timers.get(30000)(); assert.equal(reloads,1);
opened=true; timers.get(30000)(); assert.equal(reloads,1); opened=false;
focused=true; timers.get(30000)(); assert.equal(reloads,1); focused=false;
document.visibilityState='hidden'; timers.get(30000)(); assert.equal(reloads,1);
document.visibilityState='visible'; toggle.checked=false; events.change();
assert.ok(location.href.includes('refresh=off')); timers.get(30000)(); assert.equal(reloads,1);
toggle.checked=true; events.change(); assert.ok(!location.href.includes('refresh=off'));
activeControl=true; timers.get(30000)(); assert.equal(reloads,1); activeControl=false;
formEvents.input(); timers.get(30000)(); assert.equal(reloads,1);
console.log('countdown, expiry, local refresh, focus, decision controls, disclosure, visibility, preference and form guards passed');
'''], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_dashboard_separates_views_and_keeps_pause_discoverable(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
        for view in ('next', 'decisions', 'history', 'results', 'controls'):
            assert f'data-view="{view}"' in page
            assert f'data-nav="{view}"' in page
        # A safety action remains outside the view that navigation hides.
        topbar = re.search(r'<header class="topbar">(.*?)</header>', page, re.S)[1]
        assert '/control?action=pause' in topbar
        assert 'Awaiting first verified scheduled run' in page
        assert 'Planned sequence, not live progress' in page


def test_filtered_empty_inbox_does_not_claim_no_pending_proposals(tmp_path):
    from agents.dashboard import dashboard_snapshot
    from agents.dashboard_view import render_dashboard
    inbox, config = setup_runtime(tmp_path)
    issue(inbox)
    page = render_dashboard(dashboard_snapshot(inbox, NOW), config, 'token',
                            {'lane': 'B', 'status': 'PENDING', 'date': ''})
    assert 'No matching proposals' in page
    assert 'No decisions waiting' not in page


def test_navigation_deep_links_back_and_unknown_hash_without_network():
    import subprocess
    result = subprocess.run(['node', '-e', r'''
const assert = require('node:assert/strict'), vm = require('node:vm'), fs = require('node:fs');
const views = ['next','decisions','history','results','controls'].map(id=>({id,dataset:{view:id},hidden:false,focus(){this.focused=true;}}));
const links = views.map(v=>({dataset:{nav:v.id},attrs:{},setAttribute(k,v){this.attrs[k]=v;},removeAttribute(k){delete this.attrs[k];}}));
const events = {}, title = {textContent:''};
const location = {hash:'#history',search:'',href:'http://127.0.0.1:8766/#history'};
const document = {body:{dataset:{auto:'off'}},querySelector:s=>s==='#view-title'?title:null,
  querySelectorAll:s=>s==='[data-view]'?views:s==='[data-nav]'?links:[]};
vm.runInNewContext(fs.readFileSync('agents/static/dashboard.js','utf8'), {document,
 window:{location,addEventListener:(name,fn)=>events[name]=fn,history:{replaceState(){}},scrollTo(){}},
 URL,URLSearchParams,Date,setInterval(){}});
assert.deepEqual(views.filter(v=>!v.hidden).map(v=>v.id),['history']);
assert.equal(links[2].attrs['aria-current'],'page');
location.hash='#decisions'; events.hashchange();
assert.deepEqual(views.filter(v=>!v.hidden).map(v=>v.id),['decisions']);
assert.ok(views[1].focused); assert.equal(links[2].attrs['aria-current'],undefined);
location.hash='#history'; events.hashchange();
assert.equal(views[2].hidden,false);
location.hash='#activity'; events.hashchange();
assert.equal(title.textContent,'Decision room');
location.hash='#unknown'; events.hashchange();
assert.deepEqual(views.filter(v=>!v.hidden).map(v=>v.id),['next']);
console.log('Deep links, view visibility, selection and focus passed');
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_decision_room_interaction_reducers_and_dom_state_are_local_only():
    import subprocess
    result = subprocess.run(['node', '-e', r'''
const assert = require('node:assert/strict');
const room = require('./agents/static/decision-room.js');

assert.deepEqual(
  room.chooseStage({available:['evidence','research','risk'], selected:'research'}, 'risk'),
  {available:['evidence','research','risk'], selected:'risk'});
assert.deepEqual(
  room.chooseLane({available:['A','B'], selected:'A'}, 'B'),
  {available:['A','B'], selected:'B'});
assert.equal(
  room.chooseReview({available:['latest','older'], selected:'older'}, 'missing').selected,
  'latest');

const camel = name => name.replace(/-([a-z])/g, (_m, letter) => letter.toUpperCase());
class Node {
  constructor(dataset = {}, children = []) {
    this.dataset = dataset; this.children = children; this.hidden = false;
    this.attrs = {}; this.listeners = {}; this.value = '';
    children.forEach(child => child.parent = this);
  }
  matches(selector) {
    const found = /^\[data-([a-z-]+)\]$/.exec(selector);
    return Boolean(found && Object.hasOwn(this.dataset, camel(found[1])));
  }
  all() { return [this, ...this.children.flatMap(child => child.all())]; }
  querySelectorAll(selector) { return this.all().filter(node => node !== this && node.matches(selector)); }
  querySelector(selector) {
    if (selector === '[data-review]:not([hidden])') {
      return this.querySelectorAll('[data-review]').find(node => !node.hidden) || null;
    }
    return this.querySelectorAll(selector)[0] || null;
  }
  setAttribute(key, value) { this.attrs[key] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  contains(node) { return this.all().includes(node); }
  closest(selector) { for (let node = this; node; node = node.parent) if (node.matches(selector)) return node; return null; }
}
const button = (kind, value) => new Node({[`${kind}Choice`]:value});
const panel = (kind, value) => new Node({[`${kind}Panel`]:value});
const latestRisk = button('stage', 'risk'), latestLaneB = button('lane', 'B');
const latest = new Node({review:'latest', defaultStage:'risk'}, [
  button('stage', 'evidence'), latestRisk,
  panel('stage', 'evidence'), panel('stage', 'risk'),
  button('lane', 'A'), latestLaneB, panel('lane', 'A'), panel('lane', 'B')
]);
const older = new Node({review:'older', defaultStage:'final'}, [
  button('stage', 'evidence'), button('stage', 'final'),
  panel('stage', 'evidence'), panel('stage', 'final'),
  button('lane', 'A'), button('lane', 'B'), panel('lane', 'A'), panel('lane', 'B')
]);
const select = new Node({reviewChoice:''});
const status = new Node({decisionRoomStatus:''}); status.textContent = '';
const root = new Node({decisionRoom:''}, [select, status, latest, older]);
const values = new Map([['shadow-review','missing'], ['shadow-stage','missing'], ['shadow-lane','missing']]);
const storage = {getItem:key=>values.get(key) || null, setItem:(key,value)=>values.set(key,value)};

room.init(root, storage);
assert.equal(select.value, 'latest');
assert.equal(latest.hidden, false); assert.equal(older.hidden, true);
assert.equal(latest.querySelector('[data-stage-panel]').hidden, true);
assert.equal(latest.querySelectorAll('[data-stage-panel]')[1].hidden, false);
assert.equal(latestRisk.attrs['aria-pressed'], 'true');
assert.equal(latest.querySelector('[data-lane-panel]').hidden, false);
assert.match(status.textContent, /Saved view was unavailable/);
assert.deepEqual([...values.entries()].sort(), [
  ['shadow-lane','A'], ['shadow-review','latest'], ['shadow-stage','risk']
]);

root.listeners.click({target:latestLaneB});
assert.equal(latest.querySelectorAll('[data-lane-panel]')[1].hidden, false);
assert.equal(latestLaneB.attrs['aria-pressed'], 'true');
select.value = 'older'; select.listeners.change();
assert.equal(latest.hidden, true); assert.equal(older.hidden, false);
assert.equal(values.get('shadow-stage'), 'final');
assert.match(status.textContent, /Review changed/);
console.log('reducers, scoped DOM state, fallback, announcement and local-only initialization passed');
'''], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


def test_mobile_navigation_has_three_primary_links_and_more_disclosure(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
    desktop = page.split('<nav class="desktop-nav"', 1)[1].split('</nav>', 1)[0]
    phone = page.split('<nav class="phone-nav"', 1)[1].split('</nav>', 1)[0]
    assert desktop.count('data-nav=') == 6
    assert phone.count('data-nav=') == 6
    primary = phone.split('<details class="more-nav"', 1)[0]
    assert [f'data-nav="{name}"' in primary for name in ('next', 'decisions', 'activity')] == [True, True, True]
    more = phone.split('<details class="more-nav"', 1)[1]
    assert '<summary>More</summary>' in more
    for name in ('history', 'results', 'controls'):
        assert f'data-nav="{name}"' in more


def test_next_review_never_inherits_a_previous_completed_status(tmp_path):
    from agents.dashboard import dashboard_snapshot
    from agents.dashboard_view import render_dashboard
    inbox, config = setup_runtime(tmp_path)
    put_cycle(inbox, '2026-09-28', 'COMPLETED', decision={'picks': []}, results=[])
    state = dashboard_snapshot(inbox, datetime(2026, 9, 28, 15, tzinfo=timezone.utc))
    page = render_dashboard(state, config, 'token', {'lane': '', 'status': '', 'date': ''})
    next_panel = page.split('<div class="day-sheet">')[1].split('<a class="attention-row"')[0]
    assert 'Completed' not in next_panel
    assert 'Paper reviews enabled' in next_panel


def test_no_decision_returns_to_approvals_not_an_unrelated_overview(tmp_path):
    from broker.models import Quote
    from test_risk_engine import make_proposal
    inbox, _ = setup_runtime(tmp_path)
    now = datetime.now(timezone.utc)
    card = inbox.issue(make_proposal(quantity=Decimal('.49')),
                       Quote(ticker='VTI', bid=Decimal(100), ask=Decimal('100.20'), timestamp=now),
                       Decimal('.20'), now, now)
    with serving(inbox) as url:
        token = re.search('name="csrf" value="([^"]+)"', read(url))[1]
        request = Request(url + '/decision', data=urlencode({'csrf':token, 'id':card['id'], 'decision':'NO'}).encode())
        with urlopen(request) as response:
            assert response.url.endswith('/#decisions')
        assert inbox.cards()[0]['status'] == 'NO'


def test_filters_are_collapsed_until_needed_and_active_filters_stay_visible(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        default = read(url)
        assert default.count('<details class="filter-disclosure">') == 2
        filtered = read(url + '/?lane=B')
        assert filtered.count('<details class="filter-disclosure" open>') == 2


def test_clear_filters_stays_in_its_section_and_skip_target_accepts_focus(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        page = read(url)
        for section in ('history', 'decisions'):
            content = page.split(f'<section id="{section}"')[1].split('</section>')[0]
            assert f'href="/#{section}">Clear</a>' in content
        assert '<main id="main" tabindex="-1">' in page


def test_display_receipt_fetch_is_same_origin_only_in_csp(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    with serving(inbox) as url:
        with urlopen(url) as response:
            policy = response.headers['Content-Security-Policy']
            assert "connect-src 'self'" in policy
            assert "default-src 'none'" in policy


def test_overview_does_not_record_hidden_cards_and_view_receipts_require_csrf(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    card = issue(inbox)
    with serving(inbox) as url:
        page = read(url)
        with inbox.connect() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='card_views'").fetchone()
            assert not exists or db.execute('SELECT count(*) FROM card_views').fetchone()[0] == 0
        token = re.search('name="csrf" value="([^"]+)"', page)[1]
        with pytest.raises(HTTPError) as error:
            post(url + '/views', ids=json.dumps([card['id']]))
        assert error.value.code == 403
        post(url + '/views', csrf=token, ids=json.dumps([card['id']]))
        post(url + '/views', csrf=token, ids=json.dumps([card['id']]))
        with inbox.connect() as db:
            assert [r[0] for r in db.execute('SELECT card_id FROM card_views')] == [card['id']]
            assert db.execute('SELECT count(*) FROM cycle_runs').fetchone()[0] == 0
        with pytest.raises(HTTPError):
            post(url + '/views', csrf=token, ids=json.dumps(['unknown-card']))


def test_optional_view_receipt_failure_does_not_break_dashboard(tmp_path, monkeypatch):
    import sqlite3
    from agents import notification_outbox
    inbox, _ = setup_runtime(tmp_path)
    issue(inbox)
    def fail(*args, **kwargs):
        raise sqlite3.OperationalError('test locked receipt store')
    monkeypatch.setattr(notification_outbox, 'record_views', fail)
    with serving(inbox) as url:
        assert 'Overview' in read(url)


def test_browser_records_cards_only_when_approvals_are_shown():
    import subprocess
    result = subprocess.run(['node', '-e', r'''
(async()=>{
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const events={},calls=[],location={hash:'#next',search:'',href:'http://127.0.0.1:8766/#next'};
const views=['next','decisions','history'].map(view=>({dataset:{view},hidden:false,focus(){}}));
const document={body:{dataset:{auto:'off'}},visibilityState:'visible',
 querySelector:s=>s==='input[name="csrf"]'?{value:'test-token'}:null,
 querySelectorAll:s=>s==='[data-view]'?views:s==='[data-card-id]'?[{dataset:{cardId:'card-1'}}]:[]};
vm.runInNewContext(fs.readFileSync('agents/static/dashboard.js','utf8'),{document,URL,URLSearchParams,Date,setInterval(){},
 window:{location,scrollTo(){},addEventListener:(name,fn)=>events[name]=fn,history:{replaceState(){}}},
 fetch:async(url,options)=>{calls.push({url,options});return {ok:true};}});
assert.equal(calls.length,0);
location.hash='#history';events.hashchange();assert.equal(calls.length,0);
location.hash='#decisions';events.hashchange();await new Promise(setImmediate);
assert.equal(calls.length,1);assert.equal(calls[0].url,'/views');assert.equal(calls[0].options.method,'POST');
const body=new URLSearchParams(calls[0].options.body);
assert.equal(body.get('csrf'),'test-token');assert.deepEqual(JSON.parse(body.get('ids')),['card-1']);
events.hashchange();await new Promise(setImmediate);assert.equal(calls.length,1);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
