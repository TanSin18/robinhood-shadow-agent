"""Risk seat: code only. Size, caps, book stops and fills. No model can change any of this."""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

D = Decimal


def size(book, spec, marks, ask: Decimal, fraction: Decimal | None = None):
    """Quantity for a new name: at most max_fraction of book value (or a given fraction), within settled cash."""
    fill = ask * (1 + spec.slippage)
    value = book.value(marks)
    notional = min(value * (fraction if fraction is not None else spec.max_fraction), book.settled)
    if fraction is not None:
        notional = min(notional, value * spec.max_fraction)
    qty = (notional / fill).quantize(D('0.000001'), rounding=ROUND_DOWN)
    if qty * fill < D(1):
        return None, fill
    return qty, fill


def stops(book, value: Decimal, spec):
    daily = bool(book.day_start_value) and value <= book.day_start_value * (1 - spec.daily_stop)
    weekly = bool(book.week_start_value) and value <= book.week_start_value * (1 - spec.weekly_stop)
    return daily, weekly


def can_enter(book, spec, entries_today, value):
    daily, weekly = stops(book, value, spec)
    if weekly:
        return False, 'WEEKLY_LOSS_HIT'
    if daily:
        return False, 'DAILY_LOSS_HIT'
    if len(book.positions) >= spec.max_names:
        return False, 'MAX_NAMES'
    if entries_today >= spec.entries_per_day:
        return False, 'ENTRIES_PER_DAY'
    return True, None
