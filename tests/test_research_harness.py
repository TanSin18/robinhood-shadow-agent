import csv
import random
from datetime import date, timedelta
from pathlib import Path

import pytest

from research.harness import (PRIOR_EXPLORATORY, HarnessError, TrialLog, deflated_sharpe, fingerprint, load_recipe,
                              monthly_folds, run)

RECIPES = Path(__file__).resolve().parents[1] / 'research' / 'recipes'
ETFS = ['GLD', 'QQQ', 'SOXX', 'SPY', 'TLT', 'VTI', 'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY']


def _bars(path, years=16, seed=3):
    rng, rows, d, days = random.Random(seed), [], date(2008, 1, 2), []
    while len(days) < int(252 * years):
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    for s in ETFS:
        price, drift = 50.0, rng.uniform(0.0, 0.0006)
        for day in days:
            o = price
            price *= 1 + drift + rng.gauss(0, 0.011)
            rows.append((s, day, o, price, 1e6))
    with open(path, 'w', newline='') as h:
        w = csv.writer(h); w.writerow(['symbol', 'day', 'open', 'close', 'volume']); w.writerows(rows)
    return path


def test_both_recipes_load_and_hash(tmp_path):
    for name in ('registered_momentum_126_200_top1', 'dual_trend_vol_target_etf17'):
        recipe, sha = load_recipe(RECIPES / f'{name}.yaml')
        assert recipe['recipe']['id'] == name and len(sha) == 64


def test_sp500_recipes_are_refused(tmp_path):
    p = tmp_path / 'sp.yaml'
    p.write_text('recipe: {id: x, status: research_only_never_official}\nuniverse: {kind: sp500_point_in_time}\n')
    with pytest.raises(HarnessError, match='UNIVERSE_NOT_ALLOWED'):
        load_recipe(p)


def test_trial_log_refuses_official_directory(tmp_path):
    (tmp_path / 'agent.db').write_text('')
    with pytest.raises(HarnessError):
        TrialLog(tmp_path / 'trials.db')


def test_prior_looks_are_counted(tmp_path):
    log = TrialLog(tmp_path / 'r' / 'trials.db')
    assert log.count() == len(PRIOR_EXPLORATORY) == 13
    TrialLog(tmp_path / 'r' / 'trials.db')
    assert log.count() == 13          # not double-counted on reopen


def test_fingerprint_records_symbols_span_and_sha(tmp_path):
    bars = _bars(tmp_path / 'bars.csv')
    fp, _ = fingerprint(bars, ETFS, {'minimum_years': 15, 'certified_label': 'CERTIFIED_ETF_HISTORY'})
    assert fp['label'] == 'CERTIFIED_ETF_HISTORY' and len(fp['bars_sha256']) == 64
    assert set(fp['symbols']) == set(ETFS) and fp['symbols']['SPY']['first_session'] == '2008-01-02'
    short, _ = fingerprint(_bars(tmp_path / 'b2.csv', years=3), ETFS, {'minimum_years': 15})
    assert short['label'] == 'NOT_CERTIFIED'


def test_deflation_gets_harder_with_more_trials():
    one = deflated_sharpe(0.03, 0, 3, 4000, 1, None)['probability']
    many = deflated_sharpe(0.03, 0, 3, 4000, 50, 0.0004)['probability']
    assert one > many


def test_runs_both_recipes_and_logs_every_trial(tmp_path):
    bars = _bars(tmp_path / 'bars.csv')
    log = tmp_path / 'research' / 'trials.db'
    for name in ('registered_momentum_126_200_top1', 'dual_trend_vol_target_etf17'):
        r = run(RECIPES / f'{name}.yaml', bars, log)
        assert r['verdict'] in {'PASS', 'NOT_PROVEN'} and r['walk_forward']['folds'] > 100
        assert r['dataset']['bars_sha256'] and r['deflated_sharpe']['trials_counted'] >= 14
    assert TrialLog(log).count() == 15


