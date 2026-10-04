"""Evaluation metrics and the statistics that keep them honest. numpy, and scipy for the t distribution.

Stock-session rows are not independent observations: instruments of one session share the market move, and a 10-session
label overlaps the labels of the nine sessions before it. Uncertainty is therefore never computed as if every row were
a fresh draw. A per-session series is cut into consecutive batches two label horizons long, and the interval is a
Student t interval on the batch means (``batch_interval``). With fewer than three batches there is no interval and no
p-value: the data cannot support one, and saying so is the result.

Plan v1 used a percentile moving-block bootstrap with blocks one horizon long. The independent review showed that it
is anti-conservative at this sample size (a no-information ranking had a "90% interval" above zero 9% to 14% of the
time on development sessions and up to 25% on the holdout, and its tail share could be exactly 0). It was replaced; see
the plan's amendments.

A session a model does not rank (every prediction equal) has rank correlation 0 for that model. Every model is
therefore averaged, compared and paired over the same sessions.

Sharpe is deliberately absent: no trading strategy is registered, so there is no return stream to take a ratio of.
"""
from __future__ import annotations

import numpy as np

MINIMUM_BATCHES = 3
BATCH_HORIZONS = 2
INTERVAL_METHOD = 'Student t on the means of consecutive batches two label horizons long; no interval below three batches'


def _finite(*arrays):
    keep = np.ones(len(arrays[0]), dtype=bool)
    for a in arrays:
        keep &= np.isfinite(np.asarray(a, dtype=float))
    return [np.asarray(a, dtype=float)[keep] for a in arrays]


def rank(values):
    """Average ranks (ties share the mean rank), 1-based."""
    values = np.asarray(values, dtype=float)
    order = np.argsort(values, kind='mergesort')
    ranks = np.empty(len(values), dtype=float)
    ranks[order] = np.arange(1, len(values) + 1)
    unique, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, weights=ranks)
    return (sums / counts)[inverse]


def pearson(a, b):
    a, b = _finite(a, b)
    if len(a) < 3 or a.std() == 0 or b.std() == 0:
        return float('nan')
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a, b):
    a, b = _finite(a, b)
    if len(a) < 3:
        return float('nan')
    return pearson(rank(a), rank(b))


# ---------------------------------------------------------------------------- regression
def regression(y, prediction) -> dict:
    y, prediction = _finite(y, prediction)
    if not len(y):
        return {'n': 0}
    error = prediction - y
    total = float(np.sum((y - y.mean()) ** 2))
    moved = prediction != 0
    return {'n': int(len(y)), 'mae': float(np.mean(np.abs(error))), 'rmse': float(np.sqrt(np.mean(error ** 2))),
            # R2 against the sample mean of the evaluated period (which no model could know) and against a zero forecast (which every model could make)
            'r2': float(1 - np.sum(error ** 2) / total) if total > 0 else float('nan'),
            'r2_vs_zero': float(1 - np.sum(error ** 2) / np.sum(y ** 2)) if np.sum(y ** 2) > 0 else float('nan'),
            'pearson': pearson(y, prediction), 'spearman': spearman(y, prediction),
            'directional_accuracy': float(np.mean(np.sign(prediction[moved]) == np.sign(y[moved]))) if moved.any() else float('nan'),
            'share_with_a_direction': float(np.mean(moved))}


def bucket_means(y, prediction, buckets=5) -> list:
    """Mean realised target by prediction bucket, lowest prediction first."""
    y, prediction = _finite(y, prediction)
    if len(y) < buckets * 2 or np.all(prediction == prediction[0]):
        return []
    edges = np.quantile(prediction, np.linspace(0, 1, buckets + 1))
    index = np.clip(np.searchsorted(edges, prediction, side='right') - 1, 0, buckets - 1)
    return [{'bucket': k + 1, 'n': int((index == k).sum()), 'mean_prediction': float(prediction[index == k].mean()) if (index == k).any() else None,
             'mean_realized': float(y[index == k].mean()) if (index == k).any() else None} for k in range(buckets)]


