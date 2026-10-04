"""Corporate-action consistency and the points where a price series cannot be compared across.

Nothing here changes a stored value. The audit finds sessions where prices before and after are not comparable on the
price-return basis, and names why:

* SPIN_OFF / LARGE_DISTRIBUTION: a recorded ex-date whose price gap is not a loss.
* SPLIT_FACTOR_WITHOUT_ACTION: the ratio of unadjusted to split-adjusted close steps and no split is recorded there.
* ACTION_WITHOUT_SPLIT_FACTOR: a split is recorded and the ratio does not step.

A feature whose lookback reaches across such a session is unavailable; a label whose window contains one is excluded.
"""
from __future__ import annotations

import math

import numpy as np

from .panel import first_session_on_or_after

TOLERANCE = 0.005
LARGE_DISTRIBUTION = 0.05
SPIN_OFF, LARGE, NO_ACTION, NO_FACTOR = 'SPIN_OFF', 'LARGE_DISTRIBUTION', 'SPLIT_FACTOR_WITHOUT_ACTION', 'ACTION_WITHOUT_SPLIT_FACTOR'


def split_factor(panel) -> np.ndarray:
    """Unadjusted close over split-adjusted close: the number of today's shares that one share of that day became."""
    with np.errstate(invalid='ignore', divide='ignore'):
        return panel['close_unadjusted'] / panel['close']


def _number(text):
    try:
        value = float(text)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def breaks(panel, actions) -> dict:
    """{'breaks': [{session, index, reason, ...}], 'splits_confirmed': n, 'split_convention': {...}}.

    ``actions`` are this security's stored action rows. A split's value may be given as new-per-old or old-per-new;
    either is accepted when it matches the observed step, and the convention seen is reported."""
    sessions, present = panel['sessions'], panel['present']
    factor = split_factor(panel)
    found, convention, confirmed = [], {'new_per_old': 0, 'old_per_new': 0}, 0
    valid = np.flatnonzero(present)
    steps = {}
    for a, b in zip(valid, valid[1:]):
        change = abs(math.log(factor[a] / factor[b]))
        if change > TOLERANCE + panel['half_ulp'][a] + panel['half_ulp'][b]:
            steps[int(b)] = factor[a] / factor[b]
    splits = {}
    for action in actions:
        k = first_session_on_or_after(panel, action['effective_date'])
        if k is None:
            continue
        if action['type'] == 'split':
            splits.setdefault(k, []).append(action)
        elif action['type'] == 'spin_off' and action.get('provider_code') != 'spunofffrom':
            found.append({'session': sessions[k], 'index': k, 'reason': SPIN_OFF, 'provider_code': action.get('provider_code')})
        elif action['type'] == 'cash_dividend':
            value = _number(action.get('value'))
            before = [j for j in valid if j < k]
            if value is not None and before:
                j = before[-1]
                share = max(value / panel['close_unadjusted'][j], value / panel['close'][j])       # the dividend's basis is not documented: test both
                if share >= LARGE_DISTRIBUTION:
                    found.append({'session': sessions[k], 'index': k, 'reason': LARGE, 'share_of_prior_close': round(float(share), 6)})
    for k, step in sorted(steps.items()):
        matched = False
        for action in splits.get(k, []):
            value = _number(action.get('value'))
            if value is None:
                continue
            bound = TOLERANCE + panel['half_ulp'][k] + (panel['half_ulp'][valid[np.searchsorted(valid, k) - 1]] if np.searchsorted(valid, k) else 0)
            if abs(math.log(step / value)) <= bound:
                convention['new_per_old'] += 1
                matched = True
            elif abs(math.log(step * value)) <= bound:
                convention['old_per_new'] += 1
                matched = True
        if matched:
            confirmed += 1
        else:
            found.append({'session': sessions[k], 'index': k, 'reason': NO_ACTION, 'observed_step': round(float(step), 6),
                          'recorded_split_values': [a.get('value') for a in splits.get(k, [])]})
    first_bar = int(valid[0]) if len(valid) else None
    for k, rows in sorted(splits.items()):
        if first_bar is not None and k > first_bar and k not in steps:           # a split on the very first bar has no earlier price to step from
            values = [_number(a.get('value')) for a in rows]
            if any(v is not None and abs(math.log(v)) > TOLERANCE for v in values):       # a recorded 1:1 "split" changes nothing and is not a break
                found.append({'session': sessions[k], 'index': k, 'reason': NO_FACTOR, 'recorded_split_values': [a.get('value') for a in rows]})
    found.sort(key=lambda b: (b['index'], b['reason']))
    return {'breaks': found, 'splits_confirmed': confirmed, 'split_convention': convention}


def break_mask(panel, found) -> np.ndarray:
    mask = np.zeros(len(panel['sessions']), bool)
    for b in found:
        mask[b['index']] = True
    return mask


def total_return_audit(panel, actions) -> dict:
    """Counts the steps in the vendor's total-return factor and how many fall on a recorded dividend or spin-off date.
    A report only. The total-return close is used by nothing until this passes across the stored universe."""
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = panel['close_total_return'] / panel['close']
    valid = np.flatnonzero(panel['present'] & np.isfinite(ratio))
    dated = set()
    for action in actions:
        if action['type'] in ('cash_dividend', 'spin_off'):
            k = first_session_on_or_after(panel, action['effective_date'])
            if k is not None:
                dated.add(k)
    steps = [int(b) for a, b in zip(valid, valid[1:]) if abs(math.log(ratio[b] / ratio[a])) > 1e-4 + panel['half_ulp'][a] + panel['half_ulp'][b]]
    on_action = sum(k in dated for k in steps)
    return {'factor_steps': len(steps), 'steps_on_a_recorded_distribution': on_action, 'steps_without_a_record': len(steps) - on_action,
            'recorded_distributions_without_a_step': len(dated - set(steps))}
