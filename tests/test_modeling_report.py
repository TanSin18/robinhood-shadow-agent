"""Checkpoint 7 end to end on a small synthetic dataset: the whole laboratory run, its report, the registry, the exported
file and the page that reads it.

What is proven here: the report that the page shows is the report the run assembled; a score that is only a rank has no
error in return units; every target names the naive baseline it was judged against, and a risk model is judged against
the strongest one; a multi-head network has one research status per head; recalibration and stacking learn only from
inner blocks; a rerun gives the same numbers; the exported file holds no feature row, no sample and no prediction."""
import json
import sqlite3

import pytest

np = pytest.importorskip('numpy')
for module in ('sklearn', 'xgboost', 'lightgbm', 'catboost', 'torch'):
    pytest.importorskip(module)

from agents.desk import modeling_lab
from firm_lab import modeling_view
from firm_lab.modeling import cli, deep, lab as lab_module, models, registry, report as report_module, selection, targets, timeview, tournament
from firm_lab.modeling.dataset import Dataset

FAMILIES = {'trend': ['sma200_distance', 'sma50_distance'], 'momentum': ['return20', 'return63', 'return126', 'rsi14_wilder'], 'volatility': ['realized_vol20'],
            'fibonacci': ['fib_a', 'fib_b'], 'support_resistance': ['sr_a'], 'breakout_structure': ['bo_a'], 'fundamentals': ['fund_a'], 'earnings_events': ['ev_a'],
            'sector': ['sec_a'], 'macro_context': ['days_since_fomc', 'fed_latest_change_bps', 'pce_core_mom_sa']}
NAMES = [n for members in FAMILIES.values() for n in members]
FAMILY = {n: f for f, members in FAMILIES.items() for n in members}
SESSIONS, INSTRUMENTS = 300, 12
SMALL_GRIDS = {'ridge': [{'alpha': 100.0}, {'alpha': 1000.0}], 'elastic_net': [{'alpha': 0.002, 'l1_ratio': 0.5}], 'logistic': [{'C': 0.01}],
               'xgboost': [{'max_depth': 2, 'n_estimators': 20, 'learning_rate': 0.1}], 'lightgbm': [{'num_leaves': 4, 'n_estimators': 20, 'learning_rate': 0.1}],
               'catboost': [{'depth': 2, 'iterations': 20, 'learning_rate': 0.1}]}


def synthetic(seed=0) -> Dataset:
    g = np.random.default_rng(seed)
    rows = [(i, s) for s in range(SESSIONS) for i in range(INSTRUMENTS)]
    X = g.normal(size=(len(rows), len(NAMES)))
    session, instrument = np.array([s for _, s in rows]), np.array([i for i, _ in rows])
    for name in FAMILIES['macro_context']:
        X[:, NAMES.index(name)] = g.normal(size=SESSIONS)[session]                                  # the same for every instrument on a day
    for name in ('fund_a', 'ev_a'):
        X[instrument >= 4, NAMES.index(name)] = np.nan                                              # single stocks only
    X[:, NAMES.index('realized_vol20')] = np.abs(X[:, NAMES.index('realized_vol20')])
    y = {}
    for h in targets.HORIZONS:
        v = 0.012 * X[:, NAMES.index('return20')] * (h / 10) + g.normal(scale=0.03, size=len(rows))
        v[session + h >= SESSIONS] = np.nan
        y[f'excess_return_{h}'] = v
    y[targets.CLASSIFICATION] = np.where(np.isfinite(y['excess_return_10']), (y['excess_return_10'] > 0).astype(float), np.nan)
    live = session + 10 < SESSIONS
    y['close_mae_10'] = np.where(live, -np.abs(g.normal(scale=0.02, size=len(rows))), np.nan)
    y['close_mfe_10'] = np.where(live, np.abs(g.normal(scale=0.02, size=len(rows))), np.nan)
    # future volatility is mostly the last 20 sessions' volatility: persistence is by far the strongest naive baseline
    y['future_realized_vol_10'] = np.where(live, 0.1 + 0.2 * X[:, NAMES.index('realized_vol20')] + g.normal(scale=0.01, size=len(rows)), np.nan)
    return Dataset(sessions=[f'S{k:03d}' for k in range(SESSIONS)], instruments=[f'I{k:02d}' for k in range(INSTRUMENTS)], feature_names=list(NAMES),
                   feature_family=dict(FAMILY), X=X, row_instrument=instrument, row_session=session, y=y, snapshot_ids=[f'{k:064d}' for k in range(len(rows))],
                   label_records=[{} for _ in rows], excluded={},
                   manifest={'dataset_hash': 'd' * 64, 'calculation_hash': 'c' * 64, 'encoding_version': 'numeric-encoding-v1', 'hashes': {}, 'source_sha256': 's' * 64,
                             'benchmark': 'VTI', 'feature_availability': {n: 1.0 for n in NAMES}})


