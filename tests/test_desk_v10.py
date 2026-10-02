"""v10 pages: Robinhood-style Portfolio tabs, Rule book and Architecture."""
import json

from agents.desk.router import render
from agents.desk import rulebook

CAP = {
    'cycle_id': 'c1', 'observed_at': '2026-10-01T14:02:11+00:00',
    'decision': {'signal_instruments': ['SOXX'], 'type': 'DESK_ENTRY'},
    'features': {'SOXX': {'price': '568.64', 'ma200': '452.31', 'momentum_126d': '0.73', 'momentum_63d': '-0.05',
                          'momentum_252d': '1.11', 'one_day_return': '0.002'},
                 'XLK': {'price': '195.75', 'ma200': '160', 'momentum_126d': '0.47', 'one_day_return': '0.006'},
                 'GLD': {'price': '380.84', 'ma200': '416.30', 'momentum_126d': '-0.11', 'one_day_return': '-0.005'},
                 'AAPL': {'price': '333.02', 'ma200': '288.60', 'momentum_126d': '0.31', 'one_day_return': '0.011'}},
    'signals': [{'instrument': 'SOXX', 'strategy': 'momentum_rotation_126d_trend200_top1', 'thesis': 'SOXX ranks highest.'}],
    'strategies': {'momentum_rotation': {'ranked': ['SOXX', 'XLK'], 'evaluated': ['SOXX', 'XLK', 'GLD'],
                                         'blocked': {'GLD': 'price is not above its 200-session moving average'}},
                   'mean_reversion': {'blocked': {'SOXX': 'latest completed-session drop is smaller than 3%'}}},
    'liquidity': {'SOXX': '3433123163.51'},
    'closes': {'SOXX': {f'2026-0{m}-{d:02d}': str(400 + m * 10 + d) for m in range(4, 10) for d in range(1, 28)}},
}


def _state():
    fill = {'client_order_id': 'card-1', 'ticker': 'SOXX', 'side': 'buy', 'quantity': '2.322090', 'price': '566.64',
            'spread_cost': '0.17', 'status': 'filled', 'timestamp': '2026-10-01T14:02:11+00:00'}
    paper = [{'lane': 'A', 'track': t, 'start': '25000.00', 'capital_version': '1.6.0', 'settled_cash': '23684.21', 'unsettled_cash': '0',
              'marks': {'SOXX': '566.49'}, 'peak': '25000', 'day_start_value': '25000', 'fills': [fill],
              'positions': [{'ticker': 'SOXX', 'asset_class': 'etf', 'quantity': '2.322090', 'average_cost': '566.64', 'multiplier': 1}]}
             for t in ('agent_alone', 'with_approvals', 'deterministic_no_ai')]
    card = {'id': 'card-1', 'status': 'YES', 'author': 'Desk rule (no AI)', 'vol': '0.378', 'decided': '2026-10-01T14:21:50+00:00',
            'response_seconds': 1179, 'proposal': {'thesis': 'SOXX ranks highest.', 'good_if': 'stays above', 'invalidation': 'closes below',
                                                   'horizon_days': 20, 'limit_price': '569.39', 'client_order_id': 'card-1'}}
    return {'preview': True, 'updated_at': '2026-10-01T15:00:00+00:00', 'cards': [card],
            'research': {'rebase': {'timestamp': '2026-10-01T14:00:40+00:00', 'capital': '25000.00'}},
            'portfolio': {'paper': paper, 'fills': [fill], 'capsule': CAP,
                          'values': [{'timestamp': '2026-10-01T14:02:11+00:00', 'lane': 'A', 'track': 'agent_alone', 'value': '25000.00',
                                      'data_mode': 'live_readonly'}],
                          'real': {'as_of': '2026-09-28T22:53:31+00:00', 'cash': '500', 'positions': [], 'open_orders': {'equity': 0}},
                          'tripwire': [{'status': 'VERIFIED_UNCHANGED', 'created_at': '2026-10-01T14:00:40+00:00'}]}}


