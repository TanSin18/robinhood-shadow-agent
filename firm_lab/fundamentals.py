"""A small, normalized set of company facts from SEC XBRL data. Raw and normalized facts only: no ratio, score, rank
or composite is computed from them, here or anywhere else.

Normalization fails closed. A normalized field is filled only by the explicit rules in ``RULES`` (written out in
docs/firm_lab/sec_xbrl_normalization.md). Anything else is left unresolved, with the reason: nothing is guessed,
derived or merged across concepts that could mean different things.

Point in time. A fact is known from the moment the SEC accepted the filing it appeared in (the filing-header time).
Every appearance of a fact in a filing is its own observation. When a later filing reports a different value for the
same period, that is a new version; the earlier observation is never changed, and ``as_of`` returns only what had
been accepted by the time asked about.

Pure functions: no network, no file.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

USD, USD_PER_SHARE, SHARES = 'USD', 'USD/shares', 'shares'
DURATION, INSTANT = 'duration', 'instant'
PERIODIC_FORMS = ('10-K', '10-Q', '10-K/A', '10-Q/A')
# Days from period start to period end, inclusive. 52/53-week fiscal calendars fall inside these ranges. The name says how long
# the period is and nothing more: a 12-month period is not assumed to be a fiscal year (some companies also report trailing
# twelve months in a quarterly report).
PERIOD_TYPES = (('3M', 80, 100), ('6M', 170, 190), ('9M', 260, 285), ('12M', 350, 380))
CURRENT, COMPARATIVE = 'current', 'comparative'

NOT_REPORTED = 'NOT_REPORTED_UNDER_A_MAPPED_CONCEPT'
CONFLICTING_CONCEPTS = 'CONFLICTING_CONCEPTS'
CONFLICTING_VALUES = 'CONFLICTING_VALUES'
UNEXPECTED_UNIT = 'UNEXPECTED_UNIT'
UNEXPECTED_PERIOD_KIND = 'UNEXPECTED_PERIOD_KIND'
UNCLASSIFIED_PERIOD = 'UNCLASSIFIED_PERIOD'
UNPARSEABLE_VALUE = 'UNPARSEABLE_VALUE'
BROADER_CONCEPT_NOT_MAPPED = 'BROADER_CONCEPT_NOT_MAPPED'
NEEDS_COMPONENT_RULE = 'NEEDS_COMPONENT_RULE'
LONG_TERM_DEBT_PART_MISSING = 'LONG_TERM_DEBT_PART_MISSING'
SHORT_TERM_DEBT_NOT_REPORTED = 'SHORT_TERM_DEBT_NOT_REPORTED'
DEBT_COMPONENTS_DO_NOT_RECONCILE = 'DEBT_COMPONENTS_DO_NOT_RECONCILE'
# Total debt from its parts (rule "components"). Borrowings only: lease liabilities are not debt here.
#   total = LongTermDebtCurrent + LongTermDebtNoncurrent + short-term borrowings
# The two long-term parts are both required and do not overlap (current maturities; the rest). Short-term borrowings are
# ShortTermBorrowings when reported, otherwise CommercialPaper when reported (commercial paper is a kind of short-term
# borrowing: the two are never added to each other). When neither is reported the short-term part is zero only if the
# company reports DebtCurrent equal to LongTermDebtCurrent, which says all current debt is the current maturities; in
# every other case absence is not read as zero and the field stays unresolved. LongTermDebt is not used: in real
# filings it need not equal the two parts (it may be stated before hedge adjustments or at face value).
DEBT_LONG_TERM_PARTS = ('LongTermDebtCurrent', 'LongTermDebtNoncurrent')
DEBT_SHORT_TERM = ('ShortTermBorrowings', 'CommercialPaper')
DEBT_CURRENT_TOTAL = 'DebtCurrent'
DEBT_COMPONENT_CONCEPTS = DEBT_LONG_TERM_PARTS + DEBT_SHORT_TERM + (DEBT_CURRENT_TOTAL,)


@dataclass(frozen=True)
class Rule:
    field: str
    accept: tuple                       # us-gaap concepts that mean this field; if several are reported for one period they must agree
    unit: str
    kind: str                           # duration or instant
    critical: bool = False              # the schema is not usable for a company if a critical field is unresolved
    alternates: tuple = ()              # related concepts that are NOT accepted; seeing one explains why the field is unresolved
    alternate_reason: str = NOT_REPORTED
    note: str = ''


RULES = (
    Rule('revenue', ('Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet'), USD, DURATION, critical=True,
         alternates=('RevenueFromContractWithCustomerIncludingAssessedTax', 'RevenuesNetOfInterestExpense'),
         note='Total revenue as the company reports it. If more than one accepted concept appears for a period, they must be equal.'),
    Rule('gross_profit', ('GrossProfit',), USD, DURATION,
         alternates=('CostOfRevenue', 'CostOfGoodsAndServicesSold'),
         note='Only when the company reports a gross profit line. It is never derived from revenue and cost of revenue.'),
    Rule('operating_income', ('OperatingIncomeLoss',), USD, DURATION, critical=True,
         note='Operating income or loss as reported.'),
    Rule('net_income', ('NetIncomeLoss',), USD, DURATION, critical=True,
         alternates=('ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic'),
         note='Net income attributable to the parent. Profit including non-controlling interests is a different figure and is not accepted.'),
    Rule('eps_diluted', ('EarningsPerShareDiluted',), USD_PER_SHARE, DURATION, critical=True,
         alternates=('EarningsPerShareBasicAndDiluted', 'EarningsPerShareBasic'),
         note='Diluted earnings per share as reported.'),
    Rule('operating_cash_flow', ('NetCashProvidedByUsedInOperatingActivities',), USD, DURATION, critical=True,
         alternates=('NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',),
         note='As reported. In a quarterly report the cash-flow statement covers the fiscal year to date; the period is kept as reported and '
              'is never turned into a single quarter.'),
    Rule('capital_expenditure', ('PaymentsToAcquirePropertyPlantAndEquipment',), USD, DURATION,
         alternates=('PaymentsToAcquireProductiveAssets', 'PaymentsToAcquireOtherPropertyPlantAndEquipment'),
         alternate_reason=BROADER_CONCEPT_NOT_MAPPED,
         note='Purchases of property, plant and equipment only. A broader line (for example one that also includes intangible assets) is '
              'not treated as the same thing.'),
    Rule('cash_and_equivalents', ('CashAndCashEquivalentsAtCarryingValue',), USD, INSTANT, critical=True,
         alternates=('CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents', 'CashAndCashEquivalentsFairValueDisclosure'),
         note='Cash and cash equivalents on the balance sheet. Totals that include restricted cash are a different figure.'),
    Rule('total_debt', ('DebtLongtermAndShorttermCombinedAmount',), USD, INSTANT, critical=True,
         alternates=('LongTermDebt', 'LongTermDebtNoncurrent', 'LongTermDebtCurrent', 'CommercialPaper', 'ShortTermBorrowings', 'DebtCurrent',
                     'LongTermDebtAndCapitalLeaseObligations'),
         alternate_reason=NEEDS_COMPONENT_RULE,
         note='The combined debt figure when the company reports one; otherwise the documented sum of non-overlapping parts '
              '(debt_from_components). Never a guess: a part that is not reported is not taken as zero.'),
    Rule('diluted_shares_weighted_average', ('WeightedAverageNumberOfDilutedSharesOutstanding',), SHARES, DURATION, critical=True,
         note='Weighted-average diluted shares for the period, as used for diluted EPS. Not a point-in-time share count.'),
)
RULE_BY_FIELD = {r.field: r for r in RULES}
FIELDS = tuple(r.field for r in RULES)
CRITICAL_FIELDS = tuple(r.field for r in RULES if r.critical)
WATCHED_CONCEPTS = frozenset(c for r in RULES for c in r.accept + r.alternates)
RULES_VERSION = 'sec-xbrl-normalization-v2'
# The capability rule (operator instruction, 2026-10-03). Required: the capability is AVAILABLE only when every required field
# is resolved, and confirmed in the filing, for the current period of every filing read, for every company of the sample.
# Optional: company-dependent; a missing one is recorded and does not block. Not collected: never synthesized from other lines.
REQUIRED_FIELDS = CRITICAL_FIELDS
OPTIONAL_FIELDS = tuple(r.field for r in RULES if not r.critical)
NOT_COLLECTED = ('free_cash_flow', 'ebitda')


def _decimal(value):
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _day(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def period_type(start, end) -> str:
    """'instant' with no start; otherwise 3M, 6M, 9M or 12M by inclusive length, or '' when it is none of those."""
    if start is None:
        return INSTANT
    first, last = _day(start), _day(end)
    if first is None or last is None:
        return ''
    days = (last - first).days + 1
    for name, low, high in PERIOD_TYPES:
        if low <= days <= high:
            return name
    return ''


def debt_from_components(rows) -> dict:
    """``rows``: the facts of one filing. Returns {balance date: outcome}; an outcome is either
    {'value', 'parts': [{'concept', 'value', 'role'}], 'source': fact} or {'reason', 'detail', 'concepts'}.
    Only dates that carry at least one long-term part are considered."""
    by_date = {}
    for f in rows:
        if f['concept'] in DEBT_COMPONENT_CONCEPTS and f.get('start') is None:
            by_date.setdefault(str(f.get('end')), {}).setdefault(f['concept'], []).append(f)
    out = {}
    for end, found in by_date.items():
        concepts = sorted(found)
        if not any(c in found for c in DEBT_LONG_TERM_PARTS):
            continue
        fail = lambda reason, detail: {'reason': reason, 'detail': detail, 'concepts': concepts}
        values, problem = {}, None
        for concept, members in found.items():
            if any(m.get('unit') != USD for m in members):
                problem = fail(UNEXPECTED_UNIT, f'{concept}: expected {USD}')
                break
            numbers = {_decimal(m.get('val')) for m in members}
            if None in numbers:
                problem = fail(UNPARSEABLE_VALUE, f'{concept}: a value is not a number')
                break
            if len(numbers) > 1:
                problem = fail(CONFLICTING_VALUES, f'{concept}: {sorted(str(x) for x in numbers)}')
                break
            values[concept] = numbers.pop()
        if problem:
            out[end] = problem
            continue
        missing = [c for c in DEBT_LONG_TERM_PARTS if c not in values]
        if missing:
            out[end] = fail(LONG_TERM_DEBT_PART_MISSING, 'not reported: ' + ', '.join(missing) + '; a part that is not reported is not taken as zero')
            continue
        current = values['LongTermDebtCurrent']
        parts = [{'concept': c, 'value': str(values[c]), 'role': 'added'} for c in DEBT_LONG_TERM_PARTS]
        short = next((c for c in DEBT_SHORT_TERM if c in values), None)
        if short:
            if short == 'ShortTermBorrowings' and 'CommercialPaper' in values and values['CommercialPaper'] > values[short]:
                out[end] = fail(DEBT_COMPONENTS_DO_NOT_RECONCILE, 'CommercialPaper is larger than ShortTermBorrowings, of which it should be a part')
                continue
            if DEBT_CURRENT_TOTAL in values and values[DEBT_CURRENT_TOTAL] != current + values[short]:
                out[end] = fail(DEBT_COMPONENTS_DO_NOT_RECONCILE, f'DebtCurrent {values[DEBT_CURRENT_TOTAL]} is not LongTermDebtCurrent {current} + '
                                                                  f'{short} {values[short]}')
                continue
            parts.append({'concept': short, 'value': str(values[short]), 'role': 'added'})
            total = current + values['LongTermDebtNoncurrent'] + values[short]
        elif DEBT_CURRENT_TOTAL in values and values[DEBT_CURRENT_TOTAL] == current:
            # all current debt is the current maturities of long-term debt: there is no other short-term borrowing
            parts.append({'concept': DEBT_CURRENT_TOTAL, 'value': str(values[DEBT_CURRENT_TOTAL]), 'role': 'evidence that short-term borrowings are zero'})
            total = current + values['LongTermDebtNoncurrent']
        else:
            out[end] = fail(SHORT_TERM_DEBT_NOT_REPORTED, 'neither ShortTermBorrowings nor CommercialPaper is reported, and DebtCurrent does not show '
                                                          'that there is none; absence is not taken as zero')
            continue
        out[end] = {'value': total, 'parts': parts, 'source': found['LongTermDebtNoncurrent'][0]}
    return out


def normalize(facts, filings, *, instrument, cik) -> dict:
    """``facts``: SEC company facts, one dict per (concept, unit, period, filing): taxonomy, concept, unit, start (absent
    for an instant), end, val, accn, fy, fp, form, filed, frame.
    ``filings``: accession -> {form, report_date, accepted_timestamp, ...} for the filings to read.

    Returns {'accepted': [records], 'unresolved': [entries], 'raw_facts': n, 'concepts_seen': {...}}. Deterministic: the
    same input always gives the same output, in the same order."""
    accepted, unresolved = [], []
    relevant = [f for f in facts if f.get('accn') in filings and f.get('taxonomy') == 'us-gaap' and f.get('concept') in WATCHED_CONCEPTS]
    seen = {}
    for f in relevant:
        seen[f['concept']] = seen.get(f['concept'], 0) + 1
    by_filing = {}
    for f in relevant:
        by_filing.setdefault(f['accn'], []).append(f)
    for accession in sorted(filings, key=lambda a: (str(filings[a].get('accepted_timestamp')), a)):
        filing, rows = filings[accession], by_filing.get(accession, [])
        report_end = str(filing.get('report_date') or '')
        for rule in RULES:
            groups = {}
            for f in rows:
                if f['concept'] in rule.accept:
                    groups.setdefault((f.get('start'), f.get('end')), []).append(f)
            current_found = False
            for (start, end) in sorted(groups, key=lambda p: (str(p[1]), str(p[0]))):
                members = groups[(start, end)]
                where = {'instrument': instrument, 'field': rule.field, 'accession_number': accession, 'period_start': start, 'period_end': end,
                         'concepts': sorted({m['concept'] for m in members})}
                relation = CURRENT if str(end) == report_end else COMPARATIVE
                if relation == CURRENT:
                    current_found = True                                   # something was reported, even if it turns out unusable
                if any(m.get('unit') != rule.unit for m in members):
                    unresolved.append({**where, 'reason': UNEXPECTED_UNIT, 'detail': f'expected {rule.unit}, found '
                                       + ', '.join(sorted({str(m.get("unit")) for m in members})), 'relation': relation})
                    continue
                if (start is None) != (rule.kind == INSTANT):
                    unresolved.append({**where, 'reason': UNEXPECTED_PERIOD_KIND, 'detail': f'{rule.field} is a {rule.kind} fact', 'relation': relation})
                    continue
                kind = period_type(start, end)
                if not kind:
                    unresolved.append({**where, 'reason': UNCLASSIFIED_PERIOD, 'detail': f'{start} to {end} is not 3, 6, 9 or 12 months long',
                                       'relation': relation})
                    continue
                values = {}
                for m in members:
                    number = _decimal(m.get('val'))
                    if number is None:
                        values = None
                        break
                    values.setdefault(m['concept'], set()).add(number)
                if values is None:
                    unresolved.append({**where, 'reason': UNPARSEABLE_VALUE, 'detail': 'a value is not a number', 'relation': relation})
                    continue
                if any(len(v) > 1 for v in values.values()):
                    unresolved.append({**where, 'reason': CONFLICTING_VALUES, 'relation': relation,
                                       'detail': '; '.join(f'{c}: {sorted(str(x) for x in v)}' for c, v in sorted(values.items()))})
                    continue
                distinct = {next(iter(v)) for v in values.values()}
                if len(distinct) > 1:                                      # two accepted concepts, two different numbers: not merged, not chosen
                    unresolved.append({**where, 'reason': CONFLICTING_CONCEPTS, 'relation': relation,
                                       'detail': '; '.join(f'{c} = {next(iter(v))}' for c, v in sorted(values.items()))})
                    continue
                concept = next(c for c in rule.accept if c in values)       # the first accepted concept that is present, in rule order
                chosen = next(m for m in members if m['concept'] == concept)
                accepted.append({
                    'instrument': instrument, 'cik': f'{int(cik):010d}', 'taxonomy': 'us-gaap', 'concept': concept, 'normalized_field': rule.field,
                    'mapping_rule': RULES_VERSION + ':' + rule.field, 'agreeing_concepts': sorted(c for c in values if c != concept) or None,
                    'unit': rule.unit, 'value': str(next(iter(values[concept]))), 'period_type': kind, 'period_start': start, 'period_end': end,
                    'relation_to_filing': relation, 'filing_fiscal_year': chosen.get('fy'), 'filing_fiscal_period': chosen.get('fp'),
                    'form': chosen.get('form'), 'accession_number': accession, 'filing_date': chosen.get('filed'), 'frame': chosen.get('frame'),
                    'accepted_timestamp': filing.get('accepted_timestamp')})
            if rule.field == 'total_debt':
                # no combined figure for a date: the documented sum of non-overlapping parts, or the reason there is none
                direct = {r['period_end'] for r in accepted if r['accession_number'] == accession and r['normalized_field'] == 'total_debt'}
                failed = {u['period_end'] for u in unresolved if u['accession_number'] == accession and u['field'] == 'total_debt'}
                for end, outcome in sorted(debt_from_components(rows).items()):
                    if end in direct or end in failed:
                        continue
                    relation = CURRENT if end == report_end else COMPARATIVE
                    if relation == CURRENT:
                        current_found = True
                    if 'reason' in outcome:
                        unresolved.append({'instrument': instrument, 'field': rule.field, 'accession_number': accession, 'period_start': None,
                                           'period_end': end, 'concepts': outcome['concepts'], 'relation': relation, 'reason': outcome['reason'],
                                           'detail': outcome['detail']})
                        continue
                    source = outcome['source']
                    accepted.append({
                        'instrument': instrument, 'cik': f'{int(cik):010d}', 'taxonomy': 'us-gaap',
                        'concept': '+'.join(p['concept'] for p in outcome['parts'] if p['role'] == 'added'), 'normalized_field': rule.field,
                        'mapping_rule': RULES_VERSION + ':total_debt:components', 'agreeing_concepts': None, 'unit': rule.unit,
                        'value': str(outcome['value']), 'period_type': INSTANT, 'period_start': None, 'period_end': end,
                        'relation_to_filing': relation, 'filing_fiscal_year': source.get('fy'), 'filing_fiscal_period': source.get('fp'),
                        'form': source.get('form'), 'accession_number': accession, 'filing_date': source.get('filed'), 'frame': None,
                        'accepted_timestamp': filing.get('accepted_timestamp'), 'derived_from': outcome['parts']})
            if not current_found and report_end:
                alternates = sorted({f['concept'] for f in rows if f['concept'] in rule.alternates and str(f.get('end')) == report_end})
                unresolved.append({'instrument': instrument, 'field': rule.field, 'accession_number': accession, 'period_start': None,
                                   'period_end': report_end, 'concepts': alternates, 'relation': CURRENT,
                                   'reason': rule.alternate_reason if alternates else NOT_REPORTED,
                                   'detail': ('reported only as ' + ', '.join(alternates)) if alternates else
                                             'none of ' + ', '.join(rule.accept) + ' is reported for the period of this filing'})
    return {'accepted': accepted, 'unresolved': unresolved, 'raw_facts': len(relevant), 'concepts_seen': dict(sorted(seen.items()))}


def _key(record):
    return (record['instrument'], record['normalized_field'], record.get('period_start'), record['period_end'])


def _filed_order(record):
    return (str(record.get('filing_date')), str(record['accession_number']), record['normalized_field'], str(record['period_end']),
            str(record.get('period_start')))


def assign_versions(records) -> list:
    """Adds ``version``, ``is_restatement`` and ``prior_value`` to each record. ``records`` must be the complete normalized
    history of the company (every periodic filing the SEC data holds), so the numbering does not depend on which filings
    Firm Lab happens to read or in which order it reads them.

    Observations of the same field and period are ordered by filing date, then accession number (a tie-break only: two
    periodic filings on one date with different values for the same period). The first is version 1. The version goes
    up by one in the filing where the reported value changes, and that observation is the restatement; later filings
    that repeat the changed value keep its version and are not restatements themselves."""
    state, out = {}, []
    for record in sorted(records, key=_filed_order):
        before = state.get(_key(record))
        if before is None:
            version, restated, previous = 1, False, None
        elif _decimal(before[1]) == _decimal(record['value']):
            version, restated, previous = before[0], False, None
        else:
            version, restated, previous = before[0] + 1, True, before[1]
        state[_key(record)] = (version, str(record['value']))
        out.append({**record, 'version': version, 'is_restatement': restated, 'prior_value': previous})
    return out


def as_of(rows, known_by: str) -> dict:
    """The latest observation of each (instrument, field, period) accepted at or before ``known_by`` (ISO UTC text).
    A restatement is invisible until the moment the SEC accepted the filing that carries it."""
    latest = {}
    for row in sorted(rows, key=lambda r: (str(r['accepted_timestamp']), str(r['accession_number']))):
        if str(row['accepted_timestamp']) <= str(known_by):
            latest[_key(row)] = row
    return latest


def quality(accepted, unresolved, filings) -> dict:
    """Whether the sample for one company is good enough to rely on. Critical fields must be resolved for the current
    period of every filing read; non-critical fields may stay unresolved, with their reasons."""
    critical = sorted({(u['accession_number'], u['field']) for u in unresolved if u['field'] in CRITICAL_FIELDS and u['relation'] == CURRENT})
    have = {}
    for r in accepted:
        if r['relation_to_filing'] == CURRENT:
            have.setdefault(r['accession_number'], set()).add(r['normalized_field'])
    missing = sorted((a, f) for a in filings for f in CRITICAL_FIELDS if f not in have.get(a, set()))
    blocking = sorted(set(critical) | set(missing))
    by_field = {}
    for u in unresolved:
        by_field.setdefault(u['field'], {})
        by_field[u['field']][u['reason']] = by_field[u['field']].get(u['reason'], 0) + 1
    return {'passes': not blocking, 'critical_unresolved': [{'accession_number': a, 'field': f} for a, f in blocking],
            'unresolved_by_field': {f: dict(sorted(r.items())) for f, r in sorted(by_field.items())},
            'fields_resolved_for_current_period': {a: sorted(v) for a, v in sorted(have.items())}}
