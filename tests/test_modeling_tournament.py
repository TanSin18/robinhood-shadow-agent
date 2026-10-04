"""Checkpoint 7 tournament mechanics on a synthetic dataset with a planted signal and with pure noise.

What is proven here: a model is never fitted on a row it predicts or on a label that overlaps the block; a
configuration is chosen without touching the block being predicted or the holdout; results are reproducible; a planted
signal is found and noise is not promoted; the registry refuses a production or live status and is append-only."""
import json
import sqlite3

import pytest

np = pytest.importorskip('numpy')

from firm_lab.modeling import deep, metrics, models, registry, selection, targets, timeview, tournament
from firm_lab.modeling.dataset import MINIMUM_HISTORY, Dataset

NAMES = ['return20', 'return63', 'return126', 'sma200_distance', 'realized_vol20', 'sma50_distance', 'rsi14_wilder', 'signal', 'noise_a', 'noise_b']
FAMILY = {'return20': 'momentum', 'return63': 'momentum', 'return126': 'momentum', 'sma200_distance': 'trend', 'realized_vol20': 'volatility',
          'sma50_distance': 'trend', 'rsi14_wilder': 'momentum', 'signal': 'fibonacci', 'noise_a': 'sector', 'noise_b': 'sector'}


def synthetic(strength=0.02, sessions=378, instruments=22, seed=0) -> Dataset:
    """Rows for every instrument and session. With ``strength`` > 0 the 10-session label is partly the 'signal' column."""
    generator = np.random.default_rng(seed)
    rows = [(i, s) for s in range(sessions) for i in range(instruments)]
    X = generator.normal(size=(len(rows), len(NAMES)))
    row_session = np.array([s for _, s in rows])
    y = {}
    for h in targets.HORIZONS:
        y[f'excess_return_{h}'] = strength * X[:, NAMES.index('signal')] * (h / 10) + generator.normal(scale=0.03, size=len(rows))
        y[f'excess_return_{h}'][row_session + h >= sessions] = np.nan                               # the window runs past the stored history
    y[targets.CLASSIFICATION] = np.where(np.isfinite(y['excess_return_10']), (y['excess_return_10'] > 0).astype(float), np.nan)
    for name in targets.RISK:
        y[name] = np.where(row_session + 10 < sessions, np.abs(generator.normal(scale=0.02, size=len(rows))), np.nan)
    return Dataset(sessions=[f'S{k:03d}' for k in range(sessions)], instruments=[f'I{k:02d}' for k in range(instruments)], feature_names=list(NAMES),
                   feature_family=dict(FAMILY), X=X, row_instrument=np.array([i for i, _ in rows]), row_session=row_session, y=y,
                   snapshot_ids=[f'snap{k}' for k in range(len(rows))], label_records=[{} for _ in rows], excluded={},
                   manifest={'dataset_hash': 'd' * 64, 'calculation_hash': 'c' * 64, 'encoding_version': 'numeric-encoding-v1'})


class Spy(models.Model):
    """Records exactly which rows and labels it was given."""
    seen = []
    preprocess = None

    def fit(self, X, y, context):
        Spy.seen.append({'sessions': set(int(s) for s in context['session']), 'rows': len(X), 'labels': np.array(y, copy=True), 'params': dict(self.params)})
        self.mean = float(np.mean(y))
        return self

    def predict(self, X, context):
        return np.full(len(X), self.mean) + self.params.get('shift', 0.0)


def test_the_common_sample_and_the_design_are_what_the_plan_says():
    data = synthetic()
    rows = tournament.eligible_rows(data)
    assert data.row_session[rows].min() == MINIMUM_HISTORY == 63 and data.row_session[rows].max() == 378 - 1 - 20      # history before, every label after
    design = tournament.design(data)
    assert (design['horizon'], design['embargo'], len(design['folds'])) == (20, 5, 5) and design['gap_before_holdout'] == 25
    assert len(design['holdout'].validation) == 59 and tournament.PLAN_VERSION == 'checkpoint7-tournament-plan-v3.1'


