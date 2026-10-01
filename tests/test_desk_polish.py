from agents.desk.router import render


def test_preview_results_does_not_turn_missing_performance_into_zero():
    html = render('/scoreboard', {'preview': True, 'decision_room': []}, None, '')
    assert 'Not measured' in html
    assert '$0' not in html
    assert 'href="/room"' in html
    assert 'Return after costs' in html
    assert 'No results are assumed' not in html


def test_polish_does_not_change_operational_shell():
    preview = render('/scoreboard', {'preview': True}, None, '')
    operational = render('/scoreboard', {}, None, '')
    assert '/assets/agent-polish.css' in preview
    assert '/assets/agent-polish.css' not in operational
    assert 'Preview — view only' in preview


def test_portfolio_does_not_invent_broker_balances():
    html = render('/portfolio', {'preview': True}, None, '')
    assert 'Real · Robinhood Agentic' in html and 'Paper accounts' in html
    assert 'No verified snapshot of the Robinhood Agentic account is recorded yet. Missing is not zero.' in html
    assert 'No paper accounts are recorded yet.' in html
    assert '$500.00' not in html
    assert '<form' not in html


def test_portfolio_shows_recorded_real_snapshot_and_paper_split():
    state = {'preview': True, 'updated_at': '2026-09-30T15:00:00+00:00', 'portfolio': {
        'real': {'as_of': '2026-09-28T22:53:31+00:00', 'cash': '500', 'positions': [], 'open_orders': {'equity': 0, 'option': 0, 'crypto': 0},
                 'last_check': {'status': 'VERIFIED_UNCHANGED', 'created_at': '2026-09-30T14:00:07+00:00'}},
        'paper': [{'lane': 'A', 'track': 'agent_alone', 'settled_cash': '474.52', 'unsettled_cash': '0',
                   'positions': [{'ticker': 'SOXX', 'quantity': '0.044920', 'average_cost': '567.23', 'multiplier': 1}]},
                  {'lane': 'A', 'track': 'with_approvals', 'settled_cash': '500', 'unsettled_cash': '0', 'positions': []}],
        'values': [{'timestamp': '2026-09-30T14:00:46+00:00', 'lane': 'A', 'track': 'with_approvals', 'value': '500'}]}}
    html = render('/portfolio', state, None, '')
    assert '$500.00' in html and 'Verified Unchanged' in html and 'Sep 30, 10:00 AM ET' in html
    assert 'SOXX' in html and 'AI alone' in html and 'acct-A-deterministic_no_ai' not in html
    assert 'data-tab="tab-real"' in html and 'data-tab="tab-paper"' in html
    assert 'v10-chart' in html and 'style=' not in html and '<script>' not in html
