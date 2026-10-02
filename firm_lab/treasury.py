"""The 13-week Treasury-bill accrual index and the fixed 70/30 ruler, as the frozen methodology defines them
(docs/firm_lab/treasury_bill_total_return_methodology.md, construction A).

Pure arithmetic over stored auction records and stored VTI closes. No network, no file is read here, and nothing in
this module is read by a ranking, a selection or an execution path: the result is a ruler only.

Where the methodology leaves a detail open, the reading used here is written down in
docs/firm_lab/treasury_index_implementation_note.md and nowhere silently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from .sessions import ET

SIX = Decimal('0.000001')
HUNDRED = Decimal(100)
TERM_MIN_DAYS, TERM_MAX_DAYS = 80, 100                 # methodology section 11
KNOWN_AT_CLOCK = time(17, 0)                           # methodology section 10: 5:00 p.m. New York time on the auction date
MAX_SESSION_GAP_DAYS = 4                               # a longer hole between stored VTI sessions means sessions are missing
WEIGHT_VTI, WEIGHT_BILL = Decimal('0.70'), Decimal('0.30')
SECURITY_TYPE, SECURITY_TERM = 'Bill', '13-Week'
OK, DATA_GAP = 'OK', 'DATA_GAP'
PRECISION = 40                                         # far more than the twelve decimal places the methodology asks for

PRICE_FORMULA_MISMATCH = 'PRICE_FORMULA_MISMATCH'
TERM_OUT_OF_RANGE = 'TERM_OUT_OF_RANGE'
ISSUE_NOT_BEFORE_MATURITY = 'ISSUE_NOT_BEFORE_MATURITY'
UNPARSEABLE_DATE = 'UNPARSEABLE_DATE'
UNPARSEABLE_NUMBER = 'UNPARSEABLE_NUMBER'
KNOWN_AT_RULE_MISMATCH = 'KNOWN_AT_RULE_MISMATCH'
NOT_A_13_WEEK_BILL = 'NOT_A_13_WEEK_BILL'
RECORDS_DISAGREE = 'RECORDS_DISAGREE'
AMBIGUOUS_ISSUE_DATE = 'AMBIGUOUS_ISSUE_DATE'
NO_AUCTION_RECORD = 'NO_AUCTION_RECORD'
VTI_SESSION_GAP = 'VTI_SESSION_GAP'
INDEX_NOT_AVAILABLE = 'INDEX_NOT_AVAILABLE'


def q6(value: Decimal) -> Decimal:
    """Six decimals, for storage and display."""
    return value.quantize(SIX, rounding=ROUND_HALF_UP)


def result_known_at(auction_date) -> datetime:
    """When an auction result counts as known: 5:00 p.m. New York time on the auction date, as a UTC instant."""
    day = auction_date if isinstance(auction_date, date) else date.fromisoformat(str(auction_date))
    return datetime.combine(day, KNOWN_AT_CLOCK, ET).astimezone(timezone.utc)


def official_price(rate_percent: Decimal, days: int) -> Decimal:
    """31 CFR 356, Appendix B: P = 100 x (1 - d x r / 360), before rounding. ``rate_percent`` is the discount rate in percent."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return HUNDRED * (1 - (Decimal(rate_percent) / HUNDRED) * Decimal(days) / Decimal(360))


def price_rounding(price: Decimal, rate_percent: Decimal, days: int):
    """How the published price equals the official formula at six decimals: 'half_up', 'down' (truncated), or None when it
    does not. Both are "the formula rounded to six decimals"; anything else is a mismatch."""
    exact = official_price(rate_percent, days)
    if price == exact.quantize(SIX, rounding=ROUND_HALF_UP):
        return 'half_up'
    if price == exact.quantize(SIX, rounding=ROUND_DOWN):
        return 'down'
    return None