def test_portfolio_paper_home_explains_each_holding():
    html = render('/portfolio', _state(), None, '')
    assert html.count('data-acct="A-') == 3
    assert 'Why it was picked' in html and '<dt>Decision source</dt><dd>Desk rule (no AI)</dd>' in html
    assert 'What would make it sell' in html and '8% under your cost ($521.31)' in html
    assert 'class="pk-badge win">#1' in html and 'class="pk-badge">#2' in html and 'ETFs trading below their 200-session average' in html
    assert 'Passed both tests' in html and 'Single stocks' in html and 'class="pk-funnel"' in html
    assert 'Single stock' in html                        # AAPL is not bought by the ETF rules
    # Approval arm: decision source, operator approval, approval time and fill time are four separate facts
    assert '<dt>Operator approval</dt><dd>YES (19 min 39 s after the card arrived)</dd>' in html
    assert '<dt>Approval time</dt><dd>Thu Oct 1, 10:21 AM ET</dd>' in html and '<dt>Fill time</dt><dd>Thu Oct 1, 10:02 AM ET</dd>' in html
    assert html.count('<dt>Operator approval</dt><dd>Not required in this arm</dd>') == 2      # the other two arms
    approval = html[html.index('id="acct-A-with_approvals"'):html.index('id="acct-A-deterministic_no_ai"')]
    assert ('<dl class="v10-trade-meta"><div><dt>Decision source</dt><dd>Desk rule (no AI)</dd></div><div><dt>Operator approval</dt><dd>YES</dd></div>'
            '<div><dt>Approval time</dt><dd>Oct 1, 10:21 AM ET</dd></div><div><dt>Fill time</dt><dd>Oct 1, 10:02 AM ET</dd></div></dl>') in approval
    for r in ('1D', '1W', '1M', 'ALL'):
        assert f'data-range="{r}"' in html
    assert 'v10-donut' in html and 'style=' not in html and '<script>' not in html and '<form' not in html


def test_price_chart_moves_bars_to_their_real_session():
    from agents.desk.portfolio import _closes
    pts = _closes(CAP, 'SOXX')
    assert pts[0][0].date().isoformat() == '2026-04-02'   # stored as 04-01 (00:00 UTC bar), shown on its session


def test_real_tab_is_read_only_and_never_invents_numbers():
    html = render('/portfolio', _state(), None, '')
    assert 'Real account' in html and 'No positions. The system has never traded this account.' in html
    assert 'Buying power</dt><dd>not recorded' in html and 'No account numbers' in html


def test_capsule_view_strips_account_identifiers():
    from agents.desk.preview import _capsule_view
    payload = {'strategy_assessment': {'features': {}, 'signals': [{'instrument': 'SOXX', 'account_id': '123456789'}]},
               'outcome': {'desk_results': [{'instrument': 'SOXX', 'account_number': '987'}]}, 'inputs': {}}
    view = _capsule_view({'cycle_id': 'c', 'created_at': '2026-10-01T14:00:00+00:00', 'payload': json.dumps(payload)})
    text = json.dumps(view)
    assert '123456789' not in text and '987' not in text and 'SOXX' in text


def test_rule_book_lists_every_rule_with_a_source_and_no_private_paths():
    cat = rulebook.catalogue()
    n = sum(len(g['rules']) for g in cat['rule_groups'])
    html = render('/rules', {'preview': True}, None, '')
    assert '<h1>Rule book</h1>' in html and html.count('class="rb-rule"') >= n
    assert all(r.get('source') for g in cat['rule_groups'] for r in g['rules'])
    raw = rulebook.DATA.read_text()
    assert '/home/' not in raw and '/Users/' not in raw and 'account_id": "' not in raw
    assert 'Known issues' in html and 'Shorthand decoded' in html and 'A day, minute by minute' in html
    assert 'style=' not in html and '<script>' not in html


def test_architecture_shows_the_missing_order_path_and_questions():
    html = render('/architecture', _state(), None, '')
    assert '<h1>Architecture</h1>' in html and 'ar-edge blocked' in html and 'no such tool exists' in html
    assert html.count('class="ar-q"') == 1 and 'Questions for you' in html
    assert 'NOT PROVEN' in html and 'style=' not in html and '<script>' not in html


