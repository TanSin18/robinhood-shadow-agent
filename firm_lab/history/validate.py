"""Row checks for a daily bar. A failing row is rejected with every reason that applies. Nothing is repaired.

A number is a plain decimal in ASCII digits, with an optional exponent: no plus sign, no separators, no spaces inside,
no other script's digits. A minus sign is read so that a negative value is named as what it is (and "-0" is negative).
Python would accept more than that; a price file should not need it.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

from . import calendar

REASONS = ('MISSING_FIELD', 'NOT_FINITE', 'NON_POSITIVE_PRICE', 'LOW_ABOVE_OPEN_OR_CLOSE', 'HIGH_BELOW_OPEN_OR_CLOSE', 'LOW_ABOVE_HIGH', 'NEGATIVE_VOLUME',
           'INVALID_TOTAL_RETURN_CLOSE', 'NOT_AN_EXCHANGE_SESSION', 'SESSION_NOT_COMPLETE_AT_CAPTURE', 'UNKNOWN_SECURITY', 'AMBIGUOUS_SECURITY', 'CONFLICTING_DUPLICATE',
           'CURRENCY_NOT_USD')
PRICES = ('open', 'high', 'low', 'close', 'close_unadjusted')
REQUIRED = ('session',) + PRICES + ('volume',)
NUMBER = re.compile(r'-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?', re.ASCII)
SESSION = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', re.ASCII)
SMALLEST_PRICE = 1e-6                     # below a ten-thousandth of a cent nothing is a price


def _number(text):
    if not isinstance(text, str) or not NUMBER.fullmatch(text):
        return None
    value = float(text)
    return value if math.isfinite(value) else None


def bar_reasons(row, *, captured_at=None) -> list:
    """Reasons this row is not a valid bar; empty when it is. ``captured_at`` is a UTC ISO timestamp (``store.utc_time``);
    without it the capture-time check is not made (a block is checked again when it is stored)."""
    reasons = []
    if any(row.get(k) in (None, '') for k in REQUIRED):
        reasons.append('MISSING_FIELD')
    numbers = {k: _number(row.get(k)) for k in PRICES + ('volume',) if row.get(k) not in (None, '')}
    if any(v is None for v in numbers.values()):
        reasons.append('NOT_FINITE')
    if any(numbers.get(k) is not None and numbers[k] < SMALLEST_PRICE for k in PRICES):
        reasons.append('NON_POSITIVE_PRICE')
    o, h, l, c = (numbers.get(k) for k in ('open', 'high', 'low', 'close'))
    if None not in (o, l, c) and l > min(o, c):
        reasons.append('LOW_ABOVE_OPEN_OR_CLOSE')
    if None not in (o, h, c) and h < max(o, c):
        reasons.append('HIGH_BELOW_OPEN_OR_CLOSE')
    if None not in (h, l) and l > h:
        reasons.append('LOW_ABOVE_HIGH')
    if numbers.get('volume') is not None and (numbers['volume'] < 0 or str(row.get('volume')).startswith('-')):
        reasons.append('NEGATIVE_VOLUME')
    total = row.get('close_total_return')
    if total not in (None, '') and (_number(total) is None or _number(total) < SMALLEST_PRICE):
        reasons.append('INVALID_TOTAL_RETURN_CLOSE')                    # the column is optional, but what is there must be a price
    session = row.get('session') or ''
    if session and (not isinstance(session, str) or not SESSION.fullmatch(session) or not calendar.is_session(session)):
        reasons.append('NOT_AN_EXCHANGE_SESSION')
    elif session and captured_at is not None and datetime.fromisoformat(calendar.session_close(session)) > datetime.fromisoformat(captured_at):
        reasons.append('SESSION_NOT_COMPLETE_AT_CAPTURE')
    return reasons


def block_reasons(columns) -> list:
    """Every reason any row of a stored block fails the row checks. The store refuses a block unless this is empty."""
    found = set()
    names = ('open', 'high', 'low', 'close', 'volume', 'close_unadjusted', 'close_total_return')
    for k, session in enumerate(columns['sessions']):
        found.update(bar_reasons({'session': session, **{name: columns[name][k] for name in names}}))
    return sorted(found)
