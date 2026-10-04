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
    """The naive baseline with the highest development mean IC. A session a baseline does not rank counts as 0 in its
    mean, so a constant forecast has mean IC 0 and a candidate is never tested against less than zero."""
    return max(sorted(baselines), key=lambda name: _zero_if_none(baselines[name]['dev_mean_ic']))


def strongest_loss_baseline(fold_losses: dict) -> str:
    """For a target judged by a loss: the naive baseline with the lowest mean development loss. A model that beats a weak
    naive forecast and loses to a stronger one has not beaten "the naive baseline"."""
    return min(sorted(fold_losses), key=lambda name: float(np.mean(fold_losses[name])))


def _zero_if_none(value):
    return 0.0 if value is None or not np.isfinite(value) else float(value)


def status(record, baselines: dict, *, holm_rejected, sufficient=True) -> tuple:
    """(status, reasons) for one ranking/regression/classification model against the naive baselines of its target.

    ``record`` and each baseline: {'dev_mean_ic', 'holdout_mean_ic', 'fold_ics', 'dev_ic_series', 'holdout_ic_series',
    'horizon'}; a classifier also has 'dev_log_loss' and 'naive_log_loss' (the lower of the base rate's and a coin
    flip's). Series cover every session of the period, with 0 where a model ranked nothing.

    Plan v2: a model that fails the data-sufficiency gate is EXPERIMENTAL whatever it scored (its result is not evidence
    for or against it); a challenger's paired development interval must be above zero against every naive baseline,
    not only the one that happened to score highest. Plan v3: its development mean IC must also be above what the same
    predictions earn with instrument identities shuffled ('dev_identity_p' at most 0.05); a record without that p-value
    has not passed."""
    reasons = []
    strongest = strongest_baseline(baselines)
    baseline = baselines[strongest]
    dev, base = _zero_if_none(record['dev_mean_ic']), _zero_if_none(baseline['dev_mean_ic'])
    below = dev <= 0 or dev <= base
    if below:
        reasons.append(f'development mean IC {dev:+.4f} is not above ' + ('zero' if dev <= 0 else f'the strongest baseline ({base:+.4f})'))
    if not sufficient:
        reasons.append(EXPERIMENTAL_INSUFFICIENT_DATA + ': fails the data-sufficiency gate; its result is not evidence for or against it, and it cannot be a challenger')
        return 'EXPERIMENTAL', reasons
    if below:
        return 'REJECTED', reasons
    horizon = int(record['horizon'])
    paired = {name: metrics.paired_difference(_series(record['dev_ic_series']), _series(other['dev_ic_series']), horizon=horizon) for name, other in baselines.items()}
    not_beaten = sorted(name for name, p in paired.items() if not (np.isfinite(p['low']) and p['low'] > 0))
    positive_folds = sum(1 for x in record['fold_ics'] if x is not None and np.isfinite(x) and x > 0)
    holdout, base_holdout = _zero_if_none(record['holdout_mean_ic']), _zero_if_none(baseline['holdout_mean_ic'])
    checks = {'paired development difference interval above zero against every naive baseline': not not_beaten,
              f'positive in at least {FOLDS_REQUIRED} of {len(record["fold_ics"])} folds': positive_folds >= FOLDS_REQUIRED,
              'holdout mean IC above zero and at least the strongest baseline’s': holdout > 0 and holdout >= base_holdout,
              f'development mean IC above the same predictions with instrument identities shuffled (p at most {metrics.IDENTITY_LEVEL})':
                  bool(np.isfinite(_nan_if_none(record.get('dev_identity_p'))) and record['dev_identity_p'] <= metrics.IDENTITY_LEVEL)}
    if record.get('dev_log_loss') is not None:
        checks['development log loss below the base rate and below a coin flip'] = record['dev_log_loss'] < record['naive_log_loss']
    failed = [name for name, ok in checks.items() if not ok]
    reasons += [f'not met: {name}' for name in failed]
    if not_beaten:
        reasons.append('interval not above zero against: ' + ', '.join(not_beaten))
    main = paired[strongest]
    reasons.append(f'paired development difference against {strongest} {main["estimate"]:+.4f} (90% interval {main["low"]:+.4f} to {main["high"]:+.4f}, {main["batches"]} batches)'
                   if np.isfinite(main['low']) else f'paired development difference against {strongest} {main["estimate"]:+.4f}: {main["batches"]} batches, too few for an interval')
    if failed:
        return 'EXPERIMENTAL', reasons
    paired_holdout = metrics.paired_difference(_series(record['holdout_ic_series']), _series(baseline['holdout_ic_series']), horizon=horizon)
    if holm_rejected and np.isfinite(paired_holdout['low']) and paired_holdout['low'] > 0:
        reasons.append('holdout mean IC above zero after Holm adjustment, and the paired holdout difference interval is above zero')
        return 'ELIGIBLE_FOR_FUTURE_REVIEW', reasons
    reasons.append('holdout does not establish the edge after adjustment for the number of models compared'
                   + ('' if np.isfinite(paired_holdout['low']) else f' (the holdout holds {paired_holdout["batches"]} batches: too few for any interval)'))
    return 'CHALLENGER', reasons


