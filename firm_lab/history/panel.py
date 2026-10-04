"""One security's stored bars as arrays on the exchange calendar.

Every exchange session between the first and the last stored bar has a slot; a session with no bar is NaN, so a window
that reaches across a missing session is visibly incomplete instead of silently shorter. Values are parsed from the
stored text; the text itself is kept for the rounding bounds used by the consistency audit.
"""
from __future__ import annotations

import numpy as np

from . import calendar

NUMERIC = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return')


def _decimals(text) -> int:
    text = str(text)
    if 'e' in text.lower() or '.' not in text:
        return 0
    return len(text.split('.', 1)[1])


def from_columns(columns) -> dict:
    """Arrays for one security from ``HistoryStore.bars``. Empty input gives an empty panel."""
    stored = list(columns['sessions'])
    if not stored:
        return {'sessions': (), 'present': np.zeros(0, bool), **{c: np.zeros(0) for c in NUMERIC}, 'half_ulp': np.zeros(0)}
    if stored != sorted(set(stored)):
        raise ValueError('BARS_NOT_IN_SESSION_ORDER')
    span = calendar.sessions(stored[0], stored[-1])
    slot = {s: k for k, s in enumerate(span)}
    out = {'sessions': span, 'present': np.zeros(len(span), bool)}
    index = np.array([slot[s] for s in stored])
    out['present'][index] = True
    for c in NUMERIC:
        values = np.full(len(span), np.nan)
        values[index] = [float(v) if v not in ('', None) else np.nan for v in columns[c]]
        out[c] = values
    # the largest relative error rounding can have put into unadjusted/adjusted: used only as a tolerance, never to change a value
    bound = np.full(len(span), np.nan)
    bound[index] = [0.5 * 10.0 ** -_decimals(c) / float(c) + 0.5 * 10.0 ** -_decimals(u) / float(u) for c, u in zip(columns['close'], columns['close_unadjusted'])]
    out['half_ulp'] = bound
    return out


def load(store, security_id, **kw) -> dict:
    columns = store.bars(security_id, **kw)
    out = from_columns(columns)
    out['blocks'] = columns['blocks']
    out['security_id'] = security_id
    return out


def first_session_on_or_after(panel, day):
    """Index of the first calendar slot of this panel on or after ``day``; None if it lies past the last bar."""
    sessions = panel['sessions']
    lo, hi = 0, len(sessions)
    while lo < hi:
        mid = (lo + hi) // 2
        if sessions[mid] < day:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(sessions) else None
