"""Corporate-action consistency, the exact split-adjusted close, and the sessions prices cannot be compared across.

Nothing here changes a stored value. The audit finds sessions where prices before and after are not comparable on the
price-return basis, and names why:

* SPIN_OFF / LARGE_DISTRIBUTION: a recorded ex-date whose price gap is not a loss.
* SPLIT_FACTOR_WITHOUT_ACTION: the ratio of unadjusted to split-adjusted close steps and no split explains it: none is
  recorded there, the recorded ratio does not match, or the adjusted series is not continuous across it.
* ACTION_WITHOUT_SPLIT_FACTOR: a split is recorded and the ratio does not step.

A feature whose lookback reaches across such a session is unavailable; a label whose window contains one is excluded.

The exact close. A vendor reprints its adjusted prices after every split, at a fixed number of decimals. For a stock
that later split many times the reprinted early prices are small numbers rounded coarsely, and that coarseness is
information about the future. The unadjusted close does not have the problem: it is the price printed on the day. So
the close used across sessions is rebuilt from the unadjusted close and the confirmed split ratios, and the adjusted
prints are used only within one bar (its own open, high and low relative to its own close).
"""
from __future__ import annotations

import math

import numpy as np

from .panel import first_session_on_or_after

TOLERANCE = 0.005
LARGE_DISTRIBUTION = 0.05
PRECISION_BOUND = 5e-4                    # an adjusted price printed more coarsely than 0.05% of itself cannot support high/low/open features
DIRECTION_FROM = 0.2                      # a split of at least about 1.22-for-1 is large enough to check which way the factor stepped
SPIN_OFF, LARGE, NO_ACTION, NO_FACTOR = 'SPIN_OFF', 'LARGE_DISTRIBUTION', 'SPLIT_FACTOR_WITHOUT_ACTION', 'ACTION_WITHOUT_SPLIT_FACTOR'
# What the action table is taken to mean where the reprinted prices are too coarse to show it. Both are counted against
# the cases the prices can show (``split_convention``, ``dividend_basis``), so a vendor that means otherwise is found out.
SPLIT_VALUE_MEANS = 'new_per_old'         # a split's value is new shares per old share
DIVIDEND_VALUE_MEANS = 'unadjusted'       # a cash dividend's value is the amount paid per share on the day


def split_factor(panel) -> np.ndarray:
    """Unadjusted close over split-adjusted close: the number of today's shares that one share of that day became."""
    with np.errstate(invalid='ignore', divide='ignore'):
        return panel['close_unadjusted'] / panel['close']


def coarse_print(panel) -> np.ndarray:
    """True where the adjusted close is printed more coarsely than PRECISION_BOUND of its own value."""
    with np.errstate(invalid='ignore'):
        return np.asarray(panel['present'], bool) & (panel['print_error'] > PRECISION_BOUND)