def _date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def check_record(record) -> list:
    """Why a published auction record cannot be used, as (code, detail) pairs. An empty list means it can."""
    out = []
    if record.get('security_type') != SECURITY_TYPE or record.get('security_term') != SECURITY_TERM:
        out.append((NOT_A_13_WEEK_BILL, f'{record.get("security_type")!r} {record.get("security_term")!r}'))
    auction, issue, maturity = (_date(record.get(k)) for k in ('auction_date', 'issue_date', 'maturity_date'))
    for name, value in (('auction_date', auction), ('issue_date', issue), ('maturity_date', maturity)):
        if value is None:
            out.append((UNPARSEABLE_DATE, f'{name}={record.get(name)!r}'))
    rate, price = _decimal(record.get('high_discount_rate')), _decimal(record.get('price_per100'))
    for name, value in (('high_discount_rate', rate), ('price_per100', price)):
        if value is None:
            out.append((UNPARSEABLE_NUMBER, f'{name}={record.get(name)!r}'))
    if issue and maturity:
        days = (maturity - issue).days
        if days <= 0:
            out.append((ISSUE_NOT_BEFORE_MATURITY, f'issue {issue} maturity {maturity}'))
        elif not TERM_MIN_DAYS <= days <= TERM_MAX_DAYS:
            out.append((TERM_OUT_OF_RANGE, f'{days} days from issue to maturity; a 13-week bill has {TERM_MIN_DAYS}-{TERM_MAX_DAYS}'))
        elif rate is not None and price is not None and price_rounding(price, rate, days) is None:
            out.append((PRICE_FORMULA_MISMATCH, f'published {price}, formula gives {q6(official_price(rate, days))} for {rate}% over {days} days'))
    if auction and record.get('result_known_at') is not None:
        try:
            stated = datetime.fromisoformat(str(record['result_known_at']).replace('Z', '+00:00'))
        except ValueError:
            stated = None
        if stated is None or stated.tzinfo is None or stated != result_known_at(auction):
            out.append((KNOWN_AT_RULE_MISMATCH, f'result_known_at={record.get("result_known_at")!r} is not 17:00 New York time on {auction}'))
    return out


def check_records(records) -> list:
    """(index, code, detail) for every record that fails ``check_record``."""
    return [(i, code, detail) for i, r in enumerate(records) for code, detail in check_record(r)]


@dataclass(frozen=True)
class Bill:
    cusip: str
    auction_date: date
    issue: date
    maturity: date
    price: Decimal                      # purchase price per $100 of face value, as published
    rate: Decimal                       # high discount rate in percent, as published
    known_at: datetime                  # the later of the 5:00 p.m. rule and the moment Firm Lab ingested the record

    def value(self, day: date) -> Decimal:
        """Methodology section 7: straight-line accretion from the purchase price to par, in actual calendar days."""
        with localcontext() as ctx:
            ctx.prec = PRECISION
            return self.price + (HUNDRED - self.price) * Decimal((day - self.issue).days) / Decimal((self.maturity - self.issue).days)


def bills_from_rows(rows, as_of: datetime):
    """Stored auction rows -> (usable bills by issue date, unusable issue dates with the reason).

    A row is one stored version of a published record. Rows for the same auction (CUSIP and auction date) that differ in
    any economic field make that auction unusable. A record not yet known at ``as_of`` is left out as if it did not exist."""
    groups = {}
    for row in rows:
        groups.setdefault((row.get('cusip'), row.get('auction_date')), []).append(row)
    bills, unusable = {}, {}
    for (cusip, _), versions in sorted(groups.items(), key=lambda item: (str(item[0][1]), str(item[0][0]))):
        economic = {(v.get('issue_date'), v.get('maturity_date'), str(_decimal(v.get('high_discount_rate'))), str(_decimal(v.get('price_per100'))))
                    for v in versions}
        first = versions[0]
        ingested = min(datetime.fromisoformat(str(v['ingested_at'])) for v in versions)
        rule = result_known_at(first['auction_date']) if _date(first.get('auction_date')) else ingested
        known = max(rule, ingested)
        if known > as_of:
            continue
        issues = {_date(v.get('issue_date')) for v in versions} - {None}
        problems = [code for code, _ in check_record(first)]
        if len(economic) > 1:
            problems = [RECORDS_DISAGREE]
        if problems:
            for issue in issues:
                unusable[issue] = ', '.join(sorted(set(problems)))
            continue
        issue = _date(first['issue_date'])
        if issue in bills or issue in unusable:
            other = bills.pop(issue, None)
            unusable[issue] = AMBIGUOUS_ISSUE_DATE + (f' ({other.cusip} and {cusip})' if other else '')
            continue
        bills[issue] = Bill(str(cusip), _date(first['auction_date']), issue, _date(first['maturity_date']), _decimal(first['price_per100']),
                            _decimal(first['high_discount_rate']), known)
    return bills, unusable


@dataclass
class IndexResult:
    values: dict = field(default_factory=dict)            # calendar day -> index level (unrounded Decimal)
    holdings: dict = field(default_factory=dict)          # calendar day -> CUSIP held, or 'UNINVESTED'
    known_at: dict = field(default_factory=dict)          # calendar day -> latest known-at among the bills used so far
    rolls: list = field(default_factory=list)             # (day, CUSIP, purchase price)
    uninvested_days: list = field(default_factory=list)
    status: str = OK
    gap_date: date = None
    gap_reason: str = ''


