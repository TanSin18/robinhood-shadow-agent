"""Equity total return from stored closes and stored cash distributions. Pure arithmetic: no network, no file, and
nothing here is read by a ranking, a selection or an execution path.

Method (docs/firm_lab/vti_total_return_methodology.md):

  * The price series is the stored completed-session closes, as they are: split-adjusted by their provider, never
    dividend-adjusted. No vendor "adjusted close" and no vendor total-return index is used.
  * A cash distribution is reinvested at the close of its ex-dividend session:
        TR(t) = TR(t-1) x (P(t) + D(t)) / P(t-1)
    where D(t) is the sum of cash distributions whose ex-date is session t, per share on the same share basis as P.
  * The price-return index is 100 x P(t) / P(start). It is a separate series and is never overwritten.
  * A distribution is used only if it was known at the time of the computation, and every observation carries the
    later of its session close and the known-at of the distributions applied up to it.
  * Splits: when the stored closes are split-adjusted, a distribution paid before a later split is divided by that
    split's ratio so that it is on the same share basis as the closes.
  * It stops rather than guess: an ex-date that is not a stored session, a hole in the stored sessions, or a
    distribution in another currency ends the series there (DATA_GAP).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext

from .treasury import MAX_SESSION_GAP_DAYS, PRECISION, q6

OK, DATA_GAP = 'OK', 'DATA_GAP'
HUNDRED = Decimal(100)
EX_DATE_NOT_A_SESSION = 'EX_DATE_NOT_A_SESSION'
SESSION_GAP = 'SESSION_GAP'
CURRENCY_NOT_USD = 'CURRENCY_NOT_USD'
AMOUNT_NOT_POSITIVE = 'AMOUNT_NOT_POSITIVE'
MISSING_IN_INDEPENDENT = 'MISSING_IN_INDEPENDENT_SOURCE'
MISSING_IN_PRIMARY = 'MISSING_IN_PRIMARY_SOURCE'
AMOUNT_MISMATCH = 'AMOUNT_MISMATCH'
CADENCE_GAP = 'CADENCE_GAP'
NO_PRIMARY_RECORDS = 'NO_PRIMARY_RECORDS'
NO_INDEPENDENT_RECORDS = 'NO_INDEPENDENT_RECORDS'


@dataclass(frozen=True)
class Distribution:
    ex_date: date
    amount: Decimal                     # cash per share, as paid
    currency: str
    known_at: datetime                  # when Firm Lab could have known the amount
    kind: str = 'cash_dividend'


@dataclass(frozen=True)
class Split:
    effective_date: date
    ratio: Decimal                      # new shares for each old share (2 for a 2-for-1 split)


def per_adjusted_share(distribution: Distribution, splits, price_basis_date: date) -> Decimal:
    """The distribution on the share basis of closes that were split-adjusted as of ``price_basis_date``."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        amount = Decimal(distribution.amount)
        for split in splits:
            if distribution.ex_date < split.effective_date <= price_basis_date:
                amount = amount / Decimal(split.ratio)
        return amount


def compare_sources(primary, independent, start: date, end: date, *, max_gap_days: int = 110) -> list:
    """Why the primary (issuer) distribution history cannot be trusted over [start, end], as (code, detail) pairs.
    Every primary record must be matched, on ex-date and exact amount, by the independent source, and the
    independent source must hold nothing extra. A hole longer than ``max_gap_days`` between ex-dates (or between the
    window's ends and the nearest ex-date) is reported too: a missing quarter would otherwise go unnoticed."""
    mine = {}
    for d in primary:
        if start <= d.ex_date <= end:
            mine[d.ex_date] = mine.get(d.ex_date, Decimal(0)) + Decimal(d.amount)
    theirs = {}
    for d in independent:
        if start <= d.ex_date <= end:
            theirs[d.ex_date] = theirs.get(d.ex_date, Decimal(0)) + Decimal(d.amount)
    out = []
    if not primary:
        out.append((NO_PRIMARY_RECORDS, 'the issuer source returned no distribution'))
    if not independent:
        out.append((NO_INDEPENDENT_RECORDS, 'no independent source is stored to check the issuer against'))
    for day in sorted(set(mine) | set(theirs)):
        if day not in theirs:
            out.append((MISSING_IN_INDEPENDENT, f'{day}: {mine[day]} per share in the issuer source only'))
        elif day not in mine:
            out.append((MISSING_IN_PRIMARY, f'{day}: {theirs[day]} per share in the independent source only'))
        elif mine[day] != theirs[day]:
            out.append((AMOUNT_MISMATCH, f'{day}: issuer {mine[day]}, independent {theirs[day]}'))
    marks = [start] + sorted(mine) + [end]
    for a, b in zip(marks, marks[1:]):
        if (b - a).days > max_gap_days:
            out.append((CADENCE_GAP, f'no ex-date between {a} and {b} ({(b - a).days} days)'))
    return out


