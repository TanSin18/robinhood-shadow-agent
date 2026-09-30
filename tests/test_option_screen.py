from research.strategy_signals import option_screen, rank_option_candidates


def cand(i, underlying='SOXX', kind='call', bid='1.00', ask='1.10', units='1', available='500', stale=False):
    return {'instrument': f'opt{i}', 'underlying': underlying, 'bid': bid, 'ask': ask, 'max_buy_units': units,
            'available_risk_notional': available, 'quote_stale': stale,
            'contract': {'type': kind, 'id': f'opt{i}'}}


def test_screen_counts_first_failing_filter_and_agrees_with_ranker():
    signals = [{'instrument': 'SOXX', 'side': 'buy', 'strategy': 'momentum_rotation_126d_trend200_top1'}]
    cands = [cand(1), cand(2, stale=True), cand(3, underlying='AAPL'), cand(4, kind='put'),
             cand(5, bid='0'), cand(6, bid='1.00', ask='2.00'), cand(7, units='0'),
             cand(8, bid='9.00', ask='9.50', units='1', available='500')]
    screen = option_screen(cands, signals)
    removed = {row['stage']: row['removed'] for row in screen['funnel']}
    assert screen['contracts_seen'] == 8 and screen['passed_all_filters'] == 1
    assert removed == {'quote_fresh': 1, 'underlying_has_buy_signal': 1, 'is_call': 1, 'valid_bid_ask': 1,
                       'spread_within_15pct': 1, 'at_least_one_contract_buyable': 1, 'one_contract_affordable': 1}
    ranked = rank_option_candidates([c for c in cands if not c['quote_stale']], signals)
    assert [r['instrument'] for r in ranked] == ['opt1']
    assert screen['by_underlying']['SOXX']['cheapest_call_cost'] == '110.00'
