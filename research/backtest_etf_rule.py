"""Honest backtest of the registered desk ETF rule (research only; never trades).

Replicates the live v1.5 desk policy as closely as daily bars allow:

* Signal: among reviewed ETFs with >= 253 completed closes, close above the
  200-session average and positive 126-session momentum, pick the single highest
  momentum (ties by symbol). Features use completed sessions only (through t-1).
* Execution: at the next session's open (the 10:00 ET run proxy) paying half the
  assumed spread plus the paper broker's 0.1% slippage on buys; sells at the bid.
* Sizing (live RiskEngine): notional = equity * min(25%, 10% * 20% / vol20),
  minus what is already held in that ETF, capped by settled cash; one entry per
  day; at most 5 open positions; minimum $1 notional; fractional shares.
* Exit (v1.5.1): sell the whole position when its close is at or below the
  200-session average or 126-session momentum is not positive.
* Settlement T+1, FIFO tax lots, 35% short-term / 15% long-term tax on net
  realized gains each calendar year with loss carry-forward, liquidation tax at
  the end for every strategy and benchmark.
* Registered breakers (as live): no buys on a day down >= 3% or a week down
  >= 5%, and a permanent buy latch once drawdown from peak reaches 10% (the live
  ``peak_breaker_latched`` has no automatic reset). Exits still run.

Data: split-adjusted price-only daily bars (no dividends) from
``research.history_backfill``. Dividends are missing for the strategy and every
benchmark alike; high-yield holdings (TLT, XLU, XLRE) are disadvantaged most.

    python -m research.backtest_etf_rule --bars bars.csv --out report.json [--md report.md]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta

ETF_UNIVERSE_V142 = ('GLD', 'QQQ', 'SOXX', 'SPY', 'TLT', 'VTI', 'XLE', 'XLU')
SECTOR_ETFS_V15 = ('XLB', 'XLC', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLV', 'XLY')
ETF_UNIVERSE = tuple(sorted(ETF_UNIVERSE_V142 + SECTOR_ETFS_V15))
SPDR_SECTORS = ('XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY')
# Assumed half-spreads (fraction of price). Conservative for today's liquidity,
# optimistic for 2008. The live rule refuses entries above a 0.3% full spread.
HALF_SPREAD = defaultdict(lambda: 0.0005, {'SPY': 0.0001, 'QQQ': 0.0001, 'VTI': 0.0002, 'GLD': 0.0002, 'TLT': 0.0002})
REGIMES = {
    'GFC 2008-09 → 2009-03': ('2008-09-01', '2009-03-09'),
    'Q4 2018 selloff': ('2018-10-01', '2018-12-24'),
    'COVID crash 2020': ('2020-02-19', '2020-03-23'),
    'COVID rebound 2020': ('2020-03-24', '2020-12-31'),
    'Rate shock 2022': ('2022-01-03', '2022-12-30'),
    'Mega-cap grind 2023-25': ('2023-01-03', '2025-12-31'),
}


@dataclass(frozen=True)
class Params:
    universe: tuple = ETF_UNIVERSE
    lookback: int = 126
    trend: int = 200
    warmup: int = 253
    top_n: int = 1
    target_fraction: float = 0.10
    target_vol: float = 0.20
    max_fraction: float = 0.25
    max_positions: int = 5
    min_notional: float = 1.0
    slippage: float = 0.001
    st_tax: float = 0.35
    lt_tax: float = 0.15
    guards: bool = True
    capital: float = 500.0
    full_invest: bool = False   # economic test of the signal: 100% in the top pick, rotate on change
    latch_reset_drawdown: float | None = None   # draft v1.6.1: clear the 10% latch once drawdown <= this
    latch_rebase_sessions: int | None = None    # draft v1.6.1 option B: after N latched sessions, reset the peak to today


def load_bars(path):
    """Load bars. Robinhood daily bars begin at 00:00 UTC, which an ET conversion labels as the
    previous calendar day (sessions appear as Sun-Thu). Such files are shifted forward one day."""
    bars = defaultdict(dict)
    with open(path, newline='') as handle:
        rows = list(csv.DictReader(handle))
    sundays = sum(1 for r in rows if date.fromisoformat(r['day']).weekday() == 6)
    shift = sundays > len(rows) * 0.05
    for row in rows:
        close = float(row['close'])
        opened = float(row['open']) if row.get('open') not in (None, '', 'None') else None
        day = date.fromisoformat(row['day'])
        if shift:
            day += timedelta(days=1)
        bars[row['symbol']][day.isoformat()] = (opened, close)
    return bars, shift


class Panel:
    """Bars aligned to the master calendar (SPY sessions)."""

    def __init__(self, bars, calendar_symbol='SPY'):
        self.days = sorted(bars[calendar_symbol])
        self.symbols = sorted(bars)
        self.close, self.open, self.present = {}, {}, {}
        self.open_missing = 0
        for s in self.symbols:
            closes, opens, present, last = [], [], [], None
            for d in self.days:
                bar = bars[s].get(d)
                if bar is None:
                    closes.append(last); opens.append(None); present.append(False)
                else:
                    o, c = bar
                    if o is None:
                        self.open_missing += 1
                        o = c
                    closes.append(c); opens.append(o); present.append(True); last = c
            self.close[s], self.open[s], self.present[s] = closes, opens, present

    def features(self, lookback, trend, warmup):
        """Per symbol, per day index i: features from closes through i-1 (completed sessions)."""
        out = {}
        for s in self.symbols:
            closes = self.close[s]
            valid = [c for c in closes]
            ma, mom, vol, count = [None] * len(closes), [None] * len(closes), [None] * len(closes), [0] * len(closes)
            seen, window_sum, logs = [], 0.0, []
            for i in range(len(closes)):
                # state reflects closes[0..i-1]
                n = len(seen)
                count[i] = n
                if n >= trend:
                    ma[i] = window_sum / trend
                if n > lookback:
                    mom[i] = seen[-1] / seen[-lookback - 1] - 1
                if n >= 21:
                    rets = logs[-20:]
                    mean = sum(rets) / 20
                    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / 19)
                    vol[i] = sd * math.sqrt(252) if sd > 0 else None
                if self.present[s][i] and valid[i] is not None:
                    if seen:
                        logs.append(math.log(valid[i] / seen[-1]))
                    seen.append(valid[i])
                    window_sum += valid[i]
                    if len(seen) > trend:
                        window_sum -= seen[-trend - 1]
            out[s] = {'ma': ma, 'mom': mom, 'vol': vol, 'count': count}
        return out


@dataclass
class Lot:
    qty: float
    cost: float
    day: str


@dataclass
class Book:
    settled: float
    unsettled: float = 0.0
    lots: dict = field(default_factory=lambda: defaultdict(list))
    realized_st: float = 0.0
    realized_lt: float = 0.0
    carry_loss: float = 0.0
    tax_paid: float = 0.0
    cost_paid: float = 0.0

    def qty(self, s):
        return sum(l.qty for l in self.lots.get(s, []))

    def value(self, prices):
        return self.settled + self.unsettled + sum(self.qty(s) * prices[s] for s in self.lots if self.lots[s])

    def buy(self, s, qty, price, mark, day):
        self.settled -= qty * price
        self.cost_paid += qty * (price - mark)
        self.lots[s].append(Lot(qty, price, day))

    def sell_all(self, s, price, mark, day):
        proceeds = 0.0
        for lot in self.lots.pop(s, []):
            gain = lot.qty * (price - lot.cost)
            held = (date.fromisoformat(day) - date.fromisoformat(lot.day)).days
            if held > 365:
                self.realized_lt += gain
            else:
                self.realized_st += gain
            proceeds += lot.qty * price
            self.cost_paid += lot.qty * (mark - price)
        self.unsettled += proceeds
        return proceeds

    def sell_qty(self, s, qty, price, mark, day):
        """FIFO partial sale."""
        remaining, lots = qty, self.lots.get(s, [])
        while remaining > 1e-12 and lots:
            lot = lots[0]
            take = min(lot.qty, remaining)
            gain = take * (price - lot.cost)
            held = (date.fromisoformat(day) - date.fromisoformat(lot.day)).days
            if held > 365:
                self.realized_lt += gain
            else:
                self.realized_st += gain
            self.unsettled += take * price
            self.cost_paid += take * (mark - price)
            lot.qty -= take
            remaining -= take
            if lot.qty <= 1e-12:
                lots.pop(0)

    def year_end_tax(self, st, lt):
        net_st, net_lt = self.realized_st, self.realized_lt
        # Carry-forward loss offsets short-term first, then long-term.
        loss = self.carry_loss
        take = min(loss, max(0.0, net_st)); net_st -= take; loss -= take
        take = min(loss, max(0.0, net_lt)); net_lt -= take; loss -= take
        if net_st < 0 and net_lt > 0:
            take = min(-net_st, net_lt); net_lt -= take; net_st += take
        if net_lt < 0 and net_st > 0:
            take = min(-net_lt, net_st); net_st -= take; net_lt += take
        loss += -min(0.0, net_st) + -min(0.0, net_lt)
        tax = max(0.0, net_st) * st + max(0.0, net_lt) * lt
        self.settled -= tax
        self.tax_paid += tax
        self.carry_loss, self.realized_st, self.realized_lt = loss, 0.0, 0.0
        return tax

    def liquidation_tax(self, prices, day, st, lt):
        """Tax if everything were sold at ``prices`` on ``day`` (no costs)."""
        shadow = Book(settled=0.0, realized_st=self.realized_st, realized_lt=self.realized_lt, carry_loss=self.carry_loss)
        shadow.lots = defaultdict(list, {s: [Lot(l.qty, l.cost, l.day) for l in ls] for s, ls in self.lots.items()})
        for s in list(shadow.lots):
            shadow.sell_all(s, prices[s], prices[s], day)
        return shadow.year_end_tax(st, lt)


def simulate(panel, p: Params, feats=None, start_index=None):
    feats = feats or panel.features(p.lookback, p.trend, p.warmup)
    universe = [s for s in p.universe if s in panel.close]
    days = panel.days
    start = start_index if start_index is not None else first_decision_index(panel, feats, p)
    book = Book(settled=p.capital)
    curve, trades, peak, locked, prev_equity = [], [], p.capital, False, p.capital
    latched_on, week, week_start, latched_days = None, None, p.capital, 0
    invested_days = 0
    for i in range(start, len(days)):
        day = days[i]
        book.settled += book.unsettled; book.unsettled = 0.0          # T+1 settlement
        marks = {s: (panel.open[s][i] if panel.open[s][i] is not None else panel.close[s][i]) for s in universe}
        equity_open = book.value({s: (marks[s] or 0.0) for s in universe})
        qualifying = []
        for s in universe:
            f = feats[s]
            if f['count'][i] < p.warmup or f['ma'][i] is None or f['mom'][i] is None:
                continue
            last = panel.close[s][i - 1]
            if last is not None and last > f['ma'][i] and f['mom'][i] > 0:
                qualifying.append((-f['mom'][i], s))
        qualifying.sort()
        picks = [s for _, s in qualifying[:p.top_n]]
        # Exits (registered v1.5.1 rule), or rotation for the economic full-invest test.
        for s in sorted(list(book.lots)):
            if not book.lots[s] or not panel.present[s][i]:
                continue
            f = feats[s]
            last = panel.close[s][i - 1]
            broken = f['ma'][i] is not None and (last <= f['ma'][i] or (f['mom'][i] is not None and f['mom'][i] <= 0))
            if broken or (p.full_invest and s not in picks):
                mark = marks[s]
                qty = book.qty(s)
                book.sell_all(s, mark * (1 - HALF_SPREAD[s]), mark, day)
                trades.append({'day': day, 'side': 'sell', 'symbol': s, 'qty': qty, 'price': mark,
                               'reason': 'exit_rule' if broken else 'rotation'})
        drawdown = 1 - equity_open / peak if peak > 0 else 0
        day_loss = 1 - equity_open / prev_equity if prev_equity > 0 else 0
        iso_week = date.fromisoformat(day).isocalendar()[:2]
        if iso_week != week:
            week, week_start = iso_week, prev_equity
        weekly_loss = 1 - equity_open / week_start if week_start > 0 else 0
        if locked and p.latch_reset_drawdown is not None and drawdown <= p.latch_reset_drawdown:
            locked = False            # draft v1.6.1 reset (research only)
        if locked and p.latch_rebase_sessions is not None and latched_days >= p.latch_rebase_sessions:
            locked, peak, drawdown, latched_days = False, equity_open, 0.0, 0   # option B: new high-water mark
        latched_days = latched_days + 1 if locked else 0
        if p.guards and drawdown >= 0.10 and not locked:
            # Live: peak_breaker_latched is set at a 10% drawdown and nothing clears it.
            locked, latched_on = True, day
        blocked = p.guards and (locked or day_loss >= 0.03 or weekly_loss >= 0.05)
        if picks and not blocked:
            if p.full_invest:
                targets = [(s, None) for s in picks]
            else:
                targets = [(picks[0], None)]    # one Lane A entry per day
            for s, _ in targets:
                if not panel.present[s][i]:
                    continue
                mark = marks[s]
                vol = feats[s]['vol'][i]
                if mark is None or vol is None:
                    continue
                held_value = book.qty(s) * mark
                open_positions = sum(1 for k, v in book.lots.items() if v)
                if held_value == 0 and open_positions >= p.max_positions:
                    continue
                if p.full_invest:
                    want = equity_open / len(picks) - held_value
                else:
                    want = equity_open * min(p.max_fraction, p.target_fraction * p.target_vol / vol) - held_value
                fill = mark * (1 + HALF_SPREAD[s]) * (1 + p.slippage)
                budget = min(book.settled, want)
                qty = math.floor(budget / fill * 1e6) / 1e6
                if qty * fill < p.min_notional:
                    continue
                book.buy(s, qty, fill, mark, day)
                trades.append({'day': day, 'side': 'buy', 'symbol': s, 'qty': qty, 'price': mark, 'reason': 'entry'})
        closes = {s: (panel.close[s][i] or 0.0) for s in universe}
        if i + 1 == len(days) or days[i + 1][:4] != day[:4]:
            book.year_end_tax(p.st_tax, p.lt_tax)
        equity = book.value(closes)
        if any(book.lots.values()):
            invested_days += 1
        curve.append((day, equity))
        peak, prev_equity = max(peak, equity), equity
    final_prices = {s: (panel.close[s][-1] or 0.0) for s in universe}
    liq = book.liquidation_tax(final_prices, days[-1], p.st_tax, p.lt_tax)
    return {'curve': curve, 'trades': trades, 'tax_paid': book.tax_paid, 'liquidation_tax': liq,
            'cost_paid': book.cost_paid, 'invested_share': invested_days / max(1, len(curve)),
            'locked': locked, 'latched_on': latched_on}


def first_decision_index(panel, feats, p):
    for i in range(len(panel.days)):
        if any(feats[s]['count'][i] >= p.warmup for s in p.universe if s in feats):
            return i
    raise ValueError('not enough history for any ETF')


def buy_and_hold(panel, symbol, start, p: Params):
    days = panel.days
    mark = panel.open[symbol][start]
    fill = mark * (1 + HALF_SPREAD[symbol]) * (1 + p.slippage)
    qty = p.capital / fill
    curve = [(days[i], qty * panel.close[symbol][i]) for i in range(start, len(days))]
    gain = qty * (panel.close[symbol][-1] - fill)
    held = (date.fromisoformat(days[-1]) - date.fromisoformat(days[start])).days
    liq = max(0.0, gain) * (p.lt_tax if held > 365 else p.st_tax)
    return {'curve': curve, 'trades': [{'day': days[start], 'side': 'buy', 'symbol': symbol}], 'tax_paid': 0.0,
            'liquidation_tax': liq, 'cost_paid': qty * (fill - mark), 'invested_share': 1.0, 'locked': False,
            'latched_on': None}


def equal_weight(panel, symbols, start, p: Params):
    """Monthly rebalance to equal weight across whichever symbols have bars; trades only the
    differences (FIFO lots, same costs and tax as every other line)."""
    book = Book(settled=p.capital)
    curve = []
    days = panel.days
    for i in range(start, len(days)):
        day = days[i]
        book.settled += book.unsettled; book.unsettled = 0.0
        live = [s for s in symbols if s in panel.close and panel.present[s][i] and panel.open[s][i]]
        if i == start or day[:7] != days[i - 1][:7]:
            prices = {s: panel.open[s][i] for s in live}
            equity = book.settled + sum(book.qty(s) * prices.get(s, panel.close[s][i] or 0.0) for s in book.lots)
            target = equity / max(1, len(live))
            for s in list(book.lots):
                if s not in prices and book.lots[s]:
                    continue
                excess = book.qty(s) * prices[s] - target if s in prices else 0.0
                if excess > 1e-9:
                    book.sell_qty(s, excess / prices[s], prices[s] * (1 - HALF_SPREAD[s]), prices[s], day)
            book.settled += book.unsettled; book.unsettled = 0.0      # same-day proceeds for a rebalance
            for s in live:
                short = target - book.qty(s) * prices[s]
                fill = prices[s] * (1 + HALF_SPREAD[s]) * (1 + p.slippage)
                qty = min(short, book.settled) / fill
                if qty * fill > 1e-9:
                    book.buy(s, qty, fill, prices[s], day)
        if i + 1 == len(days) or days[i + 1][:4] != day[:4]:
            book.year_end_tax(p.st_tax, p.lt_tax)
        curve.append((day, book.value({s: panel.close[s][i] or 0.0 for s in panel.close})))
    liq = book.liquidation_tax({s: panel.close[s][-1] or 0.0 for s in panel.close}, days[-1], p.st_tax, p.lt_tax)
    return {'curve': curve, 'trades': [], 'tax_paid': book.tax_paid, 'liquidation_tax': liq,
            'cost_paid': book.cost_paid, 'invested_share': 1.0, 'locked': False, 'latched_on': None}


def stats(result, capital):
    curve = result['curve']
    values = [v for _, v in curve]
    years = (date.fromisoformat(curve[-1][0]) - date.fromisoformat(curve[0][0])).days / 365.25
    end_after_tax = values[-1] - result['liquidation_tax']
    rets = [b / a - 1 for a, b in zip(values, values[1:]) if a > 0]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    peak, mdd = values[0], 0.0
    for v in values:
        peak = max(peak, v); mdd = max(mdd, 1 - v / peak)
    by_year = {}
    for (d, v), (_, prev) in zip(curve[1:], curve[:-1]):
        by_year.setdefault(d[:4], [prev, v])[1] = v
    return {
        'start': curve[0][0], 'end': curve[-1][0], 'years': round(years, 2),
        'end_value': round(values[-1], 2), 'end_value_after_tax': round(end_after_tax, 2),
        'cagr_pre_liquidation': round((values[-1] / capital) ** (1 / years) - 1, 4),
        'cagr_after_all_tax': round((end_after_tax / capital) ** (1 / years) - 1, 4),
        'ann_vol': round(sd * math.sqrt(252), 4),
        'sharpe_rf0': round(mean / sd * math.sqrt(252), 3) if sd > 0 else None,
        'max_drawdown': round(mdd, 4),
        'trades': len(result['trades']),
        'invested_share_of_days': round(result['invested_share'], 3),
        'tax_paid': round(result['tax_paid'], 2), 'liquidation_tax': round(result['liquidation_tax'], 2),
        'cost_paid': round(result['cost_paid'], 2),
        'calendar_returns': {y: round(b / a - 1, 4) for y, (a, b) in sorted(by_year.items())},
        'buy_lock_triggered': result['locked'],
        'drawdown_latch_on': result.get('latched_on'),
    }


def aligned_returns(a, b):
    bv = dict(b['curve'])
    pairs = [(v, bv[d]) for d, v in a['curve'] if d in bv]
    ra = [y / x - 1 for (x, _), (y, _) in zip(pairs, pairs[1:])]
    rb = [y / x - 1 for (_, x), (_, y) in zip(pairs, pairs[1:])]
    return ra, rb


def bootstrap_excess(a, b, *, block=21, draws=2000, seed=7):
    """Stationary-block bootstrap CI for annualized excess log growth of a over b."""
    ra, rb = aligned_returns(a, b)
    diff = [math.log1p(x) - math.log1p(y) for x, y in zip(ra, rb)]
    n = len(diff)
    point = sum(diff) / n * 252
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        total, taken = 0.0, 0
        while taken < n:
            j = rng.randrange(n)
            length = min(block, n - taken)
            for k in range(length):
                total += diff[(j + k) % n]
            taken += length
        samples.append(total / n * 252)
    samples.sort()
    return {'annual_excess_log_growth': round(point, 4),
            'ci90': [round(samples[int(0.05 * draws)], 4), round(samples[int(0.95 * draws)], 4)],
            'share_of_draws_above_zero': round(sum(1 for s in samples if s > 0) / draws, 3),
            'block_days': block, 'draws': draws, 'note': 'pre-tax daily equity, so tax timing is excluded'}


def regime_table(results, keys):
    table = {}
    for name, (lo, hi) in REGIMES.items():
        row = {}
        for key in keys:
            pts = [(d, v) for d, v in results[key]['curve'] if lo <= d <= hi]
            if len(pts) > 5:
                row[key] = round(pts[-1][1] / pts[0][1] - 1, 4)
        if row:
            table[name] = row
    return table


def run(bars_path, capital=500.0):
    bars, shifted = load_bars(bars_path)
    panel = Panel(bars)
    base = Params(capital=capital)
    feats = panel.features(base.lookback, base.trend, base.warmup)
    start = max(first_decision_index(panel, feats, base),
                next(i for i, _ in enumerate(panel.days) if panel.present.get('VTI', [False] * len(panel.days))[i]))
    results = {
        'registered_rule': simulate(panel, base, feats, start),
        'registered_rule_no_guards': simulate(panel, replace(base, guards=False), feats, start),
        'registered_rule_v142_8etfs': simulate(panel, replace(base, universe=ETF_UNIVERSE_V142), feats, start),
        'signal_full_invest_top1': simulate(panel, replace(base, full_invest=True, guards=False), feats, start),
        'signal_full_invest_top3': simulate(panel, replace(base, full_invest=True, guards=False, top_n=3), feats, start),
        'vti_buy_hold': buy_and_hold(panel, 'VTI', start, base),
        'spy_buy_hold': buy_and_hold(panel, 'SPY', start, base),
        'equal_weight_spdr_sectors': equal_weight(panel, SPDR_SECTORS, start, base),
    }
    cash_curve = [(d, capital) for d in panel.days[start:]]
    results['cash'] = {'curve': cash_curve, 'trades': [], 'tax_paid': 0.0, 'liquidation_tax': 0.0,
                       'cost_paid': 0.0, 'invested_share': 0.0, 'locked': False, 'latched_on': None}
    summary = {k: stats(v, capital) for k, v in results.items() if k != 'cash'}
    summary['cash'] = {'cagr_after_all_tax': 0.0, 'note': 'Paper cash earns nothing; a T-bill would have earned ~1.5%/yr on average.'}
    sensitivity = {}
    for lookback in (63, 126, 252):
        for trend in (100, 150, 200):
            p = replace(base, lookback=lookback, trend=trend, full_invest=True, guards=False)
            f = panel.features(lookback, trend, base.warmup)
            s = stats(simulate(panel, p, f, start), capital)
            sensitivity[f'mom{lookback}_ma{trend}'] = {k: s[k] for k in ('cagr_after_all_tax', 'sharpe_rf0', 'max_drawdown', 'trades')}
    coverage = {s: {'first_day': next((d for d, ok in zip(panel.days, panel.present[s]) if ok), None),
                    'sessions': sum(panel.present[s])} for s in panel.symbols}
    report = {
        'what': 'Backtest of the registered v1.5 desk ETF rule vs VTI, SPY, equal-weight SPDR sectors and cash',
        'data': {'source': 'Robinhood read gateway via research.history_backfill (split-adjusted, price only, no dividends)',
                 'bars_sha256': hashlib.sha256(open(bars_path, 'rb').read()).hexdigest(),
                 'sessions': len(panel.days), 'first_session': panel.days[0], 'last_session': panel.days[-1],
                 'opens_missing_used_close': panel.open_missing,
                 'session_labels_shifted_plus_one_day': shifted, 'coverage': coverage,
                 'survivorship': 'ETF list is today\'s reviewed list; funds that closed are absent.'},
        'assumptions': {'capital': capital, 'half_spread': {**{k: v for k, v in HALF_SPREAD.items()}, 'default': 0.0005},
                        'slippage_on_buys': base.slippage, 'execution': 'next session open after the signal close',
                        'tax': {'short_term': base.st_tax, 'long_term': base.lt_tax},
                        'ai_cost': 'not included; the ETF rule uses no AI. $0.40/day would be ~$100/yr, i.e. 20%/yr of a $500 book.'},
        'summary': summary,
        'excess_vs_vti': {k: bootstrap_excess(results[k], results['vti_buy_hold'])
                          for k in ('registered_rule', 'signal_full_invest_top1', 'signal_full_invest_top3', 'equal_weight_spdr_sectors')},
        'regimes': regime_table(results, ['registered_rule', 'signal_full_invest_top1', 'vti_buy_hold', 'equal_weight_spdr_sectors']),
        'sensitivity_full_invest': sensitivity,
        'recent_trades_registered': results['registered_rule']['trades'][-12:],
    }
    report['verdict'] = verdict(report)
    return report


def verdict(report):
    s = report['summary']
    rule, vti = s['registered_rule'], s['vti_buy_hold']
    sig = s['signal_full_invest_top1']
    ci = report['excess_vs_vti']['signal_full_invest_top1']['ci90']
    lines = [
        f"Registered rule (as sized live): {rule['cagr_after_all_tax']:.1%}/yr after tax vs VTI {vti['cagr_after_all_tax']:.1%}/yr; "
        f"max drawdown {rule['max_drawdown']:.0%} vs {vti['max_drawdown']:.0%}; invested on {rule['invested_share_of_days']:.0%} of days.",
        f"Signal alone (100% in the top pick): {sig['cagr_after_all_tax']:.1%}/yr after tax, Sharpe {sig['sharpe_rf0']} vs VTI {vti['sharpe_rf0']}; "
        f"90% interval for annual excess over VTI (pre-tax): {ci[0]:+.1%} to {ci[1]:+.1%}.",
    ]
    free = s['registered_rule_no_guards']
    if rule.get('drawdown_latch_on'):
        lines.append(f"The registered 10% drawdown breaker latched on {rule['drawdown_latch_on']} and never reset, so the book "
                     f"stopped buying for good. Without breakers the same sizing made {free['cagr_after_all_tax']:.1%}/yr "
                     f"(Sharpe {free['sharpe_rf0']}, max drawdown {free['max_drawdown']:.0%}): lower risk, lower return, no edge.")
    beats = rule['cagr_after_all_tax'] > vti['cagr_after_all_tax'] and ci[0] > 0
    lines.append('PASS: evidence of an edge over VTI after costs and tax.' if beats else
                 'NOT PROVEN: the rule does not clearly beat buy-and-hold VTI after costs and tax. '
                 'Do not add AI, options or capital on the strength of this rule.')
    return lines


def to_markdown(report):
    out = ['# ETF rule backtest', '', '## Verdict', ''] + [f'- {l}' for l in report['verdict']]
    d = report['data']
    out += ['', f"Data: {d['first_session']} → {d['last_session']} ({d['sessions']} sessions), {d['source']}. "
            f"{d['survivorship']}", '', '## Results ($%s start)' % report['assumptions']['capital'], '',
            '| Strategy | CAGR after all tax | CAGR pre-liquidation | Sharpe | Max DD | Trades | Invested days | Tax | Costs |',
            '|---|---|---|---|---|---|---|---|---|']
    for k, s in report['summary'].items():
        if 'sharpe_rf0' not in s:
            continue
        out.append(f"| {k} | {s['cagr_after_all_tax']:.2%} | {s['cagr_pre_liquidation']:.2%} | {s['sharpe_rf0']} | "
                   f"{s['max_drawdown']:.1%} | {s['trades']} | {s['invested_share_of_days']:.0%} | ${s['tax_paid']:.2f} | ${s['cost_paid']:.2f} |")
    out += ['', '## Excess over VTI (block bootstrap, pre-tax)', '', '| Strategy | Annual excess | 90% interval | Draws > 0 |', '|---|---|---|---|']
    for k, e in report['excess_vs_vti'].items():
        out.append(f"| {k} | {e['annual_excess_log_growth']:+.2%} | {e['ci90'][0]:+.2%} to {e['ci90'][1]:+.2%} | {e['share_of_draws_above_zero']:.0%} |")
    out += ['', '## Regimes (total return in window)', '']
    keys = sorted({k for row in report['regimes'].values() for k in row})
    out += ['| Window | ' + ' | '.join(keys) + ' |', '|---' * (len(keys) + 1) + '|']
    for name, row in report['regimes'].items():
        out.append(f'| {name} | ' + ' | '.join(f"{row[k]:+.1%}" if k in row else '–' for k in keys) + ' |')
    out += ['', '## Parameter sensitivity (signal alone, full invest)', '', '| Setting | CAGR after tax | Sharpe | Max DD | Trades |', '|---|---|---|---|---|']
    for k, s in report['sensitivity_full_invest'].items():
        out.append(f"| {k} | {s['cagr_after_all_tax']:.2%} | {s['sharpe_rf0']} | {s['max_drawdown']:.1%} | {s['trades']} |")
    years = sorted({y for s in report['summary'].values() for y in s.get('calendar_returns', {})})
    cols = ['registered_rule', 'signal_full_invest_top1', 'vti_buy_hold']
    out += ['', '## Calendar years', '', '| Year | ' + ' | '.join(cols) + ' |', '|---' * (len(cols) + 1) + '|']
    for y in years:
        out.append(f'| {y} | ' + ' | '.join(f"{report['summary'][c]['calendar_returns'].get(y, 0):+.1%}" for c in cols) + ' |')
    a = report['assumptions']
    out += ['', '## Assumptions', '', f"- Execution: {a['execution']}; buys pay half-spread + {a['slippage_on_buys']:.1%} slippage; sells at the bid.",
            f"- Tax: {a['tax']['short_term']:.0%} short-term / {a['tax']['long_term']:.0%} long-term on net realized gains yearly, loss carry-forward, liquidation tax at the end for every line.",
            '- Prices are split-adjusted without dividends for every line, so absolute returns are understated by roughly 1.5–2%/yr for equity funds and more for TLT/XLU/XLRE.',
            f"- AI: {a['ai_cost']}", '- Equal-weight sectors rebalance monthly and pay the same costs and tax.']
    return '\n'.join(out) + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--bars', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--md')
    parser.add_argument('--capital', type=float, default=500.0)
    args = parser.parse_args(argv)
    report = run(args.bars, args.capital)
    with open(args.out, 'w') as handle:
        json.dump(report, handle, indent=1)
    if args.md:
        with open(args.md, 'w') as handle:
            handle.write(to_markdown(report))
    print('\n'.join(report['verdict']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
