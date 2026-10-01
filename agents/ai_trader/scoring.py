"""Scoreboard: books A/B/C against VTI, Official paper, the random control and cash.

After costs: spreads are already in the fills; the AI bill is charged to A and B; an estimated 35%
short-term tax is taken from any positive cumulative gain. Promotion language is only "A vs VTI with
the interval above zero"; if A does not also beat C the result is labelled LUCK_OR_BETA.
"""
from __future__ import annotations

import math
from decimal import Decimal

D = Decimal
TAX = D('0.35')
MIN_TRADES, MIN_SESSIONS = 200, 252


def _series(store, book):
    with store.connect() as db:
        rows = db.execute('SELECT day, value, api_cost_cum, vti, official FROM book_values WHERE book=? ORDER BY id', (book,)).fetchall()
    by_day = {}
    for r in rows:
        by_day[r['day']] = r       # last record of the day
    return by_day


def _after_cost(value, api, start):
    net = D(value) - D(api or 0)
    gain = net - start
    return net - max(D(0), gain) * TAX


def _boot(diff, block=10, draws=2000, seed=11):
    import random
    n = len(diff)
    rng = random.Random(seed)
    samples = []
    for _ in range(draws):
        total, taken = 0.0, 0
        while taken < n:
            j, k = rng.randrange(n), min(block, n - taken)
            total += sum(diff[(j + i) % n] for i in range(k))
            taken += k
        samples.append(total / n * 252)
    samples.sort()
    return round(samples[int(0.05 * draws)], 4), round(samples[int(0.95 * draws)], 4)


def compare(a, b, a_start, b_start, b_is_price=False):
    days = sorted(set(a) & set(b))
    if len(days) < 3:
        return {'sessions': len(days), 'status': 'INSUFFICIENT_DATA'}
    av = [float(_after_cost(a[d]['value'], a[d]['api_cost_cum'], a_start)) for d in days]
    bv = [float(b[d]) if b_is_price else float(_after_cost(b[d]['value'], b[d]['api_cost_cum'], b_start)) for d in days]
    diff = [math.log(av[i + 1] / av[i]) - math.log(bv[i + 1] / bv[i]) for i in range(len(days) - 1)]
    point = sum(diff) / len(diff) * 252
    ci = _boot(diff) if len(diff) >= 20 else None
    return {'sessions': len(days), 'annual_excess': round(point, 4), 'ci90': ci,
            'first': days[0], 'last': days[-1]}


def scoreboard(store, spec):
    books = {b: _series(store, b) for b in ('A', 'B', 'C')}
    start = spec.capital
    vti = {d: r['vti'] for d, r in books['A'].items() if r['vti'] is not None}
    official = {d: r['official'] for d, r in books['A'].items() if r['official'] is not None}
    a = store.book('A')
    out = {'spec': spec.id, 'closed_trades_A': a.closed_trades, 'ai_bill_usd': str(store.spent()), 'lines': {}}
    for name in ('A', 'B', 'C'):
        s = books[name]
        if not s:
            continue
        last = s[max(s)]
        out['lines'][name] = {
            'value_after_costs': str(_after_cost(last['value'], last['api_cost_cum'], start).quantize(D('0.01'))),
            'vs_vti': compare(s, vti, start, start, b_is_price=True),
            'vs_cash': {'excess_usd': str((_after_cost(last['value'], last['api_cost_cum'], start) - start).quantize(D('0.01')))},
        }
        if official:
            out['lines'][name]['vs_official'] = compare(s, official, start, start, b_is_price=True)
    if books['A'] and books['C']:
        out['A_vs_C'] = compare(books['A'], books['C'], start, start)
    av = out['lines'].get('A', {}).get('vs_vti', {})
    enough = a.closed_trades >= MIN_TRADES or av.get('sessions', 0) >= MIN_SESSIONS
    beats_vti = bool(av.get('ci90')) and av['ci90'][0] > 0
    beats_c = bool(out.get('A_vs_C', {}).get('ci90')) and out['A_vs_C']['ci90'][0] > 0
    out['verdict'] = ('PASS' if enough and beats_vti and beats_c else
                      'LUCK_OR_BETA' if enough and beats_vti else
                      'NOT_PROVEN' if enough else 'TOO_EARLY')
    out['rule'] = '200 closed trades or 252 sessions; A beats VTI with the 90% interval above zero, and beats random C'
    return out
