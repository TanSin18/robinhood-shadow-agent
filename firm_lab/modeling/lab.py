"""The laboratory run: executes the tournament plan once and writes the registry and the report. Manual and local.

Order of work: dataset and split design; baselines; linear, tree and neural families on every regression horizon and on
the classification target; sequence and transformer models; multi-task; distribution and risk targets; feature-family
ablation; specialists, ensembles, gating and meta-label; uncertainty, calibration, disagreement and conditional views;
importance; statuses by the rules fixed in advance. No step turns a prediction into an action.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np

from . import BENCHMARK, EXPERIMENTAL_INSUFFICIENT_DATA, INSUFFICIENT_DATA, TIME_POLICY, WARNING, dataset, deep, metrics, models, registry, selection, splits, targets, tournament
from .dataset import GROUPS

ALL_GROUPS = tuple(name for name, _ in GROUPS)
TECHNICAL = ('technical_baseline',)
SEQUENCE_GROUPS = ('technical_baseline', 'structure')
QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)
SPECIALISTS = {'technical': ('technical_baseline', 'fibonacci', 'structure'), 'fundamental': ('fundamentals',), 'event': ('earnings',),
               'sector': ('sector',), 'macro': ('macro',)}
# A plausible round-trip cost range for liquid funds and large stocks, per pair of legs, in return units. Stated, not fitted.
COST_RANGE = (0.0010, 0.0040)
RESEARCH_THRESHOLDS = (0.0, 0.005, 0.01)


def _spec(name, cls, target, columns, grid=None, **extra):
    return {'name': name, 'cls': cls, 'grid': grid or [{}], 'target': target, 'columns': columns, **extra}


def _strip(record):
    """A metric record without its long per-session series (those are stored with the predictions)."""
    if not isinstance(record, dict):
        return record
    return {k: _strip(v) for k, v in record.items() if k not in ('ic_series',)}


def summarize(result, data, *, head=0, target=None, draws=2000) -> dict:
    name = target or (result['target'][head] if isinstance(result['target'], (tuple, list)) else result['target'])
    dev = tournament.score(result, data, part='dev', head=head, target=name, draws=draws)
    holdout = tournament.score(result, data, part='holdout', head=head, target=name, draws=draws)
    horizon = int(name.rsplit('_', 1)[1]) if name[-1].isdigit() else targets.RISK_HORIZON
    out = {'target': name, 'horizon': horizon, 'dev': _strip(dev), 'holdout': _strip(holdout), 'fold_ics': tournament.fold_ics(result, data, head=head, target=name),
           'dev_mean_ic': dev.get('ranking', {}).get('mean_ic'), 'holdout_mean_ic': holdout.get('ranking', {}).get('mean_ic'),
           'dev_ic_series': dev.get('ranking', {}).get('ic_series', []), 'holdout_ic_series': holdout.get('ranking', {}).get('ic_series', []),
           'p_holdout_ic_not_positive': holdout.get('ranking', {}).get('p_ic_not_positive')}
    if 'classification' in dev:
        out['dev_log_loss'] = dev['classification']['log_loss']
    return out


def fold_losses(result, data, target, loss) -> tuple:
    """(per-fold losses, holdout loss) for a model judged by a loss."""
    folds, holdout = [], None
    for b in result['blocks']:
        rows, prediction = b['rows'][b['predicted']], b['prediction'][b['predicted']]
        value = loss(data.y[target][rows], prediction)
        if b['block'] == 'final_holdout':
            holdout = value
        else:
            folds.append(value)
    return folds, holdout


def rmse(y, prediction):
    return float(np.sqrt(np.mean((np.asarray(prediction) - np.asarray(y)) ** 2)))


class Lab:
    def __init__(self, path, *, log=print, quick=False, draws=2000):
        self.path, self.log, self.quick, self.draws = path, log, quick, draws
        self.results, self.summaries, self.configurations = {}, {}, 0
        self.started = time.time()

    # ------------------------------------------------------------------ plumbing
    def columns(self, groups):
        return self.data.columns(groups)

    def run(self, key, spec, **kw):
        result = tournament.run(spec, self.data, self.definition, **kw)
        self.results[key] = result
        if result['status'] == 'RUN':
            self.configurations += result['configurations_tried'] * len(result['blocks'])
        self.log(f'[{time.time() - self.started:7.0f}s] {key}: {result["status"]}' + (f' in {result["seconds"]}s' if result['status'] == 'RUN' else f' ({result["reason"]})'))
        return result

    def summary(self, key, **kw):
        result = self.results[key]
        if result['status'] != 'RUN':
            self.summaries[key] = {'status': 'NOT_RUN', 'reason': result['reason']}
        else:
            self.summaries[key] = summarize(result, self.data, draws=self.draws, **kw)
        return self.summaries[key]

    # ------------------------------------------------------------------ phases
    def prepare(self):
        self.data = dataset.build(self.path)
        dataset.register(self.path, self.data)
        self.definition = tournament.design(self.data)
        d = self.data
        rows = tournament.eligible_rows(d)
        self.rows = rows
        sessions = np.unique(d.row_session[rows])
        table = np.full((len(sessions), len(d.instruments)), np.nan)
        position = {s: k for k, s in enumerate(sessions)}
        for r in rows:
            table[position[d.row_session[r]], d.row_instrument[r]] = d.y[targets.PRIMARY][r]
        self.breadth = selection.participation_ratio(table)
        self.pair_correlation = tournament.average_pair_correlation(d)
        self.log(f'dataset {d.manifest["dataset_hash"][:12]}: {len(rows)} samples, {len(sessions)} sessions, {len(d.feature_names)} features; '
                 f'effective independent instruments {self.breadth:.1f}')

    def baselines(self):
        full = self.columns(ALL_GROUPS)
        for target in targets.REGRESSION:
            self.run(f'zero/{target}', _spec('zero', models.Zero, target, full))
            self.run(f'historical_mean/{target}', _spec('historical_mean', models.HistoricalMean, target, full))
            self.run(f'instrument_mean/{target}', _spec('instrument_mean', models.InstrumentMean, target, full))
            for name, feature in (('momentum_20', 'return20'), ('momentum_63', 'return63'), ('momentum_126', 'return126')):
                self.run(f'{name}/{target}', _spec(name, models.SingleFeature, target, full, grid=[{'feature': feature}]))
            self.run(f'registered_style_momentum/{target}', _spec('registered_style_momentum', models.SingleFeature, target, full,
                                                                 grid=[{'feature': 'return126', 'gate': 'sma200_distance'}]))
        self.run(f'base_rate/{targets.CLASSIFICATION}', _spec('base_rate', models.BaseRate, targets.CLASSIFICATION, full))

    def families(self):
        full = self.columns(ALL_GROUPS)
        small = [self.data.feature_names.index(n) for n in models.SMALL_TECHNICAL]
        for target in targets.REGRESSION:
            self.run(f'least_squares_small/{target}', _spec('least_squares_small', models.LeastSquares, target, small))
            self.run(f'ridge/{target}', _spec('ridge', models.Ridge, target, full, grid=models.GRIDS['ridge']))
            self.run(f'elastic_net/{target}', _spec('elastic_net', models.ElasticNet, target, full, grid=models.GRIDS['elastic_net']))
            self.run(f'xgboost/{target}', _spec('xgboost', models.XGBoost, target, full, grid=models.GRIDS['xgboost']))
            self.run(f'lightgbm/{target}', _spec('lightgbm', models.LightGBM, target, full, grid=models.GRIDS['lightgbm']))
            self.run(f'catboost/{target}', _spec('catboost', models.CatBoost, target, full, grid=models.GRIDS['catboost']))
            self.run(f'mlp/{target}', _spec('mlp', deep.MLP, target, full))
        c = targets.CLASSIFICATION
        self.run(f'logistic/{c}', _spec('logistic', models.Logistic, c, full, grid=models.GRIDS['logistic']))
        self.run(f'xgboost/{c}', _spec('xgboost', models.XGBoostClassifier, c, full, grid=models.GRIDS['xgboost']))
        self.run(f'lightgbm/{c}', _spec('lightgbm', models.LightGBMClassifier, c, full, grid=models.GRIDS['lightgbm']))
        self.run(f'catboost/{c}', _spec('catboost', models.CatBoostClassifier, c, full, grid=models.GRIDS['catboost']))
        self.run(f'mlp/{c}', _spec('mlp', deep.MLP, c, full, grid=[{'heads': ('classification',)}]))

    def sequence_models(self):
        columns = self.columns(SEQUENCE_GROUPS)
        primary = targets.PRIMARY
        for name, cls in (('tcn', deep.TCN), ('gru', deep.GRU), ('lstm', deep.LSTM), ('transformer_encoder', deep.TransformerEncoder)):
            self.run(f'{name}/{primary}', _spec(name, cls, primary, columns))
        # the same rows and descriptors without the sequence, so the sequence itself is what is compared
        self.run(f'mlp_sequence_features/{primary}', _spec('mlp_sequence_features', deep.MLP, primary, columns))

    MULTI = (('excess_return_5', 'regression'), ('excess_return_10', 'regression'), ('excess_return_20', 'regression'),
             (targets.CLASSIFICATION, 'classification'), ('future_realized_vol_10', 'regression'))

    def multi_task(self):
        names, heads = tuple(n for n, _ in self.MULTI), tuple(h for _, h in self.MULTI)
        self.run('mlp_multi_task', _spec('mlp_multi_task', deep.MLP, names, self.columns(ALL_GROUPS), grid=[{'heads': heads}]))
        self.run('transformer_multi_task', _spec('transformer_multi_task', deep.TransformerEncoder, names, self.columns(SEQUENCE_GROUPS), grid=[{'heads': heads}]))

    def distribution(self):
        full, technical = self.columns(ALL_GROUPS), self.columns(TECHNICAL)
        for q in QUANTILES:
            tag = f'q{int(q * 100):02d}'
            self.run(f'train_quantile/{tag}', _spec('train_quantile', models.TrainQuantile, targets.PRIMARY, full, grid=[{'quantile': q}], quantile=q))
            self.run(f'linear_quantile/{tag}', _spec('linear_quantile', models.LinearQuantile, targets.PRIMARY, technical, grid=[{'quantile': q, 'alpha': 0.01}], quantile=q))
            self.run(f'lightgbm_quantile/{tag}', _spec('lightgbm_quantile', models.LightGBMQuantile, targets.PRIMARY, full,
                                                      grid=[{'quantile': q, 'num_leaves': 4, 'n_estimators': 100, 'learning_rate': 0.05}], quantile=q))

    def risk(self):
        full = self.columns(ALL_GROUPS)
        for target in targets.RISK:
            self.run(f'historical_mean/{target}', _spec('historical_mean', models.HistoricalMean, target, full))
            self.run(f'ridge/{target}', _spec('ridge', models.Ridge, target, full, grid=models.GRIDS['ridge']))
            self.run(f'lightgbm/{target}', _spec('lightgbm', models.LightGBM, target, full, grid=models.GRIDS['lightgbm']))
        self.run('volatility_persistence/future_realized_vol_10', _spec('volatility_persistence', models.SingleFeature, 'future_realized_vol_10', full,
                                                                        grid=[{'feature': 'realized_vol20'}]))

    def ablation(self):
        sets = [('technical_baseline', TECHNICAL)] + [(f'technical+{name}', TECHNICAL + (name,)) for name in ALL_GROUPS if name != 'technical_baseline'] + [('full', ALL_GROUPS)]
        self.ablation_sets = [name for name, _ in sets]
        for name, groups in sets:
            columns = self.columns(groups)
            self.run(f'ablation/ridge/{name}', _spec('ridge', models.Ridge, targets.PRIMARY, columns, grid=models.GRIDS['ridge']))
            self.run(f'ablation/lightgbm/{name}', _spec('lightgbm', models.LightGBM, targets.PRIMARY, columns, grid=models.GRIDS['lightgbm']))

    def specialists(self):
        for name, groups in SPECIALISTS.items():
            columns = self.columns(groups)
            self.run(f'specialist/{name}', _spec(f'specialist_{name}', models.LightGBM, targets.PRIMARY, columns, grid=models.GRIDS['lightgbm']), keep_models=False)

    # ------------------------------------------------------------------ combinations built from out-of-sample predictions
    def _inner_predictions(self, keys_specs, block):
        """For one outer block: each member's predictions on the inner tuning block (trained on the purged earlier part
        of the outer training window). What a combiner may learn from, since none of it touches the outer block."""
        d, rows = self.data, self.rows
        inner = splits.inner(block.train, horizon=tournament.PURGE, embargo=tournament.EMBARGO)
        train = rows[np.isin(d.row_session[rows], inner.train)]
        test = rows[np.isin(d.row_session[rows], inner.validation)]
        columns = []
        for key, spec in keys_specs:
            chosen = next(b['chosen'] for b in self.results[key]['blocks'] if b['block'] == block.name)
            _, prediction, _ = tournament.fit_predict(spec['cls'], chosen, d, spec['target'], spec['columns'], train, test)
            columns.append(prediction)
        return test, np.column_stack(columns)

    def ensembles(self):
        d = self.data
        members = [(f'specialist/{name}', _spec(f'specialist_{name}', models.LightGBM, targets.PRIMARY, self.columns(groups)))
                   for name, groups in SPECIALISTS.items()]
        blocks = list(self.definition['folds']) + [self.definition['holdout']]
        out = {name: {'blocks': []} for name in ('specialist_equal_weight', 'specialist_linear_stacker', 'specialist_gating')}
        weights_log, gate_log = [], []
        context_columns = [d.feature_names.index(n) for n in ('realized_vol20', 'return20')]
        for block in blocks:
            outer = np.column_stack([next(b['prediction'] for b in self.results[key]['blocks'] if b['block'] == block.name) for key, _ in members])
            rows = next(b['rows'] for b in self.results[members[0][0]]['blocks'] if b['block'] == block.name)
            inner_rows, inner_predictions = self._inner_predictions(members, block)
            y_inner = d.y[targets.PRIMARY][inner_rows]
            # equal weight
            equal = outer.mean(axis=1)
            # linear stacker: non-negative least squares on the inner predictions, weights normalised to sum to one
            weights = self._nonnegative_weights(inner_predictions, y_inner)
            weights_log.append({'block': block.name, 'weights': dict(zip([k for k, _ in members], weights.tolist()))})
            stacked = outer @ weights
            # gating: weights that vary with two context descriptors, fitted on the inner predictions only
            gated, note = self._gate(inner_predictions, y_inner, d.X[np.ix_(inner_rows, context_columns)], outer, d.X[np.ix_(rows, context_columns)])
            gate_log.append({'block': block.name, 'note': note})
            for name, prediction in (('specialist_equal_weight', equal), ('specialist_linear_stacker', stacked), ('specialist_gating', gated)):
                out[name]['blocks'].append({'block': block.name, 'rows': rows, 'prediction': prediction, 'predicted': np.ones(len(rows), dtype=bool),
                                            'chosen': {}, 'tried': [], 'train_rows': 0, 'train_sessions': 0, 'parameters': 0, 'describe': {}})
        for name, body in out.items():
            self.results[f'ensemble/{name}'] = {'name': name, 'status': 'RUN', 'family': 'ensemble', 'kind': models.REGRESSION, 'target': targets.PRIMARY,
                                               'columns': [], 'blocks': body['blocks'], 'seconds': 0.0, 'configurations_tried': 1, 'quantile': None}
        # an equal-weight average across model families, on the full feature set
        family_keys = [f'{m}/{targets.PRIMARY}' for m in ('ridge', 'elastic_net', 'xgboost', 'lightgbm', 'catboost', 'mlp') if self.results.get(f'{m}/{targets.PRIMARY}', {}).get('status') == 'RUN']
        blocks_out = []
        for block in blocks:
            stack = np.column_stack([self._standardised(next(b for b in self.results[key]['blocks'] if b['block'] == block.name)) for key in family_keys])
            rows = next(b['rows'] for b in self.results[family_keys[0]]['blocks'] if b['block'] == block.name)
            blocks_out.append({'block': block.name, 'rows': rows, 'prediction': stack.mean(axis=1), 'predicted': np.ones(len(rows), dtype=bool), 'chosen': {},
                               'tried': [], 'train_rows': 0, 'train_sessions': 0, 'parameters': 0, 'describe': {'members': family_keys}})
        self.results['ensemble/family_equal_weight'] = {'name': 'family_equal_weight', 'status': 'RUN', 'family': 'ensemble', 'kind': models.REGRESSION,
                                                        'target': targets.PRIMARY, 'columns': [], 'blocks': blocks_out, 'seconds': 0.0,
                                                        'configurations_tried': 1, 'quantile': None, 'scale': 'rank'}
        self.ensemble_notes = {'stacker_weights': weights_log, 'gating': gate_log, 'family_members': family_keys}

    def _standardised(self, block):
        """A block's predictions as per-session ranks scaled to [-0.5, 0.5]: averaging ranks, not units, so no model's
        scale dominates. Uses only the predictions themselves."""
        prediction, session = block['prediction'], self.data.row_session[block['rows']]
        out = np.zeros(len(prediction))
        for day in np.unique(session):
            mask = session == day
            out[mask] = (metrics.rank(prediction[mask]) - 0.5) / mask.sum() - 0.5
        return out

    @staticmethod
    def _nonnegative_weights(predictions, y, iterations=500):
        """Projected-gradient least squares with weights >= 0 summing to 1. Equal weights if nothing can be learned."""
        n = predictions.shape[1]
        w = np.full(n, 1.0 / n)
        if len(y) < 20 or not np.all(np.isfinite(predictions)):
            return w
        step = 1.0 / (np.linalg.norm(predictions, 2) ** 2 + 1e-12)
        for _ in range(iterations):
            w = np.clip(w - step * predictions.T @ (predictions @ w - y), 0, None)
            total = w.sum()
            w = w / total if total > 0 else np.full(n, 1.0 / n)
        return w

    def _gate(self, inner_predictions, y, inner_context, outer_predictions, outer_context):
        """A two-descriptor softmax gate over the specialists. Research prototype; returns equal weighting when torch or
        the data are not there."""
        if not models.available('torch') or len(y) < 200:
            return outer_predictions.mean(axis=1), INSUFFICIENT_DATA + ': equal weights used'
        import torch
        torch.manual_seed(5)
        torch.set_num_threads(2)
        mean, std = np.nanmean(inner_context, axis=0), np.nanstd(inner_context, axis=0)
        std = np.where(std > 0, std, 1.0)
        prepare = lambda c: torch.tensor(np.nan_to_num((c - mean) / std), dtype=torch.float32)
        gate = torch.nn.Linear(inner_context.shape[1], inner_predictions.shape[1])
        optimiser = torch.optim.Adam(gate.parameters(), lr=0.02, weight_decay=0.05)
        p, t, c = torch.tensor(inner_predictions, dtype=torch.float32), torch.tensor(y, dtype=torch.float32), prepare(inner_context)
        for _ in range(150):
            optimiser.zero_grad()
            torch.mean(((torch.softmax(gate(c), dim=1) * p).sum(dim=1) - t) ** 2).backward()
            optimiser.step()
        with torch.no_grad():
            weights = torch.softmax(gate(prepare(outer_context)), dim=1).numpy()
        return (weights * outer_predictions).sum(axis=1), f'gate with {sum(p.numel() for p in gate.parameters())} parameters fitted on {len(y)} inner rows'

    def meta_label(self):
        """Can a second model tell when the primary model's direction is right? Compared with a plain rule: trust larger
        predictions more. Research only: nothing is filtered or acted on."""
        d, key = self.data, f'ridge/{targets.PRIMARY}'
        spec = _spec('ridge', models.Ridge, targets.PRIMARY, self.columns(ALL_GROUPS))
        parts = {'dev': {'y': [], 'meta': [], 'size': []}, 'holdout': {'y': [], 'meta': [], 'size': []}}
        for block in list(self.definition['folds']) + [self.definition['holdout']]:
            outer = next(b for b in self.results[key]['blocks'] if b['block'] == block.name)
            inner_rows, inner_prediction = self._inner_predictions([(key, spec)], block)
            inner_prediction = inner_prediction[:, 0]
            correct = (np.sign(inner_prediction) == np.sign(d.y[targets.PRIMARY][inner_rows])).astype(float)
            columns = self.columns(TECHNICAL)
            if len(np.unique(correct)) < 2 or not models.available('sklearn'):
                continue
            meta = models.Logistic(C=0.01)
            Xi = np.column_stack([d.X[np.ix_(inner_rows, columns)], np.abs(inner_prediction)])
            meta.fit(Xi, correct, {})
            rows, prediction = outer['rows'], outer['prediction']
            Xo = np.column_stack([d.X[np.ix_(rows, columns)], np.abs(prediction)])
            part = 'holdout' if block.name == 'final_holdout' else 'dev'
            parts[part]['y'].append((np.sign(prediction) == np.sign(d.y[targets.PRIMARY][rows])).astype(float))
            parts[part]['meta'].append(meta.predict(Xo, {}))
            parts[part]['size'].append(np.abs(prediction))
        out = {}
        for part, body in parts.items():
            if not body['y']:
                out[part] = {'status': INSUFFICIENT_DATA}
                continue
            y, meta, size = (np.concatenate(body[k]) for k in ('y', 'meta', 'size'))
            out[part] = {'n': int(len(y)), 'primary_direction_right_rate': float(y.mean()), 'meta_model_auc': metrics.roc_auc(y, meta),
                         'prediction_size_rule_auc': metrics.roc_auc(y, size), 'meta_model_brier': float(np.mean((meta - y) ** 2)),
                         'constant_rate_brier': float(np.mean((y.mean() - y) ** 2))}
        self.meta = {'primary_model': 'ridge on the full feature set', 'question': 'is the primary model’s predicted direction right?', **out,
                     'note': 'Research diagnostic. Not a trade filter; nothing is acted on.'}

    # ------------------------------------------------------------------ diagnostics
    def uncertainty(self):
        """Model uncertainty from a session-block bootstrap ensemble of one tree model; outcome uncertainty from the
        quantile interval. Both are compared with the size of the realised error, on development rows."""
        d, rows = self.data, self.rows
        columns = self.columns(ALL_GROUPS)
        out = {}
        if models.available('lightgbm'):
            generator = np.random.default_rng(101)
            spread, error = [], []
            for block in self.definition['folds']:
                train = rows[np.isin(d.row_session[rows], block.train)]
                test = rows[np.isin(d.row_session[rows], block.validation)]
                days = np.unique(d.row_session[train])
                members = []
                for bag in range(8 if not self.quick else 3):
                    starts = generator.choice(len(days) - 10, size=max(1, len(days) // 10), replace=True)
                    picked = np.concatenate([days[s:s + 10] for s in starts])
                    bag_rows = np.concatenate([train[d.row_session[train] == day] for day in picked])
                    _, prediction, _ = tournament.fit_predict(models.LightGBM, models.GRIDS['lightgbm'][0], d, targets.PRIMARY, columns, bag_rows, test, seed=bag)
                    members.append(prediction)
                members = np.column_stack(members)
                spread.append(members.std(axis=1))
                error.append(np.abs(members.mean(axis=1) - d.y[targets.PRIMARY][test]))
            spread, error = np.concatenate(spread), np.concatenate(error)
            out['epistemic_bootstrap_ensemble'] = {'method': 'LightGBM refitted on 8 session-block resamples of each training window', 'n': int(len(error)),
                                                   'mean_spread': float(spread.mean()), 'spread_vs_absolute_error_spearman': metrics.spearman(spread, error)}
        low, high = self.results.get('lightgbm_quantile/q10'), self.results.get('lightgbm_quantile/q90')
        if low and high and low['status'] == high['status'] == 'RUN':
            r, lo = tournament.gather(low, 'dev')
            _, hi = tournament.gather(high, 'dev')
            width = np.abs(hi - lo)
            centre = tournament.gather(self.results['lightgbm_quantile/q50'], 'dev')[1]
            out['aleatoric_quantile_interval'] = {'method': 'width of the LightGBM 10%-90% interval', 'n': int(len(r)), 'mean_width': float(width.mean()),
                                                  'width_vs_absolute_error_spearman': metrics.spearman(width, np.abs(centre - d.y[targets.PRIMARY][r]))}
        seeds = self.results.get(f'mlp/{targets.PRIMARY}')
        if seeds and seeds['status'] == 'RUN':
            stack = np.concatenate([b['seed_predictions'][:, :, 0] for b in seeds['blocks'] if b['block'] != 'final_holdout'], axis=1)
            r, mean = tournament.gather(seeds, 'dev')
            out['epistemic_seed_disagreement'] = {'method': 'standard deviation across 3 seeds of the feed-forward network', 'n': int(stack.shape[1]),
                                                  'mean_spread': float(stack.std(axis=0).mean()),
                                                  'spread_vs_absolute_error_spearman': metrics.spearman(stack.std(axis=0), np.abs(mean - d.y[targets.PRIMARY][r]))}
        out['note'] = ('A model’s own confidence is not a probability. These numbers say only whether wider disagreement or a wider interval went '
                       'with larger errors on development rows.')
        self.uncertainty_record = out

    def calibration(self):
        """Reliability of the classifiers as fitted, and of one of them after a logistic recalibration learned on the inner
        block of each training window (never on the block being predicted)."""
        d, c = self.data, targets.CLASSIFICATION
        out = {}
        for name in ('base_rate', 'logistic', 'xgboost', 'lightgbm', 'catboost', 'mlp'):
            key = f'{name}/{c}'
            if self.results.get(key, {}).get('status') == 'RUN':
                for part in ('dev', 'holdout'):
                    rows, prediction = tournament.gather(self.results[key], part)
                    record = metrics.classification(d.y[c][rows], prediction)
                    out.setdefault(name, {})[part] = record
        key = f'lightgbm/{c}'
        if self.results.get(key, {}).get('status') == 'RUN' and models.available('sklearn'):
            from sklearn.linear_model import LogisticRegression
            spec = _spec('lightgbm', models.LightGBMClassifier, c, self.columns(ALL_GROUPS))
            pieces = {'dev': ([], []), 'holdout': ([], [])}
            for block in list(self.definition['folds']) + [self.definition['holdout']]:
                inner_rows, inner_prediction = self._inner_predictions([(key, spec)], block)
                y_inner = d.y[c][inner_rows]
                if len(np.unique(y_inner)) < 2:
                    continue
                logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
                scaler = LogisticRegression(C=1.0).fit(logit(inner_prediction[:, 0])[:, None], y_inner.astype(int))
                outer = next(b for b in self.results[key]['blocks'] if b['block'] == block.name)
                part = 'holdout' if block.name == 'final_holdout' else 'dev'
                pieces[part][0].append(d.y[c][outer['rows']])
                pieces[part][1].append(scaler.predict_proba(logit(outer['prediction'])[:, None])[:, 1])
            out['lightgbm_recalibrated'] = {part: metrics.classification(np.concatenate(y), np.concatenate(p)) for part, (y, p) in pieces.items() if y}
        self.calibration_record = out

    def disagreement(self):
        d = self.data
        keys = [f'{m}/{targets.PRIMARY}' for m in ('ridge', 'elastic_net', 'xgboost', 'lightgbm', 'catboost', 'mlp') if self.results.get(f'{m}/{targets.PRIMARY}', {}).get('status') == 'RUN']
        out = {'models': keys}
        for part in ('dev', 'holdout'):
            rows = tournament.gather(self.results[keys[0]], part)[0]
            stack = np.column_stack([tournament.gather(self.results[k], part)[1] for k in keys])
            dispersion = stack.std(axis=1)
            signs = np.sign(stack)
            split = np.mean(np.abs(signs.sum(axis=1)) < len(keys))
            error = np.abs(stack.mean(axis=1) - d.y[targets.PRIMARY][rows])
            out[part] = {'n': int(len(rows)), 'mean_prediction_dispersion': float(dispersion.mean()),
                         'dispersion_quantiles': np.quantile(dispersion, [0.1, 0.5, 0.9]).tolist(), 'share_with_sign_disagreement': float(split),
                         'ensemble_variance': float(np.mean(stack.var(axis=1))), 'dispersion_vs_absolute_error_spearman': metrics.spearman(dispersion, error)}
        out['note'] = 'A diagnostic. Disagreement is not converted into any rule.'
        self.disagreement_record = out

    def conditional(self):
        """Results by factual context, only where the count allows. No regime label is created: a context here is a
        directly observed fact (a volatility tercile of VTI's own closes with cut-offs from the first training window,
        or days since a published Fed decision)."""
        d = self.data
        key = f'ridge/{targets.PRIMARY}'
        rows, prediction = tournament.gather(self.results[key], 'dev')
        days, ic = metrics.session_ic(d.y[targets.PRIMARY][rows], prediction, d.row_session[rows])
        sessions, closes = targets.load_closes(self.path)
        bench = np.asarray(closes[BENCHMARK])
        logs = np.diff(np.log(bench))
        vol = np.array([np.nan if t < 20 else logs[t - 20:t].std(ddof=1) * np.sqrt(252) for t in range(len(bench))])
        first_train = np.asarray(self.definition['folds'][0].train)
        cuts = np.nanquantile(vol[first_train], [1 / 3, 2 / 3])
        out = {'model': 'ridge on the full feature set, development sessions', 'vti_volatility_terciles': {'cut_offs_from': 'the first training window', 'cut_offs': cuts.tolist(), 'groups': []}}
        for label, mask in (('low', vol[days] <= cuts[0]), ('middle', (vol[days] > cuts[0]) & (vol[days] <= cuts[1])), ('high', vol[days] > cuts[1])):
            values = ic[mask & np.isfinite(ic)]
            windows = len(values) // 10
            out['vti_volatility_terciles']['groups'].append({'group': label, 'sessions': int(len(values)), 'non_overlapping_windows': int(windows),
                                                             'mean_ic': float(values.mean()) if len(values) else None,
                                                             'meaningful': bool(windows >= 6)})
        groups = out['vti_volatility_terciles']
        readable = sum(1 for g in groups['groups'] if g['meaningful'])
        groups['comparison_possible'] = bool(readable >= 2)
        groups['result'] = ('Groups can be compared: at least two hold 6 or more non-overlapping windows.' if readable >= 2 else
                            INSUFFICIENT_DATA + ': Too few sessions fall in two groups. The cut-offs come from the first training window, and almost every later '
                            'session lies on one side of them, so there is no comparison between volatility groups to read.')
        fed = d.feature_names.index('days_since_fomc')
        change = d.feature_names.index('fed_latest_change_bps')
        by_session = {}
        for r in rows:
            by_session.setdefault(int(d.row_session[r]), (d.X[r, fed], d.X[r, change]))
        known = np.array([np.isfinite(by_session[int(s)][0]) for s in days])
        after_change = np.array([np.isfinite(by_session[int(s)][1]) and by_session[int(s)][1] != 0 and by_session[int(s)][0] <= 14 for s in days])
        out['fed'] = {'development_sessions_with_a_validated_fed_observation': int(known.sum()),
                      'sessions_within_14_days_after_a_validated_change': int(after_change.sum()),
                      'result': INSUFFICIENT_DATA + ': too few sessions follow a validated Fed change to condition on' if after_change.sum() < 60 else 'see groups'}
        pce = d.feature_names.index('pce_core_mom_sa')
        with_pce = np.array([np.isfinite(d.X[r, pce]) for r in rows])
        out['pce'] = {'development_rows_with_a_validated_pce_value': int(with_pce.sum()), 'development_rows': int(len(rows)),
                      'result': INSUFFICIENT_DATA + ': validated PCE values begin 2026-07-30; development sessions with one are too few to split'
                      if with_pce.mean() < 0.5 else 'available'}
        out['note'] = 'No macro regime exists and none is created. A group with fewer than 6 non-overlapping windows is shown but is not meaningful.'
        self.conditional_record = out

    def importance(self):
        """What the reference models leaned on, by feature family. Reliance is not cause."""
        d, rows = self.data, self.rows
        columns = self.columns(ALL_GROUPS)
        names = [d.feature_names[c] for c in columns]
        block = self.definition['folds'][-1]
        train = rows[np.isin(d.row_session[rows], block.train)]
        test = rows[np.isin(d.row_session[rows], block.validation)]
        out = {'fitted_on': 'the last development fold’s training window; evaluated on that fold’s validation block'}

        def by_family(values, feature_names):
            total = {}
            for name, value in zip(feature_names, values):
                family = d.feature_family[name.replace('__missing', '')]
                total[family] = total.get(family, 0.0) + float(abs(value))
            whole = sum(total.values()) or 1.0
            return {k: round(v / whole, 4) for k, v in sorted(total.items(), key=lambda kv: -kv[1])}

        ridge_choice = next(b['chosen'] for b in self.results[f'ridge/{targets.PRIMARY}']['blocks'] if b['block'] == block.name)
        ridge, _, _ = tournament.fit_predict(models.Ridge, ridge_choice, d, targets.PRIMARY, columns, train, test)
        ridge_names = ridge.pre.names(names)
        order = np.argsort(-np.abs(ridge.coefficients))[:12]
        out['ridge'] = {'method': 'absolute standardised coefficients', 'family_share': by_family(ridge.coefficients, ridge_names),
                        'largest': [{'feature': ridge_names[i], 'coefficient': float(ridge.coefficients[i])} for i in order]}
        if models.available('lightgbm'):
            choice = next(b['chosen'] for b in self.results[f'lightgbm/{targets.PRIMARY}']['blocks'] if b['block'] == block.name)
            tree, prediction, _ = tournament.fit_predict(models.LightGBM, choice, d, targets.PRIMARY, columns, train, test)
            kept = [names[k] for k in tree.pre.keep]
            contributions = tree.contributions(d.X[np.ix_(test, columns)])
            mean_abs = np.abs(contributions).mean(axis=0)
            order = np.argsort(-mean_abs)[:12]
            out['lightgbm'] = {'gain_family_share': by_family(tree.importance(), kept), 'tree_shap_family_share': by_family(mean_abs, kept),
                               'method': 'split-gain importance, and mean absolute TreeSHAP contribution on the validation block (computed by the library)',
                               'largest_by_tree_shap': [{'feature': kept[i], 'mean_absolute_contribution': float(mean_abs[i])} for i in order]}
            # permutation by family: shuffle a family's columns across instruments within each session, see what the ranking loses
            generator = np.random.default_rng(303)
            y, session = d.y[targets.PRIMARY][test], d.row_session[test]
            base = np.nanmean(metrics.session_ic(y, prediction, session)[1])
            loss = {}
            for family in sorted(set(d.feature_family[n] for n in kept)):
                drops = []
                for _ in range(5):
                    shuffled = d.X[np.ix_(test, columns)].copy()
                    members = [k for k, n in enumerate(names) if d.feature_family[n] == family]
                    for day in np.unique(session):
                        index = np.flatnonzero(session == day)
                        shuffled[np.ix_(index, members)] = shuffled[np.ix_(generator.permutation(index), members)]
                    drops.append(base - np.nanmean(metrics.session_ic(y, tree.predict(shuffled, {}), session)[1]))
                loss[family] = round(float(np.mean(drops)), 4)
            out['lightgbm']['permutation_ic_loss_by_family'] = dict(sorted(loss.items(), key=lambda kv: -kv[1]))
            out['lightgbm']['validation_mean_ic'] = float(base)
            self.explain_model, self.explain_columns, self.explain_names = tree, columns, kept
        out['limits'] = ('Importance describes what a fitted model used, on one fold. It is not causal, it is unstable on this little data, and correlated '
                         'descriptors share credit arbitrarily. Macro descriptors are the same for every instrument on a day, so they cannot change a '
                         'within-session ranking. No explanation is written by a language model, and attention weights are not presented as explanations.')
        self.importance_record = out

    def examples(self, count=6):
        """A few holdout predictions with their family contributions, labelled research-only, for the laboratory page."""
        if not hasattr(self, 'explain_model'):
            self.example_records = []
            return
        d = self.data
        result = self.results[f'lightgbm/{targets.PRIMARY}']
        rows, prediction = tournament.gather(result, 'holdout')
        last = rows[d.row_session[rows] == d.row_session[rows].max()]
        order = np.argsort(-np.abs(prediction[np.isin(rows, last)]))[:count]
        chosen = last[order]
        contributions = self.explain_model.contributions(d.X[np.ix_(chosen, self.explain_columns)])
        keys = [f'{m}/{targets.PRIMARY}' for m in ('ridge', 'xgboost', 'lightgbm', 'catboost', 'mlp') if self.results.get(f'{m}/{targets.PRIMARY}', {}).get('status') == 'RUN']
        out = []
        for n, r in enumerate(chosen):
            family = {}
            for name, value in zip(self.explain_names, contributions[n]):
                family[d.feature_family[name]] = family.get(d.feature_family[name], 0.0) + float(value)
            position = int(np.flatnonzero(rows == r)[0])
            others = {k.split('/')[0]: float(tournament.gather(self.results[k], 'holdout')[1][position]) for k in keys}
            low, high = (tournament.gather(self.results[f'lightgbm_quantile/{q}'], 'holdout')[1][position] if self.results.get(f'lightgbm_quantile/{q}', {}).get('status') == 'RUN' else None for q in ('q10', 'q90'))
            top = np.argsort(-np.abs(contributions[n]))[:4]
            out.append({'instrument': d.instruments[d.row_instrument[r]], 'session': d.sessions[d.row_session[r]], 'label': 'RESEARCH ONLY — NOT A RECOMMENDATION',
                        'predicted_excess_return_10': others.get('lightgbm'), 'benchmark_prediction': 0.0, 'predictions_by_model': others,
                        'model_dispersion': float(np.std(list(others.values()))), 'interval_10_90': [low, high],
                        'family_contributions': {k: round(v, 5) for k, v in sorted(family.items(), key=lambda kv: -abs(kv[1]))},
                        'largest_features': [{'feature': self.explain_names[i], 'contribution': float(contributions[n][i])} for i in top],
                        'explanation_model': 'LightGBM fitted on the last development fold’s training window (TreeSHAP), shown beside the registered models’ predictions',
                        'feature_snapshot_id': d.snapshot_ids[r], 'calculation_hash': d.manifest['calculation_hash'],
                        'realized_excess_return_10': float(d.y[targets.PRIMARY][r])})
        self.example_records = out

    def frequency(self):
        """Counts kept for later analysis of how many candidates a research threshold would leave. No threshold is chosen
        and none is tuned toward a trade count."""
        d = self.data
        out = {'candidates_per_session': len(d.instruments), 'thresholds_are': 'research thresholds, not rules', 'models': {}}
        for name in ('ridge', 'lightgbm'):
            result = self.results.get(f'{name}/{targets.PRIMARY}')
            if not result or result['status'] != 'RUN':
                continue
            rows, prediction = tournament.gather(result, 'dev')
            session = d.row_session[rows]
            per = {str(t): float(np.mean([np.sum(prediction[session == s] > t) for s in np.unique(session)])) for t in RESEARCH_THRESHOLDS}
            out['models'][name] = {'prediction_quantiles': dict(zip(('p05', 'p25', 'p50', 'p75', 'p95'), np.quantile(prediction, [0.05, 0.25, 0.5, 0.75, 0.95]).tolist())),
                                   'mean_count_per_session_above_threshold': per,
                                   'mean_cross_sectional_prediction_spread': float(np.mean([np.ptp(prediction[session == s]) for s in np.unique(session)]))}
        self.frequency_record = out

    def sufficiency(self):
        out = {}
        for key, result in self.results.items():
            if result.get('status') != 'RUN' or not result.get('family', '').startswith(('D_', 'E_', 'F_')):
                continue
            block = result['blocks'][-2]            # the last development fold: the largest development training window
            gate = deep.sufficiency(parameters=block['parameters'], training_rows=block['train_rows'], training_sessions=block['train_sessions'],
                                    instruments=self.breadth, horizon=tournament.PURGE if isinstance(result['target'], (tuple, list)) else
                                    int(str(result['target']).rsplit('_', 1)[1]) if str(result['target'])[-1].isdigit() else 10,
                                    average_pair_correlation=0.0)
            gate['effective_independent_instruments'] = round(self.breadth, 1)
            gate['average_pair_correlation'] = round(self.pair_correlation, 3)
            seeds = [b['seed_predictions'] for b in result['blocks'] if b['block'] != 'final_holdout' and 'seed_predictions' in b]
            if seeds:
                stack = np.concatenate([s[:, :, 0] for s in seeds], axis=1)
                rows = tournament.gather(result, 'dev')[0]
                name = result['target'][0] if isinstance(result['target'], (tuple, list)) else result['target']
                name = targets.PRIMARY if name == targets.CLASSIFICATION else name
                ics = [float(np.nanmean(metrics.session_ic(self.data.y[name][rows], stack[k], self.data.row_session[rows])[1])) for k in range(stack.shape[0])]
                gate['development_mean_ic_by_seed'] = ics
                gate['seed_ic_range'] = float(max(ics) - min(ics))
            gate['label'] = 'sufficient' if gate['sufficient'] else EXPERIMENTAL_INSUFFICIENT_DATA
            out[key] = gate
        self.sufficiency_record = out

    def execute(self):
        """The whole plan, in order. Run once."""
        for step in (self.prepare, self.baselines, self.families, self.sequence_models, self.multi_task, self.distribution, self.risk, self.ablation,
                     self.specialists, self.ensembles, self.meta_label, self.sufficiency, self.uncertainty, self.calibration, self.disagreement,
                     self.conditional, self.importance, self.examples, self.frequency):
            step()
        return self