def test_guide_steps_open_into_every_rule():
    html = render('/guide', {'preview': True}, None, '')
    assert 'Every rule at this step' in html and 'href="/rules"' in html
    assert 'There are three rules: ETF momentum and the 3% dip' in html and '26 coded checks' in html


def test_analyst_page_empty_and_with_records(tmp_path):
    import sqlite3
    from agents.desk.analyst_page import load
    html = render('/analyst', {'preview': True, 'analyst': {'exists': False}}, None, '')
    assert '<h1>Analyst desk</h1>' in html and 'Not set up yet' in html
    official = tmp_path / 'rt' / 'data' / 'agent.db'
    official.parent.mkdir(parents=True)
    path = tmp_path / 'robinhood-diagnostics' / 'analyst' / 'analyst.db'
    path.parent.mkdir(parents=True)
    db = sqlite3.connect(path)
    for t in ('notes', 'regimes', 'kelly', 'auction', 'news'):
        extra = ', kind TEXT, model TEXT, checks_json TEXT' if t == 'notes' else (', kind TEXT' if t == 'news' else '')
        db.execute(f'CREATE TABLE {t} (id INTEGER PRIMARY KEY, at TEXT, day TEXT{extra}, payload_json TEXT)')
    db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)')
    db.execute('CREATE TABLE budget (id INTEGER PRIMARY KEY, at TEXT, day TEXT, seat TEXT, model TEXT, reserved TEXT, actual TEXT, status TEXT)')
    note = {'headline': 'Chips <lead>', 'market_read': 'Quiet.', 'news': [{'ticker': 'SOXX', 'sentiment': 'positive', 'relevance': 'high',
                                                                       'note': 'n', 'headline_ids': ['news:1']}], 'watch': ['x']}
    db.execute("INSERT INTO notes(at,day,kind,model,checks_json,payload_json) VALUES('2026-10-02T14:10:00+00:00','2026-10-02','morning','m',?,?)",
               (json.dumps({'ok': True, 'flags': []}), json.dumps(note)))
    db.execute("INSERT INTO news(at,day,kind,payload_json) VALUES('2026-10-02T14:09:00+00:00','2026-10-02','morning',?)",
               (json.dumps({'items': [{'id': 'news:1', 'ticker': 'SOXX', 'title': 'Chips up', 'url': 'https://example.com/a', 'source': 'Ex'}]}),))
    reg = {'status': 'OK', 'model': 'm', 'current': 'calm', 'current_probabilities': {'calm': .8, 'normal': .19, 'stressed': .01},
           'tomorrow_probabilities': {'calm': .78, 'normal': .2, 'stressed': .02}, 'current_run_sessions': 39, 'sessions': 5000,
           'states': [{'name': n, 'ann_return_pct': 1, 'ann_vol_pct': 2, 'expected_duration_sessions': 3, 'share_of_days': .3}
                      for n in ('calm', 'normal', 'stressed')], 'transition': [[.9, .09, .01]] * 3, 'path': [['2026-10-01', 'calm']]}
    db.execute("INSERT INTO regimes(at,day,payload_json) VALUES('2026-10-02T20:20:00+00:00','2026-10-02',?)", (json.dumps(reg),))
    db.execute("INSERT INTO budget(at,day,seat,model,reserved,actual,status) VALUES('x','2026-10-02','commentary','m','0.02','0.004','SETTLED')")
    db.commit()
    db.close()
    state = {'preview': True, 'analyst': load(official)}
    html = render('/analyst', state, None, '')
    assert 'Chips &lt;lead&gt;' in html and 'href="https://example.com/a"' in html and 'Code checks passed' in html
    assert 'an-strip' in html and 'Calm' in html and '$0.004' in html and 'data-tab="an-guard"' in html
    assert 'data-tab="an-team"' in html and 'Mojo Jojo' in html and 'No note yet' in html
    assert 'style=' not in html and '<script>' not in html and '<form' not in html
