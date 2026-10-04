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
        self.definition = tournament.design(self.data)
        self.rows = tournament.eligible_rows(self.data)
        self.breadth, self.pair_correlation = 10.0, 0.0


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
        run = SmallLab(path, log=lambda _text: None, quick=True, draws=100).execute()
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
    assert result['scale'] == 'rank' and 'regression' not in tournament.score(result, finished['run'].data, part='dev', draws=50)


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