@dataclass
class TotalReturnResult:
    total_return: dict = field(default_factory=dict)      # session date -> index level (unrounded Decimal)
    price_return: dict = field(default_factory=dict)      # session date -> index level (unrounded Decimal)
    applied: list = field(default_factory=list)           # (ex-date, amount as paid, amount on the adjusted share basis)
    known_at: dict = field(default_factory=dict)          # session date -> latest known-at among the distributions applied so far
    status: str = OK
    gap_date: date = None
    gap_reason: str = ''


def total_return_index(sessions, distributions, splits=(), *, as_of: datetime, price_basis_date: date = None,
                       start_value: Decimal = HUNDRED) -> TotalReturnResult:
    """``sessions`` is [(session date, close)] in order. Returns both indices, base ``start_value`` on the first session."""
    out = TotalReturnResult()
    if not sessions:
        return out
    days = [d for d, _ in sessions]
    first, last = days[0], days[-1]
    basis = price_basis_date or last
    usable = [d for d in distributions if d.known_at <= as_of and first < d.ex_date <= last]
    by_day = {}
    for d in usable:
        by_day.setdefault(d.ex_date, []).append(d)

    def stop(day, reason):
        out.status, out.gap_date, out.gap_reason = DATA_GAP, day, reason
        return out

    session_set = set(days)
    with localcontext() as ctx:
        ctx.prec = PRECISION
        level = Decimal(start_value)
        out.total_return[first], out.price_return[first], out.known_at[first] = level, Decimal(start_value), None
        previous_day, previous_close, known = first, Decimal(sessions[0][1]), None
        for day, close in sessions[1:]:
            if (day - previous_day).days > MAX_SESSION_GAP_DAYS:
                return stop(day, f'{SESSION_GAP}: no session is stored between {previous_day} and {day}')
            skipped = sorted(x for x in by_day if previous_day < x < day and x not in session_set)
            if skipped:
                return stop(skipped[0], f'{EX_DATE_NOT_A_SESSION}: a distribution has ex-date {skipped[0]}, which is not a stored session')
            cash = Decimal(0)
            for d in by_day.get(day, ()):
                if str(d.currency).upper() != 'USD':
                    return stop(day, f'{CURRENCY_NOT_USD}: the distribution of {day} is in {d.currency!r}')
                if Decimal(d.amount) <= 0:
                    return stop(day, f'{AMOUNT_NOT_POSITIVE}: the distribution of {day} is {d.amount}')
                adjusted = per_adjusted_share(d, splits, basis)
                cash += adjusted
                out.applied.append((day, Decimal(d.amount), adjusted))
                known = d.known_at if known is None else max(known, d.known_at)
            close = Decimal(close)
            level = level * (close + cash) / previous_close
            out.total_return[day] = level
            out.price_return[day] = Decimal(start_value) * close / Decimal(sessions[0][1])
            out.known_at[day] = known
            previous_day, previous_close = day, close
    return out


__all__ = ['Distribution', 'Split', 'TotalReturnResult', 'compare_sources', 'per_adjusted_share', 'total_return_index', 'q6']
