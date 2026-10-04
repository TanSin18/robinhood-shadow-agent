"""Turns a finished laboratory run into registry records and one report. Applies the status rules fixed in advance.

Nothing here selects a model for use. "Best" means the highest development score under the stated metric, and is shown
with its holdout result and its research status; a naive baseline can be, and is allowed to be, the best.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np

from firm_lab.research_features.types import content_hash

from . import EXPERIMENTAL_INSUFFICIENT_DATA, INSUFFICIENT_DATA, TIME_POLICY, WARNING, deep, metrics, models, registry, selection, targets, tournament
from .lab import ALL_GROUPS, COST_RANGE, GATE_SEED, QUANTILES, SEQUENCE_GROUPS, SPECIALISTS, TECHNICAL, fold_losses, rmse, summarize

BASELINES = ('zero', 'historical_mean', 'instrument_mean', 'momentum_20', 'momentum_63', 'momentum_126', 'registered_style_momentum')
NAIVE_CLASSIFIERS = ('base_rate', 'coin_flip')
NETWORK_FAMILIES = ('D_', 'E_', 'F_')
HOLM_LEVEL = 0.10
ADVANCED_FAMILIES = ('C_boosted_trees', 'D_neural', 'E_sequence', 'F_transformer', 'ensemble')
ARCHITECTURE = {
    'zero': 'constant 0', 'historical_mean': 'training mean', 'instrument_mean': 'per-instrument training mean',
    'momentum_20': 'one-variable line on return20', 'momentum_63': 'one-variable line on return63', 'momentum_126': 'one-variable line on return126',
    'registered_style_momentum': 'one-variable line on return126 where price is above its 200-session average', 'base_rate': 'training positive share',
    'coin_flip': 'constant probability 0.5',
    'least_squares_small': 'least squares on 5 descriptors', 'ridge': 'ridge regression', 'elastic_net': 'elastic net', 'logistic': 'L2 logistic regression',
    'xgboost': 'gradient-boosted trees (XGBoost)', 'lightgbm': 'gradient-boosted trees (LightGBM)', 'catboost': 'gradient-boosted trees (CatBoost)',
    'mlp': 'feed-forward network 32-16, dropout 0.3', 'mlp_sequence_features': 'feed-forward network 32-16 on the sequence models’ descriptors',
    'tcn': 'causal dilated convolutions, width 16, 20 sessions', 'gru': 'GRU, width 16, 20 sessions', 'lstm': 'LSTM, width 16, 20 sessions',
    'transformer_encoder': 'encoder-only transformer, 1 layer, 2 heads, width 16, 20 sessions',
    'mlp_multi_task': 'feed-forward network with 5 output heads', 'transformer_multi_task': 'encoder-only transformer with 5 output heads',
    'specialist_equal_weight': 'equal-weight average of 5 specialist models', 'specialist_linear_stacker': 'non-negative linear stacker over 5 specialists, fitted on inner blocks',
    'specialist_gating': 'two-descriptor softmax gate over 5 specialists, fitted on inner blocks', 'family_equal_weight': 'equal-weight average of per-session ranks across model families',
}


def _groups(key, name):
    if key.startswith('ablation/'):
        tail = key.split('/')[-1]
        return list(ALL_GROUPS) if tail == 'full' else ['technical_baseline'] + ([tail.split('+')[1]] if '+' in tail else [])
    if key.startswith('specialist/'):
        return list(SPECIALISTS[key.split('/')[1]])
    if name in ('tcn', 'gru', 'lstm', 'transformer_encoder', 'mlp_sequence_features', 'transformer_multi_task'):
        return list(SEQUENCE_GROUPS)
    if name == 'least_squares_small':
        return ['technical_baseline (5 descriptors)']
    if name.startswith('specialist_') or name == 'family_equal_weight':
        return ['predictions of member models']
    return list(ALL_GROUPS)


def _sufficient(lab, key) -> bool:
    """Whether a result passed the data-sufficiency gate. A result fitted as a network must have a gate record: a missing
    record is an error, never a pass. A combination is sufficient only if every network inside it is."""
    result, record = lab.results[key], lab.sufficiency_record
    network = result.get('family', '').startswith(NETWORK_FAMILIES) or (key == 'ensemble/specialist_gating' and bool(getattr(lab, 'gate_fits', {})))
    if network:
        if key not in record:
            raise ValueError('SUFFICIENCY_RECORD_MISSING:' + key)
        return bool(record[key]['sufficient'])
    members = [m for m in result.get('members', []) if lab.results[m].get('family', '').startswith(NETWORK_FAMILIES)]
    for member in members:
        if member not in record:
            raise ValueError('SUFFICIENCY_RECORD_MISSING:' + member)
    return all(record[m]['sufficient'] for m in members)


def _row(key, lab, summary, *, role, status, reasons, label=None):
    result = lab.results[key]
    dev, holdout = summary.get('dev', {}), summary.get('holdout', {})
    ranking_dev, ranking_holdout = dev.get('ranking', {}), holdout.get('ranking', {})
    folds = summary.get('fold_ics', [])
    row = {'key': key, 'name': label or result['name'], 'family': result.get('family'), 'role': role, 'status': status, 'status_reasons': reasons,
           'target': summary.get('target'), 'dev_mean_ic': summary.get('dev_mean_ic'), 'dev_ic_interval_90': ranking_dev.get('ic_interval_90'),
           'dev_sessions': ranking_dev.get('sessions'), 'dev_sessions_ranked': ranking_dev.get('sessions_with_a_ranking'),
           'dev_non_overlapping_windows': ranking_dev.get('non_overlapping_windows'), 'dev_batches': ranking_dev.get('batches'), 'fold_ics': folds,
           'folds_positive': int(sum(1 for x in folds if x is not None and np.isfinite(x) and x > 0)), 'folds': len(folds),
           'holdout_mean_ic': summary.get('holdout_mean_ic'), 'holdout_ic_interval_90': ranking_holdout.get('ic_interval_90'),
           'holdout_sessions': ranking_holdout.get('sessions'), 'holdout_sessions_ranked': ranking_holdout.get('sessions_with_a_ranking'),
           'holdout_non_overlapping_windows': ranking_holdout.get('non_overlapping_windows'), 'holdout_batches': ranking_holdout.get('batches'),
           'dev_top_minus_bottom': ranking_dev.get('top_bottom', {}).get('top_minus_bottom'), 'dev_top_minus_bottom_interval_90': ranking_dev.get('top_minus_bottom_interval_90'),
           'holdout_top_minus_bottom': ranking_holdout.get('top_bottom', {}).get('top_minus_bottom'),
           'holdout_top_minus_bottom_interval_90': ranking_holdout.get('top_minus_bottom_interval_90'),
           'dev_top_hit_rate': ranking_dev.get('top_bottom', {}).get('top_hit_rate'),
           'parameters': max((b['parameters'] for b in result['blocks']), default=0), 'configurations_tried': result.get('configurations_tried', 1),
           'seconds': result.get('seconds')}
    for part, record in (('dev', dev), ('holdout', holdout)):
        regression = record.get('regression')
        if regression:
            row.update({f'{part}_rmse': regression['rmse'], f'{part}_mae': regression['mae'], f'{part}_r2': regression['r2'],
                        f'{part}_r2_vs_zero': regression['r2_vs_zero'], f'{part}_pearson': regression['pearson'], f'{part}_spearman': regression['spearman'],
                        f'{part}_directional_accuracy': regression['directional_accuracy']})
            row[f'{part}_buckets'] = record.get('buckets')
        classification = record.get('classification')
        if classification:
            row.update({f'{part}_roc_auc': classification['roc_auc'], f'{part}_pr_auc': classification['pr_auc'], f'{part}_log_loss': classification['log_loss'],
                        f'{part}_brier': classification['brier'], f'{part}_calibration_error': classification['calibration_error'],
                        f'{part}_base_rate': classification['base_rate'], f'{part}_reliability': classification['reliability']})
    return row


def _label(target):
    """The label a model is ranked on: a classifier of the 10-session sign is ranked on the 10-session excess return."""
    return targets.PRIMARY if target == targets.CLASSIFICATION else target


def assemble(lab, *, supersedes=None) -> dict:
    """Summaries, statuses and the report dictionary. Does not write anything."""
    d = lab.data
    tables, cache = {}, {}

    def summary(key, **kw):
        if lab.results.get(key, {}).get('status') != 'RUN':
            return None
        token = _token(key, kw)
        if token not in cache:
            cache[token] = summarize(lab.results[key], d, **kw)
        return cache[token]

    # ---- the Holm family of a label: every registered model that is judged by ranking it (plan section 7), not only the
    #      candidates of one table. Quantile and risk models are judged by a loss and have no rank test. Two registry rows with
    #      the same predictions (the full-set ablation run is the same model as the family run) are one test, not two.
    multi_names = [n for n, _ in lab.MULTI]
    family, same_as, seen = {t: {} for t in targets.REGRESSION}, {}, {t: {} for t in targets.REGRESSION}
    for key, result in lab.results.items():
        if result.get('status') != 'RUN' or result.get('kind') == models.QUANTILE:
            continue
        multi = isinstance(result['target'], (tuple, list))
        for head, target in enumerate(result['target'] if multi else [result['target']]):
            if target not in targets.REGRESSION + (targets.CLASSIFICATION,):
                continue
            kw = {'head': head} if multi else {}
            token, label = _token(key, kw), _label(target)
            series = summary(key, **kw)['holdout_ic_series']
            digest = content_hash([round(float(v), 12) for v in series] + [round(float(v), 12) for v in summary(key, **kw)['dev_ic_series']])
            if digest in seen[label] and summary(key, **kw)['holdout']['ranking']['sessions_with_a_ranking']:
                same_as[token] = seen[label][digest]                    # identical session-by-session results: the same test
                continue
            seen[label].setdefault(digest, token)
            family[label][token] = summary(key, **kw)['p_holdout_ic_not_positive']
    holm = {label: metrics.holm(values, level=HOLM_LEVEL) for label, values in family.items()}
    for label in holm:
        for token, first in same_as.items():
            if first in holm[label]:
                holm[label][token] = holm[label][first]

    def judged(target, candidates, classification=False):
        """Rows for one target: naive baselines, then candidates with statuses from the fixed rules."""
        label = _label(target)
        baselines = {name: summary(f'{name}/{label}') for name in BASELINES}
        strongest = selection.strongest_baseline(baselines)
        rows, naive_log_loss = [], None
        if not classification:
            for name in BASELINES:
                rows.append(_row(f'{name}/{target}', lab, baselines[name], role='BASELINE', status='EXPERIMENTAL',
                                 reasons=['naive baseline: a reference, not a candidate'] + (['the strongest baseline on development sessions'] if name == strongest else [])))
        else:
            naive = {name: summary(f'{name}/{target}') for name in NAIVE_CLASSIFIERS}
            naive_log_loss = min(v['dev_log_loss'] for v in naive.values())
            for name, record in naive.items():
                best = record['dev_log_loss'] == naive_log_loss
                rows.append(_row(f'{name}/{target}', lab, record, role='BASELINE', status='EXPERIMENTAL',
                                 reasons=['naive baseline: ' + ARCHITECTURE[name]] + (['the lower naive log loss on development sessions'] if best else [])))
        for key, label_shown, kw in candidates:
            if lab.results.get(key, {}).get('status') != 'RUN':
                continue
            record = dict(summary(key, **kw))
            if classification:
                record['naive_log_loss'] = naive_log_loss
            test = holm[label][_token(key, kw)]
            status, reasons = selection.status(record, baselines, holm_rejected=test['rejected'], sufficient=_sufficient(lab, key))
            batches = record['holdout']['ranking']['batches']
            reasons = [f'compared with the strongest naive baseline: {strongest}'] + reasons + [
                (f'holdout mean IC above zero: Holm-adjusted p {test["adjusted"]:.3f} in a family of {test["family_size"]} tests, level {HOLM_LEVEL:.2f}: '
                 + ('met' if test['rejected'] else 'not met') + f' (a t test on {batches} batch means; it does not by itself make a challenger)')
                if np.isfinite(_none_to_nan(record['p_holdout_ic_not_positive'])) else
                f'holdout mean IC above zero: no test, the holdout has {batches} batch' + ('' if batches == 1 else 'es')
                + f' and three are needed (counted as p = 1 in the family of {test["family_size"]} tests)']
            row = _row(key, lab, record, role='CANDIDATE', status=status, reasons=reasons, label=label_shown)
            row['sufficiency'] = None if key not in lab.sufficiency_record else lab.sufficiency_record[key]['label']
            row['holm_adjusted_p'], row['holm_family_size'], row['holm_met'] = test['adjusted'], test['family_size'], test['rejected']
            row['dev_identity_p'] = record.get('dev_identity_p')
            rows.append(row)
        for key, label_shown, kw in candidates:
            if lab.results.get(key, {}).get('status') == 'NOT_RUN':
                rows.append({'key': key, 'name': label_shown, 'role': 'CANDIDATE', 'status': None, 'not_run': lab.results[key]['reason'], 'target': target})
        return rows, strongest

    strongest_by_target = {}
    for target in targets.REGRESSION:
        candidates = [(f'{m}/{target}', m, {}) for m in ('least_squares_small', 'ridge', 'elastic_net', 'xgboost', 'lightgbm', 'catboost', 'mlp')]
        head = multi_names.index(target)
        candidates += [('mlp_multi_task', f'mlp_multi_task[{target}]', {'head': head}), ('transformer_multi_task', f'transformer_multi_task[{target}]', {'head': head})]
        if target == targets.PRIMARY:
            candidates += [(f'{m}/{target}', m, {}) for m in ('mlp_sequence_features', 'tcn', 'gru', 'lstm', 'transformer_encoder')]
            candidates += [(f'ensemble/{m}', m, {}) for m in ('specialist_equal_weight', 'specialist_linear_stacker', 'specialist_gating', 'family_equal_weight')]
        tables[target], strongest_by_target[target] = judged(target, candidates)
    c = targets.CLASSIFICATION
    candidates = [(f'{m}/{c}', m, {}) for m in ('logistic', 'xgboost', 'lightgbm', 'catboost', 'mlp')]
    candidates += [('mlp_multi_task', f'mlp_multi_task[{c}]', {'head': multi_names.index(c)}), ('transformer_multi_task', f'transformer_multi_task[{c}]', {'head': multi_names.index(c)})]
    tables[c], strongest_by_target[c] = judged(c, candidates, classification=True)

    # ---- distribution: pinball loss per quantile, interval coverage
    distribution = {'quantiles': list(QUANTILES), 'models': {}}
    for name in ('train_quantile', 'linear_quantile', 'lightgbm_quantile'):
        per, folds_all, ok = {}, [], True
        for q in QUANTILES:
            key = f'{name}/q{int(q * 100):02d}'
            if lab.results.get(key, {}).get('status') != 'RUN':
                ok = False
                distribution['models'][name] = {'not_run': lab.results.get(key, {}).get('reason', 'not run')}
                break
            folds, holdout = fold_losses(lab.results[key], d, targets.PRIMARY, lambda y, p, q=q: metrics.pinball(y, p, q))
            per[str(q)] = {'dev_pinball': float(np.mean(folds)), 'holdout_pinball': holdout, 'fold_pinball': folds}
            folds_all.append(folds)
        if not ok:
            continue
        coverage = {}
        for low, high in ((0.10, 0.90), (0.25, 0.75)):
            for part in ('dev', 'holdout'):
                rows, lo = tournament.gather(lab.results[f'{name}/q{int(low * 100):02d}'], part)
                _, hi = tournament.gather(lab.results[f'{name}/q{int(high * 100):02d}'], part)
                coverage[f'{int(low * 100)}-{int(high * 100)} {part}'] = {**metrics.coverage(d.y[targets.PRIMARY][rows], lo, hi), 'nominal': high - low}
        distribution['models'][name] = {'by_quantile': per, 'mean_dev_pinball': float(np.mean([v['dev_pinball'] for v in per.values()])),
                                        'mean_holdout_pinball': float(np.mean([v['holdout_pinball'] for v in per.values()])),
                                        'fold_mean_pinball': np.mean(np.asarray(folds_all), axis=0).tolist(), 'coverage': coverage}
    if 'by_quantile' in distribution['models'].get('train_quantile', {}):
        base = distribution['models']['train_quantile']
        for name in ('linear_quantile', 'lightgbm_quantile'):
            body = distribution['models'].get(name, {})
            if 'by_quantile' in body:
                body['status'], body['status_reasons'] = selection.loss_status(body['fold_mean_pinball'], base['fold_mean_pinball'], body['mean_holdout_pinball'], base['mean_holdout_pinball'])
                body['role'] = 'CANDIDATE'
        base['status'], base['status_reasons'], base['role'] = 'EXPERIMENTAL', ['naive baseline: the training quantiles'], 'BASELINE'

    # ---- risk targets: RMSE against the strongest naive baseline of the target (the training mean, or for volatility a line on
    #      the last 20 sessions' realised volatility if that is the better naive forecast on development sessions)
    risk, risk_baselines = {}, {}
    NAIVE = {'historical_mean': 'naive baseline: the training mean', 'volatility_persistence': 'naive baseline: a line on the last 20 sessions’ realised volatility'}
    for target in targets.RISK:
        naive = {name: fold_losses(lab.results[f'{name}/{target}'], d, target, rmse) for name in NAIVE if lab.results.get(f'{name}/{target}', {}).get('status') == 'RUN'}
        strongest = selection.strongest_loss_baseline({name: folds for name, (folds, _) in naive.items()})
        base_folds, base_holdout = naive[strongest]
        risk_baselines[target] = strongest
        body = {}
        for name, (folds, holdout) in naive.items():
            rows, prediction = tournament.gather(lab.results[f'{name}/{target}'], 'dev')
            body[name] = {'role': 'BASELINE', 'status': 'EXPERIMENTAL', 'status_reasons': [NAIVE[name]] + (['the strongest naive baseline on development sessions'] if name == strongest else []),
                          'dev_rmse': float(np.mean(folds)), 'holdout_rmse': holdout, 'fold_rmse': folds, 'dev_spearman': metrics.spearman(d.y[target][rows], prediction)}
        for name in ('ridge', 'lightgbm'):
            key = f'{name}/{target}'
            if lab.results.get(key, {}).get('status') != 'RUN':
                body[name] = {'not_run': lab.results.get(key, {}).get('reason', 'not run')}
                continue
            folds, holdout = fold_losses(lab.results[key], d, target, rmse)
            status, reasons = selection.loss_status(folds, base_folds, holdout, base_holdout)
            rows, prediction = tournament.gather(lab.results[key], 'dev')
            body[name] = {'role': 'CANDIDATE', 'status': status, 'status_reasons': [f'compared with the strongest naive baseline: {strongest}'] + reasons,
                          'compared_with': strongest, 'dev_rmse': float(np.mean(folds)), 'holdout_rmse': holdout, 'fold_rmse': folds,
                          'dev_spearman': metrics.spearman(d.y[target][rows], prediction)}
        risk[target] = body

    # ---- ablation: each family added to the technical baseline, paired per session
    ablation = {'reference_models': ['ridge', 'lightgbm'], 'sets': lab.ablation_sets, 'rows': [], 'target': targets.PRIMARY,
                'note': 'The "sector" set holds only trailing returns relative to VTI: sector-relative descriptors need historical sector mappings, which do not exist '
                        'for any historical session. Macro descriptors are the same for every instrument on a day and cannot change a within-session ranking.'}
    fib = {}
    for model in ('ridge', 'lightgbm'):
        base = summary(f'ablation/{model}/technical_baseline')
        for name in lab.ablation_sets:
            s = summary(f'ablation/{model}/{name}')
            if s is None:
                ablation['rows'].append({'model': model, 'set': name, 'not_run': lab.results[f'ablation/{model}/{name}']['reason']})
                continue
            row = {'model': model, 'set': name, 'features': len(lab.results[f'ablation/{model}/{name}']['columns']), 'dev_mean_ic': s['dev_mean_ic'],
                   'holdout_mean_ic': s['holdout_mean_ic'], 'fold_ics': s['fold_ics'], 'dev_rmse': s['dev']['regression']['rmse'], 'holdout_rmse': s['holdout']['regression']['rmse']}
            if name != 'technical_baseline' and base is not None:
                paired = metrics.paired_difference(np.asarray(s['dev_ic_series'], dtype=float), np.asarray(base['dev_ic_series'], dtype=float), horizon=10)
                row.update({'dev_ic_change': paired['estimate'], 'dev_ic_change_interval_90': [paired['low'], paired['high']], 'dev_batches': paired['batches'],
                            'holdout_ic_change': (s['holdout_mean_ic'] or 0.0) - (base['holdout_mean_ic'] or 0.0),
                            'dev_rmse_change': s['dev']['regression']['rmse'] - base['dev']['regression']['rmse']})
                if name == 'technical+fibonacci':
                    fib[model] = {'dev': paired, 'holdout_difference': row['holdout_ic_change']}
            ablation['rows'].append(row)
    verdict, why = selection.fibonacci_verdict(fib)
    ablation['fibonacci'] = {'answer': verdict, 'statement': f'FIBONACCI ADDS INCREMENTAL OOS VALUE = {verdict}', 'why': why,
                             'by_reference_model': {m: {'dev_ic_change': v['dev']['estimate'], 'dev_interval_90': [v['dev']['low'], v['dev']['high']],
                                                        'holdout_ic_change': v['holdout_difference'], 'development_batches': v['dev'].get('batches')} for m, v in fib.items()}}

    # ---- specialists and combinations
    specialists = {'target': targets.PRIMARY, 'rows': []}
    for name in SPECIALISTS:
        s = summary(f'specialist/{name}')
        specialists['rows'].append({'specialist': name, 'groups': list(SPECIALISTS[name]), 'features': len(lab.results[f'specialist/{name}']['columns']),
                                    'dev_mean_ic': s['dev_mean_ic'], 'holdout_mean_ic': s['holdout_mean_ic'], 'fold_ics': s['fold_ics'],
                                    'dev_sessions_ranked': s['dev']['ranking']['sessions_with_a_ranking'], 'dev_sessions': s['dev']['ranking']['sessions'],
                                    'dev_rmse': s['dev']['regression']['rmse'],
                                    'note': 'the same for every instrument on a day: cannot rank within a session' if name == 'macro' else
                                            'descriptors exist for 5 single stocks only' if name in ('fundamental', 'event') else
                                            'trailing returns relative to VTI only; no sector-relative descriptor exists historically' if name == 'sector' else ''})
    unified = summary(f'lightgbm/{targets.PRIMARY}')
    specialists['unified_model'] = {'model': 'lightgbm on the full feature set', 'dev_mean_ic': unified['dev_mean_ic'], 'holdout_mean_ic': unified['holdout_mean_ic']}
    specialists['combinations'] = [{'name': r['name'], 'dev_mean_ic': r['dev_mean_ic'], 'holdout_mean_ic': r['holdout_mean_ic'], 'fold_ics': r['fold_ics'], 'status': r['status']}
                                   for r in tables[targets.PRIMARY] if r.get('family') == 'ensemble']
    specialists['notes'] = lab.ensemble_notes

    # ---- multi-task against separately trained networks
    multi = {'heads': multi_names, 'rows': []}
    for target in targets.REGRESSION + (c,):
        single = summary(f'mlp/{target}')
        for name in ('mlp_multi_task', 'transformer_multi_task'):
            if lab.results.get(name, {}).get('status') != 'RUN':
                continue
            s = summary(name, head=multi_names.index(target))
            multi['rows'].append({'target': target, 'model': name, 'dev_mean_ic': s['dev_mean_ic'], 'holdout_mean_ic': s['holdout_mean_ic'],
                                  'separately_trained_mlp_dev_mean_ic': None if single is None else single['dev_mean_ic'],
                                  'separately_trained_mlp_holdout_mean_ic': None if single is None else single['holdout_mean_ic']})
    multi['tested'] = bool(multi['rows'])

    # ---- highest development scores, with what the holdout said and how many were compared
    definition = lab.definition
    development_sessions = int(sum(len(f.validation) for f in definition['folds']))
    holdout_sessions = int(len(definition['holdout'].validation))

    def best(rows, field='dev_mean_ic', lowest=False, only=None):
        pool = [r for r in rows if r.get(field) is not None and np.isfinite(r[field]) and (only is None or only(r))]
        if not pool:
            return None
        r = (min if lowest else max)(pool, key=lambda r: r[field])
        out = {k: r.get(k) for k in ('name', 'family', 'role', 'status', 'dev_mean_ic', 'holdout_mean_ic', 'fold_ics', 'dev_rmse', 'holdout_rmse', 'dev_log_loss',
                                     'holdout_log_loss', 'dev_roc_auc', 'holdout_roc_auc', 'sufficiency', 'dev_batches', 'holdout_batches')}
        out['highest_of'] = len(pool)
        return out

    primary_rows = tables[targets.PRIMARY]
    best_models = {f'best_{h}d': best(tables[f'excess_return_{h}']) for h in targets.HORIZONS}
    best_models['best_classifier'] = best(tables[c], 'dev_log_loss', lowest=True)
    best_models['strongest_baseline'] = best(primary_rows, only=lambda r: r['role'] == 'BASELINE')
    best_models['strongest_advanced_candidate'] = best(primary_rows, only=lambda r: r['role'] == 'CANDIDATE' and r.get('family') in ADVANCED_FAMILIES)
    quantile_models = {k: v for k, v in distribution['models'].items() if 'mean_dev_pinball' in v}
    if quantile_models:
        name = min(quantile_models, key=lambda k: quantile_models[k]['mean_dev_pinball'])
        best_models['best_distribution_model'] = {'name': name, 'role': quantile_models[name].get('role'), 'mean_dev_pinball': quantile_models[name]['mean_dev_pinball'],
                                                  'mean_holdout_pinball': quantile_models[name]['mean_holdout_pinball'], 'status': quantile_models[name].get('status'),
                                                  'highest_of': len(quantile_models)}
    downside = {k: v for k, v in risk['close_mae_10'].items() if 'dev_rmse' in v}
    name = min(downside, key=lambda k: downside[k]['dev_rmse'])
    best_models['best_downside_model'] = {'name': name, 'role': downside[name]['role'], 'target': 'close_mae_10', 'dev_rmse': downside[name]['dev_rmse'],
                                          'holdout_rmse': downside[name]['holdout_rmse'], 'status': downside[name]['status'], 'highest_of': len(downside)}
    statuses = {}
    for rows in tables.values():
        for r in rows:
            if r.get('status') and r['role'] == 'CANDIDATE':
                statuses[r['status']] = statuses.get(r['status'], 0) + 1
    best_models['candidate_status_counts'] = statuses
    best_models['note'] = ('"Highest" is the highest development score among the rows compared. It is not a selection for use. The highest of many noisy scores is '
                           'biased upward: read it with its holdout number, its research status and, for a network, its data-sufficiency label. With this little '
                           'data a naive baseline scoring highest, or nothing being established, is a real and acceptable result.')

    # ---- size of the ranking spread beside a stated cost range; not a profit figure
    economic = {'cost_range_round_trip_two_legs': list(COST_RANGE), 'statement': 'A top-5 minus bottom-5 mean realised 10-session excess return, beside a stated '
                'plausible cost range. Not net strategy P&L: no weights, no holding rule, no cost model, no capacity. The last column is a description of the '
                'interval, not a signal.', 'rows': []}
    for r in primary_rows:
        if r.get('dev_top_minus_bottom') is not None and (r['role'] == 'BASELINE' and r['name'] == strongest_by_target[targets.PRIMARY] or r['name'] in ('ridge', 'lightgbm', 'xgboost', 'catboost', 'family_equal_weight')):
            interval = r.get('dev_top_minus_bottom_interval_90')
            economic['rows'].append({'name': r['name'], 'dev_spread': r['dev_top_minus_bottom'], 'dev_interval_90': interval, 'dev_batches': r.get('dev_batches'),
                                     'holdout_spread': r['holdout_top_minus_bottom'], 'holdout_interval_90': r['holdout_top_minus_bottom_interval_90'],
                                     'development_interval_above_stated_cost_range': bool(interval and interval[0] is not None and np.isfinite(interval[0]) and interval[0] > COST_RANGE[1])})

    rows_all = lab.rows
    sessions = np.unique(d.row_session[rows_all])
    blocks = [b.as_dict(d.sessions) for b in definition['folds']] + [definition['holdout'].as_dict(d.sessions)]
    in_a_group = d.columns(ALL_GROUPS)
    strict = getattr(lab, 'strict_closes', None)
    windows = lambda n: {'sessions': n, 'non_overlapping_windows': {str(h): n // h for h in targets.HORIZONS},
                         'batches_for_an_interval': {str(h): n // (metrics.BATCH_HORIZONS * h) for h in targets.HORIZONS}}
    report = {
        'warning': WARNING, 'plan_version': tournament.PLAN_VERSION, 'time_policy': TIME_POLICY, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'code_hash': registry.code_hash(), 'library_versions': models.versions(), 'supersedes': supersedes,
        'dataset': {'dataset_hash': d.manifest['dataset_hash'], 'hashes': d.manifest['hashes'], 'source_sha256': d.manifest['source_sha256'],
                    'calculation_hash': d.manifest['calculation_hash'], 'instruments': d.instruments, 'benchmark': d.manifest['benchmark'],
                    'stored_sessions': len(d.sessions), 'first_session': d.sessions[0], 'last_session': d.sessions[-1],
                    'usable_samples': int(len(rows_all)), 'usable_sessions': int(len(sessions)), 'first_usable_session': d.sessions[sessions[0]],
                    'last_usable_session': d.sessions[sessions[-1]],
                    'strict_point_in_time_samples': 0 if strict == 0 else None, 'closes_held_at_their_own_session_close': strict,
                    'features': len(d.feature_names), 'features_in_a_model_group': len(in_a_group),
                    'features_ever_available': int(sum(1 for i in in_a_group if d.manifest['feature_availability'][d.feature_names[i]] > 0)),
                    'features_by_family': {f: sum(1 for n in d.feature_names if d.feature_family[n] == f) for f in sorted(set(d.feature_family.values()))},
                    'feature_availability_by_family': {f: round(float(np.mean([d.manifest['feature_availability'][n] for n in d.feature_names if d.feature_family[n] == f])), 3)
                                                       for f in sorted(set(d.feature_family.values()))},
                    'excluded_features': len(d.excluded), 'targets': list(targets.ALL), 'horizons': list(targets.HORIZONS), 'target_version': targets.TARGET_VERSION,
                    'evaluation_windows': {'development': windows(development_sessions), 'holdout': windows(holdout_sessions),
                                           'note': 'Counted on the sessions that are actually predicted. Non-overlapping is not the same as independent: neighbouring '
                                                   'windows still share market conditions.'},
                    'label_windows_in_all_usable_sessions': {str(h): int(len(sessions) // h) for h in targets.HORIZONS},
                    'average_pair_correlation_of_labels': lab.pair_correlation, 'effective_independent_instruments': lab.breadth[targets.PRIMARY],
                    'effective_independent_instruments_by_target': lab.breadth, 'breadth_measured_on': 'development sessions',
                    'limitations': [
                        'Retrospective: every input was captured on 2026-10-01 to 2026-10-03. Under the strict known-at rule there are 0 usable samples.',
                        'A close is treated as known at its own session close; closes are split-adjusted as of the capture date.',
                        f'{len(d.instruments)} instruments, most of them funds; {development_sessions} development and {holdout_sessions} holdout sessions are predicted: '
                        f'{development_sessions // 10} and {holdout_sessions // 10} non-overlapping 10-session windows, {development_sessions // 20} and {holdout_sessions // 20} of 20 sessions.',
                        f'The holdout is too short for a test on the 10- and 20-session targets (fewer than {metrics.MINIMUM_BATCHES} batches of two horizons): '
                        'no model can reach ELIGIBLE_FOR_FUTURE_REVIEW on them with this data.',
                        'Labels are price returns on both legs: distributions are not added back.',
                        'The label starts at the close the features end at: a research label, not an executable entry.',
                        'No OHLCV, intraday, CPI, labor, Treasury-yield, market-volatility, consensus or historical sector-constituent data. Nothing substitutes for them.',
                        'Fundamental and event descriptors exist for 5 single stocks only. Sector mappings are effective 2026-10-03 and are unavailable for every historical '
                        'session, so the "sector" set holds only trailing returns relative to VTI.',
                        'Macro descriptors (Fed, PCE) are validated from mid-2026 only and are identical across instruments on a day.',
                        'The holdout has been read by every run: under plan v1, under v2 after the independent review, and under v3 after the verification review. '
                        'No prediction changed between the v2 and v3 runs. Every change was made for a stated defect, not to move a result; the changes and the '
                        'statuses they moved are listed in docs/firm_lab/CHECKPOINT7_CLOSURE.md.']},
        'validation': {'split_method': definition['version'], 'walk_forward_folds': len(definition['folds']), 'purge_sessions': definition['horizon'],
                       'embargo_sessions': definition['embargo'], 'gap_before_holdout_sessions': definition['gap_before_holdout'], 'blocks': blocks,
                       'development_sessions': development_sessions, 'holdout_sessions': holdout_sessions,
                       'inner_tuning': 'the last quarter of each training window, purged; every tried configuration recorded',
                       'configurations_fitted': int(lab.configurations), 'interval_method': metrics.INTERVAL_METHOD,
                       'unranked_sessions': 'a session a model does not rank counts as rank correlation 0 for that model',
                       'multiple_testing': 'Holm at 10% over every registered model that is judged by ranking the label (baselines, candidates, ablation and specialist '
                                           'runs; classifiers with the 10-session models; two rows with identical results count once), on holdout mean IC above zero',
                       'holm_family_sizes': {label: len(values) for label, values in family.items()},
                       'holm_rows_identical_to_another': same_as,
                       'identity_shuffle': f'{metrics.identity_permutation_p.__kwdefaults__["draws"]} shuffles of instrument identities, fixed seed; a challenger needs p at most {metrics.IDENTITY_LEVEL}'},
        'tables': tables, 'strongest_baseline': strongest_by_target, 'distribution': distribution, 'risk': risk, 'risk_baselines': risk_baselines, 'ablation': ablation,
        'specialists': specialists, 'multi_task': multi, 'uncertainty': lab.uncertainty_record, 'calibration': lab.calibration_record,
        'disagreement': lab.disagreement_record, 'meta_label': lab.meta, 'conditional': lab.conditional_record, 'importance': lab.importance_record,
        'examples': lab.example_records, 'sufficiency': lab.sufficiency_record, 'frequency': lab.frequency_record, 'economic': economic,
        'best_research_models': best_models, 'seconds': round(time.time() - lab.started, 1),
    }
    # a run identity, not a content hash: it names this execution, and every registry row of the run carries it
    report['report_id'] = content_hash([report['dataset']['dataset_hash'], report['code_hash'], report['plan_version'], report['generated_at']])
    return report


def _token(key, kw) -> str:
    return key + ('' if not kw else '#' + ','.join(f'{k}={v}' for k, v in sorted(kw.items())))


def _none_to_nan(value):
    return float('nan') if value is None else float(value)


def _judgements(report) -> dict:
    """{result key: [judged rows]} from every part of the report that gives a research status: the ranking tables, the
    risk targets and the quantile models. The registry row of a model carries exactly what the report says about it."""
    out = {}
    for rows in report['tables'].values():
        for r in rows:
            if r.get('status'):
                out.setdefault(r['key'], []).append(r)
    for target, body in report['risk'].items():
        for name, r in body.items():
            if r.get('status'):
                out.setdefault(f'{name}/{target}', []).append({**r, 'key': f'{name}/{target}', 'name': name, 'target': target})
    for name, body in report['distribution']['models'].items():
        if body.get('status'):
            for q in report['distribution']['quantiles']:
                key = f'{name}/q{int(q * 100):02d}'
                out.setdefault(key, []).append({'key': key, 'name': name, 'target': targets.PRIMARY, 'role': body.get('role', 'CANDIDATE'), 'status': body['status'],
                                                'status_reasons': list(body['status_reasons']) + ['judged as a set of five quantiles by mean pinball loss'],
                                                'quantile': q, 'mean_dev_pinball': body['mean_dev_pinball'], 'mean_holdout_pinball': body['mean_holdout_pinball']})
    return out


def write(lab, report) -> dict:
    """Stores every evaluated model, its out-of-sample predictions and the report in the modeling database."""
    d = lab.data
    code, versions, run = report['code_hash'], report['library_versions'], report['report_id']
    definition = lab.definition
    split = {'version': definition['version'], 'purge': definition['horizon'], 'embargo': definition['embargo'], 'folds': len(definition['folds']),
             'blocks': report['validation']['blocks']}
    judgements = _judgements(report)
    count = 0
    with registry.Registry(lab.path) as store:
        for key, result in lab.results.items():
            if result.get('status') != 'RUN':
                continue
            identity = registry.model_id(key, result['target'], d.manifest['dataset_hash'], [b['chosen'] for b in result['blocks']], code, run)
            artifacts = {}
            for part in ('dev', 'holdout'):
                rows, prediction = tournament.gather(result, part)
                artifacts[part] = store.add_predictions(identity, rows, prediction, part=part)
            judged = judgements.get(key, [])
            # one research status per judged head; the model's own status is that of the primary target's head when it has one
            leading = next((r for r in judged if r['target'] == targets.PRIMARY), judged[0] if judged else None)
            names = [d.feature_names[i] for i in result['columns']]
            network = result.get('family', '').startswith(NETWORK_FAMILIES)
            record = {
                'model_id': identity, 'report_id': run, 'name': key, 'family': result.get('family'), 'architecture': ARCHITECTURE.get(result['name'], result['name']),
                'target': result['target'], 'horizons': sorted({int(str(t).rsplit('_', 1)[1]) for t in ([result['target']] if isinstance(result['target'], str) else result['target'])
                                                                if str(t)[-1].isdigit()}),
                'feature_groups': _groups(key, result['name']), 'feature_names': names, 'feature_versions': {'calculation_hash': d.manifest['calculation_hash'],
                                                                                                             'encoding': d.manifest['encoding_version']},
                'training_window': [b['train'] for b in report['validation']['blocks']], 'validation_window': [b['validation'] for b in report['validation']['blocks']],
                'split': split, 'hyperparameters': {'chosen_by_block': {b['block']: b['chosen'] for b in result['blocks']},
                                                    'tried_by_block': {b['block']: b['tried'] for b in result['blocks']}, 'quantile': result.get('quantile'),
                                                    'members': result.get('members')},
                'seeds': list(deep.SEEDS) if network else [GATE_SEED] if key == 'ensemble/specialist_gating' else [0],
                'library_versions': versions, 'code_hash': code, 'dataset_hash': d.manifest['dataset_hash'],
                'metrics': [{k: v for k, v in r.items() if k not in ('status_reasons',)} for r in judged],
                'artifact': {'kind': 'out-of-sample predictions (development folds and final holdout), stored in modeling_predictions', 'sha256': artifacts,
                             'fitted_weights_stored': False, 'refit': 'deterministic from dataset_hash, split, hyperparameters and seeds',
                             'use': 'research record only: nothing here can be loaded by a trading path'},
                'status': leading['status'] if leading else 'EXPERIMENTAL',
                'status_reasons': leading['status_reasons'] if leading else ['a diagnostic or component run; not judged as a candidate on its own'],
                'status_by_target': {r['target']: r['status'] for r in judged},
                'role': leading['role'] if leading else 'DIAGNOSTIC',
                'time_policy': TIME_POLICY, 'plan_version': tournament.PLAN_VERSION,
                'parameters': max((b['parameters'] for b in result['blocks']), default=0),
                'sufficiency': lab.sufficiency_record.get(key),
            }
            count += store.add_model(record)
        store.add_run(run, {'report_id': run, 'plan_version': report['plan_version'], 'dataset_hash': d.manifest['dataset_hash'],
                            'code_hash': code, 'models_registered': count, 'configurations_fitted': report['validation']['configurations_fitted'],
                            'seconds': report['seconds'], 'state': 'FINISHED', 'supersedes': report.get('supersedes')})
        store.add_report(run, report)
    return {'models_registered': count, 'report_id': run}
