"""Ask Bubbles: the packet, the front-door form, the runtime hand-off and the shared mirror."""
import json
import sqlite3
import sys
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

import pytest

from agents.desk import ask_page
from test_dashboard import read, serving
from test_inbox_lanes import setup_runtime

ACCOUNT = '442776613'


def state():
    review = {'review_id': 'abc123', 'timestamp': '2026-10-05T14:02:11+00:00', 'decision_type': 'DESK_ENTRY',
              'decision_reason': 'Desk rule (no AI): registered ETF entry issued to paper arms.', 'signal_instruments': ['SOXX'],
              'ai_gate': {'open': False, 'reason': 'AI_NOT_NEEDED'}, 'header': {'outcome': 'Desk rule entry', 'duration': '88 seconds'},
              'category': {'group': 'official', 'counts': True, 'tags': []}, 'outcome': {'pending_count': 0}, 'lanes': {'A': [], 'B': []},
              'stages': [{'key': 'evidence', 'label': 'Evidence', 'status_label': 'Completed', 'summary': '890 quotes recorded.'},
                         {'key': 'critic', 'label': 'Critic', 'status_label': 'Not called', 'summary': 'AI was not needed.', 'mandate': 'Attack the idea.'}],
              'log': [{'actor': 'evidence', 'title': 'Collected market data', 'detail': ['890 quotes'], 'time': '2026-10-05T14:02:11+00:00'},
                      {'actor': 'critic', 'title': 'Skipped', 'detail': ['AI gate closed'], 'time': '2026-10-05T14:02:12+00:00'}],
              'checks': {'operational': [{'check': 'Tripwire', 'value': 'CLEAR', 'status': 'pass', 'note': ''}], 'risk': [], 'missing_evidence': []}}
    return {'preview': True, 'updated_at': '2026-10-05T19:05:00+00:00', 'decision_room': [review], 'paused': False,
            'portfolio': {'paper': [{'lane': 'A', 'track': 'agent_alone', 'start': '25000', 'settled_cash': '23684.21', 'unsettled_cash': '0',
                                     'marks': {'SOXX': '566.49'}, 'positions': [{'ticker': 'SOXX', 'quantity': '2.32209', 'average_cost': '566.64'}]}],
                          'real': {'cash': '987.65', 'positions': [], 'last_check': {'status': 'VERIFIED_UNCHANGED'}},
                          'fills': [{'ticker': 'SOXX', 'side': 'buy', 'quantity': '2.322090', 'price': '566.640000', 'status': 'filled',
                                     'track': 'A:agent_alone', 'timestamp': '2026-10-05T14:02:11+00:00'}],
                          'tripwire': [{'status': 'VERIFIED_UNCHANGED', 'change_class': None, 'created_at': '2026-10-05T14:00:40+00:00'}],
                          'capsule': {'observed_at': '2026-10-05T14:02:00+00:00', 'decision': {'signal_instruments': ['SOXX']},
                                      'features': {'SOXX': {'price': '566.5', 'ma200': '450.6', 'momentum_126d': '0.73', 'one_day_return': '0.0021'},
                                                   'VTI': {'price': '330', 'ma200': '310', 'momentum_126d': '0.1', 'one_day_return': '-0.002'}},
                                      'strategies': {'momentum_rotation': {'ranked': ['SOXX', 'XLK'], 'blocked': {}}}}},
            'research': {'protective': [{'timestamp': '2026-10-05T19:50:51+00:00', 'status': None, 'fired': 0, 'held': ['SOXX'], 'error_type': None}]},
            'analyst': {'exists': True, 'team': {'pip': {'at': '2026-10-05T14:06:00+00:00', 'base_rate': 'Trend rules lagged VTI after tax.', 'cited_numbers': []}},
                        'close': None, 'morning': {'at': '2026-10-05T14:07:00+00:00', 'headline': 'Calm tape.'},
                        'regime': {'status': 'OK', 'current': 'calm', 'current_probabilities': {'calm': 0.88}, 'current_run_sessions': 40, 'last_day': '2026-10-02'},
                        'spent': {'day': '2026-10-05', 'usd': 0.05}}}


