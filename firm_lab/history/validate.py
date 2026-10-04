"""Row checks for a daily bar. A failing row is rejected with every reason that applies. Nothing is repaired."""
from __future__ import annotations

import math

from . import calendar

REASONS = ('MISSING_FIELD', 'NOT_FINITE', 'NON_POSITIVE_PRICE', 'LOW_ABOVE_OPEN_OR_CLOSE', 'HIGH_BELOW_OPEN_OR_CLOSE', 'LOW_ABOVE_HIGH', 'NEGATIVE_VOLUME',
           'NOT_AN_EXCHANGE_SESSION', 'SESSION_NOT_COMPLETE_AT_CAPTURE', 'UNKNOWN_SECURITY', 'AMBIGUOUS_SECURITY', 'CONFLICTING_DUPLICATE', 'CURRENCY_NOT_USD')
PRICES = ('open', 'high', 'low', 'close', 'close_unadjusted')
REQUIRED = ('session',) + PRICES + ('volume',)


def _number(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def bar_reasons(row, *, captured_at) -> list:
    """Reasons this row is not a valid bar; empty when it is. ``captured_at`` is an ISO timestamp in UTC."""
    reasons = []
    if any(row.get(k) in (None, '') for k in REQUIRED):
        reasons.append('MISSING_FIELD')
    numbers = {k: _number(row.get(k)) for k in PRICES + ('volume',) if row.get(k) not in (None, '')}
    if any(v is None for v in numbers.values()):
        reasons.append('NOT_FINITE')
    if any(numbers.get(k) is not None and numbers[k] <= 0 for k in PRICES):
        reasons.append('NON_POSITIVE_PRICE')
    o, h, l, c = (numbers.get(k) for k in ('open', 'high', 'low', 'close'))
    if None not in (o, l, c) and l > min(o, c):
        reasons.append('LOW_ABOVE_OPEN_OR_CLOSE')
    if None not in (o, h, c) and h < max(o, c):
        reasons.append('HIGH_BELOW_OPEN_OR_CLOSE')
    if None not in (h, l) and l > h:
        reasons.append('LOW_ABOVE_HIGH')
    if numbers.get('volume') is not None and numbers['volume'] < 0:
        reasons.append('NEGATIVE_VOLUME')
    session = row.get('session') or ''
    if session and not calendar.is_session(session):
        reasons.append('NOT_AN_EXCHANGE_SESSION')
    elif session and calendar.session_close(session) > captured_at:
        reasons.append('SESSION_NOT_COMPLETE_AT_CAPTURE')
    return reasons