def accrual_index(bills, unusable, start: date, end: date, start_value: Decimal = HUNDRED) -> IndexResult:
    """I(start) = start_value; one bill at a time, bought at its auction price on its issue date, held to maturity, rolled
    the same day into the bill issued that day. With no bill issued that day the money earns nothing until the next
    13-week issue date. The series stops (DATA_GAP) on the first day it needs a bill that is missing or unusable."""
    out = IndexResult()
    every = sorted(set(bills) | set(unusable))

    def stop(day, reason):
        out.status, out.gap_date, out.gap_reason = DATA_GAP, day, reason
        return out

    earlier = [d for d in every if d <= start]
    if not earlier:
        return stop(start, f'{NO_AUCTION_RECORD}: no 13-week bill issued on or before {start} is stored')
    if earlier[-1] in unusable:
        return stop(start, f'the bill issued {earlier[-1]} is needed and cannot be used: {unusable[earlier[-1]]}')
    with localcontext() as ctx:
        ctx.prec = PRECISION
        bill, units, cash, known = bills[earlier[-1]], None, None, None
        if bill.maturity > start:
            units, known = Decimal(start_value) / bill.value(start), bill.known_at          # entered at its accrued value (section 13)
            out.rolls.append((start, bill.cusip, bill.value(start)))
        else:
            cash, bill = Decimal(start_value), None                                         # the latest bill has already matured
        day = start
        while day <= end:
            if bill is not None and day >= bill.maturity:
                cash, bill, units = units * HUNDRED, None, None                             # redeemed at par
            if bill is None:
                if day in unusable:
                    return stop(day, f'the bill issued {day} is needed and cannot be used: {unusable[day]}')
                if day in bills and bills[day].maturity > day:
                    bill = bills[day]
                    units = cash / bill.price                                               # all proceeds, at the auction price
                    known = bill.known_at if known is None else max(known, bill.known_at)
                    out.rolls.append((day, bill.cusip, bill.price))
                elif not any(d > day for d in every):
                    return stop(day, f'{NO_AUCTION_RECORD}: no 13-week bill issued on or after {day} is stored')
                else:
                    out.uninvested_days.append(day)                                         # earns nothing until the next issue date
            out.values[day] = units * bill.value(day) if bill is not None else cash
            out.holdings[day] = bill.cusip if bill is not None else 'UNINVESTED'
            out.known_at[day] = known
            day += timedelta(days=1)
    return out


@dataclass
class RulerResult:
    values: dict = field(default_factory=dict)            # session date -> 70/30 level (unrounded Decimal)
    rebalances: list = field(default_factory=list)        # session dates on which the weights were reset
    status: str = OK
    gap_date: date = None
    gap_reason: str = ''


def fixed_70_30(sessions, index: dict, start_value: Decimal = HUNDRED) -> RulerResult:
    """70% VTI + 30% bill index, weights reset at the close of the first stored session of each calendar month.
    ``sessions`` is [(session date, VTI close)] in order. No settlement lag, no cost (methodology section 6)."""
    out = RulerResult()
    if not sessions:
        return out
    with localcontext() as ctx:
        ctx.prec = PRECISION
        first_day, first_close = sessions[0]
        if first_day not in index:
            out.status, out.gap_date, out.gap_reason = DATA_GAP, first_day, f'{INDEX_NOT_AVAILABLE}: the bill index has no value for {first_day}'
            return out
        vti_units = WEIGHT_VTI * Decimal(start_value) / Decimal(first_close)
        bill_units = WEIGHT_BILL * Decimal(start_value) / index[first_day]
        out.values[first_day] = Decimal(start_value)
        previous = first_day
        for day, close in sessions[1:]:
            if (day - previous).days > MAX_SESSION_GAP_DAYS:
                out.status, out.gap_date = DATA_GAP, day
                out.gap_reason = f'{VTI_SESSION_GAP}: no VTI session is stored between {previous} and {day}'
                return out
            if day not in index:
                out.status, out.gap_date, out.gap_reason = DATA_GAP, day, f'{INDEX_NOT_AVAILABLE}: the bill index has no value for {day}'
                return out
            level = vti_units * Decimal(close) + bill_units * index[day]
            out.values[day] = level
            if (day.year, day.month) != (previous.year, previous.month):                    # first stored session of a new month
                vti_units = WEIGHT_VTI * level / Decimal(close)
                bill_units = WEIGHT_BILL * level / index[day]
                out.rebalances.append(day)
            previous = day
    return out