class SmallLab(lab_module.Lab):
    def prepare(self):
        self.data = synthetic()
        self.measure()


def _database(folder):
    path = folder / 'firm_lab_modeling.db'
    db = sqlite3.connect(path)
    with db:
        timeview.create_tables(db)
        db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
        for key, value in (('mode', 'BUILD_OBSERVE'), ('database_role', 'CHECKPOINT7_MODELING_RESEARCH'), ('time_policy', json.dumps({'source_sha256': 's' * 64}))):
            db.execute('INSERT INTO firm_meta VALUES (?,?,?)', (key, value, '2026-10-03T00:00:00+00:00'))
        db.execute('INSERT INTO modeling_datasets VALUES (?,?,?)', ('d:samples', json.dumps({'samples': 'not for export'}), '2026-10-03T00:00:00+00:00'))
    db.close()
    return path


def _run(path):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(models, 'GRIDS', SMALL_GRIDS)
        patch.setattr(deep, 'SEEDS', (11, 23))
        patch.setattr(deep.TorchModel, 'EPOCHS', 4)
        closes = 100 * np.exp(np.cumsum(np.random.default_rng(5).normal(scale=0.01, size=SESSIONS)))
        patch.setattr(targets, 'load_closes', lambda _path: ([f'S{k:03d}' for k in range(SESSIONS)], {'VTI': list(closes)}))
        run = SmallLab(path, log=lambda _text: None, quick=True).execute()
        body = report_module.assemble(run)
        written = report_module.write(run, body)
    return run, body, written


@pytest.fixture(scope='module')
def finished(tmp_path_factory):
    folder = tmp_path_factory.mktemp('laboratory')
    path = _database(folder)
    run, body, written = _run(path)
    return {'folder': folder, 'path': path, 'run': run, 'report': registry.clean(body), 'written': written}


def test_a_score_that_is_only_a_rank_has_no_error_in_return_units(finished):
    rows = {r['name']: r for r in finished['report']['tables'][targets.PRIMARY]}
    ranked = rows['family_equal_weight']
    assert ranked['dev_mean_ic'] is not None and ranked['holdout_mean_ic'] is not None             # it is still judged as a ranking
    for field in ('dev_rmse', 'holdout_rmse', 'dev_mae', 'dev_r2', 'dev_r2_vs_zero', 'dev_directional_accuracy', 'dev_buckets'):
        assert ranked.get(field) is None, field                                                      # a rank is not a return forecast
    assert rows['ridge']['dev_rmse'] is not None and rows['specialist_equal_weight']['dev_rmse'] is not None       # averages of return forecasts keep theirs
    result = finished['run'].results['ensemble/family_equal_weight']
    assert result['scale'] == 'rank' and 'regression' not in tournament.score(result, finished['run'].data, part='dev')


def test_every_target_names_the_naive_baseline_it_was_judged_against(finished):
    report = finished['report']
    assert set(report['strongest_baseline']) == set(targets.REGRESSION) | {targets.CLASSIFICATION}
    assert report['strongest_baseline'][targets.CLASSIFICATION] == report['strongest_baseline'][targets.PRIMARY]   # a classifier ranks the 10-session return
    for row in report['tables'][targets.CLASSIFICATION]:
        if row['role'] == 'CANDIDATE' and row.get('status'):
            assert row['status_reasons'][0] == 'compared with the strongest naive baseline: ' + report['strongest_baseline'][targets.CLASSIFICATION]


