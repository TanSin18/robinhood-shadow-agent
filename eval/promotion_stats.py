"""Statistical promotion gate (pre-declared; replaces the 4-week / 30-decision checklist).

Pre-declared metric: annualized excess log growth of each paper arm over the
observed VTI price series, after the arm's own spreads (bid marks), AI costs and
an estimated short-term tax on gains, measured only on official runs
(on/after 2026-10-01 09:30 ET, live_readonly data). Build-phase runs never count.

A result may be called an edge only when ALL hold:
  * sample: at least 200 filled decisions, or at least 252 official sessions;
  * the 90% block-bootstrap interval of the annual excess lies entirely above 0;
  * every cost is included (bid marks, AI cost, estimated tax);
  * the metric above is unchanged since registration.
Anything else reads NOT PROVEN, with the reasons. It never unlocks live money:
that stays a separate human decision.
"""
from __future__ import annotations

import json
import math
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
OFFICIAL_FROM = datetime(2026, 10, 1, 9, 30, tzinfo=ET)
METRIC = 'annual_excess_log_growth_vs_vti_after_spread_ai_cost_and_estimated_short_term_tax'
MIN_DECISIONS = 200
MIN_SESSIONS = 252
SHORT_TERM_TAX = 0.35
ARMS = ('agent_alone', 'with_approvals', 'deterministic_no_ai')
AI_ARMS = ('agent_alone', 'with_approvals')


def _rows(db, table):
    try:
        return [json.loads(r[0]) for r in db.execute(f'SELECT payload_json FROM {table} ORDER BY id')]
    except sqlite3.Error:
        return []


def _official(ts):
    try:
        return datetime.fromisoformat(ts) >= OFFICIAL_FROM
    except (TypeError, ValueError):
        return False


def _day(ts):
    return datetime.fromisoformat(ts).astimezone(ET).date().isoformat()


def load(path):
    """Read-only view of the official database."""
    uri = f'file:{Path(path).resolve()}?mode=ro'
    with sqlite3.connect(uri, uri=True) as db:
        values, fills, costs = _rows(db, 'daily_values'), _rows(db, 'fills'), _rows(db, 'api_costs')
    series = {arm: {} for arm in ARMS}
    vti = {}
    for v in values:
        ts = v.get('timestamp')
        if not _official(ts) or v.get('data_mode') != 'live_readonly':
            continue
        if v.get('kind') == 'paper_valuation' and v.get('lane') == 'A' and v.get('track') in series \
                and v.get('value') is not None and 'comparison' not in v:
            series[v['track']][_day(ts)] = float(v['value'])
        elif v.get('benchmark') == 'VTI' and isinstance(v.get('close'), dict) and v['close'].get('date'):
            # Keyed by run day (like the arms); the close itself is the prior session's.
            vti[_day(ts)] = float(v['close'].get('price') or 0) or None
    decisions = {arm: 0 for arm in ARMS}
    for f in fills:
        track = str(f.get('track', ''))
        arm = track.split(':')[-1] if track else f.get('arm')
        if arm in decisions and f.get('status') == 'filled' and _official(f.get('timestamp')):
            decisions[arm] += 1
    ai_cost = {}
    for c in costs:
        if _official(c.get('timestamp')):
            try:
                ai_cost[_day(c['timestamp'])] = ai_cost.get(_day(c['timestamp']), 0.0) + float(c.get('cost_usd') or c.get('estimated_cost_usd') or 0)
            except (TypeError, ValueError):
                continue
    return {'series': series, 'vti': {d: p for d, p in vti.items() if p}, 'decisions': decisions, 'ai_cost': ai_cost}


def _net_curve(values, ai_cost, charge_ai):
    days = sorted(values)
    start = values[days[0]] if days else None
    spent, out = 0.0, []
    for d in days:
        if charge_ai:
            spent += ai_cost.get(d, 0.0)
        net = values[d] - spent
        gain = net - start
        out.append((d, start + gain * (1 - SHORT_TERM_TAX) if gain > 0 else net))
    return out


def bootstrap(diff, *, block=21, draws=2000, seed=11):
    n = len(diff)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        total, taken = 0.0, 0
        while taken < n:
            j = rng.randrange(n)
            k = min(block, n - taken)
            total += sum(diff[(j + i) % n] for i in range(k))
            taken += k
        samples.append(total / n * 252)
    samples.sort()
    return [samples[int(0.05 * draws)], samples[int(0.95 * draws)]]


def evaluate(data, *, registered_metric=METRIC):
    out = {'metric': METRIC, 'official_from': OFFICIAL_FROM.isoformat(),
           'rule': f'>= {MIN_DECISIONS} filled decisions or >= {MIN_SESSIONS} official sessions, '
                   '90% interval above zero, all costs in, metric unchanged', 'arms': {}}
    for arm in ARMS:
        curve = _net_curve(data['series'][arm], data['ai_cost'], arm in AI_ARMS)
        pairs = [(v, data['vti'][d]) for d, v in curve if d in data['vti']]
        diff = [math.log(b / a) - math.log(y / x) for (a, x), (b, y) in zip(pairs, pairs[1:]) if a > 0 and x > 0]
        sessions, decisions = len(pairs), data['decisions'][arm]
        reasons = []
        if decisions < MIN_DECISIONS and sessions < MIN_SESSIONS:
            reasons.append(f'SAMPLE_TOO_SMALL: {decisions}/{MIN_DECISIONS} decisions, {sessions}/{MIN_SESSIONS} sessions')
        if registered_metric != METRIC:
            reasons.append('METRIC_CHANGED')
        point = ci = None
        if len(diff) >= 20:
            point = sum(diff) / len(diff) * 252
            ci = bootstrap(diff)
            if ci[0] <= 0:
                reasons.append('INTERVAL_INCLUDES_ZERO_OR_BELOW')
        else:
            reasons.append('FEWER_THAN_20_COMPARABLE_SESSIONS')
        out['arms'][arm] = {'sessions': sessions, 'decisions': decisions,
                            'annual_excess': None if point is None else round(point, 4),
                            'ci90': None if ci is None else [round(c, 4) for c in ci],
                            'verdict': 'EDGE_SHOWN' if not reasons else 'NOT_PROVEN', 'reasons': reasons}
    out['unlocks_live_money'] = False
    return out


if __name__ == '__main__':
    import sys
    print(json.dumps(evaluate(load(sys.argv[1])), indent=1))