# ---------------------------------------------------------------------------- classification
def roc_auc(y, score):
    y, score = _finite(y, score)
    positives, negatives = int((y == 1).sum()), int((y == 0).sum())
    if not positives or not negatives:
        return float('nan')
    ranks = rank(score)
    return float((ranks[y == 1].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def average_precision(y, score):
    """Area under the precision-recall curve as a step function over distinct score thresholds. Rows that share a score
    enter together, so the result does not depend on the order of the rows."""
    y, score = _finite(y, score)
    positives = float((y == 1).sum())
    if not positives:
        return float('nan')
    values, inverse = np.unique(-score, return_inverse=True)
    hits = np.bincount(inverse, weights=(y == 1).astype(float), minlength=len(values))
    counts = np.bincount(inverse, minlength=len(values))
    true_positives, predicted = np.cumsum(hits), np.cumsum(counts)
    precision, recall = true_positives / predicted, true_positives / positives
    return float(np.sum(np.diff(np.concatenate([[0.0], recall])) * precision))


def classification(y, probability, bins=10) -> dict:
    y, probability = _finite(y, probability)
    if not len(y):
        return {'n': 0}
    p = np.clip(probability, 1e-6, 1 - 1e-6)
    edges = np.linspace(0, 1, bins + 1)
    index = np.clip(np.searchsorted(edges, probability, side='right') - 1, 0, bins - 1)
    table, error = [], 0.0
    for k in range(bins):
        mask = index == k
        if mask.any():
            mean_p, rate = float(probability[mask].mean()), float(y[mask].mean())
            error += mask.mean() * abs(mean_p - rate)
            table.append({'bucket': f'{edges[k]:.1f}-{edges[k + 1]:.1f}', 'n': int(mask.sum()), 'mean_probability': mean_p, 'observed_rate': rate})
    return {'n': int(len(y)), 'base_rate': float(y.mean()), 'roc_auc': roc_auc(y, probability), 'pr_auc': average_precision(y, probability),
            'log_loss': float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))), 'brier': float(np.mean((probability - y) ** 2)),
            'calibration_error': float(error), 'accuracy': float(np.mean((probability > 0.5) == (y == 1))), 'reliability': table}


# ---------------------------------------------------------------------------- cross-sectional ranking
def session_ic(y, prediction, session) -> tuple:
    """(sessions in order, Spearman rank correlation across the instruments of each session). A session whose predictions
    are all equal has no ranking and gives nan."""
    y, prediction, session = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float), np.asarray(session)
    days = np.unique(session)
    values = []
    for day in days:
        mask = session == day
        values.append(spearman(y[mask], prediction[mask]))
    return days, np.asarray(values, dtype=float)


def _tail_mean(values, scores, k, highest):
    """Mean of ``values`` over the k highest (or lowest) scores. Rows tied across the cut share the remaining places, so
    the answer is the expected value under a random tie-break and does not depend on row order."""
    order = -scores if highest else scores
    total, taken = 0.0, 0
    for level in np.unique(order):
        group = values[order == level]
        room = k - taken
        if len(group) <= room:
            total, taken = total + group.sum(), taken + len(group)
        else:
            total, taken = total + room * group.mean(), k
        if taken >= k:
            break
    return total / k


def top_bottom(y, prediction, session, *, k=5) -> dict:
    """Per session: mean realised target of the k highest-predicted instruments, of the k lowest, and of all. No weights,
    no costs, no holding: a description of the ranking, not a portfolio."""
    y, prediction, session = np.asarray(y, dtype=float), np.asarray(prediction, dtype=float), np.asarray(session)
    top, bottom, everything, hit = [], [], [], []
    for day in np.unique(session):
        mask = (session == day) & np.isfinite(y) & np.isfinite(prediction)
        if mask.sum() < 2 * k or np.all(prediction[mask] == prediction[mask][0]):
            continue
        values, scores = y[mask], prediction[mask]
        top.append(_tail_mean(values, scores, k, True))
        bottom.append(_tail_mean(values, scores, k, False))
        everything.append(values.mean())
        hit.append(_tail_mean((values > 0).astype(float), scores, k, True))
    if not top:
        return {'sessions': 0}
    top, bottom, everything = np.asarray(top), np.asarray(bottom), np.asarray(everything)
    return {'sessions': int(len(top)), 'k': k, 'top_mean': float(top.mean()), 'bottom_mean': float(bottom.mean()), 'all_mean': float(everything.mean()),
            'top_minus_bottom': float((top - bottom).mean()), 'top_minus_all': float((top - everything).mean()), 'top_hit_rate': float(np.mean(hit)),
            'series_top_minus_bottom': (top - bottom).tolist()}


# ---------------------------------------------------------------------------- distribution
def pinball(y, prediction, quantile) -> float:
    y, prediction = _finite(y, prediction)
    difference = y - prediction
    return float(np.mean(np.maximum(quantile * difference, (quantile - 1) * difference))) if len(y) else float('nan')


def coverage(y, lower, upper) -> dict:
    y, lower, upper = _finite(y, lower, upper)
    if not len(y):
        return {'n': 0}
    return {'n': int(len(y)), 'coverage': float(np.mean((y >= lower) & (y <= upper))), 'mean_width': float(np.mean(upper - lower)),
            'crossed': float(np.mean(upper < lower))}


# ---------------------------------------------------------------------------- inference that respects overlap
def non_overlapping(values, horizon) -> np.ndarray:
    """Every ``horizon``-th value of a per-session series: values whose label windows do not overlap."""
    return np.asarray(values, dtype=float)[::max(1, int(horizon))]


