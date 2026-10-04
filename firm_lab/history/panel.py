"""One security's stored bars as arrays on the exchange calendar.

Every exchange session between the first and the last stored bar has a slot; a session with no bar is NaN, so a window
that reaches across a missing session is visibly incomplete instead of silently shorter. Values are parsed from the
stored text; the text itself is kept for the rounding bounds used by the consistency audit.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import numpy as np

from . import calendar

NUMERIC = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return')


def _decimals(text) -> int:
    """Digits after the decimal point in a printed number ("29.50" -> 2, "1e-05" -> 5, "29" -> 0)."""
    try:
        exponent = Decimal(str(text).strip()).as_tuple().exponent
    except InvalidOperation:
        raise ValueError('INVALID_STORED_BAR') from None
    return max(0, -exponent) if isinstance(exponent, int) else 0


def _places(texts) -> int:
    """The precision a column is printed at: the most decimals any of its values shows. A vendor that strips trailing
    zeros prints "29" for 29.00; the column, not the single value, says how finely the price was rounded."""
    return max((_decimals(t) for t in texts if t not in ('', None)), default=0)


def from_columns(columns) -> dict:
    """Arrays for one security from ``HistoryStore.bars``. Empty input gives an empty panel."""
    stored = list(columns['sessions'])
    if not stored:
        return {'sessions': (), 'present': np.zeros(0, bool), **{c: np.zeros(0) for c in NUMERIC}, 'half_ulp': np.zeros(0), 'print_error': np.zeros(0)}
    if stored != sorted(set(stored)):
        raise ValueError('BARS_NOT_IN_SESSION_ORDER')
    try:
        span = calendar.sessions(stored[0], stored[-1])
        slot = {s: k for k, s in enumerate(span)}
        index = np.array([slot[s] for s in stored])
    except KeyError:
        raise ValueError('INVALID_STORED_BAR') from None
    out = {'sessions': span, 'present': np.zeros(len(span), bool)}
    out['present'][index] = True
    for c in NUMERIC:
        values = np.full(len(span), np.nan)
        try:
            values[index] = [float(v) if v not in ('', None) else np.nan for v in columns[c]]
        except (TypeError, ValueError):
            raise ValueError('INVALID_STORED_BAR') from None
        out[c] = values
    if not (np.all(out['close'][index] > 0) and np.all(out['close_unadjusted'][index] > 0)):
        raise ValueError('INVALID_STORED_BAR')                          # ingestion rejects these; a stored block must not hold one
    # How coarsely the vendor printed each price, relative to the price. A tolerance and a report, never a correction.
    adjusted, printed = 0.5 * 10.0 ** -_places(columns['close']), 0.5 * 10.0 ** -_places(columns['close_unadjusted'])
    out['print_error'] = adjusted / out['close']
    out['half_ulp'] = out['print_error'] + printed / out['close_unadjusted']
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
