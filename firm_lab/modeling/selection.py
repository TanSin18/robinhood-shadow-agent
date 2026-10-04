"""Research status rules, fixed before the tournament ran (CHECKPOINT7_TOURNAMENT_PLAN.md, sections 5, 8 and 9).

A status is a research label. There is no production or live status and nothing here promotes, deploys or trades.
"""
from __future__ import annotations

import numpy as np

from . import EXPERIMENTAL_INSUFFICIENT_DATA, STATUSES, metrics

MINIMUM_RELEVANT_IC = 0.01
FOLDS_REQUIRED = 4


def participation_ratio(table) -> float:
    """The effective number of independent columns of a [session, instrument] label table: (sum of eigenvalues)^2 over
    the sum of squared eigenvalues of its correlation matrix. 22 instruments that all move together count as about one."""
    table = np.asarray(table, dtype=float)
    table = table[:, np.all(np.isfinite(table), axis=0)]
    if table.shape[1] < 2 or table.shape[0] < 3:
        return float(table.shape[1])
    values = np.clip(np.linalg.eigvalsh(np.corrcoef(table.T)), 0, None)
    return float(values.sum() ** 2 / np.sum(values ** 2))


def strongest_baseline(baselines: dict) -> str:
    """The naive baseline with the highest development mean IC; a baseline that ranks nothing (a constant) counts as 0."""
    def key(name):
        ic = baselines[name]['dev_mean_ic']
        return -1.0 if ic is None or not np.isfinite(ic) else ic
    return max(sorted(baselines), key=key)


def strongest_loss_baseline(fold_losses: dict) -> str:
    """For a target judged by a loss: the naive baseline with the lowest mean development loss. A model that beats a weak
    naive forecast and loses to a stronger one has not beaten "the naive baseline"."""
    return min(sorted(fold_losses), key=lambda name: float(np.mean(fold_losses[name])))


def _zero_if_none(value):
    return 0.0 if value is None or not np.isfinite(value) else float(value)


def status(record, baseline, *, holm_rejected, sufficient=True) -> tuple:
    """(status, reasons) for one ranking/regression/classification model against the strongest baseline.

    ``record``/``baseline``: {'dev_mean_ic', 'holdout_mean_ic', 'fold_ics', 'dev_ic_series', 'holdout_ic_series', 'horizon',
    and for a classifier 'dev_log_loss' with 'base_rate_log_loss'}."""
    reasons = []
    dev, base = _zero_if_none(record['dev_mean_ic']), _zero_if_none(baseline['dev_mean_ic'])
    if dev <= 0 or dev <= base:
        reasons.append(f'development mean IC {dev:+.4f} is not above ' + ('zero' if dev <= 0 else f'the strongest baseline ({base:+.4f})'))
        return 'REJECTED', reasons
    block = int(record['horizon'])
    paired = metrics.paired_difference(_series(record['dev_ic_series']), _series(baseline['dev_ic_series']), block=block)
    positive_folds = sum(1 for x in record['fold_ics'] if x is not None and np.isfinite(x) and x > 0)
    holdout, base_holdout = _zero_if_none(record['holdout_mean_ic']), _zero_if_none(baseline['holdout_mean_ic'])
    checks = {'paired development difference interval above zero': bool(np.isfinite(paired['low']) and paired['low'] > 0),
              f'positive in at least {FOLDS_REQUIRED} of {len(record["fold_ics"])} folds': positive_folds >= FOLDS_REQUIRED,
              'holdout mean IC above zero and at least the baseline': holdout > 0 and holdout >= base_holdout}
    if record.get('dev_log_loss') is not None:
        checks['development log loss below the base rate'] = record['dev_log_loss'] < record['base_rate_log_loss']
    if not sufficient:
        reasons.append(EXPERIMENTAL_INSUFFICIENT_DATA + ': fails the data-sufficiency gate; cannot be a challenger')
    failed = [name for name, ok in checks.items() if not ok]
    reasons += [f'not met: {name}' for name in failed]
    reasons.append(f'paired development difference {paired["estimate"]:+.4f} (90% interval {paired["low"]:+.4f} to {paired["high"]:+.4f})'
                   if np.isfinite(paired.get('low', np.nan)) else 'paired development difference: too few sessions for an interval')
    if failed or not sufficient:
        return 'EXPERIMENTAL', reasons
    paired_holdout = metrics.paired_difference(_series(record['holdout_ic_series']), _series(baseline['holdout_ic_series']), block=block)
    if holm_rejected and np.isfinite(paired_holdout['low']) and paired_holdout['low'] > 0:
        reasons.append('holdout mean IC above zero after Holm adjustment, and the paired holdout difference interval is above zero')
        return 'ELIGIBLE_FOR_FUTURE_REVIEW', reasons
    reasons.append('holdout does not establish the edge after adjustment for the number of models compared')
    return 'CHALLENGER', reasons


def loss_status(fold_losses, baseline_fold_losses, holdout_loss, baseline_holdout_loss) -> tuple:
    """Status for a quantile or risk model, by a loss where lower is better, against its naive baseline."""
    pairs = [(a, b) for a, b in zip(fold_losses, baseline_fold_losses) if a is not None and b is not None]
    better = sum(1 for a, b in pairs if a < b)
    mean_model, mean_base = float(np.mean([a for a, _ in pairs])), float(np.mean([b for _, b in pairs]))
    if mean_model >= mean_base:
        return 'REJECTED', [f'development loss {mean_model:.6f} is not below the naive baseline ({mean_base:.6f})']
    if better >= FOLDS_REQUIRED and holdout_loss < baseline_holdout_loss:
        return 'CHALLENGER', [f'below the naive baseline in {better} of {len(pairs)} folds and on the holdout']
    return 'EXPERIMENTAL', [f'below the naive baseline on average, in {better} of {len(pairs)} folds; holdout '
                            + ('below' if holdout_loss < baseline_holdout_loss else 'not below') + ' the baseline']


def _series(values):
    return np.asarray([np.nan if v is None else v for v in values], dtype=float)


def fibonacci_verdict(comparisons: dict) -> tuple:
    """('YES' | 'NO' | 'INCONCLUSIVE', explanation) from {reference model: {'dev': bootstrap record, 'holdout_difference': float}}."""
    lows = [c['dev']['low'] for c in comparisons.values()]
    highs = [c['dev']['high'] for c in comparisons.values()]
    points = [c['dev']['estimate'] for c in comparisons.values()]
    holdouts = [c['holdout_difference'] for c in comparisons.values()]
    if all(np.isfinite(lows)) and all(x > 0 for x in lows) and all(x > 0 for x in holdouts):
        return 'YES', 'the development interval is above zero for every reference model and the holdout difference is positive for every one'
    if (all(np.isfinite(highs)) and all(x < MINIMUM_RELEVANT_IC for x in highs)) or (all(x <= 0 for x in points) and all(x <= 0 for x in holdouts)):
        return 'NO', ('the development interval rules out an improvement of 0.01 for every reference model' if all(x < MINIMUM_RELEVANT_IC for x in highs)
                      else 'the difference is at or below zero for every reference model on both development and holdout')
    return 'INCONCLUSIVE', 'the intervals include both no improvement and a material one, or the reference models and periods disagree'


assert set(STATUSES) == {'EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW'}
