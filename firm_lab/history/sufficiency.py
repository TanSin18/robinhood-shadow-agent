"""The data-sufficiency bars of ``CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md`` as code. Counting only: nothing is fitted.

The specification was written before any data was collected. A test fails if a number here and a number there differ.
"""
from __future__ import annotations

import math

import numpy as np

SPEC_VERSION = 'checkpoint8-sufficiency-v1'
REFERENCE_IC = 0.03
WEAK_IC = 0.05
POWER_FACTOR = 2.49                       # one-sided 5% test, 80% power: 1.645 + 0.842
PER_PARAMETER = 10
SUFFICIENT, BORDERLINE, INSUFFICIENT, NOT_MEASURABLE = 'SUFFICIENT', 'BORDERLINE', 'INSUFFICIENT', 'NOT_MEASURABLE'
TESTABLE, WEAKLY_TESTABLE, NOT_TESTABLE = 'TESTABLE', 'WEAKLY_TESTABLE', 'NOT_TESTABLE'
# family -> (reference parameter count, smallest configuration worth running, is a network, is a sequence model)
FAMILIES = {'linear': (60, 20, False, False), 'xgboost': (2400, 400, False, False), 'lightgbm': (2400, 400, False, False), 'catboost': (4800, 400, False, False),
            'mlp': (6000, 1000, True, False), 'tcn': (20000, 5000, True, True), 'lstm_gru': (9000, 4000, True, True), 'transformer': (20000, 3500, True, True),
            'multi_task': (6100, 1100, True, False)}
HISTORY = {'target_first_session': '1998-01-02', 'minimum_first_session': '2005-01-03', 'target_members': 1000, 'minimum_members': 500}
REGIME_BAR = {'bear_markets': 2, 'corrections': 4, 'high_volatility_episodes': 3, 'rising_rate_periods': 1, 'falling_rate_periods': 1}
NETWORK_BAR = {'bear_markets_in_training': 2, 'calendar_years_in_training': 8, 'sequence_sessions': 63, 'sequence_share': 0.95}
COVERAGE = {'bars_complete_target': 0.995, 'bars_complete_minimum': 0.99, 'rejected_target': 0.001, 'rejected_minimum': 0.005, 'cross_check_minimum': 0.995,
            'earnings_target': 0.80, 'earnings_minimum': 0.60, 'filings_target': 0.90, 'filings_minimum': 0.75, 'macro_target': 0.98, 'macro_minimum': 0.95,
            'facts_target': 0.70, 'per_year_target': 0.95, 'per_year_minimum': 0.90}


def required_observations(ic=REFERENCE_IC) -> int:
    return math.ceil(round((POWER_FACTOR / ic) ** 2, 6))