def test_a_risk_model_is_judged_against_the_strongest_naive_baseline_not_the_weakest(finished):
    report = finished['report']
    assert report['risk_baselines'] == {'close_mae_10': 'historical_mean', 'close_mfe_10': 'historical_mean', 'future_realized_vol_10': 'volatility_persistence'}
    body = report['risk']['future_realized_vol_10']
    assert body['volatility_persistence']['dev_rmse'] < body['historical_mean']['dev_rmse']        # planted: persistence is the stronger naive forecast
    assert body['volatility_persistence']['role'] == body['historical_mean']['role'] == 'BASELINE'
    for name in ('ridge', 'lightgbm'):
        model = body[name]
        folds, base = model['fold_rmse'], body['volatility_persistence']['fold_rmse']
        expected = selection.loss_status(folds, base, model['holdout_rmse'], body['volatility_persistence']['holdout_rmse'])[0]
        assert model['status'] == expected and model['compared_with'] == 'volatility_persistence'
        if model['dev_rmse'] >= body['volatility_persistence']['dev_rmse']:
            assert model['status'] == 'REJECTED'                                                    # beating the training mean is not enough
    assert selection.strongest_loss_baseline({'a': [0.3, 0.3], 'b': [0.1, 0.2], 'c': [0.2, 0.2]}) == 'b'


def test_a_multi_head_network_has_a_status_per_head_and_the_primary_head_names_the_model(finished):
    models_stored = {m['name']: m for m in registry.Registry(finished['path']).models()}
    tables = finished['report']['tables']
    for name in ('mlp_multi_task', 'transformer_multi_task'):
        record = models_stored[name]
        by_head = {target: next(r['status'] for r in rows if r['key'] == name) for target, rows in tables.items()}
        assert record['status_by_target'] == by_head and len(by_head) == 4
        assert record['status'] == by_head[targets.PRIMARY]                                         # the primary question decides, not whichever table came first
    assert models_stored['ridge/excess_return_10']['status_by_target'] == {targets.PRIMARY: models_stored['ridge/excess_return_10']['status']}


def test_the_report_has_no_empty_placeholder_and_says_when_groups_cannot_be_compared(finished):
    report = finished['report']
    assert 'families' not in report['importance'] and report['importance']['ridge']['family_share']
    groups = report['conditional']['vti_volatility_terciles']
    readable = sum(1 for g in groups['groups'] if g['meaningful'])
    assert groups['comparison_possible'] == (readable >= 2) and groups['result']
    if not groups['comparison_possible']:
        assert groups['result'].startswith('INSUFFICIENT_DATA')


def test_every_fitted_model_is_registered_with_its_configuration_seeds_and_the_run_it_belongs_to(finished):
    report, written = finished['report'], finished['written']
    with registry.Registry(finished['path']) as store:
        stored = store.models()
        assert store.latest_report()['report_id'] == report['report_id'] == written['report_id']
    assert len(stored) == written['models_registered'] == sum(1 for r in finished['run'].results.values() if r['status'] == 'RUN')
    assert {m['report_id'] for m in stored} == {report['report_id']} and {m['status'] for m in stored} <= set(selection.STATUSES)
    ridge = next(m for m in stored if m['name'] == f'ridge/{targets.PRIMARY}')
    blocks = ['fold_1', 'fold_2', 'fold_3', 'fold_4', 'fold_5', 'final_holdout']
    assert sorted(ridge['hyperparameters']['chosen_by_block']) == sorted(blocks) and all(ridge['hyperparameters']['chosen_by_block'][b] in SMALL_GRIDS['ridge'] for b in blocks)
    assert all(len(ridge['hyperparameters']['tried_by_block'][b]) == 2 for b in blocks)             # every tried configuration and its inner score is on record
    assert ridge['seeds'] == [0] and ridge['dataset_hash'] == 'd' * 64 and ridge['code_hash'] == registry.code_hash() and ridge['artifact']['fitted_weights_stored'] is False
    network = next(m for m in stored if m['name'] == f'mlp/{targets.PRIMARY}')
    assert network['seeds'] == [11, 23] and network['parameters'] > 0 and network['sufficiency']['label'] in ('sufficient', 'EXPERIMENTAL_INSUFFICIENT_DATA')
    assert not [m for m in stored if m['role'] == 'BASELINE' and m['status'] != 'EXPERIMENTAL']     # a naive baseline is a reference, never a challenger


