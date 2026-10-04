"""The validation tournament: every model family under the same purged walk-forward design, on the same samples.

Design, fixed before any model was fitted (``docs/firm_lab/CHECKPOINT7_TOURNAMENT_PLAN.md``):

* one common sample: rows with at least 63 sessions of history and a label for every horizon;
* expanding walk-forward over the development period, five validation blocks, purge of 20 sessions (the longest
  label), embargo of 5 sessions;
* a final holdout: the last fifth of the labelled sessions, separated from development by purge and embargo, read once;
* configurations chosen inside each training window on an inner purged block, never on the block being predicted.

Complexity earns nothing. A model is compared with the strongest naive baseline, on sessions, with overlap respected.
"""
from __future__ import annotations

import time

import numpy as np

from . import deep, metrics, models, splits, targets
from .dataset import MINIMUM_HISTORY, sequences

PLAN_VERSION = 'checkpoint7-tournament-plan-v1'
PURGE = targets.MAX_HORIZON
EMBARGO = 5
FOLDS = 5
MINIMUM_TRAIN = 80
HOLDOUT_FRACTION = 0.2
TOP_K = 5


def eligible_rows(data) -> np.ndarray:
    """Rows of the common sample: enough history, and a label for every horizon and every risk target."""
    ok = data.row_session >= MINIMUM_HISTORY
    for name in targets.ALL:
        ok &= np.isfinite(data.y[name])
    return np.flatnonzero(ok)


def design(data) -> dict:
    rows = eligible_rows(data)
    sessions = np.unique(data.row_session[rows])
    if not len(sessions) or tuple(sessions) != tuple(range(sessions[0], sessions[-1] + 1)):
        raise ValueError('LABELLED_SESSIONS_ARE_NOT_CONTIGUOUS')
    definition = splits.walk_forward(int(sessions[0]), int(sessions[-1]), horizon=PURGE, embargo=EMBARGO, folds=FOLDS,
                                     minimum_train=MINIMUM_TRAIN, holdout_fraction=HOLDOUT_FRACTION)
    problems = splits.check(definition)
    if problems:
        raise ValueError('INVALID_SPLIT:' + '; '.join(problems))
    return definition


def _inputs(data, rows, columns, sequence):
    if sequence:
        windows, full = sequences(data, rows, columns, deep.SEQUENCE_LENGTH)
        return windows, full
    return data.X[np.ix_(rows, columns)], np.ones(len(rows), dtype=bool)


def _context(data, rows, columns, seed):
    return {'instrument': data.row_instrument[rows], 'session': data.row_session[rows], 'feature_names': [data.feature_names[c] for c in columns],
            'seed': seed, 'horizon': PURGE}


def _target(data, target, rows):
    if isinstance(target, (tuple, list)):
        return np.column_stack([data.y[t][rows] for t in target])
    return data.y[target][rows]


def _score(kind, y, prediction, session, quantile=None) -> float:
    """The inner selection criterion, higher is better. Regression: mean session rank correlation. Classification:
    negative log loss. Quantile: negative pinball loss."""
    if prediction.ndim > 1:
        prediction, y = prediction[:, 0], y[:, 0]
    if kind == models.CLASSIFICATION:
        return -metrics.classification(y, prediction)['log_loss']
    if kind == models.QUANTILE:
        return -metrics.pinball(y, prediction, quantile)
    ic = metrics.session_ic(y, prediction, session)[1]
    ic = ic[np.isfinite(ic)]
    return float(ic.mean()) if len(ic) else -float(np.sqrt(np.mean((prediction - y) ** 2)))


def fit_predict(cls, params, data, target, columns, train_rows, predict_rows, seed=0):
    """Fits one configuration on ``train_rows`` and predicts ``predict_rows``. Returns (model, predictions, mask of
    predicted rows that could be predicted: a sequence model needs a full window)."""
    model = cls(**params)
    sequence = getattr(model, 'sequence', False)
    X_train, full_train = _inputs(data, train_rows, columns, sequence)
    X_test, full_test = _inputs(data, predict_rows, columns, sequence)
    train_rows = train_rows[full_train]
    model.fit(X_train[full_train], _target(data, target, train_rows), _context(data, train_rows, columns, seed))
    prediction = np.full((len(predict_rows),) + (() if not isinstance(target, (tuple, list)) else (len(target),)), np.nan)
    if full_test.any():
        prediction[full_test] = model.predict(X_test[full_test], _context(data, predict_rows[full_test], columns, seed))
    return model, prediction, full_test


