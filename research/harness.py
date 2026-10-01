"""Research harness: pre-registered recipes, dataset fingerprints, walk-forward folds, trial log.

Research only. Never reads or writes the Official database; the trial log must live in its
own directory. Every run is a row in the trial log, kept forever, failures included, and the
best result is judged against how many trials were taken (deflated Sharpe).

    python -m research.harness run --recipe research/recipes/<id>.yaml --bars <bars.csv> \
        --log <dir>/trials.db --out <dir>/<id>.json [--md <dir>/<id>.md]
    python -m research.harness log --log <dir>/trials.db

Recipes whose universe is not a fixed ETF list (S&P 500, point-in-time stocks) are refused
until a certified point-in-time dataset exists.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import NormalDist

from research.backtest_etf_rule import (HALF_SPREAD, Book, Panel, Params, bootstrap_excess, buy_and_hold,
                                        first_decision_index, load_bars, simulate, stats)

N = NormalDist()
ALLOWED_UNIVERSES = {'etf_list'}
# Exploratory looks taken on 2026-09-30 before this harness existed (backtest variants and the
# 9-cell lookback/trend sensitivity grid). They count toward the number of trials.
PRIOR_EXPLORATORY = [
    'backtest_2026-09-30:registered_rule', 'backtest_2026-09-30:registered_rule_no_guards',
    'backtest_2026-09-30:registered_rule_v142_8etfs', 'backtest_2026-09-30:signal_full_invest_top3',
    *[f'backtest_2026-09-30:sensitivity_mom{m}_ma{t}' for m in (63, 126, 252) for t in (100, 150, 200)],
]


class HarnessError(RuntimeError):
    pass


# ------------------------------------------------------------------ recipe + dataset
def load_recipe(path):
    import yaml
    raw = Path(path).read_bytes()
    recipe = yaml.safe_load(raw)
    if not isinstance(recipe, dict) or 'recipe' not in recipe or 'universe' not in recipe:
        raise HarnessError('RECIPE_SHAPE_INVALID')
    if recipe['universe'].get('kind') not in ALLOWED_UNIVERSES:
        raise HarnessError('UNIVERSE_NOT_ALLOWED: S&P-wide and stock recipes need a certified point-in-time dataset first')
    if recipe['recipe'].get('status') != 'research_only_never_official':
        raise HarnessError('RECIPE_MUST_BE_RESEARCH_ONLY')
    return recipe, hashlib.sha256(raw).hexdigest()


def fingerprint(bars_path, symbols, requirement):
    raw = Path(bars_path).read_bytes()
    bars, shifted = load_bars(bars_path)
    per = {}
    for s in symbols:
        days = sorted(bars.get(s, {}))
        per[s] = {'first_session': days[0] if days else None, 'last_session': days[-1] if days else None,
                  'sessions': len(days)}
    missing = [s for s in symbols if not per[s]['sessions']]
    firsts = [v['first_session'] for v in per.values() if v['first_session']]
    lasts = [v['last_session'] for v in per.values() if v['last_session']]
    span_years = ((date.fromisoformat(max(lasts)) - date.fromisoformat(min(firsts))).days / 365.25) if firsts else 0
    certified = (not missing and span_years >= float(requirement.get('minimum_years', 0))
                 and not requirement.get('point_in_time_universe_required'))
    return {'bars_sha256': hashlib.sha256(raw).hexdigest(), 'bars_file': Path(bars_path).name,
            'symbols': per, 'missing_symbols': missing, 'first_session': min(firsts) if firsts else None,
            'last_session': max(lasts) if lasts else None, 'span_years': round(span_years, 2),
            'session_labels_shifted_plus_one_day': shifted, 'adjustment': 'split_only_price_return_no_dividends',
            'label': requirement.get('certified_label', 'CERTIFIED') if certified else 'NOT_CERTIFIED'}, bars


# ------------------------------------------------------------------ engines
def _vol(closes, present, i, n):
    vals = [closes[k] for k in range(max(0, i - 3 * n), i) if present[k] and closes[k]][-(n + 1):]
    if len(vals) < n + 1:
        return None
    rets = [math.log(b / a) for a, b in zip(vals, vals[1:])]
    m = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return sd * math.sqrt(252) if sd > 0 else None


def engine_registered_rule(panel, recipe, capital):
    sig = recipe['signal']
    p = Params(universe=tuple(recipe['universe']['symbols']), lookback=sig['momentum_sessions'],
               trend=sig['trend_sessions'], top_n=sig['picks'], capital=capital, guards=True)
    feats = panel.features(p.lookback, p.trend, p.warmup)
    start = _start(panel, feats, p)
    return simulate(panel, p, feats, start), start


def engine_dual_trend_vol_target(panel, recipe, capital):
    sig, size = recipe['signal'], recipe['sizing']
    symbols = [s for s in recipe['universe']['symbols'] if s in panel.close]
    p = Params(universe=tuple(symbols), lookback=sig['absolute_momentum_sessions'], trend=sig['trend_sessions'],
               capital=capital, guards=False)
    feats = panel.features(p.lookback, p.trend, p.warmup)
    start = _start(panel, feats, p)
    book, curve, trades, targets, days = Book(settled=capital), [], [], {}, panel.days
    invested = 0
    for i in range(start, len(days)):
        day = days[i]
        book.settled += book.unsettled; book.unsettled = 0.0
        opens = {s: panel.open[s][i] for s in symbols if panel.present[s][i] and panel.open[s][i]}
        if i == start or day[:7] != days[i - 1][:7]:
            equity = book.settled + sum(book.qty(s) * (opens.get(s) or panel.close[s][i - 1] or 0.0) for s in book.lots)
            raw = {}
            for s in symbols:
                f = feats[s]
                last = panel.close[s][i - 1]
                if (f['count'][i] >= p.warmup and f['ma'][i] and f['mom'][i] is not None and last
                        and last > f['ma'][i] and f['mom'][i] > 0 and s in opens):
                    v = _vol(panel.close[s], panel.present[s], i, 63)
                    if v:
                        raw[s] = (1 / v, v)
            total = sum(w for w, _ in raw.values())
            weights = {s: min(size['max_per_etf'], w / total) for s, (w, _) in raw.items()} if total else {}
            est = sum(weights[s] * raw[s][1] for s in weights)
            scale = min(1.0, size['portfolio_target_vol'] / est) if est > 0 else 0.0
            weights = {s: w * scale for s, w in weights.items()}
            if sum(weights.values()) > size['max_gross']:
                k = size['max_gross'] / sum(weights.values())
                weights = {s: w * k for s, w in weights.items()}
            targets = {s: equity * w for s, w in weights.items()}
            for s in sorted(list(book.lots)):     # sell what is above target (or no longer held)
                if not book.lots[s] or s not in opens:
                    continue
                excess = book.qty(s) * opens[s] - targets.get(s, 0.0)
                if excess > max(1.0, 0.01 * equity) or (s not in targets and book.qty(s) > 0):
                    qty = book.qty(s) if s not in targets else excess / opens[s]
                    book.sell_qty(s, qty, opens[s] * (1 - HALF_SPREAD[s]), opens[s], day)
                    trades.append({'day': day, 'side': 'sell', 'symbol': s, 'qty': qty})
        equity_now = book.settled + book.unsettled + sum(book.qty(s) * (opens.get(s) or 0.0) for s in book.lots)
        for s, target in sorted(targets.items()):  # buy shortfalls with settled cash (T+1 aware)
            if s not in opens:
                continue
            short = target - book.qty(s) * opens[s]
            if short <= max(1.0, 0.01 * equity_now) or book.settled <= 1.0:
                continue
            fill = opens[s] * (1 + HALF_SPREAD[s]) * (1 + p.slippage)
            qty = min(short, book.settled) / fill
            book.buy(s, qty, fill, opens[s], day)
            trades.append({'day': day, 'side': 'buy', 'symbol': s, 'qty': qty})
        if i + 1 == len(days) or days[i + 1][:4] != day[:4]:
            book.year_end_tax(p.st_tax, p.lt_tax)
        value = book.value({s: panel.close[s][i] or 0.0 for s in panel.close})
        invested += 1 if any(book.lots.values()) else 0
        curve.append((day, value))
    liq = book.liquidation_tax({s: panel.close[s][-1] or 0.0 for s in panel.close}, days[-1], p.st_tax, p.lt_tax)
    return {'curve': curve, 'trades': trades, 'tax_paid': book.tax_paid, 'liquidation_tax': liq,
            'cost_paid': book.cost_paid, 'invested_share': invested / max(1, len(curve)), 'locked': False,
            'latched_on': None}, start


def engine_gem_dual_momentum(panel, recipe, capital):
    sig = recipe['signal']
    symbols = recipe['universe']['symbols']
    look = sig['lookback_sessions']
    p = Params(universe=tuple(symbols), capital=capital, guards=False)
    days = panel.days
    def ret(s, i):   # completed sessions through i-1
        closes = [panel.close[s][k] for k in range(i) if panel.present[s][k]]
        return None if len(closes) <= look else closes[-1] / closes[-look - 1] - 1
    start = next(i for i in range(len(days)) if all(
        sum(1 for k in range(i) if panel.present[s][k]) >= 253 for s in symbols))
    book, curve, trades, target, holding_log = Book(settled=capital), [], [], None, {}
    for i in range(start, len(days)):
        day = days[i]
        book.settled += book.unsettled; book.unsettled = 0.0
        opens = {s: panel.open[s][i] for s in symbols if panel.present[s][i] and panel.open[s][i]}
        if i == start or day[:7] != days[i - 1][:7]:
            rets = {s: ret(s, i) for s in sig['risk_assets']}
            if all(v is not None for v in rets.values()):
                if rets['VTI'] > sig['absolute_hurdle']:
                    target = max(sig['risk_assets'], key=lambda s: (rets[s], s == 'VTI'))
                else:
                    target = sig['safe_asset']
            holding_log[day[:7]] = target
            for s in sorted(list(book.lots)):
                if book.lots[s] and s != target and s in opens:
                    qty = book.qty(s)
                    book.sell_qty(s, qty, opens[s] * (1 - HALF_SPREAD[s]), opens[s], day)
                    trades.append({'day': day, 'side': 'sell', 'symbol': s, 'qty': qty})
        if target in opens and book.settled > 1.0:        # buy with settled cash (T+1 after a switch)
            fill = opens[target] * (1 + HALF_SPREAD[target]) * (1 + p.slippage)
            qty = book.settled / fill
            book.buy(target, qty, fill, opens[target], day)
            trades.append({'day': day, 'side': 'buy', 'symbol': target, 'qty': qty})
        if i + 1 == len(days) or days[i + 1][:4] != day[:4]:
            book.year_end_tax(p.st_tax, p.lt_tax)
        curve.append((day, book.value({s: panel.close[s][i] or 0.0 for s in panel.close})))
    liq = book.liquidation_tax({s: panel.close[s][-1] or 0.0 for s in panel.close}, days[-1], p.st_tax, p.lt_tax)
    months = list(holding_log.values())
    share = {s: round(months.count(s) / max(1, len(months)), 3) for s in symbols}
    return {'curve': curve, 'trades': trades, 'tax_paid': book.tax_paid, 'liquidation_tax': liq,
            'cost_paid': book.cost_paid, 'invested_share': 1.0, 'locked': False, 'latched_on': None,
            'holding_share': share, 'switches': sum(1 for a, b in zip(months, months[1:]) if a != b)}, start


def engine_sector_top3_12_1_ma10(panel, recipe, capital):
    sig = recipe['signal']
    symbols = [s for s in recipe['universe']['symbols'] if s in panel.close]
    far, skip, picks, months = sig['momentum_from_sessions'], sig['momentum_skip_sessions'], sig['picks'], sig['trend_filter_month_ends']
    p = Params(universe=tuple(symbols), capital=capital, guards=False)
    days = panel.days
    month_end = [k for k in range(len(days) - 1) if days[k][:7] != days[k + 1][:7]]

    def closes_before(s, i):
        return [(k, panel.close[s][k]) for k in range(i) if panel.present[s][k]]

    def score(s, i):
        c = closes_before(s, i)
        if len(c) < 253:
            return None
        mom = c[-1 - skip][1] / c[-1 - far][1] - 1
        ends = [panel.close[s][k] for k in month_end if k < i and panel.present[s][k]][-months:]
        ma = sum(ends) / len(ends) if len(ends) == months else None
        return mom, (ma is not None and c[-1][1] > ma)
    vti = panel.present.get('VTI')
    ready = []
    for s in symbols:   # first index with 253 completed closes before it
        seen, at = 0, None
        for k, ok in enumerate(panel.present[s]):
            if seen >= 253:
                at = k; break
            seen += 1 if ok else 0
        if at is not None:
            ready.append(at)
    start = sorted(ready)[picks - 1]
    if vti:
        start = max(start, next(i for i, ok in enumerate(vti) if ok))
    book, curve, trades, targets, slots = Book(settled=capital), [], [], {}, []
    for i in range(start, len(days)):
        day = days[i]
        book.settled += book.unsettled; book.unsettled = 0.0
        opens = {s: panel.open[s][i] for s in symbols if panel.present[s][i] and panel.open[s][i]}
        if i == start or day[:7] != days[i - 1][:7]:
            scored = {s: score(s, i) for s in symbols}
            ranked = sorted((s for s, v in scored.items() if v is not None), key=lambda s: (-scored[s][0], s))[:picks]
            chosen = [s for s in ranked if scored[s][1] and s in opens]
            slots.append(len(chosen))
            equity = book.settled + sum(book.qty(s) * (opens.get(s) or panel.close[s][i - 1] or 0.0) for s in book.lots)
            targets = {s: equity * sig_weight for s, sig_weight in ((s, recipe['sizing']['per_slot']) for s in chosen)}
            for s in sorted(list(book.lots)):
                if not book.lots[s] or s not in opens:
                    continue
                excess = book.qty(s) * opens[s] - targets.get(s, 0.0)
                if s not in targets or excess > max(1.0, 0.01 * equity):
                    qty = book.qty(s) if s not in targets else excess / opens[s]
                    book.sell_qty(s, qty, opens[s] * (1 - HALF_SPREAD[s]), opens[s], day)
                    trades.append({'day': day, 'side': 'sell', 'symbol': s, 'qty': qty})
        equity_now = book.settled + book.unsettled + sum(book.qty(s) * (opens.get(s) or 0.0) for s in book.lots)
        for s, target in sorted(targets.items()):
            if s not in opens:
                continue
            short = target - book.qty(s) * opens[s]
            if short <= max(1.0, 0.01 * equity_now) or book.settled <= 1.0:
                continue
            fill = opens[s] * (1 + HALF_SPREAD[s]) * (1 + p.slippage)
            qty = min(short, book.settled) / fill
            book.buy(s, qty, fill, opens[s], day)
            trades.append({'day': day, 'side': 'buy', 'symbol': s, 'qty': qty})
        if i + 1 == len(days) or days[i + 1][:4] != day[:4]:
            book.year_end_tax(p.st_tax, p.lt_tax)
        curve.append((day, book.value({s: panel.close[s][i] or 0.0 for s in panel.close})))
    liq = book.liquidation_tax({s: panel.close[s][-1] or 0.0 for s in panel.close}, days[-1], p.st_tax, p.lt_tax)
    return {'curve': curve, 'trades': trades, 'tax_paid': book.tax_paid, 'liquidation_tax': liq,
            'cost_paid': book.cost_paid, 'invested_share': sum(slots) / max(1, picks * len(slots)), 'locked': False,
            'latched_on': None, 'slots_filled_share': {n: round(slots.count(n) / max(1, len(slots)), 3) for n in range(picks + 1)}}, start


def basket_buy_and_hold(panel, weights, start, capital):
    """Static basket bought once at the start (no rebalancing, so no tax until the end)."""
    parts = []
    for s, w in weights.items():
        part = buy_and_hold(panel, s, start, Params(capital=capital * w))
        parts.append(part)
    curve = [(d, sum(p['curve'][k][1] for p in parts)) for k, (d, _) in enumerate(parts[0]['curve'])]
    return {'curve': curve, 'trades': [], 'tax_paid': 0.0, 'liquidation_tax': sum(p['liquidation_tax'] for p in parts),
            'cost_paid': sum(p['cost_paid'] for p in parts), 'invested_share': 1.0, 'locked': False, 'latched_on': None}


def period_table(strategy, benchmarks, periods):
    out = {}
    for name, (lo, hi) in periods.items():
        row = {}
        for label, res in (('strategy', strategy), *benchmarks.items()):
            pts = [(d, v) for d, v in res['curve'] if lo <= d <= hi]
            if len(pts) > 20:
                yrs = (date.fromisoformat(pts[-1][0]) - date.fromisoformat(pts[0][0])).days / 365.25
                row[label] = round((pts[-1][1] / pts[0][1]) ** (1 / yrs) - 1, 4)
        out[name] = row
    return out


ENGINES = {'registered_rule': engine_registered_rule, 'dual_trend_vol_target': engine_dual_trend_vol_target,
           'gem_dual_momentum': engine_gem_dual_momentum, 'sector_top3_12_1_ma10': engine_sector_top3_12_1_ma10}


def _start(panel, feats, p):
    vti = panel.present.get('VTI')
    first_vti = next(i for i, ok in enumerate(vti) if ok) if vti else 0
    return max(first_decision_index(panel, feats, p), first_vti)


# ------------------------------------------------------------------ walk-forward + statistics
def monthly_folds(strategy, benchmark):
    """Out-of-sample monthly folds. Recipes have no fitted parameters, so every month is
    evaluated with rules frozen before the data existed (expanding-window walk-forward)."""
    b = dict(benchmark['curve'])
    rows = [(d, v, b[d]) for d, v in strategy['curve'] if d in b]
    folds, prev = [], None
    for d, v, bv in rows:
        if prev is None or d[:7] != prev[0][:7]:
            if prev is not None:
                folds.append(_fold(start_row, prev))
            start_row = prev or (d, v, bv)
        prev = (d, v, bv)
    if prev is not None:
        folds.append(_fold(start_row, prev))
    ex = [f['excess_log'] for f in folds]
    return {'folds': len(folds), 'share_positive': round(sum(1 for e in ex if e > 0) / max(1, len(ex)), 3),
            'mean_monthly_excess_log': round(sum(ex) / max(1, len(ex)), 5),
            'worst_month': min(folds, key=lambda f: f['excess_log']) if folds else None,
            'best_month': max(folds, key=lambda f: f['excess_log']) if folds else None,
            'by_year': _by_year(folds)}


def _fold(a, b):
    return {'month': b[0][:7], 'strategy': round(b[1] / a[1] - 1, 5), 'vti': round(b[2] / a[2] - 1, 5),
            'excess_log': round(math.log(b[1] / a[1]) - math.log(b[2] / a[2]), 5)}


def _by_year(folds):
    out = {}
    for f in folds:
        out.setdefault(f['month'][:4], 0.0)
        out[f['month'][:4]] += f['excess_log']
    return {y: round(v, 4) for y, v in out.items()}


def daily_excess(strategy, benchmark):
    b = dict(benchmark['curve'])
    pairs = [(v, b[d]) for d, v in strategy['curve'] if d in b]
    return [math.log(y1 / x1) - math.log(y2 / x2) for (x1, x2), (y1, y2) in zip(pairs, pairs[1:])]


def sharpe_moments(x):
    n = len(x)
    m = sum(x) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    if sd == 0:
        return 0.0, 0.0, 3.0, n
    skew = sum(((v - m) / sd) ** 3 for v in x) / n
    kurt = sum(((v - m) / sd) ** 4 for v in x) / n
    return m / sd, skew, kurt, n


def deflated_sharpe(sr, skew, kurt, n, trials, trial_sr_variance):
    """Bailey & López de Prado (2014). Daily (non-annualized) ratios. Returns the probability the
    true ratio exceeds the best-of-``trials`` expectation under no skill."""
    trials = max(1, trials)
    if trials == 1:
        sr0 = 0.0
    else:
        g = 0.5772156649
        v = trial_sr_variance if trial_sr_variance and trial_sr_variance > 0 else 1.0 / n
        sr0 = math.sqrt(v) * ((1 - g) * N.inv_cdf(1 - 1 / trials) + g * N.inv_cdf(1 - 1 / (trials * math.e)))
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    return {'probability': round(N.cdf((sr - sr0) * math.sqrt(n - 1) / denom), 4), 'benchmark_sr_daily': round(sr0, 5),
            'trials_counted': trials}


# ------------------------------------------------------------------ trial log
class TrialLog:
    def __init__(self, path, official=None):
        self.path = Path(path).resolve()
        if (self.path.parent / 'agent.db').exists() or (official and Path(official).resolve().parent == self.path.parent):
            raise HarnessError('TRIAL_LOG_MUST_NOT_SHARE_THE_OFFICIAL_DIRECTORY')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS trials (id INTEGER PRIMARY KEY, created_at TEXT, kind TEXT, '
                       'recipe_id TEXT, recipe_sha256 TEXT, code_commit TEXT, dataset_json TEXT, result_json TEXT, '
                       'status TEXT)')
            if not db.execute("SELECT 1 FROM trials WHERE kind='exploratory_prior' LIMIT 1").fetchone():
                for name in PRIOR_EXPLORATORY:
                    db.execute('INSERT INTO trials(created_at,kind,recipe_id,status,result_json) VALUES (?,?,?,?,?)',
                               ('2026-09-30T23:45:00+00:00', 'exploratory_prior', name, 'COUNTED_NOT_PROMOTABLE',
                                json.dumps({'note': 'looked at before the harness existed; counts as a trial'})))

    def connect(self):
        return sqlite3.connect(self.path, isolation_level=None)

    def count(self):
        with self.connect() as db:
            return db.execute('SELECT count(*) FROM trials').fetchone()[0]

    def daily_srs(self):
        with self.connect() as db:
            rows = db.execute("SELECT result_json FROM trials WHERE kind='harness_run'").fetchall()
        out = []
        for (r,) in rows:
            try:
                out.append(json.loads(r)['excess_vs_vti']['daily_information_ratio'])
            except (KeyError, TypeError, ValueError):
                continue
        return out

    def add(self, **row):
        with self.connect() as db:
            cur = db.execute('INSERT INTO trials(created_at,kind,recipe_id,recipe_sha256,code_commit,dataset_json,'
                             'result_json,status) VALUES (?,?,?,?,?,?,?,?)',
                             (datetime.now(timezone.utc).isoformat(), 'harness_run', row['recipe_id'], row['recipe_sha256'],
                              row['code_commit'], json.dumps(row['dataset']), json.dumps(row['result']), row['status']))
            return cur.lastrowid

    def rows(self):
        with self.connect() as db:
            return db.execute('SELECT id, created_at, kind, recipe_id, status, recipe_sha256, dataset_json FROM trials ORDER BY id').fetchall()


def _commit():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parents[1]).stdout.strip()
    except Exception:
        return 'unknown'


# ------------------------------------------------------------------ run
def run(recipe_path, bars_path, log_path, capital=25000.0):
    recipe, recipe_sha = load_recipe(recipe_path)
    symbols = recipe['universe']['symbols']
    dataset, bars = fingerprint(bars_path, symbols, recipe.get('data_requirement', {}))
    if dataset['missing_symbols']:
        raise HarnessError(f"DATASET_MISSING_SYMBOLS: {dataset['missing_symbols']}")
    log = TrialLog(log_path)
    panel = Panel(bars, 'SPY' if 'SPY' in bars else 'VTI')
    engine = ENGINES[recipe['recipe']['engine']]
    strategy, start = engine(panel, recipe, capital)
    vti = buy_and_hold(panel, 'VTI', start, Params(capital=capital))
    excess = daily_excess(strategy, vti)
    sr, skew, kurt, n = sharpe_moments(excess)
    prior = log.daily_srs() + [sr]
    var = (sum((x - sum(prior) / len(prior)) ** 2 for x in prior) / (len(prior) - 1)) if len(prior) > 1 else None
    trials = log.count() + 1
    s, b = stats(strategy, capital), stats(vti, capital)
    boot = bootstrap_excess(strategy, vti)
    dsr = deflated_sharpe(sr, skew, kurt, n, trials, var)
    passed = dataset['label'].startswith('CERTIFIED') and boot['ci90'][0] > 0 and dsr['probability'] >= 0.95 \
        and s['cagr_after_all_tax'] > b['cagr_after_all_tax']
    verdict = 'PASS' if passed else 'NOT_PROVEN'
    extras = {}
    if 'holding_share' in strategy:
        share = strategy['holding_share']
        # Price-only data understates bond interest (~3%/yr) and EFA's extra dividend (~1.5%/yr vs VTI).
        bias = 0.03 * share.get('AGG', 0) + 0.015 * share.get('EFA', 0)
        extras.update(holding_share=share, switches=strategy['switches'], price_only_bias_estimate=round(bias, 4))
        if not passed and -bias <= boot['annual_excess_log_growth'] < 0:
            verdict = 'INCONCLUSIVE'
    sec = recipe.get('secondary_benchmark', '')
    benches = {'vti': vti}
    if sec and sec.startswith('buy_and_hold_60pct_VTI_40pct_EFA'):
        mix = basket_buy_and_hold(panel, {'VTI': 0.6, 'EFA': 0.4}, start, capital)
        benches['vti60_efa40'] = mix
        m = stats(mix, capital)
        extras['secondary_benchmark'] = {'name': sec, **{k: m[k] for k in ('cagr_after_all_tax', 'sharpe_rf0', 'max_drawdown')},
                                         'excess_vs_strategy': bootstrap_excess(strategy, mix)}
    for key in ('aim', 'stopping_rule'):
        if recipe.get(key):
            extras[key] = recipe[key]
    if 'slots_filled_share' in strategy:
        extras['slots_filled_share'] = strategy['slots_filled_share']
    if recipe.get('report_periods'):
        extras['periods_cagr_pre_tax'] = period_table(strategy, benches, recipe['report_periods'])
    result = {
        'recipe': {'id': recipe['recipe']['id'], 'version': recipe['recipe']['version'], 'sha256': recipe_sha},
        'capital': capital, 'start_session': panel.days[start], 'end_session': panel.days[-1],
        'strategy': {k: s[k] for k in ('cagr_after_all_tax', 'cagr_pre_liquidation', 'ann_vol', 'sharpe_rf0', 'max_drawdown',
                                       'trades', 'invested_share_of_days', 'tax_paid', 'cost_paid', 'drawdown_latch_on',
                                       'calendar_returns')},
        'vti': {k: b[k] for k in ('cagr_after_all_tax', 'cagr_pre_liquidation', 'ann_vol', 'sharpe_rf0', 'max_drawdown')},
        'excess_vs_vti': {**boot, 'daily_information_ratio': round(sr, 5),
                          'annualized_information_ratio': round(sr * math.sqrt(252), 3)},
        'walk_forward': monthly_folds(strategy, vti),
        'deflated_sharpe': dsr,
        'verdict': verdict,
        'pass_rule': 'certified dataset AND 90% interval of excess > 0 AND deflated Sharpe probability >= 0.95 '
                     'AND after-tax CAGR above VTI',
        'promotion': 'never automatic: a PASS only allows a shadow (Adventure) run; Official needs a signed amendment',
        **extras,
    }
    trial_id = log.add(recipe_id=recipe['recipe']['id'], recipe_sha256=recipe_sha, code_commit=_commit(),
                       dataset=dataset, result=result, status=result['verdict'])
    return {'trial_id': trial_id, 'dataset': dataset, **result}


def to_markdown(r):
    s, v, e, w, d = r['strategy'], r['vti'], r['excess_vs_vti'], r['walk_forward'], r['dataset']
    lines = [f"# Trial {r['trial_id']}: {r['recipe']['id']} v{r['recipe']['version']} — {r['verdict']}", '',
             f"Recipe sha256 `{r['recipe']['sha256']}`. Dataset `{d['bars_file']}` sha256 `{d['bars_sha256']}`, "
             f"{d['first_session']} → {d['last_session']} ({d['span_years']} years), label **{d['label']}**, {d['adjustment']}.", '',
             f"Window {r['start_session']} → {r['end_session']}, ${r['capital']:,.0f} start.", '',
             '| | Strategy | VTI |', '|---|---|---|',
             f"| CAGR after all tax | {s['cagr_after_all_tax']:.2%} | {v['cagr_after_all_tax']:.2%} |",
             f"| Volatility | {s['ann_vol']:.1%} | {v['ann_vol']:.1%} |",
             f"| Sharpe (rf 0) | {s['sharpe_rf0']} | {v['sharpe_rf0']} |",
             f"| Max drawdown | {s['max_drawdown']:.1%} | {v['max_drawdown']:.1%} |",
             f"| Trades | {s['trades']} | 1 |", '',
             f"Excess vs VTI (pre-tax): {e['annual_excess_log_growth']:+.2%}/yr, 90% interval {e['ci90'][0]:+.2%} to {e['ci90'][1]:+.2%}; "
             f"information ratio {e['annualized_information_ratio']}.", '',
             f"Walk-forward: {w['folds']} monthly out-of-sample folds, {w['share_positive']:.0%} beat VTI.", '',
             f"Deflated Sharpe: probability {r['deflated_sharpe']['probability']} after counting "
             f"{r['deflated_sharpe']['trials_counted']} trials.", '', f"**{r['verdict']}** — {r['pass_rule']}. {r['promotion']}.", '',
             '| Year | Excess log growth vs VTI |', '|---|---|']
    lines += [f'| {y} | {x:+.2%} |' for y, x in w['by_year'].items()]
    if 'holding_share' in r:
        lines += ['', f"Time held: {', '.join(f'{k} {v:.0%}' for k, v in r['holding_share'].items())}; {r['switches']} switches. "
                  f"Price-only bias estimate against the strategy: {r['price_only_bias_estimate']:.2%}/yr."]
    if 'secondary_benchmark' in r:
        sb = r['secondary_benchmark']
        lines += ['', f"Secondary benchmark ({sb['name']}): {sb['cagr_after_all_tax']:.2%}/yr after tax, Sharpe {sb['sharpe_rf0']}, "
                  f"max drawdown {sb['max_drawdown']:.1%}. Strategy excess over it: {sb['excess_vs_strategy']['annual_excess_log_growth']:+.2%}/yr "
                  f"(90% {sb['excess_vs_strategy']['ci90'][0]:+.2%} to {sb['excess_vs_strategy']['ci90'][1]:+.2%})."]
    if 'periods_cagr_pre_tax' in r:
        cols = sorted({k for row in r['periods_cagr_pre_tax'].values() for k in row})
        lines += ['', '| Period (pre-tax CAGR) | ' + ' | '.join(cols) + ' |', '|---' * (len(cols) + 1) + '|']
        lines += [f'| {n} | ' + ' | '.join(f"{row.get(c, 0):.2%}" for c in cols) + ' |' for n, row in r['periods_cagr_pre_tax'].items()]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--recipe', required=True); r.add_argument('--bars', required=True)
    r.add_argument('--log', required=True); r.add_argument('--out', required=True); r.add_argument('--md')
    r.add_argument('--capital', type=float, default=25000.0)
    lg = sub.add_parser('log'); lg.add_argument('--log', required=True)
    args = parser.parse_args(argv)
    if args.cmd == 'log':
        for row in TrialLog(args.log).rows():
            print(row[:6])
        return 0
    result = run(args.recipe, args.bars, args.log, args.capital)
    Path(args.out).write_text(json.dumps(result, indent=1))
    if args.md:
        Path(args.md).write_text(to_markdown(result))
    print(json.dumps({k: result[k] for k in ('trial_id', 'verdict')} | {'excess': result['excess_vs_vti']['annual_excess_log_growth'],
                      'ci90': result['excess_vs_vti']['ci90'], 'dsr': result['deflated_sharpe']['probability']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
