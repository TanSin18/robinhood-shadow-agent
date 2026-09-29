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
    assert 'Broker account' in html
    assert 'Paper experiment' in html
    assert 'Not connected in preview' in html
    assert '$500' not in html
    assert '<form' not in html
