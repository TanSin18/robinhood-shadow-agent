from agents.desk.run_checks import build_checks
from agents.desk.router import render

FEATS = {
    'SOXX': {'completed_closes': 377, 'price': '560', 'ma200': '450', 'above_ma200': True, 'momentum_126d': '0.7', 'one_day_return': '-0.01'},
    'QQQ': {'completed_closes': 377, 'price': '500', 'ma200': '450', 'above_ma200': True, 'momentum_126d': '0.3', 'one_day_return': '-0.01'},
    'TLT': {'completed_closes': 377, 'price': '80', 'ma200': '90', 'above_ma200': False, 'momentum_126d': '-0.1', 'one_day_return': '-0.05'},
    'META': {'completed_closes': 377, 'price': '700', 'ma200': '600', 'above_ma200': True, 'momentum_126d': '0.2', 'one_day_return': '-0.048'},
}


def terminal(signals, blocked_momentum=None, authorization=None):
    return [{'event': 'cycle_terminal', 'payload': {
        'status': 'COMPLETED', 'market_open': True, 'quote_count': 4, 'volatility_count': 4,
        'collector_evidence': {'authorization': authorization or {'status': 'WARNING_3_DAYS', 'authorization_id': 'SECRET-AUTH-ID',
                                                                'expires_at': '2026-10-01T17:00:22+00:00'},
                               'effective_write_tool_count': 0, 'account_number': 'ACCT-SECRET'},
        'strategy_assessment': {'decision_date': '2026-09-30', 'features': FEATS, 'signals': signals, 'strategies': {
            'momentum_rotation': {'evaluated': ['QQQ', 'SOXX', 'TLT'],
                                  'ranked': [{'instrument': 'SOXX'}, {'instrument': 'QQQ'}],
                                  'blocked': blocked_momentum or {'TLT': 'price is not above its 200-session moving average'}},
            'mean_reversion': {'evaluated': ['META', 'QQQ', 'SOXX', 'TLT'], 'ranked': [{'instrument': 'META'}],
                               'blocked': {'QQQ': 'drop smaller than 3%', 'SOXX': 'drop smaller than 3%', 'TLT': 'not above'}}}}}}]


SIGNALS = [{'instrument': 'SOXX', 'strategy': 'momentum_rotation_126d_trend200_top1'},
           {'instrument': 'META', 'strategy': 'mean_reversion_drop3_above_ma200'}]


def test_conditions_are_recomputed_and_match_the_recorded_outcome():
    checks = build_checks(terminal(SIGNALS))
    mom = {r['instrument']: r for r in checks['strategies'][0]['rows']}
    assert mom['SOXX']['signal'] and not mom['SOXX']['mismatch']
    assert mom['QQQ']['cells']['rank'] == {'ok': False, 'value': '#2'}
    # After the first failed condition the rule stops; later cells are "not evaluated".
    assert mom['TLT']['cells']['trend']['ok'] is False and mom['TLT']['cells']['momentum']['ok'] == 'skip'
    rev = {r['instrument']: r for r in checks['strategies'][1]['rows']}
    assert rev['META']['signal'] and rev['TLT']['cells']['drop']['ok'] == 'skip'
    assert checks['strategies'][0]['mismatches'] == checks['strategies'][1]['mismatches'] == 0


def test_disagreement_between_record_and_rule_is_flagged_not_hidden():
    checks = build_checks(terminal([SIGNALS[1]]))  # SOXX passes every condition but no signal was recorded
    mom = {r['instrument']: r for r in checks['strategies'][0]['rows']}
    assert mom['SOXX']['mismatch'] and checks['strategies'][0]['mismatches'] == 1


def test_operational_checks_show_expiry_but_never_identifiers():
    checks = build_checks(terminal(SIGNALS))
    auth = next(r for r in checks['operational'] if r['check'] == 'Robinhood authorization')
    assert auth['status'] == 'warn' and 'Thu Oct 1, 1:00 PM ET' in auth['note']
    assert 'SECRET-AUTH-ID' not in repr(checks) and 'ACCT-SECRET' not in repr(checks)
    writes = next(r for r in checks['operational'] if r['check'] == 'Write/trade tools exposed')
    assert writes['status'] == 'pass'


def test_checks_page_renders_in_preview_and_is_deferred_in_operational_mode():
    review = {'review_id': 'r', 'timestamp': '2026-09-30T14:00:00+00:00', 'stages': [], 'header': {},
              'checks': build_checks(terminal(SIGNALS))}
    html = render('/checks', {'preview': True, 'decision_room': [review]}, None, '')
    assert 'Momentum rotation' in html and 'Trend check' in html and 'SECRET-AUTH-ID' not in html
    assert 'style=' not in html
    assert 'Not available yet' in render('/checks', {}, None, '')


def test_sanitizer_keeps_token_counts_but_drops_token_values():
    from agents.desk.preview import public
    kept = public({'input_tokens': 5, 'output_tokens': 2, 'access_token': 'x', 'refresh_token': 'y', 'authorization_id': 'z'})
    assert kept == {'input_tokens': 5, 'output_tokens': 2}