def test_no_model_is_fitted_on_a_row_it_predicts_or_on_a_label_that_overlaps_the_block():
    data, Spy.seen = synthetic(), []
    design = tournament.design(data)
    spec = {'name': 'spy', 'cls': Spy, 'grid': [{'shift': 0.0}, {'shift': 0.1}], 'target': targets.PRIMARY, 'columns': list(range(len(NAMES)))}
    result = tournament.run(spec, data, design)
    blocks = list(design['folds']) + [design['holdout']]
    assert result['status'] == 'RUN' and len(result['blocks']) == 6 and len(Spy.seen) == 6 * 3      # two inner fits and one final fit per block
    holdout_sessions = set(design['holdout'].validation)
    for k, block in enumerate(blocks):
        inner_a, inner_b, final = Spy.seen[3 * k:3 * k + 3]
        validation = set(block.validation)
        for fit in (inner_a, inner_b, final):
            assert not fit['sessions'] & validation                                                 # never a row of the block being predicted
            assert max(fit['sessions']) + 20 < min(validation)                                      # every training label had closed before the block began
            assert block.name == 'final_holdout' or not fit['sessions'] & holdout_sessions          # development never sees a holdout session
        assert final['sessions'] == set(block.train)                                                # the final fit uses the whole purged training window
        assert inner_a['sessions'] == inner_b['sessions'] and inner_a['sessions'] < set(block.train) and max(inner_a['sessions']) < max(block.train) - 20
        assert not np.isnan(final['labels']).any()                                                  # no row without a label is ever a training row
        entry = result['blocks'][k]
        assert set(int(s) for s in data.row_session[entry['rows']]) == validation and len(entry['tried']) == 2
    assert result['configurations_tried'] == 2


def test_tuning_cannot_be_helped_by_the_block_it_is_judged_on():
    """A configuration is picked on the inner block. Wrecking every label of the outer block and of the holdout changes no choice."""
    data = synthetic(seed=4)
    design = tournament.design(data)
    spec = {'name': 'ridge', 'cls': models.Ridge, 'grid': models.GRIDS['ridge'], 'target': targets.PRIMARY, 'columns': list(range(len(NAMES)))}
    before = tournament.run(spec, data, design)
    wrecked = synthetic(seed=4)
    fold = design['folds'][0]
    untouched = set(fold.train)
    mask = ~np.isin(wrecked.row_session, list(untouched)) & np.isfinite(wrecked.y[targets.PRIMARY])
    wrecked.y[targets.PRIMARY][mask] = np.random.default_rng(9).normal(size=mask.sum())
    after = tournament.run(spec, wrecked, design)
    assert before['blocks'][0]['chosen'] == after['blocks'][0]['chosen'] and before['blocks'][0]['tried'] == after['blocks'][0]['tried']
    assert np.array_equal(before['blocks'][0]['prediction'], after['blocks'][0]['prediction'])     # what it predicted for the block did not depend on the block's labels


def test_a_planted_signal_is_found_and_noise_is_not_promoted():
    data = synthetic(strength=0.02, seed=1)
    design = tournament.design(data)
    columns = list(range(len(NAMES)))
    from firm_lab.modeling.lab import summarize
    ridge = summarize(tournament.run({'name': 'ridge', 'cls': models.Ridge, 'grid': models.GRIDS['ridge'], 'target': targets.PRIMARY, 'columns': columns}, data, design), data)
    zero = summarize(tournament.run({'name': 'zero', 'cls': models.Zero, 'grid': [{}], 'target': targets.PRIMARY, 'columns': columns}, data, design), data)
    momentum = summarize(tournament.run({'name': 'm', 'cls': models.SingleFeature, 'grid': [{'feature': 'return20'}], 'target': targets.PRIMARY, 'columns': columns}, data, design), data)
    assert ridge['dev_mean_ic'] > 0.3 and ridge['holdout_mean_ic'] > 0.3 and all(x > 0.2 for x in ridge['fold_ics'])
    assert zero['dev_mean_ic'] == 0.0 and zero['dev']['ranking']['sessions_with_a_ranking'] == 0     # a constant forecast ranks nothing: zero skill
    baselines = {'zero': zero, 'momentum_20': momentum}
    status, reasons = selection.status(ridge, baselines, holm_rejected=True)
    assert status == 'CHALLENGER' and 'too few for any interval' in reasons[-1]                      # a 59-session holdout cannot establish a 10-session edge
    noise = synthetic(strength=0.0, seed=2)
    design = tournament.design(noise)
    for seed in (0,):
        nothing = summarize(tournament.run({'name': 'ridge', 'cls': models.Ridge, 'grid': models.GRIDS['ridge'], 'target': targets.PRIMARY, 'columns': columns}, noise, design), noise)
        base = summarize(tournament.run({'name': 'm', 'cls': models.SingleFeature, 'grid': [{'feature': 'return20'}], 'target': targets.PRIMARY, 'columns': columns}, noise, design), noise)
        assert abs(nothing['dev_mean_ic']) < 0.06
        assert selection.status(nothing, {'m': base}, holm_rejected=False)[0] in ('REJECTED', 'EXPERIMENTAL')   # never a challenger on noise


