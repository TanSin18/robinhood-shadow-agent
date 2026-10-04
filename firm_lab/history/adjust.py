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
TICK_BOUND = 0.0005                       # a re-adjusted print must hold the day's price to a twentieth of a cent, or prices that differed on the day can merge
VOLUME_PRECISION_BOUND = 0.005            # a re-counted volume known to worse than 0.5% of itself cannot support a volume feature
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


def coarse_print(panel, splits=()) -> np.ndarray:
    """True where the vendor's print of a bar cannot give the shape of that bar. Two tests:

    * the adjusted close is printed more coarsely than PRECISION_BOUND of its own value; or
    * the bar was re-adjusted for a later split and its print, taken back to the day's own dollars, is coarser than
      TICK_BOUND. A re-adjusted price is the day's price divided by the later splits and rounded again; unless the
      rounding is much finer than a cent of the day, two prices that differed on the day can come out equal (or two
      equal ones different), and a swing high is decided by exactly such comparisons.

    A bar no later split touched is printed as it was on the day and passes the second test whatever its decimals."""
    with np.errstate(invalid='ignore'):
        readjusted = np.abs(share_divisor(panel, splits) - 1.0) > 1e-9
        in_day_dollars = panel['print_error'] * panel['close_unadjusted']
        return np.asarray(panel['present'], bool) & ((panel['print_error'] > PRECISION_BOUND) | (readjusted & (in_day_dollars > TICK_BOUND * (1 + 1e-9))))


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


def _applied(panel, splits=()) -> np.ndarray:
    """The product of the applied split ratios after each session."""
    out = np.ones(len(panel['sessions']))
    for k, ratio in splits:
        out[:k] *= ratio
    return out


def reprint_scale(panel, splits=()) -> np.ndarray:
    """What the vendor's adjusted prices of each bar must be multiplied by to stand on the exact close's share basis.

    Exactly 1 wherever the vendor's factor (unadjusted over adjusted close) is the product of the applied splits after
    the session, within what its rounding explains. That is every bar of a correct record, with or without later
    splits, so the vendor's own prints are compared with each other untouched and a tie on the day stays a tie.

    Elsewhere the vendor has adjusted for something the applied splits do not hold. The true ratio is the same over a
    whole stretch of sessions; it is taken as the median over the stretch, so that the rounding of one bar's close
    cannot tilt that bar against its neighbours."""
    count = len(panel['sessions'])
    scale = np.ones(count)
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = split_factor(panel) / _applied(panel, splits)
        off = np.asarray(panel['present'], bool) & np.isfinite(ratio) & ~(np.abs(np.log(ratio)) <= TOLERANCE + panel['half_ulp'])
    index = np.flatnonzero(off)
    if not len(index):
        return scale
    valid = np.flatnonzero(panel['present'])
    order = {int(k): n for n, k in enumerate(valid)}
    start = 0
    for n in range(1, len(index) + 1):
        a = int(index[n - 1])
        ends = n == len(index) or order[int(index[n])] != order[a] + 1 or \
            abs(math.log(ratio[index[n]] / ratio[a])) > TOLERANCE + panel['half_ulp'][index[n]] + panel['half_ulp'][a]
        if ends:                                                        # a stretch ends where the bars stop being neighbours or the ratio steps
            scale[index[start:n]] = float(np.median(ratio[index[start:n]]))
            start = n
    return scale


def share_divisor(panel, splits=()) -> np.ndarray:
    """How many of today's shares one share of each session became: what the vendor's volume was multiplied by. The
    product of the applied split ratios after the session, times ``reprint_scale`` where the vendor adjusted for more."""
    return _applied(panel, splits) * reprint_scale(panel, splits)


def volume_bounds(panel, splits=()) -> tuple:
    """(fewest, most) shares that can have traded on the day, given the vendor's re-counted volume. The vendor supplies
    volume on today's share basis: the day's shares times the divisor, a whole number of today's shares at best. A bar no
    later split touched is exact. After a forward split the re-count is exact too (one whole number of the day's shares
    fits). After a reverse split many do: the re-count has lost them."""
    divisor, volume = share_divisor(panel, splits), np.asarray(panel['volume'], float)
    with np.errstate(invalid='ignore', divide='ignore'):
        low, high = np.ceil((volume - 0.5) / divisor - 1e-9).clip(0), np.floor((volume + 0.5) / divisor + 1e-9)
        loose = high < low                                              # no whole number fits: the vendor did not round to whole shares
        low = np.where(loose, ((volume - 0.5) / divisor).clip(0), low)
        high = np.where(loose, (volume + 0.5) / divisor, high)
    exact = np.abs(divisor - 1.0) <= 1e-9
    return np.where(exact, volume, low), np.where(exact, volume, high)


def coarse_volume(panel, splits=()) -> np.ndarray:
    """True where the day's volume is known only to worse than VOLUME_PRECISION_BOUND of itself, because a later reverse
    split re-counted it into too few of today's shares (it can round to nothing at all). A bar no later split touched,
    and a bar re-counted for a forward split, are exact and are never flagged, whatever their volume."""
    low, high = volume_bounds(panel, splits)
    with np.errstate(invalid='ignore'):
        return np.asarray(panel['present'], bool) & ((high - low) / 2 > VOLUME_PRECISION_BOUND * (high + low) / 2)


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