def test_packet_holds_today_the_run_the_step_and_no_real_balances():
    pkt = ask_page.build_packet(state(), 'Why was the Critic skipped for SOXX?', 'Decision room', 'abc123', 'critic')
    text = json.dumps(pkt)
    assert pkt['context']['now'] == 'Monday Oct 5 2026, 3:05 PM ET' and pkt['context']['next_scheduled'].startswith('today 15:30 ET')
    assert pkt['run']['asked_about_step']['who'] == 'Mojo Jojo (critic, AI)' and pkt['run']['asked_about_step']['events'][0]['event'] == 'Skipped'
    whats = [e['what'] for e in pkt['activity_today']['events']]
    assert whats[0].startswith('Account tripwire check') and any('Paper fill' in w and 'SOXX' in w for w in whats)
    assert any('Blossom (research) wrote a note' in w for w in whats)
    assert pkt['feature:SOXX']['pct_vs_ma200'] == 25.72 and pkt['account:A:agent_alone']['cash_pct_of_value'] == 94.7
    assert pkt['team_status']['not_written_yet'] == ['Buttercup (filings and news)', 'Mayor (portfolio)', 'Mojo Jojo (critic)']
    assert '987.65' not in text and ACCOUNT not in text and 'real orders are blocked' in pkt['real_account']['note']
    assert pkt['TEAM_NOTES']['Blossom (research)']['base_rate'].startswith('Trend rules') and 'cited_numbers' not in pkt['TEAM_NOTES']['Blossom (research)']
    assert len(text) <= ask_page.TOKEN_BUDGET_CHARS


def test_next_event_rolls_over_the_close_and_the_weekend():
    from datetime import datetime
    assert ask_page._next_event(datetime(2026, 10, 5, 9, 0, tzinfo=ask_page.ET)).startswith('today 10:00 ET')
    assert ask_page._next_event(datetime(2026, 10, 9, 18, 0, tzinfo=ask_page.ET)).startswith('Monday Oct 12 10:00 ET')
    assert ask_page._next_event(datetime(2026, 10, 10, 11, 0, tzinfo=ask_page.ET)).startswith('Monday Oct 12 10:00 ET')


def test_page_shows_answers_checks_and_notices_and_no_form_without_a_token():
    qa = [{'status': 'ANSWERED', 'question': 'Why SOXX?', 'answer': 'It ranked first <b>.', 'missing': '', 'sources': ['run'], 'follow_ups': ['And the exit?'],
           '_checks': {'flags': []}, 'at': '2026-10-05T19:06:00+00:00', 'context': 'Decision room'},
          {'status': 'ANSWERED', 'question': 'Will it go up?', 'answer': 'Unknown.', 'missing': 'No forecast is recorded.', 'sources': [],
           '_checks': {'flags': ['NUMBER_NOT_IN_RECORDS:77.5']}, 'at': '2026-10-05T19:01:00+00:00', 'context': ''},
          {'status': 'FAILED_ModelError', 'question': 'x', 'reason': 'OUTPUT_TRUNCATED', '_checks': {}, 'at': '2026-10-05T19:00:00+00:00', 'context': ''}]
    html = ask_page.render({'ask': {'exists': True, 'qa': qa}, 'inbox_csrf': 'tok', 'ask_notice': 'BUSY'})
    assert 'It ranked first &lt;b&gt;.' in html and 'id=latest' in html and 'Code check passed' in html and 'still answering' in html
    assert 'NUMBER_NOT_IN_RECORDS:77.5' in html and 'No forecast is recorded.' in html and 'No answer (FAILED_ModelError: OUTPUT_TRUNCATED)' in html
    assert html.count('action="/ask/question"') == 1 + len(ask_page.SUGGESTED) + 1          # the box, the suggestions, one follow-up
    shared = ask_page.render({'ask': {'exists': True, 'qa': qa}})
    assert '<form' not in shared and 'read-only' in shared
    assert 'Not set up yet' in ask_page.render({'ask': {'exists': False, 'qa': []}, 'inbox_csrf': 'tok'})


