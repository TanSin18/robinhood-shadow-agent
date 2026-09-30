import csv
import math
import random
from dataclasses import replace
from datetime import date, timedelta

from research.backtest_etf_rule import (ETF_UNIVERSE, Book, Panel, Params, buy_and_hold, run, simulate,
                                        stats, to_markdown)


def _days(n, start=date(2010, 1, 4)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _bars(paths):
    return {s: {d: (p, p) for d, p in series} for s, series in paths.items()}


def test_features_use_completed_sessions_only():
    days = _days(400)
    base = {'SPY': [(d, 100 + i * 0.1) for i, d in enumerate(days)]}
    changed = {'SPY': list(base['SPY'])}
    changed['SPY'][300] = (days[300], 10_000.0)
    f1 = Panel(_bars(base)).features(126, 200, 253)['SPY']
    f2 = Panel(_bars(changed)).features(126, 200, 253)['SPY']
    for key in ('ma', 'mom', 'vol'):
        assert f1[key][300] == f2[key][300]          # the day's own close is not visible
        assert f1[key][301] != f2[key][301]


def test_single_uptrend_full_invest_tracks_buy_and_hold_minus_costs():
    days = _days(600)
    rng = random.Random(1)
    price, spy = 100.0, []
    for d in days:
        price *= 1 + 0.0008 + rng.gauss(0, 0.005)
        spy.append((d, price))
    panel = Panel(_bars({'SPY': spy, 'VTI': spy}))
    p = Params(universe=('SPY',), full_invest=True, guards=False, capital=1000)
    start = 260
    strat = simulate(panel, p, start_index=start)
    bh = buy_and_hold(panel, 'SPY', start, p)
    assert strat['trades'][0]['side'] == 'buy'
    ratio = strat['curve'][-1][1] / bh['curve'][-1][1]
    assert 0.9 < ratio <= 1.0001


def test_exit_rule_sells_below_trend():
    days = _days(520)
    up = [(d, 100 * 1.002 ** i) for i, d in enumerate(days[:400])]
    top = up[-1][1]
    down = [(d, top * 0.99 ** (i + 1)) for i, d in enumerate(days[400:])]
    panel = Panel(_bars({'SPY': up + down, 'VTI': up + down}))
    res = simulate(panel, Params(universe=('SPY',), guards=False), start_index=300)
    sells = [t for t in res['trades'] if t['side'] == 'sell']
    assert sells and sells[0]['reason'] == 'exit_rule'


def test_short_term_gain_taxed_and_losses_carry():
    book = Book(settled=100.0)
    book.buy('X', 1, 50, 50, '2020-01-02')
    book.sell_all('X', 60, 60, '2020-06-01')
    assert math.isclose(book.year_end_tax(0.35, 0.15), 3.5)
    book.buy('X', 1, 60, 60, '2021-01-04')
    book.sell_all('X', 40, 40, '2021-02-01')
    assert book.year_end_tax(0.35, 0.15) == 0 and math.isclose(book.carry_loss, 20)


def test_sizing_matches_live_formula():
    days = _days(400)
    rng = random.Random(3)
    price, s = 100.0, []
    for d in days:
        price *= 1 + 0.001 + rng.gauss(0, 0.01)
        s.append((d, price))
    panel = Panel(_bars({'SPY': s, 'VTI': s}))
    p = Params(universe=('SPY',), guards=False)
    f = panel.features(126, 200, 253)
    res = simulate(panel, p, f, start_index=300)
    first = res['trades'][0]
    i = panel.days.index(first['day'])
    expected = 500 * min(0.25, 0.10 * 0.20 / f['SPY']['vol'][i])
    assert math.isclose(first['qty'] * first['price'] * 1.0001 * 1.001, expected, rel_tol=1e-3)


def test_full_report_runs_on_synthetic_universe(tmp_path):
    days = _days(1400, date(2012, 1, 3))
    rng = random.Random(5)
    rows = []
    for s in ETF_UNIVERSE:
        price, drift = 50.0, rng.uniform(-0.0002, 0.0008)
        begin = 0 if s not in ('XLC', 'XLRE') else 700
        for d in days[begin:]:
            o = price
            price *= 1 + drift + rng.gauss(0, 0.012)
            rows.append((s, d, o, price, 1e6))
    path = tmp_path / 'bars.csv'
    with path.open('w', newline='') as h:
        w = csv.writer(h); w.writerow(['symbol', 'day', 'open', 'close', 'volume']); w.writerows(rows)
    report = run(str(path))
    assert report['summary']['registered_rule']['trades'] > 0
    assert set(report['excess_vs_vti']) >= {'registered_rule', 'signal_full_invest_top1'}
    assert report['verdict'] and '# ETF rule backtest' in to_markdown(report)


def test_midnight_utc_labels_are_shifted_to_the_session(tmp_path):
    from research.backtest_etf_rule import load_bars
    path = tmp_path / 'b.csv'
    path.write_text('symbol,day,open,close,volume\nSPY,2026-09-27,1,1,1\nSPY,2026-09-28,1,1,1\n')
    bars, shifted = load_bars(str(path))
    assert shifted and sorted(bars['SPY']) == ['2026-09-28', '2026-09-29']


def test_equal_weight_trades_only_differences():
    from research.backtest_etf_rule import equal_weight
    days = _days(90)
    flat = {s: [(d, 100.0) for d in days] for s in ('XLK', 'XLF', 'SPY')}
    panel = Panel(_bars(flat))
    res = equal_weight(panel, ('XLK', 'XLF'), 0, Params())
    assert res['tax_paid'] == 0 and res['cost_paid'] < 1.0


def test_drawdown_latch_is_permanent_like_live():
    days = _days(700)
    rng = random.Random(9)
    price, path = 100.0, []
    for i, d in enumerate(days):
        drift = 0.002 if i < 420 else (-0.004 if i < 470 else 0.003)
        price *= 1 + drift + rng.gauss(0, 0.004)
        path.append((d, price))
    panel = Panel(_bars({'SPY': path, 'VTI': path}))
    res = simulate(panel, Params(universe=('SPY',), target_fraction=1.0, max_fraction=1.0), start_index=300)
    assert res['latched_on'] is not None
    assert not [t for t in res['trades'] if t['side'] == 'buy' and t['day'] > res['latched_on']]