def _number(text):
    try:
        value = float(text)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def breaks(panel, actions) -> dict:
    """{'breaks': [...], 'splits': [(session index, new shares per old share)], 'splits_confirmed', 'splits_unchecked',
    'split_convention', 'dividend_basis', 'distributions_not_sizable'}.

    A split's value may be recorded as new-per-old or old-per-new; either is read when it matches the observed step.
    Splits recorded for one session multiply. A step large enough to tell is also checked for direction: the adjusted
    series must be continuous across it. The size of a cash distribution is read from the vendor's own total-return
    factor on the two sessions around the ex-date.

    What a later split must not decide. After later splits the vendor reprints early prices as small, coarsely rounded
    numbers, and the factor read from them is blurred. Where the blur is too large to show a recorded split, the split
    is applied as recorded (``splits_unchecked``), not turned into a break; where it is too large to say whether a
    distribution reached 5%, the recorded amount over the unadjusted close of the day decides. Both use only numbers a
    later split cannot change, so a row of a stock that split heavily afterwards is treated like any other. What does
    still depend on the reprint is whether an ERROR in the vendor's own tables is caught: a check that cannot be made
    is not a failure."""
    sessions, present = panel['sessions'], panel['present']
    factor = split_factor(panel)
    found, confirmed, unchecked, unsizable, split_steps = [], 0, 0, 0, []
    convention = {'new_per_old': 0, 'old_per_new': 0}
    basis = {'unadjusted': 0, 'adjusted': 0, 'neither': 0, 'no_total_return_factor': 0}
    valid = np.flatnonzero(present)
    previous = {int(b): int(a) for a, b in zip(valid, valid[1:])}
    steps = {}
    for b, a in previous.items():
        if abs(math.log(factor[a] / factor[b])) > TOLERANCE + panel['half_ulp'][a] + panel['half_ulp'][b]:
            steps[b] = factor[a] / factor[b]
    splits = {}
    with np.errstate(invalid='ignore', divide='ignore'):
        total = panel['close_total_return'] / panel['close']
    for action in actions:
        k = first_session_on_or_after(panel, str(action['effective_date'])[:10])
        if k is None:
            continue
        if action['type'] == 'split':
            splits.setdefault(k, []).append(action)
        elif action['type'] == 'spin_off' and action.get('provider_code') != 'spunofffrom':
            found.append({'session': sessions[k], 'index': k, 'reason': SPIN_OFF, 'provider_code': action.get('provider_code')})
        elif action['type'] == 'cash_dividend' and k in previous and present[k]:
            j = previous[k]
            value = _number(action.get('value'))
            paid = None if value is None else value / panel['close_unadjusted'][j]       # the recorded amount over the price printed on the day
            blur = 2 * (panel['print_error'][j] + panel['print_error'][k])               # how far the reprinted factor can be off
            share = None
            if math.isfinite(total[j]) and math.isfinite(total[k]) and total[k] > 0:
                share = 1.0 - total[j] / total[k]
                if value is not None:
                    adjusted = value / panel['close'][j]
                    near = lambda x: abs(x - share) <= max(0.002, 0.25 * abs(share)) + blur
                    basis['unadjusted' if near(paid) else 'adjusted' if near(adjusted) else 'neither'] += 1
            elif value is not None:
                basis['no_total_return_factor'] += 1
            if share is not None and share - blur >= LARGE_DISTRIBUTION:
                large, size = True, share
            elif share is not None and share + blur < LARGE_DISTRIBUTION:
                large, size = False, share
            elif paid is not None:                                      # the reprint cannot say: the recorded amount on the day's price does
                large, size = paid >= LARGE_DISTRIBUTION, paid
            else:
                unsizable += share is not None                          # no amount recorded and a factor too blurred to size it: counted, not guessed
                continue
            if large:
                found.append({'session': sessions[k], 'index': k, 'reason': LARGE, 'share_of_prior_close': round(float(size), 6)})
    for k, step in sorted(steps.items()):
        j = previous[k]
        bound = TOLERANCE + panel['half_ulp'][k] + panel['half_ulp'][j]
        values = [_number(a.get('value')) for a in splits.get(k, [])]
        matched = None
        if values and all(v is not None for v in values):
            combined = math.prod(values)
            if abs(math.log(step / combined)) <= bound:
                matched = ('new_per_old', combined)
            elif abs(math.log(step * combined)) <= bound:
                matched = ('old_per_new', 1.0 / combined)
        note = None
        if matched and abs(math.log(step)) > DIRECTION_FROM and abs(math.log(panel['close'][k] / panel['close'][j])) > 0.5 * abs(math.log(step)):
            matched, note = None, 'the adjusted close is not continuous across the recorded split'
        if matched:
            confirmed += 1
            convention[matched[0]] += 1
            split_steps.append((int(k), float(matched[1])))
        else:
            item = {'session': sessions[k], 'index': k, 'reason': NO_ACTION, 'observed_step': round(float(step), 6),
                    'recorded_split_values': [a.get('value') for a in splits.get(k, [])]}
            if note:
                item['note'] = note
            found.append(item)
    first_bar = int(valid[0]) if len(valid) else None
    for k, rows in sorted(splits.items()):
        if first_bar is not None and k > first_bar and k not in steps and k in previous:      # a split on the very first bar has no earlier price to step from
            values = [_number(a.get('value')) for a in rows]
            if not any(v is not None for v in values):
                continue
            combined = math.prod(v for v in values if v is not None)
            if abs(math.log(combined)) <= TOLERANCE:
                continue                                                # too small to matter at any precision
            j = previous[k]
            blur = panel['half_ulp'][k] + panel['half_ulp'][j]
            if all(v is not None for v in values) and abs(math.log(combined)) <= TOLERANCE + 2 * blur:
                # The reprinted prices here are too coarse to show a step of this size. The record stands, as recorded.
                unchecked += 1
                split_steps.append((int(k), float(combined if SPLIT_VALUE_MEANS == 'new_per_old' else 1.0 / combined)))
            else:
                found.append({'session': sessions[k], 'index': k, 'reason': NO_FACTOR, 'recorded_split_values': [a.get('value') for a in rows]})
    found.sort(key=lambda b: (b['index'], b['reason']))
    split_steps.sort()
    return {'breaks': found, 'splits': split_steps, 'splits_confirmed': confirmed, 'splits_unchecked': unchecked, 'split_convention': convention,
            'dividend_basis': basis, 'distributions_not_sizable': int(unsizable)}