def test_a_network_gives_the_same_numbers_when_it_is_fitted_again(finished):
    run = finished['run']
    data, definition = run.data, run.definition
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(deep, 'SEEDS', (11, 23))
        patch.setattr(deep.TorchModel, 'EPOCHS', 4)
        spec = {'name': 'mlp', 'cls': deep.MLP, 'grid': [{}], 'target': targets.PRIMARY, 'columns': data.columns(lab_module.ALL_GROUPS)}
        again = tournament.run(spec, data, definition)
        sequence = {'name': 'gru', 'cls': deep.GRU, 'grid': [{}], 'target': targets.PRIMARY, 'columns': data.columns(lab_module.SEQUENCE_GROUPS)}
        again_sequence = tournament.run(sequence, data, definition)
    for key, new in ((f'mlp/{targets.PRIMARY}', again), (f'gru/{targets.PRIMARY}', again_sequence)):
        for a, b in zip(run.results[key]['blocks'], new['blocks']):
            assert np.array_equal(a['prediction'], b['prediction'], equal_nan=True), key            # fixed seeds: the same fit, the same predictions
            assert np.array_equal(a['seed_predictions'], b['seed_predictions']) and a['seed_predictions'].shape[0] == 2


def test_recalibration_and_stacking_learn_only_from_inner_blocks(finished):
    """Wrecking every label of every predicted block and of the holdout changes no recalibrated probability and no stacker weight."""
    run = finished['run']
    before_calibration = run.calibration_record['lightgbm_recalibrated']
    before_weights = run.ensemble_notes['stacker_weights']
    data = run.data
    saved = {name: values.copy() for name, values in data.y.items()}
    first = run.definition['folds'][0]
    outside = ~np.isin(data.row_session, list(first.train))
    try:
        generator = np.random.default_rng(3)
        for name in (targets.PRIMARY, targets.CLASSIFICATION):
            wrecked = data.y[name].copy()
            mask = outside & np.isfinite(wrecked)
            wrecked[mask] = generator.integers(0, 2, mask.sum()) if name == targets.CLASSIFICATION else generator.normal(size=mask.sum())
            data.y[name] = wrecked
        block = first
        inner_rows, _ = run._inner_predictions([(f'lightgbm/{targets.CLASSIFICATION}', {'cls': models.LightGBMClassifier, 'target': targets.CLASSIFICATION,
                                                                                         'columns': run.columns(lab_module.ALL_GROUPS)})], block)
        assert set(int(s) for s in data.row_session[inner_rows]) <= set(first.train)                 # what a combiner learns from lies inside the training window
        assert max(data.row_session[inner_rows]) + tournament.PURGE < min(first.validation)          # and its labels had closed before the predicted block began
        assert np.array_equal(data.y[targets.CLASSIFICATION][inner_rows], saved[targets.CLASSIFICATION][inner_rows])      # untouched by the wrecking
        run.ensembles()
        assert run.ensemble_notes['stacker_weights'][0] == before_weights[0]                         # fold 1's weights did not move
        run.calibration()
        after = run.calibration_record['lightgbm_recalibrated']
        assert after['dev']['log_loss'] != before_calibration['dev']['log_loss']                     # the wrecked labels are scored ...
    finally:
        for name, values in saved.items():
            data.y[name] = values
        run.ensembles()
        run.calibration()
    assert run.calibration_record['lightgbm_recalibrated'] == before_calibration and run.ensemble_notes['stacker_weights'] == before_weights      # ... but nothing was learned from them


