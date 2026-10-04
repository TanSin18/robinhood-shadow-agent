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
from .lab import ALL_GROUPS, COST_RANGE, QUANTILES, SEQUENCE_GROUPS, SPECIALISTS, TECHNICAL, fold_losses, rmse, summarize

BASELINES = ('zero', 'historical_mean', 'instrument_mean', 'momentum_20', 'momentum_63', 'momentum_126', 'registered_style_momentum')
ADVANCED_FAMILIES = ('C_boosted_trees', 'D_neural', 'E_sequence', 'F_transformer', 'ensemble')
ARCHITECTURE = {
    'zero': 'constant 0', 'historical_mean': 'training mean', 'instrument_mean': 'per-instrument training mean',
    'momentum_20': 'one-variable line on return20', 'momentum_63': 'one-variable line on return63', 'momentum_126': 'one-variable line on return126',
    'registered_style_momentum': 'one-variable line on return126 where price is above its 200-session average', 'base_rate': 'training positive share',
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


def _row(key, lab, summary, *, role, status, reasons, label=None):
    result = lab.results[key]
    dev, holdout = summary.get('dev', {}), summary.get('holdout', {})
    ranking_dev, ranking_holdout = dev.get('ranking', {}), holdout.get('ranking', {})
    folds = summary.get('fold_ics', [])
    row = {'key': key, 'name': label or result['name'], 'family': result.get('family'), 'role': role, 'status': status, 'status_reasons': reasons,
           'target': summary.get('target'), 'dev_mean_ic': summary.get('dev_mean_ic'), 'dev_ic_interval_90': ranking_dev.get('ic_interval_90'),
           'dev_non_overlapping_windows': ranking_dev.get('non_overlapping_windows'), 'fold_ics': folds,
           'folds_positive': int(sum(1 for x in folds if x is not None and np.isfinite(x) and x > 0)), 'folds': len(folds),
           'holdout_mean_ic': summary.get('holdout_mean_ic'), 'holdout_ic_interval_90': ranking_holdout.get('ic_interval_90'),
           'holdout_non_overlapping_windows': ranking_holdout.get('non_overlapping_windows'),
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


def assemble(lab) -> dict:
    """Summaries, statuses and the report dictionary. Does not write anything."""
    d, draws = lab.data, lab.draws
    tables, summaries = {}, {}

    def summary(key, **kw):
        if key not in summaries:
            summaries[key] = summarize(lab.results[key], d, draws=draws, **kw) if lab.results[key]['status'] == 'RUN' else None
        return summaries[key]

    def judged(target, candidates, classification=False):
        """Rows for one target: baselines, then candidates with statuses from the fixed rules and a Holm family over candidates."""
        base_target = targets.PRIMARY if classification else target
        baselines = {name: summary(f'{name}/{base_target}') for name in BASELINES}
        strongest = selection.strongest_baseline(baselines)
        base = baselines[strongest]
        rows = []
        if not classification:
            for name in BASELINES:
                rows.append(_row(f'{name}/{target}', lab, baselines[name], role='BASELINE', status='EXPERIMENTAL',
                                 reasons=['naive baseline: a reference, not a candidate'] + (['the strongest baseline on development sessions'] if name == strongest else [])))
        ready = [(key, label, kw) for key, label, kw in candidates if lab.results.get(key, {}).get('status') == 'RUN']
        holm = metrics.holm({key + str(kw): summary_with(key, kw)['p_holdout_ic_not_positive'] for key, label, kw in ready})
        base_rate_loss = None
        if classification:
            rate = summary(f'base_rate/{targets.CLASSIFICATION}')
            base_rate_loss = rate['dev']['classification']['log_loss']
            rows.append(_row(f'base_rate/{targets.CLASSIFICATION}', lab, rate, role='BASELINE', status='EXPERIMENTAL', reasons=['naive baseline: the training positive share']))
        for key, label, kw in ready:
            record = dict(summary_with(key, kw))
            if classification:
                record['base_rate_log_loss'] = base_rate_loss
            sufficient = lab.sufficiency_record.get(key, {}).get('sufficient', True)
            status, reasons = selection.status(record, base, holm_rejected=holm[key + str(kw)]['rejected'], sufficient=sufficient)
            reasons = [f'compared with the strongest naive baseline: {strongest}'] + reasons + [f'Holm-adjusted p (holdout mean IC not above zero): {holm[key + str(kw)]["adjusted"]:.3f}']
            row = _row(key, lab, record, role='CANDIDATE', status=status, reasons=reasons, label=label)
            row['sufficiency'] = None if key not in lab.sufficiency_record else lab.sufficiency_record[key]['label']
            row['holm_adjusted_p'] = holm[key + str(kw)]['adjusted']
            rows.append(row)
        for key, label, kw in candidates:
            if lab.results.get(key, {}).get('status') == 'NOT_RUN':
                rows.append({'key': key, 'name': label, 'role': 'CANDIDATE', 'status': None, 'not_run': lab.results[key]['reason'], 'target': target})
        return rows, strongest

    cache = {}

    def summary_with(key, kw):
        token = key + str(kw)
        if token not in cache:
            cache[token] = summarize(lab.results[key], d, draws=draws, **kw)
        return cache[token]

    multi_names = [n for n, _ in lab.MULTI]
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
    ablation = {'reference_models': ['ridge', 'lightgbm'], 'sets': lab.ablation_sets, 'rows': [], 'target': targets.PRIMARY}
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
                paired = metrics.paired_difference(np.asarray(s['dev_ic_series'], dtype=float), np.asarray(base['dev_ic_series'], dtype=float), block=10, draws=draws)
                row.update({'dev_ic_change': paired['estimate'], 'dev_ic_change_interval_90': [paired['low'], paired['high']],
                            'holdout_ic_change': (s['holdout_mean_ic'] or 0.0) - (base['holdout_mean_ic'] or 0.0),
                            'dev_rmse_change': s['dev']['regression']['rmse'] - base['dev']['regression']['rmse']})
                if name == 'technical+fibonacci':
                    fib[model] = {'dev': paired, 'holdout_difference': row['holdout_ic_change']}
            ablation['rows'].append(row)
    verdict, why = selection.fibonacci_verdict(fib) if len(fib) == 2 else ('INCONCLUSIVE', 'a reference model did not run')
    ablation['fibonacci'] = {'answer': verdict, 'statement': f'FIBONACCI ADDS INCREMENTAL OOS VALUE = {verdict}', 'why': why,
                             'by_reference_model': {m: {'dev_ic_change': v['dev']['estimate'], 'dev_interval_90': [v['dev']['low'], v['dev']['high']],
                                                        'holdout_ic_change': v['holdout_difference'], 'development_blocks': v['dev'].get('blocks')} for m, v in fib.items()}}

    # ---- specialists and combinations
    specialists = {'target': targets.PRIMARY, 'rows': []}
    for name in SPECIALISTS:
        s = summary(f'specialist/{name}')
        specialists['rows'].append({'specialist': name, 'groups': list(SPECIALISTS[name]), 'features': len(lab.results[f'specialist/{name}']['columns']),
                                    'dev_mean_ic': s['dev_mean_ic'], 'holdout_mean_ic': s['holdout_mean_ic'], 'fold_ics': s['fold_ics'],
                                    'dev_rmse': s['dev']['regression']['rmse'],
                                    'note': 'the same for every instrument on a day: cannot rank within a session' if name == 'macro' else
                                            'descriptors exist for 5 single stocks only' if name in ('fundamental', 'event') else ''})
    unified = summary(f'lightgbm/{targets.PRIMARY}')
    specialists['unified_model'] = {'model': 'lightgbm on the full feature set', 'dev_mean_ic': unified['dev_mean_ic'], 'holdout_mean_ic': unified['holdout_mean_ic']}
    specialists['combinations'] = [{'name': r['name'], 'dev_mean_ic': r['dev_mean_ic'], 'holdout_mean_ic': r['holdout_mean_ic'], 'fold_ics': r['fold_ics'], 'status': r['status']}
                                   for r in tables[targets.PRIMARY] if r.get('family') == 'ensemble']
    specialists['notes'] = lab.ensemble_notes

    # ---- multi-task against separately trained networks
    multi = {'heads': multi_names, 'rows': []}
    for target in targets.REGRESSION + (c,):
        single = summary(f'mlp/{target}') if lab.results.get(f'mlp/{target}', {}).get('status') == 'RUN' else None
        for name in ('mlp_multi_task', 'transformer_multi_task'):
            if lab.results.get(name, {}).get('status') != 'RUN':
                continue
            s = summary_with(name, {'head': multi_names.index(target)})
            multi['rows'].append({'target': target, 'model': name, 'dev_mean_ic': s['dev_mean_ic'], 'holdout_mean_ic': s['holdout_mean_ic'],
                                  'separately_trained_mlp_dev_mean_ic': None if single is None else single['dev_mean_ic'],
                                  'separately_trained_mlp_holdout_mean_ic': None if single is None else single['holdout_mean_ic']})
    multi['tested'] = bool(multi['rows'])

    # ---- best by development score, with what the holdout said
    def best(rows, field='dev_mean_ic', lowest=False, only=None):
        pool = [r for r in rows if r.get(field) is not None and np.isfinite(r[field]) and (only is None or only(r))]
        if not pool:
            return None
        r = (min if lowest else max)(pool, key=lambda r: r[field])
        return {k: r.get(k) for k in ('name', 'family', 'role', 'status', 'dev_mean_ic', 'holdout_mean_ic', 'fold_ics', 'dev_rmse', 'holdout_rmse', 'dev_log_loss',
                                      'holdout_log_loss', 'dev_roc_auc', 'holdout_roc_auc', 'sufficiency')}

    primary_rows = tables[targets.PRIMARY]
    champions = {f'best_{h}d': best(tables[f'excess_return_{h}']) for h in targets.HORIZONS}
    champions['best_classifier'] = best(tables[c], 'dev_log_loss', lowest=True)
    champions['strongest_baseline'] = best(primary_rows, only=lambda r: r['role'] == 'BASELINE')
    champions['strongest_advanced_candidate'] = best(primary_rows, only=lambda r: r.get('family') in ADVANCED_FAMILIES)
    quantile_models = {k: v for k, v in distribution['models'].items() if 'mean_dev_pinball' in v}
    if quantile_models:
        name = min(quantile_models, key=lambda k: quantile_models[k]['mean_dev_pinball'])
        champions['best_distribution_model'] = {'name': name, 'mean_dev_pinball': quantile_models[name]['mean_dev_pinball'],
                                                'mean_holdout_pinball': quantile_models[name]['mean_holdout_pinball'], 'status': quantile_models[name].get('status')}
    downside = {k: v for k, v in risk['close_mae_10'].items() if 'dev_rmse' in v}
    name = min(downside, key=lambda k: downside[k]['dev_rmse'])
    champions['best_downside_model'] = {'name': name, 'target': 'close_mae_10', 'dev_rmse': downside[name]['dev_rmse'], 'holdout_rmse': downside[name]['holdout_rmse'],
                                        'status': downside[name]['status']}
    statuses = {}
    for rows in tables.values():
        for r in rows:
            if r.get('status') and r['role'] == 'CANDIDATE':
                statuses[r['status']] = statuses.get(r['status'], 0) + 1
    champions['candidate_status_counts'] = statuses
    champions['note'] = ('"Best" is the highest development score. It is not a selection for use. With this little data a naive baseline being best, or nothing '
                         'being established, is a real and acceptable result.')

    # ---- economic relevance: a ranking spread beside a stated cost range; not a profit figure
    economic = {'cost_range_round_trip_two_legs': list(COST_RANGE), 'statement': 'A top-5 minus bottom-5 mean realised 10-session excess return, beside a stated '
                'plausible cost range. Not net strategy P&L: no weights, no holding rule, no cost model, no capacity.', 'rows': []}
    for r in primary_rows:
        if r.get('dev_top_minus_bottom') is not None and (r['role'] == 'BASELINE' and r['name'] == strongest_by_target[targets.PRIMARY] or r['name'] in ('ridge', 'lightgbm', 'xgboost', 'catboost', 'family_equal_weight')):
            economic['rows'].append({'name': r['name'], 'dev_spread': r['dev_top_minus_bottom'], 'dev_interval_90': r['dev_top_minus_bottom_interval_90'],
                                     'holdout_spread': r['holdout_top_minus_bottom'], 'holdout_interval_90': r['holdout_top_minus_bottom_interval_90'],
                                     'dev_interval_clears_upper_cost': bool(r['dev_top_minus_bottom_interval_90'] and r['dev_top_minus_bottom_interval_90'][0] is not None
                                                                           and np.isfinite(r['dev_top_minus_bottom_interval_90'][0]) and r['dev_top_minus_bottom_interval_90'][0] > COST_RANGE[1])})

    rows_all = lab.rows
    sessions = np.unique(d.row_session[rows_all])
    definition = lab.definition
    blocks = [b.as_dict(d.sessions) for b in definition['folds']] + [definition['holdout'].as_dict(d.sessions)]
    development_sessions = definition['development_end'] - definition['first'] + 1
    report = {
        'warning': WARNING, 'plan_version': tournament.PLAN_VERSION, 'time_policy': TIME_POLICY, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'code_hash': registry.code_hash(), 'library_versions': models.versions(),
        'dataset': {'dataset_hash': d.manifest['dataset_hash'], 'hashes': d.manifest['hashes'], 'source_sha256': d.manifest['source_sha256'],
                    'calculation_hash': d.manifest['calculation_hash'], 'instruments': d.instruments, 'benchmark': d.manifest['benchmark'],
                    'stored_sessions': len(d.sessions), 'first_session': d.sessions[0], 'last_session': d.sessions[-1],
                    'usable_samples': int(len(rows_all)), 'usable_sessions': int(len(sessions)), 'first_usable_session': d.sessions[sessions[0]],
                    'last_usable_session': d.sessions[sessions[-1]], 'strict_point_in_time_samples': 0, 'features': len(d.feature_names),
                    'features_by_family': {f: sum(1 for n in d.feature_names if d.feature_family[n] == f) for f in sorted(set(d.feature_family.values()))},
                    'feature_availability_by_family': {f: round(float(np.mean([d.manifest['feature_availability'][n] for n in d.feature_names if d.feature_family[n] == f])), 3)
                                                       for f in sorted(set(d.feature_family.values()))},
                    'excluded_features': len(d.excluded), 'targets': list(targets.ALL), 'horizons': list(targets.HORIZONS), 'target_version': targets.TARGET_VERSION,
                    'non_overlapping_windows': {str(h): int(len(sessions) // h) for h in targets.HORIZONS},
                    'average_pair_correlation_of_labels': lab.pair_correlation, 'effective_independent_instruments': lab.breadth,
                    'limitations': [
                        'Retrospective: every input was captured on 2026-10-01 to 2026-10-03. Under the strict known-at rule there are 0 usable samples.',
                        'A close is treated as known at its own session close; closes are split-adjusted as of the capture date.',
                        f'{len(d.instruments)} instruments, most of them funds; {int(len(sessions))} usable sessions; about {int(len(sessions) // 10)} non-overlapping 10-session windows.',
                        'Labels are price returns on both legs: distributions are not added back.',
                        'The label starts at the close the features end at: a research label, not an executable entry.',
                        'No OHLCV, intraday, CPI, labor, Treasury-yield, market-volatility, consensus or historical sector-constituent data. Nothing substitutes for them.',
                        'Fundamental and event descriptors exist for 5 single stocks only. Sector mappings are effective 2026-10-03 and are unavailable for every historical session.',
                        'Macro descriptors (Fed, PCE) are validated from mid-2026 only and are identical across instruments on a day.']},
        'validation': {'split_method': definition['version'], 'walk_forward_folds': len(definition['folds']), 'purge_sessions': definition['horizon'],
                       'embargo_sessions': definition['embargo'], 'gap_before_holdout_sessions': definition['gap_before_holdout'], 'blocks': blocks,
                       'development_sessions': int(development_sessions), 'holdout_sessions': blocks[-1]['validation_sessions'],
                       'inner_tuning': 'the last quarter of each training window, purged; every tried configuration recorded',
                       'configurations_fitted': int(lab.configurations), 'bootstrap': f'moving block, block = label horizon, {draws} draws, fixed seed',
                       'multiple_testing': 'Holm at 10% over the candidates of each target, on holdout mean IC above zero'},
        'tables': tables, 'strongest_baseline': strongest_by_target, 'distribution': distribution, 'risk': risk, 'risk_baselines': risk_baselines, 'ablation': ablation, 'specialists': specialists,
        'multi_task': multi, 'uncertainty': lab.uncertainty_record, 'calibration': lab.calibration_record, 'disagreement': lab.disagreement_record,
        'meta_label': lab.meta, 'conditional': lab.conditional_record, 'importance': lab.importance_record, 'examples': lab.example_records,
        'sufficiency': lab.sufficiency_record, 'frequency': lab.frequency_record, 'economic': economic, 'champions': champions,
        'seconds': round(time.time() - lab.started, 1),
    }
    report['report_id'] = content_hash([report['dataset']['dataset_hash'], report['code_hash'], report['plan_version'], report['generated_at']])
    return report


def write(lab, report) -> dict:
    """Stores every evaluated model, its out-of-sample predictions and the report in the modeling database."""
    d = lab.data
    code, versions = report['code_hash'], report['library_versions']
    definition = lab.definition
    split = {'version': definition['version'], 'purge': definition['horizon'], 'embargo': definition['embargo'], 'folds': len(definition['folds']),
             'blocks': report['validation']['blocks']}
    rows_by_key = {}
    for target, rows in report['tables'].items():
        for r in rows:
            if r.get('status'):
                rows_by_key.setdefault(r['key'], []).append(r)
    count = 0
    with registry.Registry(lab.path) as store:
        for key, result in lab.results.items():
            if result.get('status') != 'RUN':
                continue
            artifacts = {}
            for part in ('dev', 'holdout'):
                rows, prediction = tournament.gather(result, part)
                identity = registry.model_id(key, result['target'], d.manifest['dataset_hash'], [b['chosen'] for b in result['blocks']], code)
                artifacts[part] = store.add_predictions(identity, rows, prediction, part=part)
            judged = rows_by_key.get(key, [])
            # one research status per judged head; the model's own status is that of the primary target's head when it has one
            leading = next((r for r in judged if r['target'] == targets.PRIMARY), judged[0] if judged else None)
            names = [d.feature_names[i] for i in result['columns']]
            record = {
                'model_id': identity, 'name': key, 'family': result.get('family'), 'architecture': ARCHITECTURE.get(result['name'], result['name']),
                'target': result['target'], 'horizons': sorted({int(str(t).rsplit('_', 1)[1]) for t in ([result['target']] if isinstance(result['target'], str) else result['target'])
                                                                if str(t)[-1].isdigit()}),
                'feature_groups': _groups(key, result['name']), 'feature_names': names, 'feature_versions': {'calculation_hash': d.manifest['calculation_hash'],
                                                                                                             'encoding': d.manifest['encoding_version']},
                'training_window': [b['train'] for b in report['validation']['blocks']], 'validation_window': [b['validation'] for b in report['validation']['blocks']],
                'split': split, 'hyperparameters': {'chosen_by_block': {b['block']: b['chosen'] for b in result['blocks']},
                                                    'tried_by_block': {b['block']: b['tried'] for b in result['blocks']}, 'quantile': result.get('quantile')},
                'seeds': list(deep.SEEDS) if result.get('family', '').startswith(('D_', 'E_', 'F_')) else [0],
                'library_versions': versions, 'code_hash': code, 'dataset_hash': d.manifest['dataset_hash'],
                'metrics': [{k: v for k, v in r.items() if k not in ('status_reasons',)} for r in judged],
                'artifact': {'kind': 'out-of-sample predictions (development folds and final holdout), stored in modeling_predictions', 'sha256': artifacts,
                             'fitted_weights_stored': False, 'refit': 'deterministic from dataset_hash, split, hyperparameters and seeds'},
                'status': leading['status'] if leading else 'EXPERIMENTAL',
                'status_reasons': leading['status_reasons'] if leading else ['a diagnostic or component run; not judged as a candidate on its own'],
                'status_by_target': {r['target']: r['status'] for r in judged},
                'role': leading['role'] if leading else 'DIAGNOSTIC', 'report_id': report['report_id'],
                'time_policy': TIME_POLICY, 'plan_version': tournament.PLAN_VERSION,
                'parameters': max((b['parameters'] for b in result['blocks']), default=0),
                'sufficiency': lab.sufficiency_record.get(key),
            }
            count += store.add_model(record)
        store.add_run(report['report_id'], {'report_id': report['report_id'], 'plan_version': report['plan_version'], 'dataset_hash': d.manifest['dataset_hash'],
                                            'code_hash': code, 'models_registered': count, 'configurations_fitted': report['validation']['configurations_fitted'],
                                            'seconds': report['seconds'], 'state': 'FINISHED'})
        store.add_report(report['report_id'], report)
    return {'models_registered': count, 'report_id': report['report_id']}