def run(spec, data, definition, *, seed=0, keep_models=False) -> dict:
    """Evaluates one specification over every fold and the holdout.

    ``spec``: {'name', 'cls', 'grid': [params, ...], 'target': name or tuple of names, 'columns': [feature indices],
               'quantile': q (quantile models only)}.
    Returns the out-of-sample predictions with the rows they belong to, the configuration chosen in each block with every
    configuration's inner score, parameter counts and timings."""
    cls, grid, target = spec['cls'], list(spec['grid']), spec['target']
    columns = list(spec['columns'])
    missing = [m for m in cls.requires if not models.available(m)]
    if missing:
        return {'name': spec['name'], 'status': 'NOT_RUN', 'reason': 'dependency unavailable: ' + ', '.join(missing)}
    rows = eligible_rows(data)
    session_of = data.row_session
    blocks, started = [], time.time()
    for block in list(definition['folds']) + [definition['holdout']]:
        train = rows[np.isin(session_of[rows], block.train)]
        test = rows[np.isin(session_of[rows], block.validation)]
        tried = []
        chosen = grid[0]
        if len(grid) > 1:
            inner = splits.inner(block.train, horizon=PURGE, embargo=EMBARGO)
            inner_train = rows[np.isin(session_of[rows], inner.train)]
            inner_test = rows[np.isin(session_of[rows], inner.validation)]
            best = -np.inf
            for params in grid:
                _, prediction, full = fit_predict(cls, params, data, target, columns, inner_train, inner_test, seed)
                score = _score(cls.kind, _target(data, target, inner_test)[full], prediction[full], session_of[inner_test][full], spec.get('quantile'))
                tried.append({'params': params, 'inner_score': None if not np.isfinite(score) else float(score)})
                if np.isfinite(score) and score > best:
                    best, chosen = score, params
        model, prediction, full = fit_predict(cls, chosen, data, target, columns, train, test, seed)
        entry = {'block': block.name, 'rows': test, 'prediction': prediction, 'predicted': full, 'chosen': chosen, 'tried': tried,
                 'train_rows': int(len(train)), 'train_sessions': int(len(np.unique(session_of[train]))),
                 'parameters': int(getattr(model, 'parameter_count', 0)), 'describe': model.describe()}
        if keep_models:
            entry['model'] = model
        if hasattr(model, 'predict_seeds') and full.any():
            sequence = getattr(model, 'sequence', False)
            X_test, _ = _inputs(data, test[full], columns, sequence)
            entry['seed_predictions'] = model.predict_seeds(X_test)
        blocks.append(entry)
    return {'name': spec['name'], 'status': 'RUN', 'family': cls.family, 'kind': cls.kind, 'target': target, 'columns': columns,
            'blocks': blocks, 'seconds': round(time.time() - started, 1), 'configurations_tried': len(grid), 'quantile': spec.get('quantile')}


def gather(result, part) -> tuple:
    """(rows, predictions) of the development folds ('dev') or of the holdout ('holdout'), predicted rows only."""
    blocks = [b for b in result['blocks'] if (b['block'] == 'final_holdout') == (part == 'holdout')]
    rows = np.concatenate([b['rows'][b['predicted']] for b in blocks]) if blocks else np.array([], dtype=int)
    prediction = np.concatenate([b['prediction'][b['predicted']] for b in blocks]) if blocks else np.array([])
    return rows, prediction


def score(result, data, *, part, head=0, target=None, draws=2000) -> dict:
    """The metric record of one result on one part. A classification model is also scored as a ranking of the 10-session
    excess return, so that every model answers the same ranking question."""
    rows, prediction = gather(result, part)
    if not len(rows):
        return {'n': 0}
    if prediction.ndim > 1:
        prediction = prediction[:, head]
    name = target or (result['target'][head] if isinstance(result['target'], (tuple, list)) else result['target'])
    y, session = data.y[name][rows], data.row_session[rows]
    kind = models.CLASSIFICATION if name == targets.CLASSIFICATION else result['kind'] if name not in targets.REGRESSION + targets.RISK else models.REGRESSION
    if result['kind'] == models.QUANTILE:
        return {'n': int(len(rows)), 'quantile': result['quantile'], 'pinball': metrics.pinball(y, prediction, result['quantile'])}
    horizon = int(name.rsplit('_', 1)[1]) if name[-1].isdigit() else targets.RISK_HORIZON
    out = {'n': int(len(rows)), 'sessions': int(len(np.unique(session)))}
    if kind == models.CLASSIFICATION:
        out['classification'] = metrics.classification(y, prediction)
        ranked = data.y[targets.PRIMARY][rows]
        out['ranking'] = metrics.ranking(ranked, prediction, session, horizon=10, k=TOP_K, draws=draws)
    else:
        out['regression'] = metrics.regression(y, prediction)
        out['buckets'] = metrics.bucket_means(y, prediction)
        out['ranking'] = metrics.ranking(y, prediction, session, horizon=horizon, k=TOP_K, draws=draws)
    return out


def fold_ics(result, data, *, head=0, target=None) -> list:
    """Mean session rank correlation in each development fold: the stability record."""
    out = []
    name = target or (result['target'][head] if isinstance(result['target'], (tuple, list)) else result['target'])
    name = targets.PRIMARY if name == targets.CLASSIFICATION else name
    for b in result['blocks']:
        if b['block'] == 'final_holdout' or not b['predicted'].any():
            continue
        rows, prediction = b['rows'][b['predicted']], b['prediction'][b['predicted']]
        if prediction.ndim > 1:
            prediction = prediction[:, head]
        ic = metrics.session_ic(data.y[name][rows], prediction, data.row_session[rows])[1]
        ic = ic[np.isfinite(ic)]
        out.append(float(ic.mean()) if len(ic) else float('nan'))
    return out


def average_pair_correlation(data, target=targets.PRIMARY) -> float:
    """The mean correlation between instruments' labels over the development sessions: how far from independent the
    cross-section is."""
    rows = eligible_rows(data)
    sessions = np.unique(data.row_session[rows])
    table = np.full((len(sessions), len(data.instruments)), np.nan)
    position = {s: k for k, s in enumerate(sessions)}
    for r in rows:
        table[position[data.row_session[r]], data.row_instrument[r]] = data.y[target][r]
    table = table[:, np.all(np.isfinite(table), axis=0)]
    if table.shape[1] < 2:
        return 0.0
    c = np.corrcoef(table.T)
    return float(c[np.triu_indices_from(c, 1)].mean())
