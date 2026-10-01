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