def breadth(table) -> dict:
    """Effective independent instruments of a [non-overlapping window, instrument] label table (NaN = not a member then).

    ``breadth_v2``: N / (1 + (N - 1) * m), where N is the median number of instruments with a label per window and m is
    the mean squared correlation between pairs, less the 1/(n - 1) a pair of unrelated series shows by chance over the n
    windows they share. Pairs sharing fewer than 24 windows are left out. Measured on development sessions only."""
    table = np.asarray(table, float)
    present = np.isfinite(table)
    per_window = present.sum(axis=1)
    n = float(np.median(per_window[per_window > 0])) if (per_window > 0).any() else 0.0
    unmeasured = {'n_eff': None, 'instruments_per_window': n, 'mean_squared_correlation': None, 'pairs': 0, 'measure': 'breadth_v2',
                  'note': 'no pair of instruments shares 24 non-overlapping windows: breadth is not measurable, and it is not assumed'}
    if table.shape[0] < 3 or table.shape[1] < 2:
        return unmeasured
    mean = np.nanmean(np.where(present, table, np.nan), axis=0)
    centred = np.where(present, table - mean, 0.0)
    mask = present.astype(float)
    shared = mask.T @ mask
    cross = centred.T @ centred
    squares = (centred ** 2).T @ mask                                  # sum of x_i^2 over the windows i shares with j
    with np.errstate(invalid='ignore', divide='ignore'):
        correlation = cross / np.sqrt(squares * squares.T)
    use = (shared >= 24) & ~np.eye(table.shape[1], dtype=bool) & np.isfinite(correlation)
    if not use.any():
        return unmeasured
    m = max(0.0, float(np.mean(correlation[use] ** 2 - 1.0 / (shared[use] - 1.0))))
    return {'n_eff': n / (1.0 + (n - 1.0) * m) if n > 1 else n, 'instruments_per_window': n, 'mean_squared_correlation': m, 'pairs': int(use.sum() // 2),
            'measure': 'breadth_v2'}


def effective_observations(sessions, horizon, n_eff):
    """Non-overlapping windows times effective independent instruments. None when breadth could not be measured."""
    return None if n_eff is None else sessions / horizon * n_eff


def detectable_ic(effective):
    """The smallest mean rank correlation the period can detect (one-sided 5%, 80% power). None when not measurable."""
    if effective is None or effective <= 0:
        return None
    return POWER_FACTOR / math.sqrt(effective)


def testability(ic) -> str:
    if ic is None:
        return NOT_MEASURABLE
    return TESTABLE if ic <= REFERENCE_IC else WEAKLY_TESTABLE if ic <= WEAK_IC else NOT_TESTABLE


def family_verdict(family, *, e_train, holdout_ic, regimes_met, bear_markets_in_training=0, training_years=0.0, sequence_share=None) -> dict:
    """SUFFICIENT / BORDERLINE / INSUFFICIENT for one family at one horizon, with the reason."""
    reference, smallest, network, sequence = FAMILIES[family]
    test = testability(holdout_ic)
    if e_train is None or test == NOT_MEASURABLE:
        return {'family': family, 'verdict': INSUFFICIENT, 'holdout': test,
                'reasons': ['breadth could not be measured, so neither the effective training observations nor the holdout can be shown to meet a bar']}
    reasons = []
    if e_train < PER_PARAMETER * smallest:
        reasons.append(f'effective training observations {e_train:,.0f} are below {PER_PARAMETER} x the smallest configuration ({smallest:,} parameters)')
    if test == NOT_TESTABLE:
        reasons.append(f'the reserved holdout cannot detect a rank correlation below {holdout_ic:.3f} (bar {WEAK_IC})')
    if network:
        if bear_markets_in_training < NETWORK_BAR['bear_markets_in_training']:
            reasons.append(f'training holds {bear_markets_in_training} bear markets; a network needs {NETWORK_BAR["bear_markets_in_training"]}')
        if training_years < NETWORK_BAR['calendar_years_in_training']:
            reasons.append(f'training spans {training_years:.1f} years; a network needs {NETWORK_BAR["calendar_years_in_training"]}')
        if test != TESTABLE:
            reasons.append('a network needs a holdout that is testable at the reference rank correlation, not merely weakly testable')
        if sequence and (sequence_share is None or sequence_share < NETWORK_BAR['sequence_share']):
            reasons.append(f'fewer than {NETWORK_BAR["sequence_share"]:.0%} of samples have {NETWORK_BAR["sequence_sessions"]} consecutive sessions')
    if reasons:
        return {'family': family, 'verdict': INSUFFICIENT, 'reasons': reasons, 'holdout': test}
    if e_train >= PER_PARAMETER * reference and test == TESTABLE and regimes_met:
        return {'family': family, 'verdict': SUFFICIENT, 'reasons': [f'{e_train:,.0f} effective training observations against {PER_PARAMETER} x {reference:,} parameters; '
                                                                      'holdout testable; regime bar met'], 'holdout': test}
    why = []
    if e_train < PER_PARAMETER * reference:
        why.append(f'{e_train:,.0f} effective training observations are below {PER_PARAMETER} x the reference configuration ({reference:,} parameters)')
    if test != TESTABLE:
        why.append('the holdout is only weakly testable')
    if not regimes_met:
        why.append('the regime bar is not met')
    return {'family': family, 'verdict': BORDERLINE, 'reasons': why, 'holdout': test}


def no_data_verdicts() -> dict:
    """The verdict for every family when no strict training data exists at all."""
    return {family: {'family': family, 'verdict': INSUFFICIENT, 'holdout': NOT_TESTABLE,
                     'reasons': ['no strict point-in-time training rows exist: no validated historical market data is stored']} for family in FAMILIES}