def break_mask(panel, found) -> np.ndarray:
    mask = np.zeros(len(panel['sessions']), bool)
    for b in found:
        mask[b['index']] = True
    return mask


def exact_close(panel, splits=()) -> np.ndarray:
    """The close on one share basis across the whole series, from the unadjusted close and the confirmed split ratios:
    the unadjusted close of session t divided by the product of the ratios of every confirmed split after t. It is the
    split-adjusted close without the vendor's rounding, and a split that is not confirmed is not applied (the session is
    a break, so nothing is compared across it)."""
    count = len(panel['sessions'])
    divisor = np.ones(count)
    for k, ratio in splits:
        divisor[:k] *= ratio
    return panel['close_unadjusted'] / divisor


def share_divisor(panel, splits=()) -> np.ndarray:
    """How many of today's shares one share of each session became: what the vendor's adjusted volume was multiplied by.
    Where the confirmed splits explain the vendor's own factor (unadjusted over adjusted close) the exact product of
    their ratios is used, so that rounding in the reprinted prices plays no part; elsewhere the vendor's factor stands."""
    count = len(panel['sessions'])
    exact = np.ones(count)
    for k, ratio in splits:
        exact[:k] *= ratio
    printed = split_factor(panel)
    with np.errstate(invalid='ignore', divide='ignore'):
        agrees = np.abs(np.log(printed / exact)) <= TOLERANCE + panel['half_ulp']
    return np.where(agrees, exact, printed)


def total_return_audit(panel, actions) -> dict:
    """Counts the steps in the vendor's total-return factor and how many fall on a recorded dividend or spin-off date.
    A report only. The total-return close is never used as a price."""
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = panel['close_total_return'] / panel['close']
    valid = np.flatnonzero(panel['present'] & np.isfinite(ratio))
    dated = set()
    for action in actions:
        if action['type'] in ('cash_dividend', 'spin_off'):
            k = first_session_on_or_after(panel, str(action['effective_date'])[:10])
            if k is not None:
                dated.add(k)
    steps = [int(b) for a, b in zip(valid, valid[1:]) if abs(math.log(ratio[b] / ratio[a])) > 1e-4 + panel['half_ulp'][a] + panel['half_ulp'][b]]
    on_action = sum(k in dated for k in steps)
    return {'factor_steps': len(steps), 'steps_on_a_recorded_distribution': on_action, 'steps_without_a_record': len(steps) - on_action,
            'recorded_distributions_without_a_step': len(dated - set(steps))}
