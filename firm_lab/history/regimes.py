"""Descriptive market environments. Segmentation of history only: no score, no classifier, no trading use.

Definitions are those of ``CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md`` §9. Each is computed from a daily close series of a
broad-market proxy and from dated policy-rate decisions, using nothing later than the session being described where
the definition is a running one (volatility quantiles use an expanding window).
"""
from __future__ import annotations

import numpy as np

BEAR, CORRECTION = 0.20, 0.10
VOL_WINDOW, VOL_MINIMUM_HISTORY = 20, 252


def drawdowns(sessions, closes, threshold=CORRECTION) -> list:
    """Declines of at least ``threshold`` from a running high of the series to the lowest close before that high is
    regained. [{'peak', 'trough', 'recovered' or None, 'depth', 'kind'}] in order. One event per high: a rally inside a
    long decline does not start a second one. A description made with hindsight, not a signal."""
    closes = np.asarray(closes, float)
    out = []
    if not len(closes):
        return out
    peak = trough = 0

    def close_event(recovered):
        depth = 1 - closes[trough] / closes[peak]
        if depth >= threshold:
            out.append({'peak': sessions[peak], 'trough': sessions[trough], 'recovered': recovered, 'depth': round(float(depth), 4),
                        'kind': 'BEAR' if depth >= BEAR else 'CORRECTION'})

    for k in range(1, len(closes)):
        if closes[k] > closes[peak]:
            close_event(sessions[k])
            peak = trough = k
        elif closes[k] < closes[trough]:
            trough = k
    close_event(None)
    return out


def volatility_classes(closes) -> np.ndarray:
    """Per session: +1 when 20-session realized volatility is in the top fifth of its own history up to that session,
    -1 in the bottom fifth, 0 otherwise, NaN before a year of history exists."""
    closes = np.asarray(closes, float)
    out = np.full(len(closes), np.nan)
    if len(closes) <= VOL_WINDOW:
        return out
    logs = np.diff(np.log(closes))
    vol = np.full(len(closes), np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(logs, VOL_WINDOW)
    vol[VOL_WINDOW:] = windows.std(axis=1, ddof=1)
    for t in range(VOL_MINIMUM_HISTORY, len(closes)):
        past = vol[VOL_WINDOW:t + 1]
        past = past[np.isfinite(past)]
        if len(past) < VOL_MINIMUM_HISTORY - VOL_WINDOW:
            continue
        low, high = np.quantile(past, [0.2, 0.8])
        out[t] = 1.0 if vol[t] >= high else -1.0 if vol[t] <= low else 0.0
    return out


def episodes(sessions, flags) -> list:
    """Maximal runs of True in ``flags`` as [first session, last session]."""
    out, start = [], None
    for k, flag in enumerate(flags):
        if flag and start is None:
            start = k
        if not flag and start is not None:
            out.append([sessions[start], sessions[k - 1]])
            start = None
    if start is not None:
        out.append([sessions[start], sessions[-1]])
    return out


def rate_periods(decisions) -> dict:
    """{'rising': [[first, last], ...], 'falling': [...]} from dated target changes [(date, change in percentage points)].
    A period runs from the first move of a direction to the last move before the direction changes."""
    out, run = {'rising': [], 'falling': []}, None
    for day, change in sorted(decisions):
        if not change:
            continue
        kind = 'rising' if change > 0 else 'falling'
        if run and run[0] == kind:
            run[2] = day
        else:
            if run:
                out[run[0]].append([run[1], run[2]])
            run = [kind, day, day]
    if run:
        out[run[0]].append([run[1], run[2]])
    return out


def coverage(sessions, closes, decisions=(), *, first=None, last=None) -> dict:
    """What a period [first, last] of the proxy series contains. Counts and dated lists; nothing is ranked or scored."""
    sessions = list(sessions)
    lo = 0 if first is None else next((k for k, s in enumerate(sessions) if s >= first), len(sessions))
    hi = len(sessions) if last is None else next((k for k, s in enumerate(sessions) if s > last), len(sessions))
    found = [d for d in drawdowns(sessions, closes) if d['peak'] < (sessions[hi - 1] if hi else '') and d['trough'] >= (sessions[lo] if lo < len(sessions) else '9')]
    vol = volatility_classes(closes)
    high = episodes(sessions[lo:hi], vol[lo:hi] == 1.0)
    low = episodes(sessions[lo:hi], vol[lo:hi] == -1.0)
    rates = rate_periods(decisions)
    inside = lambda spans: [p for p in spans if (last is None or p[0] <= last) and (first is None or p[1] >= first)]
    bears, corrections = [d for d in found if d['kind'] == 'BEAR'], [d for d in found if d['kind'] == 'CORRECTION']
    in_decline = np.zeros(len(sessions), bool)
    slot = {s: k for k, s in enumerate(sessions)}
    for d in found:
        in_decline[slot[d['peak']] + 1:slot[d['trough']] + 1] = True
    return {'first': sessions[lo] if lo < hi else None, 'last': sessions[hi - 1] if lo < hi else None, 'sessions': hi - lo,
            'bear_markets': bears, 'corrections': corrections, 'bull_sessions': int((~in_decline[lo:hi]).sum()), 'decline_sessions': int(in_decline[lo:hi].sum()),
            'high_volatility_episodes': len(high), 'high_volatility_sessions': int((vol[lo:hi] == 1.0).sum()),
            'low_volatility_episodes': len(low), 'low_volatility_sessions': int((vol[lo:hi] == -1.0).sum()),
            'rising_rate_periods': inside(rates['rising']), 'falling_rate_periods': inside(rates['falling']),
            'rate_decisions_supplied': len(list(decisions)), 'descriptive_only': True}