def test_the_exported_file_is_small_read_only_material_and_the_page_renders_the_real_report(finished, tmp_path):
    out = tmp_path / 'diag' / 'firm_lab'
    out.mkdir(parents=True)
    result = cli.export(finished['path'], out / modeling_view.FILE_NAME)
    assert result['rows']['modeling_reports'] == 1 and result['rows']['modeling_models'] == finished['written']['models_registered'] and result['rows']['modeling_datasets'] == 0
    with pytest.raises(ValueError, match='EXPORT_FOLDER_MISSING'):
        cli.export(finished['path'], tmp_path / 'no_such_folder' / modeling_view.FILE_NAME)
    with pytest.raises(ValueError, match='EXPORT_TARGET_EXISTS'):
        cli.export(finished['path'], finished['path'])
    db = sqlite3.connect(out / modeling_view.FILE_NAME)
    counts = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('modeling_predictions', 'modeling_feature_results', 'modeling_feature_inputs', 'modeling_time_view')}
    db.close()
    assert set(counts.values()) == {0}                                                               # no feature row, no sample, no prediction leaves the modeling database
    with pytest.raises(ValueError, match='EXPORT_TARGET_EXISTS'):
        cli.export(finished['path'], out / modeling_view.FILE_NAME)
    state = modeling_view.summary(out / 'firm_lab.db')
    assert state['exists'] and state['models'] == finished['written']['models_registered'] and state['report']['report_id'] == finished['report']['report_id']
    html = modeling_lab.render_modeling({'modeling': state})
    assert html.startswith('<p class="fl-stamp">MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE</p>') and 'FIBONACCI ADDS INCREMENTAL OOS VALUE = ' in html
    assert 'Strongest naive baseline on development sessions: <b>' + finished['report']['strongest_baseline'][targets.CLASSIFICATION] in html
    assert 'compared with volatility_persistence' in html and 'a rank score: no error in return units' in html
    assert 'Too few sessions fall in two groups' in html or 'Groups can be compared' in html
    # a second, older run in the same file is not counted with the newest report's models
    db = sqlite3.connect(out / modeling_view.FILE_NAME)
    with db:
        db.execute('INSERT INTO modeling_models VALUES (?,?,?)', ('old', json.dumps({'status': 'REJECTED', 'report_id': 'an-earlier-run'}), '2026-10-01T00:00:00+00:00'))
    db.close()
    again = modeling_view.summary(out / 'firm_lab.db')
    assert again['models'] == state['models'] and again['registry_statuses'] == state['registry_statuses'] and again['models_from_other_runs'] == 1


# ====================================================================================================== the independent review, end to end
def test_the_holm_family_of_a_label_is_every_registered_model_that_ranks_it(finished):
    report, run = finished['report'], finished['run']
    expected = {t: 0 for t in targets.REGRESSION}
    for result in run.results.values():
        if result['status'] != 'RUN' or result['kind'] == models.QUANTILE:
            continue
        heads = result['target'] if isinstance(result['target'], (tuple, list)) else [result['target']]
        for target in heads:
            if target in targets.REGRESSION:
                expected[target] += 1
            elif target == targets.CLASSIFICATION:
                expected[targets.PRIMARY] += 1                                                       # a classifier is tested on the 10-session label
    same = report['validation']['holm_rows_identical_to_another']
    assert same['ablation/ridge/full'] == f'ridge/{targets.PRIMARY}' and same['ablation/lightgbm/full'] == f'lightgbm/{targets.PRIMARY}'      # the same model run twice is one test
    expected[targets.PRIMARY] -= len(same)
    assert report['validation']['holm_family_sizes'] == expected
    assert expected[targets.PRIMARY] > 40 and expected['excess_return_5'] == expected['excess_return_20'] == 7 + 7 + 2      # baselines, candidates and both multi-task heads
    for target, rows in report['tables'].items():
        label = targets.PRIMARY if target == targets.CLASSIFICATION else target
        for row in rows:
            if row['role'] == 'CANDIDATE' and row.get('status'):
                assert row['holm_family_size'] == expected[label], (target, row['name'])            # not only the candidates of one table
                assert isinstance(row['holm_met'], bool) and 0 < row['dev_identity_p'] <= 1
                last = row['status_reasons'][-1]
                assert last.startswith('holdout mean IC above zero: ') and ('level 0.10: met' in last or 'level 0.10: not met' in last or 'no test, the holdout has' in last)