def _runtime(tmp_path):
    root = tmp_path / 'a' / 'b'
    root.mkdir(parents=True)
    inbox, _ = setup_runtime(root)
    path = tmp_path / 'robinhood-diagnostics' / 'analyst' / 'analyst.db'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE qa (id INTEGER PRIMARY KEY, at TEXT, day TEXT, context TEXT, question TEXT, payload_json TEXT, checks_json TEXT, status TEXT)')
    db.execute("INSERT INTO qa(at,day,context,question,payload_json,checks_json,status) VALUES ('2026-10-05T19:06:00+00:00','2026-10-05','Today page','Why SOXX?',?,?,'ANSWERED')",
               (json.dumps({'answer': 'It ranked first.', 'missing': '', 'sources': ['run'], 'follow_ups': []}), json.dumps({'ok': True, 'flags': []})))
    db.commit(); db.close()
    return inbox


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _post(url, data, origin=None):
    try:
        build_opener(_NoRedirect).open(Request(url + '/ask/question', data=urlencode(data).encode(), headers={'Origin': origin or url}))
    except HTTPError as error:
        return error.code, error.headers.get('Location')
    raise AssertionError('expected a redirect or an error')


def test_frontdoor_takes_a_question_only_with_the_token_and_from_this_origin(tmp_path, monkeypatch):
    import re
    import test_dashboard
    from agents.desk.frontdoor import make_server
    monkeypatch.setattr(test_dashboard, 'make_server', make_server)
    inbox = _runtime(tmp_path)
    seen = []

    def fake_submit(official_db, question, context, packet, **kw):
        seen.append((str(official_db), question, context, sorted(packet)))
        return seen and ('ANALYST_PAUSED' if question == 'paused?' else 'ANSWERED')
    monkeypatch.setattr(ask_page, 'submit', fake_submit)
    with serving(inbox) as url:
        page = read(url + '/portfolio')
        token = re.search('name="csrf" value="([^"]+)"', page)[1]
        assert 'class="ask-fab"' in page and 'value="Portfolio page"' in page
        assert 'class="ask-fab"' in read(url + '/legacy') and 'class="ask-fab"' not in read(url + '/ask')
        assert _post(url, {'csrf': token, 'question': 'Why SOXX?', 'context': 'x'}, origin='https://evil.example')[0] == 403
        assert _post(url, {'csrf': 'bad', 'question': 'Why SOXX?', 'context': 'x'})[0] == 403
        assert _post(url, {'csrf': token, 'question': '  Why   SOXX? ', 'context': 'Portfolio page'}) == (303, '/ask#latest')
        assert seen == [(str(inbox.path), 'Why SOXX?', 'Portfolio page', seen[0][3])] and 'context' in seen[0][3] and 'schedule' in seen[0][3]
        assert _post(url, {'csrf': token, 'question': '   ', 'context': ''}) == (303, '/ask?notice=EMPTY_QUESTION#latest')
        assert _post(url, {'csrf': token, 'question': 'x' * 501, 'context': ''}) == (303, '/ask?notice=QUESTION_TOO_LONG#latest')
        assert _post(url, {'csrf': token, 'question': 'paused?', 'context': ''}) == (303, '/ask?notice=ANALYST_PAUSED#latest')
        assert len(seen) == 2
        asked = read(url + '/ask?notice=ANALYST_PAUSED')
        assert 'It ranked first.' in asked and 'Why SOXX?' in asked and 'The analyst desk is paused' in asked
        assert 'is paused' not in read(url + '/ask?notice=%3Cscript%3E') and '<script>' not in read(url + '/ask?notice=%3Cscript%3E').replace('<script src=', '')
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + '/ask/question', data=b'x' * 5000, headers={'Origin': url}))
        assert error.value.code == 400


