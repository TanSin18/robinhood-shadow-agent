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
UNSIZED = 'DISTRIBUTION_WITHOUT_AMOUNT'
# What the action table is taken to mean. Both are counted against the cases the prices can show (``split_convention``,
# ``dividend_basis``), and a dataset is refused when the counts contradict them, so a vendor that means otherwise is found out.
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
    """{'breaks': [...], 'splits': [(bar index, new shares per old share)], 'splits_confirmed', 'splits_unchecked',
    'split_convention', 'dividend_basis', 'distributions_without_amount'}.

    The rule behind every decision here: what a row may read must not depend on a split that happened after it. After
    later splits the vendor reprints early prices as small, coarsely rounded numbers, so anything decided from the
    reprinted prices can differ between a stock that split later and one that did not. Therefore:

    * A recorded split is applied as recorded (value = new shares per old share), from the first bar on or after its
      date. The vendor's factor (unadjusted over adjusted close) is only asked whether it CONTRADICTS the record, beyond
      what its own rounding can explain. A correct record is never contradicted, however coarse the reprint; it counts
      as ``splits_confirmed`` when the step is visible and ``splits_unchecked`` when it is too small to see there.
    * Whether the series is continuous across a split is asked of the unadjusted close and the recorded ratio.
    * A cash distribution is sized by its recorded amount over the unadjusted close of the session before (the amount
      paid per share on the day). One recorded without an amount cannot be sized and is a break.
    * A break is recorded where the factor steps with no recorded split, where the record and the factor contradict
      each other, where a split is recorded the other way round, at a spin-off, and at a distribution of 5% or more.

    What can still depend on the reprint is whether an ERROR in the vendor's own tables is caught (an unrecorded split,
    a wrong ratio): a check that cannot be made is not a failure. ``split_convention`` and ``dividend_basis`` count how
    the visible cases read; a dataset is refused when they contradict the two readings above."""
    sessions, present = panel['sessions'], panel['present']
    factor, unadjusted = split_factor(panel), panel['close_unadjusted']
    found, confirmed, unchecked, unsized, split_steps = [], 0, 0, 0, []
    convention = {'new_per_old': 0, 'old_per_new': 0}
    basis = {'unadjusted': 0, 'adjusted': 0, 'neither': 0, 'no_total_return_factor': 0}
    valid = np.flatnonzero(present)
    previous = {int(b): int(a) for a, b in zip(valid, valid[1:])}

    def bar_on_or_after(day):
        """The first slot that holds a bar on or after ``day``; None past the last bar."""
        slot = first_session_on_or_after(panel, day)
        if slot is None:
            return None
        at = int(np.searchsorted(valid, slot))
        return int(valid[at]) if at < len(valid) else None

    blur = {k: panel['half_ulp'][k] + panel['half_ulp'][j] for k, j in previous.items()}       # how far rounding can move the observed step
    observed = {k: factor[j] / factor[k] for k, j in previous.items()}
    visible = {k for k in previous if abs(math.log(observed[k])) > TOLERANCE + blur[k]}
    recorded = {}
    with np.errstate(invalid='ignore', divide='ignore'):
        total = panel['close_total_return'] / panel['close']
    for action in actions:
        day = str(action['effective_date'])[:10]
        if action['type'] == 'spin_off' and action.get('provider_code') != 'spunofffrom':
            slot = first_session_on_or_after(panel, day)
            if slot is not None:
                found.append({'session': sessions[slot], 'index': slot, 'reason': SPIN_OFF, 'provider_code': action.get('provider_code')})
            continue
        k = bar_on_or_after(day)
        if k is None or k not in previous:                              # past the last bar, or on the very first: nothing to step from
            continue
        if action['type'] == 'split':
            recorded.setdefault(k, []).append(action)
        elif action['type'] == 'cash_dividend':
            j = previous[k]
            value = _number(action.get('value'))
            if value is None:                                           # no amount: it cannot be sized from anything a later split leaves alone
                unsized += 1
                found.append({'session': sessions[k], 'index': k, 'reason': UNSIZED})
                continue
            paid = value / unadjusted[j]
            if math.isfinite(total[j]) and math.isfinite(total[k]) and total[k] > 0:       # a tally only: how the vendor's own factor reads the amount
                share, adjusted = 1.0 - total[j] / total[k], value / panel['close'][j]
                near = lambda x: abs(x - share) <= max(0.002, 0.25 * abs(share)) + 2 * (panel['print_error'][j] + panel['print_error'][k])
                basis['unadjusted' if near(paid) else 'adjusted' if near(adjusted) else 'neither'] += 1
            else:
                basis['no_total_return_factor'] += 1
            if paid >= LARGE_DISTRIBUTION:
                found.append({'session': sessions[k], 'index': k, 'reason': LARGE, 'share_of_prior_close': round(float(paid), 6)})
    for k, rows in sorted(recorded.items()):
        j, limit, step = previous[k], TOLERANCE + blur[k], observed[k]
        values = [_number(a.get('value')) for a in rows]
        item = {'session': sessions[k], 'index': k, 'reason': NO_ACTION if k in visible else NO_FACTOR, 'recorded_split_values': [a.get('value') for a in rows]}
        if any(v is None for v in values):
            found.append({**item, 'note': 'a recorded split value could not be read'})
            continue
        ratio = math.prod(values)                                       # splits recorded for one session multiply
        if abs(math.log(ratio)) <= TOLERANCE:
            if k in visible:
                found.append({**item, 'observed_step': round(float(step), 6)})
            continue                                                    # a ratio of one changes nothing
        if abs(math.log(step / ratio)) <= limit:
            if abs(math.log(ratio)) > DIRECTION_FROM and abs(math.log(unadjusted[k] * ratio / unadjusted[j])) > 0.5 * abs(math.log(ratio)):
                found.append({**item, 'note': 'the unadjusted close does not move as the recorded split says'})
                continue
            split_steps.append((int(k), float(ratio)))
            if k in visible:
                confirmed += 1
                convention['new_per_old'] += 1
            else:
                unchecked += 1
        elif abs(math.log(step * ratio)) <= limit:
            # The factor steps by the inverse of the record. The unadjusted close says which of the two is wrong.
            as_recorded, inverse = abs(math.log(unadjusted[k] * ratio / unadjusted[j])), abs(math.log(unadjusted[k] / (ratio * unadjusted[j])))
            if abs(math.log(ratio)) > DIRECTION_FROM and as_recorded < inverse:
                found.append({**item, 'observed_step': round(float(step), 6), 'note': 'the vendor factor steps the wrong way for the recorded split'})
            else:
                convention['old_per_new'] += 1
                found.append({**item, 'observed_step': round(float(step), 6), 'note': 'the split is recorded the other way round'})
        else:
            found.append({**item, 'observed_step': round(float(step), 6)})
    for k in sorted(visible - set(recorded)):
        found.append({'session': sessions[k], 'index': k, 'reason': NO_ACTION, 'observed_step': round(float(observed[k]), 6), 'recorded_split_values': []})
    found.sort(key=lambda b: (b['index'], b['reason']))
    return {'breaks': found, 'splits': split_steps, 'splits_confirmed': confirmed, 'splits_unchecked': unchecked, 'split_convention': convention,
            'dividend_basis': basis, 'distributions_without_amount': unsized}


def break_mask(panel, found) -> np.ndarray:
    mask = np.zeros(len(panel['sessions']), bool)
    for b in found:
        mask[b['index']] = True
    return mask


def exact_close(panel, splits=()) -> np.ndarray:
    """The close on one share basis across the whole series, from the unadjusted close and the recorded split ratios
    that ``breaks`` applied: the unadjusted close of session t divided by the product of the ratios of every applied
    split after t. It is the split-adjusted close without the vendor's rounding. A split the vendor's own factor
    contradicts is not applied (the session is a break, so nothing is compared across it)."""
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