def test_every_result_fitted_as_a_network_is_gated_and_a_gate_failure_is_never_a_rejection_or_a_challenger(finished):
    report, run = finished['report'], finished['run']
    gates = report['sufficiency']
    networks = [key for key, r in run.results.items() if r['status'] == 'RUN' and r['family'].startswith(('D_', 'E_', 'F_'))]
    assert networks and set(networks) <= set(gates)
    assert 'ensemble/specialist_gating' in gates and gates['ensemble/specialist_gating']['parameters'] > 0      # the gating network is a network
    assert gates['ensemble/family_equal_weight']['inherited_from'] == [f'mlp/{targets.PRIMARY}']    # a combination holding a failed network fails too
    registered = {m['name']: m for m in registry.Registry(finished['path']).models()}
    assert registered['ensemble/specialist_gating']['seeds'] == [lab_module.GATE_SEED] and registered['ensemble/specialist_gating']['parameters'] > 0
    assert registered['ensemble/specialist_linear_stacker']['hyperparameters']['chosen_by_block']['fold_1']['weights']       # a combiner's weights are on record
    for rows in report['tables'].values():
        for row in rows:
            if row.get('sufficiency') == 'EXPERIMENTAL_INSUFFICIENT_DATA':
                assert row['status'] == 'EXPERIMENTAL' and any('EXPERIMENTAL_INSUFFICIENT_DATA' in r for r in row['status_reasons']), row['name']
    mlp = gates[f'mlp/{targets.PRIMARY}']
    last = run.results[f'mlp/{targets.PRIMARY}']['blocks'][-2]
    assert mlp['training_sessions'] == last['learn_sessions'] < last['train_sessions'] == mlp['training_window_sessions']      # the sessions gradient steps used


def test_nothing_measured_before_the_fits_reads_a_holdout_label(finished):
    run = finished['run']
    before = (dict(run.breadth), run.pair_correlation)
    data = run.data
    saved = {name: values.copy() for name, values in data.y.items()}
    holdout = np.isin(data.row_session, list(run.definition['holdout'].validation))
    try:
        for name in targets.REGRESSION:
            wrecked = data.y[name].copy()
            wrecked[holdout & np.isfinite(wrecked)] = np.random.default_rng(1).normal(size=int((holdout & np.isfinite(wrecked)).sum()))
            data.y[name] = wrecked
        run.measure()
        assert (dict(run.breadth), run.pair_correlation) == before                                  # the sufficiency gate's breadth is a development-only number
    finally:
        for name, values in saved.items():
            data.y[name] = values
        run.measure()
    assert set(run.breadth) == set(targets.REGRESSION)


def test_a_sequence_network_gets_the_same_missing_value_flags_as_every_other_network(finished):
    data = finished['run'].data
    rows = tournament.eligible_rows(data)[:400]
    columns = [NAMES.index('fund_a'), NAMES.index('return20')]
    from firm_lab.modeling.dataset import sequences
    windows, full = sequences(data, rows, columns, deep.SEQUENCE_LENGTH)
    model = deep.GRU()
    scaled = model._scale(windows[full], fit=True)
    assert scaled.shape[-1] == 3 and model.pre.names(['fund_a', 'return20']) == ['fund_a', 'return20', 'fund_a__missing']      # median and a flag, as the plan says
    assert set(np.unique(scaled[:, :, 2])) == {0.0, 1.0}