def test_results_are_reproducible_and_baselines_do_what_they_say():
    data = synthetic(seed=3)
    design = tournament.design(data)
    columns = list(range(len(NAMES)))
    spec = {'name': 'ridge', 'cls': models.Ridge, 'grid': models.GRIDS['ridge'], 'target': targets.PRIMARY, 'columns': columns}
    a, b = tournament.run(spec, data, design), tournament.run(spec, data, design)
    assert all(np.array_equal(x['prediction'], y['prediction']) and x['chosen'] == y['chosen'] for x, y in zip(a['blocks'], b['blocks']))
    rows = tournament.eligible_rows(data)
    train, test = rows[data.row_session[rows] < 150], rows[data.row_session[rows] > 200]
    _, zero, _ = tournament.fit_predict(models.Zero, {}, data, targets.PRIMARY, columns, train, test)
    model, mean, _ = tournament.fit_predict(models.HistoricalMean, {}, data, targets.PRIMARY, columns, train, test)
    assert not zero.any() and np.allclose(mean, data.y[targets.PRIMARY][train].mean())
    model, per, _ = tournament.fit_predict(models.InstrumentMean, {}, data, targets.PRIMARY, columns, train, test)
    first = data.row_instrument[train] == 0
    assert per[data.row_instrument[test] == 0][0] == pytest.approx(data.y[targets.PRIMARY][train][first].mean())
    gated, prediction, _ = tournament.fit_predict(models.SingleFeature, {'feature': 'return126', 'gate': 'sma200_distance'}, data, targets.PRIMARY, columns, train, test)
    below = ~(data.X[test, NAMES.index('sma200_distance')] > 0)
    assert np.allclose(prediction[below], gated.fallback) and np.ptp(prediction[~below]) > 0         # the descriptor counts only above the gate
    _, rate, _ = tournament.fit_predict(models.BaseRate, {}, data, targets.CLASSIFICATION, columns, train, test)
    assert np.allclose(rate, data.y[targets.CLASSIFICATION][train].mean())
    missing = tournament.run({'name': 'x', 'cls': type('Needs', (models.Model,), {'requires': ('a_module_that_does_not_exist',)}), 'grid': [{}],
                              'target': targets.PRIMARY, 'columns': columns}, data, design)
    assert missing == {'name': 'x', 'status': 'NOT_RUN', 'reason': 'dependency unavailable: a_module_that_does_not_exist'}


def test_a_sequence_window_holds_only_the_instruments_own_earlier_sessions():
    from firm_lab.modeling.dataset import sequences
    data = synthetic(seed=5)
    rows = np.flatnonzero((data.row_session == 100) | (data.row_session == 10))
    windows, full = sequences(data, rows, [0, 1], 20)
    index = data.row_of()
    for n, r in enumerate(rows):
        instrument, session = int(data.row_instrument[r]), int(data.row_session[r])
        if session == 10:
            assert not full[n] and np.isnan(windows[n]).all()                                       # fewer than 20 sessions exist: no window, nothing padded
            continue
        assert full[n] and np.array_equal(windows[n][-1], data.X[r, [0, 1]])                        # the last step is the sample's own session
        assert np.array_equal(windows[n][0], data.X[index[(instrument, session - 19)], [0, 1]])     # the first step is 19 sessions earlier, same instrument