def test_submit_runs_the_installed_runtime_not_the_dashboard_copy(tmp_path, monkeypatch):
    root = tmp_path / 'runtime'
    (root / 'data').mkdir(parents=True)
    (root / 'agents' / 'analyst').mkdir(parents=True)
    (root / 'agents' / '__init__.py').write_text('')
    (root / 'agents' / 'analyst' / '__init__.py').write_text('')
    (root / 'agents' / 'analyst' / 'cli.py').write_text(
        "import json, os, sys\nbody = json.loads(sys.stdin.read())\n"
        "open('seen.json', 'w').write(json.dumps({'argv': sys.argv[1:], 'q': body['question'], 'pp': os.environ.get('PYTHONPATH'), 'packet': body['packet']}))\n"
        "print('noise'); print(json.dumps({'status': 'ANSWERED' if body['question'] != 'fail' else 'DAILY_QUESTION_LIMIT'}))\n"
        "sys.exit(3 if body['question'] == 'crash' else 0)\n")
    monkeypatch.setenv('PYTHONPATH', '/somewhere/dashboard-overlay')
    db = root / 'data' / 'agent.db'
    assert ask_page.submit(db, 'Why?', 'Today page', {'run': {'id': 'run'}}) == 'ANSWERED'
    seen = json.loads((root / 'seen.json').read_text())
    assert seen == {'argv': ['ask', '--official-database', str(db)], 'q': 'Why?', 'pp': None, 'packet': {'run': {'id': 'run'}}}
    assert ask_page.submit(db, 'fail', '', {}) == 'DAILY_QUESTION_LIMIT'
    assert ask_page.submit(db, 'crash', '', {}) == 'RUNTIME_NOT_READY'
    assert ask_page.submit(tmp_path / 'nowhere' / 'data' / 'agent.db', 'Why?', '', {}) == 'RUNTIME_NOT_READY'
    assert sys.executable


def test_shared_mirror_has_no_ask_page_link_or_form(tmp_path):
    import threading
    from agents.desk.mirror import make_server
    inbox = _runtime(tmp_path)
    server = make_server(inbox.path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f'http://127.0.0.1:{server.server_port}'
        for path in ('/', '/room', '/analyst'):
            page = read(url + path)
            assert '<form' not in page and 'href="/ask"' not in page and 'ask-fab' not in page
        with pytest.raises(HTTPError) as error:
            urlopen(url + '/ask')
        assert error.value.code == 404
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url + '/ask/question', data=b'question=x'))
        assert error.value.code == 405
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_unusable_option_quotes_are_information_not_a_corporate_action_warning():
    from agents.desk.run_checks import operational as operational_checks
    payload = {'status': 'COMPLETED', 'corporate_action_exclusions': [{'instrument': '2bde0cb0-ef8a-4259-bfc4-612e143b26b1', 'reason': 'INVALID_QUOTE_PRICE'}] * 19}
    rows = {r['check']: r for r in operational_checks(payload)}
    assert rows['Corporate-action exclusions']['value'] == '0' and rows['Corporate-action exclusions']['status'] == 'pass'
    skipped = rows['Quotes left out (no usable bid/ask)']
    assert skipped['value'] == '19' and skipped['status'] == 'info' and 'all option contracts' in skipped['note']
    split = {'status': 'COMPLETED', 'corporate_action_exclusions': [{'instrument': 'XYZ', 'reason': 'UNRESOLVED_SPLIT'}]}
    rows = {r['check']: r for r in operational_checks(split)}
    assert rows['Corporate-action exclusions']['status'] == 'warn' and 'Quotes left out (no usable bid/ask)' not in rows


def test_history_page_groups_each_day_and_orders_the_run_before_its_fills():
    from agents.desk import history_page
    st = state()
    html = history_page.render(st)
    assert 'Monday, October 5' in html and html.count('class="v10-panel hd"') == 1
    assert html.index('<b>Registered paper run</b>') < html.index('<b>Bought SOXX</b>') < html.index('<b>Protective check</b>')
    assert '2.32209 shares at $566.64 · Automatic arm (Lane A)' in html and 'Nothing sold. Still holding SOXX.' in html
    assert 'Bubbles · Morning note' in html and 'Blossom wrote their daily notes.' in html
    assert 'Run details' in html and ACCOUNT not in html
    assert 'Nothing is recorded yet' in history_page.render({})


