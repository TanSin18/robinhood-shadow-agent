from agents.decision_room import project_decision_room
from agents.desk.router import render

T = '2026-09-29T14:00:{:02d}+00:00'


def trace(*events):
    return [{'trace_id': 'run-9', 'timestamp': T.format(i), **e} for i, e in enumerate(events)]


def stopped_run():
    return trace(
        {'event': 'cycle_started', 'trigger': 'scheduled', 'data_mode': 'live_readonly'},
        {'event': 'data_collected', 'quote_count': 14, 'volatility_count': 14, 'read_tools': ['get_equity_quotes'],
         'account_last4': '9999', 'account_number': 'ACCT-SECRET'},
        {'event': 'strategy_evaluated', 'signals': [{'instrument': 'SOXX', 'lane': 'A', 'confidence': '0.85'}],
         'blocked': {'mean_reversion': {'AAPL': 'drop smaller than 3%'}}, 'candidate_decisions': []},
        {'event': 'ai_invocation_gate', 'invoke': True, 'reason': 'QUALIFIED', 'candidate_ids': ['SOXX']},
        {'event': 'stage_started', 'role': 'research', 'agent': 'Research Agent'},
        {'event': 'stage_completed', 'role': 'research', 'output': {'summary': 'Compared. More.', 'compared_symbols': ['SOXX']}},
        {'event': 'stage_started', 'role': 'portfolio'},
        {'event': 'stage_completed', 'role': 'portfolio', 'output': {'picks': [{'instrument': 'SOXX', 'lane': 'A'}], 'reason': 'Top momentum.'}},
        {'event': 'stage_started', 'role': 'critic'},
        {'event': 'stage_completed', 'role': 'critic', 'output': {'rejected_instruments': ['SOXX'], 'counterargument': 'Not executable. Detail.'}},
        {'event': 'risk_evaluated', 'status': 'completed', 'real_execution': 'blocked', 'results': [{'instrument': 'SOXX', 'status': 'REJECTED'}]},
        {'event': 'cycle_terminal', 'payload': {'status': 'COMPLETED', 'account_last4': '9999',
            'decision': {'picks': [{'instrument': 'SOXX'}], 'reason': 'Top momentum.'},
            'critic': {'rejected_instruments': ['SOXX'], 'counterargument': 'Not executable. Detail.'},
            'results': [{'instrument': 'SOXX', 'status': 'REJECTED'}]}},
    )


def test_log_is_ordered_whitelisted_and_never_carries_account_fields():
    review = project_decision_room(stopped_run(), [])[0]
    titles = [e['title'] for e in review['log']]
    assert titles[0] == 'Run started' and titles[-1].startswith('Run finished')
    assert 'AI gate opened for SOXX' in titles and 'Proposed SOXX' in titles and 'Rejected SOXX' in titles
    blob = repr(review['log'])
    assert '9999' not in blob and 'ACCT-SECRET' not in blob
    html = render('/room', {'preview': True, 'decision_room': [review]}, None, '')
    assert '9999' not in html and 'ACCT-SECRET' not in html


def test_flow_marks_the_critic_stop_and_no_card_after_it():
    review = project_decision_room(stopped_run(), [])[0]
    edges = {(e['from'], e['to']): e for e in review['flow']['edges']}
    assert edges[('portfolio', 'critic')]['state'] == 'carried'
    assert edges[('critic', 'risk')] == {'from': 'critic', 'to': 'risk', 'state': 'stopped', 'label': 'rejected SOXX'}
    assert edges[('risk', 'final')]['state'] == 'skipped'
    html = render('/room', {'preview': True, 'decision_room': [review]}, None, '')
    assert 'edge-stopped' in html and 'edge-stop' in html
    assert 'data-inspect="critic"' in html and 'data-selected="critic"' in html


def test_closed_gate_marks_ai_stages_not_called_and_draws_a_labelled_bypass():
    records = trace(
        {'event': 'cycle_started'},
        {'event': 'data_collected', 'quote_count': 1, 'volatility_count': 1},
        {'event': 'ai_invocation_gate', 'invoke': False, 'reason': 'AI_NOT_NEEDED'},
        {'event': 'cycle_terminal', 'payload': {'status': 'COMPLETED', 'decision': {'type': 'HOLD_OPERATIONAL', 'picks': [],
            'reason': 'No candidate has fresh evidence.'}, 'results': []}},
    )
    review = project_decision_room(records, [])[0]
    labels = {s['key']: s['status_label'] for s in review['stages']}
    assert labels['research'] == labels['portfolio'] == labels['critic'] == 'Not called'
    assert review['flow']['bypass']['label'] == 'No AI needed · hold'
    assert all(e['state'] == 'skipped' for e in review['flow']['edges'])
    html = render('/room', {'preview': True, 'decision_room': [review]}, None, '')
    assert 'AI gate stayed closed' in html and 'No candidate has fresh evidence.' in html
    assert 'data-flow="evidence-final"' in html


def test_preview_sanitizer_drops_last4_fields():
    from agents.desk.preview import public
    assert public({'account_last4': '1', 'x': {'last4': '2', 'ok': 3}}) == {'x': {'ok': 3}}