def test_the_registry_says_about_a_risk_or_quantile_model_exactly_what_the_report_says(finished):
    report = finished['report']
    registered = {m['name']: m for m in registry.Registry(finished['path']).models()}
    checked = 0
    for target, body in report['risk'].items():
        for name, row in body.items():
            record = registered[f'{name}/{target}']
            assert (record['status'], record['role']) == (row['status'], row['role']) and record['status_by_target'] == {target: row['status']}
            checked += 1
    for name, body in report['distribution']['models'].items():
        for q in report['distribution']['quantiles']:
            record = registered[f'{name}/q{int(q * 100):02d}']
            assert (record['status'], record['role']) == (body['status'], body['role'])
            checked += 1
    assert checked == 3 * 3 + 1 + 3 * 5
    assert registered['historical_mean/close_mae_10']['role'] == 'BASELINE' and registered['train_quantile/q50']['role'] == 'BASELINE'      # a naive baseline is registered as one
    assert not [m for m in registered.values() if m['role'] == 'DIAGNOSTIC' and m['name'].split('/')[0] in ('ridge', 'lightgbm', 'linear_quantile', 'lightgbm_quantile')
                and not m['name'].startswith(('ablation', 'specialist'))]


def test_the_report_counts_the_windows_that_are_predicted_and_shows_a_best_score_with_its_caveats(finished):
    report = finished['report']
    windows = report['dataset']['evaluation_windows']
    design = finished['run'].definition
    development, holdout = sum(len(f.validation) for f in design['folds']), len(design['holdout'].validation)
    assert windows['development']['sessions'] == development and windows['holdout']['sessions'] == holdout
    assert windows['development']['non_overlapping_windows'] == {'5': development // 5, '10': development // 10, '20': development // 20}
    assert windows['holdout']['batches_for_an_interval'] == {'5': holdout // 10, '10': holdout // 20, '20': holdout // 40}
    assert 'non_overlapping_windows' not in report['dataset'] and 'champions' not in report        # the count over all sessions is no longer the headline
    for row in report['tables'][targets.PRIMARY]:
        if row.get('status'):
            assert row['dev_batches'] == development // 20 and row['holdout_batches'] == holdout // 20 and row['dev_sessions'] == development
    best = report['best_research_models']
    for key in ('best_5d', 'best_10d', 'best_20d', 'best_classifier', 'strongest_advanced_candidate'):
        assert best[key]['highest_of'] > 1 and 'holdout_mean_ic' in best[key] and 'sufficiency' in best[key]
    assert 'biased upward' in best['note']
    names = {r['name']: r for r in report['tables'][targets.CLASSIFICATION]}
    assert names['coin_flip']['role'] == names['base_rate']['role'] == 'BASELINE' and names['coin_flip']['dev_log_loss'] == pytest.approx(np.log(2))
    naive = min(names['coin_flip']['dev_log_loss'], names['base_rate']['dev_log_loss'])
    for row in report['tables'][targets.CLASSIFICATION]:
        if row['role'] == 'CANDIDATE' and row.get('status') == 'CHALLENGER':
            assert row['dev_log_loss'] < naive                                                      # a classifier must beat the better naive forecast, not the worse
    data = report['dataset']
    assert data['features'] == len(NAMES) and data['features_in_a_model_group'] == len(NAMES) and data['strict_point_in_time_samples'] == 0
    assert report['examples'][0]['shown_because'] == lab_module.EXAMPLE_RULE and 'instruments_per_session' in report['frequency']


def test_the_stored_report_can_be_checked_against_the_code_that_is_about_to_be_closed(finished, monkeypatch):
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(tournament, 'PLAN_VERSION', finished['report']['plan_version'])
        result = cli.verify(finished['path'])
    assert result['matches'] is True and result['models_of_this_run'] == finished['written']['models_registered'] and result['problems'] == []
    monkeypatch.setattr(registry, 'code_hash', lambda: 'f' * 64)
    changed = cli.verify(finished['path'])
    assert changed['matches'] is False and 'the stored report was produced by other code' in changed['problems']      # closing on a report from other code is caught