def loss_status(fold_losses, baseline_fold_losses, holdout_loss, baseline_holdout_loss) -> tuple:
    """Status for a quantile or risk model, by a loss where lower is better, against its strongest naive baseline.
    REJECTED only if worse on development; a tie is not worse."""
    pairs = [(a, b) for a, b in zip(fold_losses, baseline_fold_losses) if a is not None and b is not None and np.isfinite(a) and np.isfinite(b)]
    if not pairs:
        return 'EXPERIMENTAL', ['no development fold could be scored']
    better = sum(1 for a, b in pairs if a < b)
    mean_model, mean_base = float(np.mean([a for a, _ in pairs])), float(np.mean([b for _, b in pairs]))
    if mean_model > mean_base:
        return 'REJECTED', [f'development loss {mean_model:.6f} is worse than the naive baseline ({mean_base:.6f})']
    scored = holdout_loss is not None and baseline_holdout_loss is not None and np.isfinite(holdout_loss) and np.isfinite(baseline_holdout_loss)
    holdout_better = bool(scored and holdout_loss < baseline_holdout_loss)
    if mean_model < mean_base and better >= FOLDS_REQUIRED and holdout_better:
        return 'CHALLENGER', [f'below the naive baseline in {better} of {len(pairs)} folds and on the holdout']
    return 'EXPERIMENTAL', [('level with' if mean_model == mean_base else 'below') + f' the naive baseline on average, below it in {better} of {len(pairs)} folds; holdout '
                            + ('not scored' if not scored else 'below the baseline' if holdout_better else 'not below the baseline')]


def _series(values):
    return np.asarray([np.nan if v is None else v for v in values], dtype=float)


def fibonacci_verdict(comparisons: dict) -> tuple:
    """('YES' | 'NO' | 'INCONCLUSIVE', explanation) from {reference model: {'dev': interval record, 'holdout_difference': float}}.
    The rule needs both reference models; with fewer, or with a difference that could not be measured, the answer is INCONCLUSIVE."""
    if len(comparisons) < 2:
        return 'INCONCLUSIVE', 'a reference model did not run'
    lows = [_nan_if_none(c['dev'].get('low')) for c in comparisons.values()]
    highs = [_nan_if_none(c['dev'].get('high')) for c in comparisons.values()]
    points = [_nan_if_none(c['dev'].get('estimate')) for c in comparisons.values()]
    holdouts = [_nan_if_none(c.get('holdout_difference')) for c in comparisons.values()]
    if not (all(np.isfinite(points)) and all(np.isfinite(holdouts))):
        return 'INCONCLUSIVE', 'a difference could not be measured for a reference model'
    if all(np.isfinite(lows)) and all(x > 0 for x in lows) and all(x > 0 for x in holdouts):
        return 'YES', 'the development interval is above zero for every reference model and the holdout difference is positive for every one'
    if (all(np.isfinite(highs)) and all(x < MINIMUM_RELEVANT_IC for x in highs)) or (all(x <= 0 for x in points) and all(x <= 0 for x in holdouts)):
        return 'NO', ('the development interval rules out an improvement of 0.01 for every reference model' if all(np.isfinite(highs)) and all(x < MINIMUM_RELEVANT_IC for x in highs)
                      else 'the difference is at or below zero for every reference model on both development and holdout')
    return 'INCONCLUSIVE', 'the intervals include both no improvement and a material one, or the reference models and periods disagree'


def _nan_if_none(value):
    return float('nan') if value is None else float(value)


assert set(STATUSES) == {'EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW'}
