from datetime import date, timedelta
from decimal import Decimal as D


def closes(values, start=date(2025, 1, 1)):
    return {(start + timedelta(days=index)).isoformat(): str(value)
            for index, value in enumerate(values)}


def test_momentum_rotation_requires_full_warmup_and_positive_trend():
    from research.strategy_signals import evaluate_daily_signals

    short = {'VTI': closes([100 + index for index in range(200)])}
    assessment = evaluate_daily_signals(short, {'VTI'}, date(2026, 9, 28))
    assert assessment['signals'] == []
    assert assessment['strategies']['momentum_rotation']['blocked']['VTI'] == 'needs 253 completed closes; has 200'

    series = {'VTI': closes([100 + D(index) / 2 for index in range(253)]),
              'SPY': closes([100 + D(index) / 4 for index in range(253)])}
    assessment = evaluate_daily_signals(series, {'VTI', 'SPY'}, date(2026, 9, 28))
    signal = assessment['signals'][0]
    assert signal['instrument'] == 'VTI'
    assert signal['strategy'] == 'momentum_rotation_126d_trend200_top1'
    ranked = assessment['strategies']['momentum_rotation']['ranked']
    assert [item['instrument'] for item in ranked] == ['VTI', 'SPY']
    assert D(signal['momentum_126d']) > D(ranked[1]['momentum_126d'])
    assert signal['side'] == 'buy'


def test_momentum_rotation_keeps_cash_when_price_is_below_trend():
    from research.strategy_signals import evaluate_daily_signals

    values = [D(300) - index for index in range(253)]
    assessment = evaluate_daily_signals({'VTI': closes(values)}, {'VTI'}, date(2026, 9, 28))
    assert assessment['signals'] == []
    assert assessment['strategies']['momentum_rotation']['blocked']['VTI'] == 'price is not above its 200-session moving average'


def test_mean_reversion_triggers_on_exact_three_percent_drop_above_ma200():
    from research.strategy_signals import evaluate_daily_signals

    values = [D(100)] * 200 + [D(110), D('106.70')]
    assessment = evaluate_daily_signals({'AAPL': closes(values)}, set(), date(2026, 9, 28))
    signal = assessment['signals'][0]
    assert signal['instrument'] == 'AAPL'
    assert signal['strategy'] == 'mean_reversion_drop3_above_ma200'
    assert D(signal['one_day_return']) == D('-0.03')
    assert signal['good_if'].startswith('AAPL remains above its 200-session average')


def test_daily_signals_ignore_closes_after_decision_date():
    from research.strategy_signals import evaluate_daily_signals

    start = date(2025, 1, 1)
    values = [D(100) + index for index in range(253)]
    history = closes(values, start)
    decision = start + timedelta(days=252)
    baseline = evaluate_daily_signals({'VTI': history}, {'VTI'}, decision)
    history[(decision + timedelta(days=1)).isoformat()] = '1'
    assert evaluate_daily_signals({'VTI': history}, {'VTI'}, decision) == baseline


def test_option_ranking_requires_underlying_signal_affordability_and_tight_spread():
    from research.strategy_signals import rank_option_candidates

    contracts = [
        {'instrument': 'wide', 'underlying': 'VTI', 'bid': '0.40', 'ask': '0.60',
         'available_risk_notional': '100', 'max_buy_units': '1',
         'contract': {'type': 'call', 'strike_price': '120', 'expiration_date': '2026-10-16'}},
        {'instrument': 'tight', 'underlying': 'VTI', 'bid': '0.49', 'ask': '0.51',
         'available_risk_notional': '100', 'max_buy_units': '1',
         'contract': {'type': 'call', 'strike_price': '110', 'expiration_date': '2026-10-16'}},
        {'instrument': 'put', 'underlying': 'VTI', 'bid': '0.49', 'ask': '0.51',
         'available_risk_notional': '100', 'max_buy_units': '1',
         'contract': {'type': 'put', 'strike_price': '110', 'expiration_date': '2026-10-16'}},
    ]
    ranked = rank_option_candidates(
        contracts,
        [{'instrument': 'VTI', 'side': 'buy', 'strategy': 'momentum_rotation_126d_trend200_top1'}],
    )
    assert [item['instrument'] for item in ranked] == ['tight']
    assert ranked[0]['strategy'] == 'defined_risk_call_on_momentum_rotation_126d_trend200_top1'