def test_the_sufficiency_gate_counts_independent_observations_not_rows():
    gate = deep.sufficiency(parameters=2000, training_rows=4000, training_sessions=180, instruments=22, horizon=10, average_pair_correlation=0.0)
    assert gate['effective_independent_observations'] == pytest.approx(18 * 22) and gate['sufficient'] is False       # 396 against 20,000 needed
    assert deep.sufficiency(parameters=30, training_rows=4000, training_sessions=180, instruments=22, horizon=10, average_pair_correlation=0.0)['sufficient'] is True
    together = deep.sufficiency(parameters=30, training_rows=4000, training_sessions=180, instruments=22, horizon=10, average_pair_correlation=1.0)
    assert together['effective_independent_instruments'] == 1.0 and together['sufficient'] is False


# ====================================================================================================== registry
def _modeling_db(tmp_path):
    path = tmp_path / 'firm_lab_modeling.db'
    db = sqlite3.connect(path)
    with db:
        timeview.create_tables(db)
        db.execute('CREATE TABLE firm_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)')
        for key, value in (('mode', 'BUILD_OBSERVE'), ('database_role', 'CHECKPOINT7_MODELING_RESEARCH'), ('time_policy', json.dumps({'source_sha256': 's' * 64}))):
            db.execute('INSERT INTO firm_meta VALUES (?,?,?)', (key, value, '2026-10-03T00:00:00+00:00'))
    db.close()
    return path


def _model_record(**changes):
    record = {'model_id': 'm' * 64, 'name': 'ridge/excess_return_10', 'family': 'B_linear', 'architecture': 'ridge regression', 'target': 'excess_return_10',
              'horizons': [10], 'feature_groups': ['technical_baseline'], 'feature_names': ['return20'], 'feature_versions': {'calculation_hash': 'c' * 64},
              'training_window': [['S063', 'S122']], 'validation_window': [['S143', 'S168']], 'split': {'version': 'expanding-walk-forward-purged-v1'},
              'hyperparameters': {'alpha': 100.0}, 'seeds': [0], 'library_versions': {'numpy': '2'}, 'code_hash': 'h' * 64, 'dataset_hash': 'd' * 64,
              'metrics': [{'dev_mean_ic': np.float64(0.01), 'holdout_mean_ic': float('nan')}], 'artifact': {'sha256': {}}, 'status': 'EXPERIMENTAL',
              'status_reasons': ['x'], 'role': 'CANDIDATE'}
    record.update(changes)
    return record


def test_the_registry_keeps_every_required_field_and_refuses_a_production_or_live_status(tmp_path):
    path = _modeling_db(tmp_path)
    with registry.Registry(path) as store:
        assert store.add_model(_model_record()) is True and store.add_model(_model_record()) is False       # the same record registers once
        for status in ('PRODUCTION', 'LIVE', 'DEPLOYED', 'ACTIVE', 'CHAMPION', 'production', ''):
            with pytest.raises(ValueError, match='RESEARCH_STATUS_REQUIRED'):
                store.add_model(_model_record(model_id='x' * 64, status=status))
        for field in registry.REQUIRED:
            broken = _model_record(model_id='y' * 64)
            del broken[field]
            with pytest.raises(ValueError, match='MODEL_RECORD_INCOMPLETE'):
                store.add_model(broken)
        with pytest.raises(ValueError, match='INVALID_ROLE'):
            store.add_model(_model_record(model_id='z' * 64, role='TRADING'))
        stored = store.models()
        assert len(stored) == 1 and stored[0]['metrics'][0] == {'dev_mean_ic': 0.01, 'holdout_mean_ic': None}        # numbers are plain; "not a number" is null
        artifact = store.add_predictions('m' * 64, np.arange(5), np.linspace(0, 1, 5), part='dev')
        assert len(artifact) == 64 and store.add_report('r1', {'warning': 'x'}) and store.latest_report() == {'warning': 'x'}
    db = sqlite3.connect(path)
    for statement in ("UPDATE modeling_models SET payload='{}'", 'DELETE FROM modeling_models', "UPDATE modeling_reports SET payload='{}'",
                      'DELETE FROM modeling_predictions'):
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            db.execute(statement)
    names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    db.close()
    assert not [n for n in names if any(word in n for word in timeview.FORBIDDEN_TABLE_WORDS)]       # nothing that could hold a trade
    assert len(registry.code_hash()) == 64 and registry.code_hash() == registry.code_hash()
    other = tmp_path / 'not_modeling.db'
    sqlite3.connect(other).close()
    with pytest.raises((ValueError, sqlite3.Error)):
        registry.Registry(other)                                                                    # an unidentified database is not written to