def filled(series) -> np.ndarray:
    """A per-session series with "no ranking" counted as 0: the rank correlation of a model that ranked nothing."""
    series = np.asarray(series, dtype=float)
    return np.where(np.isfinite(series), series, 0.0)


def batch_interval(series, *, horizon) -> dict:
    """The mean of a per-session series with a 90% Student t interval on batch means, and the one-sided p-value of
    "the mean is not above zero". Batches are consecutive, at least two label horizons long, so that neighbouring batch
    means share little of any label window. Fewer than three batches: no interval and no p-value.

    Under a worst-case series (a moving sum over the whole label window) the one-sided 5% test rejects 5% to 6% of the
    time at every sample size used here; a regression test holds it to that."""
    from scipy import stats
    series = np.asarray(series, dtype=float)
    series = series[np.isfinite(series)]
    n, length = len(series), BATCH_HORIZONS * max(1, int(horizon))
    batches = n // length
    out = {'n': int(n), 'batches': int(batches), 'batch_length': int(length), 'estimate': float(series.mean()) if n else float('nan'),
           'low': float('nan'), 'high': float('nan'), 'p_not_positive': float('nan'), 'method': INTERVAL_METHOD}
    if batches < MINIMUM_BATCHES:
        out['note'] = f'{batches} batches of {length} sessions: too few for an interval'
        return out
    means = np.array([chunk.mean() for chunk in np.array_split(series, batches)])
    error = float(means.std(ddof=1) / np.sqrt(batches))
    if error == 0:
        out.update({'low': out['estimate'], 'high': out['estimate'], 'p_not_positive': 1.0, 'note': 'no variation between batches: nothing to test'})
        return out
    width = float(stats.t.ppf(0.95, batches - 1)) * error
    out.update({'low': out['estimate'] - width, 'high': out['estimate'] + width, 'standard_error': error,
                'p_not_positive': float(stats.t.sf(out['estimate'] / error, batches - 1))})
    return out


def paired_difference(series_a, series_b, *, horizon) -> dict:
    """Interval of the per-session difference a - b over every session (a session either did not rank counts as 0 for
    it). The pairing removes what the two share."""
    return batch_interval(filled(series_a) - filled(series_b), horizon=horizon)


def holm(p_values: dict, level=0.10) -> dict:
    """Holm's step-down control of the family-wise error rate over a family of tests. {name: {'p', 'adjusted', 'rejected'}}.
    A missing p-value (no interval could be formed) counts as 1."""
    items = sorted(((1.0 if p is None or not np.isfinite(p) else float(p)), name) for name, p in p_values.items())
    out, running, m = {}, 0.0, len(items)
    for position, (p, name) in enumerate(items):
        running = max(running, min(1.0, (m - position) * p))
        out[name] = {'p': p, 'adjusted': running, 'rejected': False, 'family_size': m}
    alive = True
    for p, name in items:
        alive = alive and out[name]['adjusted'] <= level
        out[name]['rejected'] = bool(alive)
    return out


def ranking(y, prediction, session, *, horizon, k=5) -> dict:
    """The cross-sectional ranking record of one model on one evaluation period. The mean is over every session of the
    period; a session without a ranking counts as 0."""
    days, raw = session_ic(y, prediction, session)
    ic = filled(raw)
    ranked = int(np.isfinite(raw).sum())
    interval = batch_interval(ic, horizon=horizon)
    spread = top_bottom(y, prediction, session, k=k)
    independent = non_overlapping(ic, horizon)
    out = {'sessions': int(len(days)), 'sessions_with_a_ranking': ranked, 'non_overlapping_windows': int(len(days) // max(1, horizon)),
           'batches': interval['batches'], 'batch_length': interval['batch_length'],
           'mean_ic': float(ic.mean()) if len(ic) else float('nan'), 'median_ic': float(np.median(ic)) if len(ic) else float('nan'),
           'mean_ic_on_ranked_sessions_only': float(np.nanmean(raw)) if ranked else float('nan'),
           'share_positive_ic': float(np.mean(ic > 0)) if len(ic) else float('nan'),
           'mean_ic_non_overlapping': float(independent.mean()) if len(independent) else float('nan'),
           'ic_interval_90': [interval['low'], interval['high']], 'p_ic_not_positive': interval['p_not_positive'], 'ic_series': ic.tolist(),
           'top_bottom': {key: value for key, value in spread.items() if key != 'series_top_minus_bottom'}}
    if spread.get('sessions'):
        gap = batch_interval(np.asarray(spread['series_top_minus_bottom']), horizon=horizon)
        out['top_minus_bottom_interval_90'] = [gap['low'], gap['high']]
    return out