def test_analyst_brief_has_a_sub_tab_per_note_and_opens_the_latest():
    from agents.desk import analyst_page
    a = {'exists': True, 'team': {}, 'morning': {'at': '2026-10-05T14:07:00+00:00', 'headline': 'Calm tape.', 'market_read': 'Quiet.', 'news': [], 'watch': ['SOXX']},
         'close': {'at': '2026-10-05T20:20:00+00:00', 'headline': 'Close: steady.', 'news': [
             {'ticker': 'XLF', 'sentiment': 'negative', 'relevance': 'medium', 'note': 'Banks soft.', 'headline_ids': ['h1']},
             {'ticker': 'SOXX', 'sentiment': 'positive', 'relevance': 'high', 'note': 'Chips firm.', 'headline_ids': []}], 'watch': []},
         'news_close': {'items': [{'id': 'h1', 'url': 'https://example.com/a', 'title': 'Banks slip', 'source': 'Example'}]}}
    html = analyst_page.render({'analyst': a, 'portfolio': {}})
    assert 'data-tabgroup="brief"' in html and html.count('data-tabpanel="brief"') == 2
    assert 'id="an-brief-close" data-tabpanel="brief" data-active' in html and 'id="an-brief-morning" data-tabpanel="brief">' in html
    assert html.index('Chips firm.') < html.index('Banks soft.')                      # most relevant first
    assert '1 headline</span>' in html and 'href="https://example.com/a"' in html
    only_close = analyst_page.render({'analyst': {**a, 'morning': None}, 'portfolio': {}})
    assert 'Not written yet' in only_close and 'Written after the 10:00 AM ET registered paper run completes.' in only_close


def test_analyst_memory_tab_shows_the_record_without_overclaiming():
    from agents.desk import analyst_page
    mem = {'scorecard': {'sentiment_calls_scored': 5, 'hits': 4, 'hit_rate_pct': 80.0, 'needed_before_any_verdict': 60, 'verdict': 'TOO_FEW_TO_JUDGE',
                         'calls_waiting_for_next_close': 2, 'regime_avg_abs_next_day_move_pct': {'calm': {'sessions': 1, 'avg_abs_move_pct': 0.27}}},
           'calls': [{'day': '2026-10-05', 'seat': 'bubbles', 'kind': 'sentiment', 'ticker': 'SOXX', 'call': 'positive', 'scored_day': '2026-10-06',
                      'next_day_return_pct': 1.2, 'spy_return_pct': 0.3, 'hit': True},
                     {'day': '2026-10-06', 'seat': 'biscuit', 'kind': 'sentiment', 'ticker': 'XLF', 'call': 'negative', 'scored_day': None},
                     {'day': '2026-10-06', 'seat': 'model', 'kind': 'regime', 'ticker': 'VTI', 'call': 'calm', 'scored_day': None}],
           'lessons': [{'day': '2026-10-05', 'job': 'close', 'lesson': 'Name the session the bars cover <b>.', 'check_next': 'as_of'}]}
    html = analyst_page.render({'analyst': {'exists': True, 'team': {}, 'memory': mem}, 'portfolio': {}})
    assert 'id="an-memory"' in html and '5 of 60' in html and 'Too few to judge' in html and '80%' in html
    assert '>hit<' in html and '>waiting<' in html and 'Buttercup' in html and 'Name the session the bars cover &lt;b&gt;.' in html
    assert 'Calm · 1 session<' in html and 'the trading rules change only by a signed amendment' in html
    empty = analyst_page.render({'analyst': {'exists': True, 'team': {}}, 'portfolio': {}})
    assert 'No calls recorded yet' in empty and '0 of 60' in empty
    pkt = ask_page.build_packet({**state(), 'analyst': {**state()['analyst'], 'memory': mem}}, 'What has the desk learned?', 'Analyst page')
    assert pkt['memory']['verdict'] == 'TOO_FEW_TO_JUDGE' and pkt['memory']['lessons'][0]['check_next'] == 'as_of'
