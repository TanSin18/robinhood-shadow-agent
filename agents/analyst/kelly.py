"""Shadow Kelly sizing per ticker, conditioned on the current market regime.

Kelly (continuous form): f* = mean excess daily return / variance of daily return. It is only as
good as the edge estimate, so three numbers are shown:
  raw         f* from history (can be wildly large or negative),
  half        f* / 2, the usual practical fraction,
  disciplined half-Kelly, but 0 unless the edge is statistically distinguishable from zero
              (t-stat >= 2) over the whole history as well as inside the regime (regime labels are
              in-sample, so a regime-only t-stat is inflated), and never above the registered 25%
              position cap or below 0 (no shorts).
These are shown beside the size the risk engine actually uses: min(25%, 2% / realized vol).
Shadow only: nothing in the trading path reads them.
"""
from __future__ import annotations

import math

RISK_FREE_ANNUAL = 0.04          # assumed cash yield for the excess return (documented constant)
CAP = 0.25                       # registered max fraction of an account in one position
T_REQUIRED = 2.0


def _stats(rets):
    n = len(rets)
    if n < 30:
        return None
    m = sum(rets) / n
    v = sum((r - m) ** 2 for r in rets) / (n - 1)
    return n, m, v


def size(closes, regime_by_day=None, current=None):
    """closes: [(day, close)]. regime_by_day: {day: state name}. Returns a dict for one ticker."""
    rf = RISK_FREE_ANNUAL / 252
    rets = [((d1, c1 / c0 - 1.0 - rf)) for (d0, c0), (d1, c1) in zip(closes, closes[1:]) if c0 and c1 and c0 > 0]
    out = {'sessions': len(rets)}
    # realized vol over the last 20 sessions, as the risk engine sizes
    last20 = [math.log(c1 / c0) for (_, c0), (_, c1) in zip(closes[-21:], closes[-20:]) if c0 and c1 and c0 > 0]
    if len(last20) >= 19:
        mu = sum(last20) / len(last20)
        vol = math.sqrt(sum((r - mu) ** 2 for r in last20) / (len(last20) - 1)) * math.sqrt(252)
        out['vol20_annual'] = round(vol, 4)
        out['risk_engine_fraction'] = round(min(CAP, 0.10 * 0.20 / vol), 4) if vol > 0 else None
    for scope, sample in (('all', [r for _, r in rets]),
                          ('regime', [r for d, r in rets if regime_by_day and current and regime_by_day.get(d) == current])):
        st = _stats(sample)
        if not st:
            out[scope] = {'sessions': len(sample), 'status': 'TOO_FEW_SESSIONS'}
            continue
        n, m, v = st
        raw = m / v if v > 0 else 0.0
        t = m / math.sqrt(v / n) if v > 0 else 0.0
        half = raw / 2
        out[scope] = {'sessions': n, 'mean_excess_daily_pct': round(m * 100, 4), 'vol_daily_pct': round(math.sqrt(v) * 100, 4),
                      't_stat': round(t, 2), 'kelly_raw': round(raw, 3), 'kelly_half': round(half, 3),
                      'kelly_disciplined': round(max(0.0, min(CAP, half)) if t >= T_REQUIRED else 0.0, 4)}
    # A regime-only edge is not enough: in-sample HMM labels flatter it. Require the full-history edge too.
    if (out.get('all') or {}).get('t_stat', 0) < T_REQUIRED and 'kelly_disciplined' in (out.get('regime') or {}):
        out['regime']['kelly_disciplined'] = 0.0
        out['regime']['disciplined_note'] = 'full-history t-stat below 2'
    return out