def test_monthly_folds_cover_each_month_once():
    s = {'curve': [('2020-01-02', 100), ('2020-01-31', 110), ('2020-02-03', 111), ('2020-02-28', 121)]}
    b = {'curve': [('2020-01-02', 100), ('2020-01-31', 100), ('2020-02-03', 100), ('2020-02-28', 100)]}
    w = monthly_folds(s, b)
    assert w['folds'] == 2 and w['share_positive'] == 1.0


def _gem_bars(path):
    rng, rows, d, days = random.Random(8), [], date(2005, 1, 3), []
    while len(days) < 252 * 17:
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += timedelta(days=1)
    for s, drift, vol in (('VTI', 0.0004, 0.012), ('EFA', 0.0003, 0.013), ('AGG', 0.0001, 0.003)):
        price = 60.0
        for day in days:
            o = price
            price *= 1 + drift + rng.gauss(0, vol)
            rows.append((s, day, o, price, 1e6))
    with open(path, 'w', newline='') as h:
        w = csv.writer(h); w.writerow(['symbol', 'day', 'open', 'close', 'volume']); w.writerows(rows)
    return path


def test_gem_recipe_runs_with_periods_secondary_benchmark_and_holdings(tmp_path):
    r = run(RECIPES / 'gem_dual_momentum_vti_efa_agg.yaml', _gem_bars(tmp_path / 'g.csv'), tmp_path / 'res' / 'trials.db')
    assert r['verdict'] in {'PASS', 'NOT_PROVEN', 'INCONCLUSIVE'}
    assert abs(sum(r['holding_share'].values()) - 1) < 0.01 and r['switches'] >= 0
    assert set(r['periods_cagr_pre_tax']) == {'pre_publication', 'post_publication'}
    assert 'vti60_efa40' in r['periods_cagr_pre_tax']['post_publication']
    assert r['secondary_benchmark']['name'].startswith('buy_and_hold_60pct')


def test_gem_holds_one_asset_and_never_peeks(tmp_path):
    from research.backtest_etf_rule import Panel, load_bars
    from research.harness import engine_gem_dual_momentum
    bars, _ = load_bars(_gem_bars(tmp_path / 'g.csv'))
    recipe, _ = load_recipe(RECIPES / 'gem_dual_momentum_vti_efa_agg.yaml')
    res, start = engine_gem_dual_momentum(Panel(bars, 'VTI'), recipe, 10000)
    assert start >= 253
    buys = {t['symbol'] for t in res['trades'] if t['side'] == 'buy'}
    assert buys <= {'VTI', 'EFA', 'AGG'} and res['trades'][0]['day'] >= Panel(bars, 'VTI').days[253]


def test_sector_recipe_holds_at_most_three_and_records_aim_and_stop(tmp_path):
    r = run(RECIPES / 'sector_top3_12_1_ma10_spdr9.yaml', _bars(tmp_path / 'b.csv'), tmp_path / 'res' / 'trials.db')
    assert r['verdict'] in {'PASS', 'NOT_PROVEN', 'INCONCLUSIVE'}
    assert 'no more research trials' in r['stopping_rule'] and 'beat VTI' in r['aim']
    assert set(r['slots_filled_share']) == {0, 1, 2, 3} and abs(sum(r['slots_filled_share'].values()) - 1) < 0.01
    assert set(r['periods_cagr_pre_tax']) == {'first_half', 'second_half'}


def test_sector_engine_never_holds_more_than_three(tmp_path):
    from research.backtest_etf_rule import Panel, load_bars
    from research.harness import engine_sector_top3_12_1_ma10
    bars, _ = load_bars(_bars(tmp_path / 'b.csv'))
    recipe, _ = load_recipe(RECIPES / 'sector_top3_12_1_ma10_spdr9.yaml')
    res, _ = engine_sector_top3_12_1_ma10(Panel(bars), recipe, 10000)
    held, worst = {}, 0
    for t in res['trades']:
        held[t['symbol']] = held.get(t['symbol'], 0) + (t['qty'] if t['side'] == 'buy' else -t['qty'])
        worst = max(worst, sum(1 for q in held.values() if q > 1e-6))
    assert worst <= 3 and not ({t['symbol'] for t in res['trades']} - set(recipe['universe']['symbols']))
