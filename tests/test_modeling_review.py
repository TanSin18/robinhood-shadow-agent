"""Regressions for the Checkpoint 7 independent review (docs/firm_lab/CHECKPOINT7_REVIEW.md). Each test failed on the
code the reviewers read (commit 3abb5dd) and passes after the repair.

What is proven here: an interval is honest at this sample size or is not given; every model is averaged and compared
over the same sessions; a challenger has to beat every naive baseline, not the one that happened to score highest; a
model that fails the data-sufficiency gate is never rejected or promoted on its score; ties do not depend on row order;
the registry cannot be overwritten or hold a status it must not; a broken stored report never takes the page down."""
import json
import math
import sqlite3
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('scipy')

from agents.desk import firm_lab_page, modeling_lab
from firm_lab import modeling, modeling_view
from firm_lab.modeling import lab as lab_module, metrics, models, registry, selection, targets, tournament
from test_modeling_isolation_ui import _lab_file, _report
from test_modeling_tournament import NAMES, _model_record, _modeling_db, synthetic

ROOT = Path(__file__).resolve().parents[1]


# ====================================================================================================== B1: intervals and p-values
def _overlapping_null(generator, n, horizon):
    """A per-session statistic with no true mean whose neighbours share a label window: the worst case for overlap."""
    shocks = generator.normal(size=n + horizon - 1)
    return np.convolve(shocks, np.ones(horizon), 'valid') / math.sqrt(horizon)


@pytest.mark.parametrize('n,horizon', [(131, 5), (131, 10), (131, 20), (59, 5)])
def test_a_no_information_series_is_called_positive_about_as_often_as_the_interval_says(n, horizon):
    generator = np.random.default_rng(100 + n + horizon)
    draws, above, covered, smallest = 1500, 0, 0, 1.0
    for _ in range(draws):
        record = metrics.batch_interval(_overlapping_null(generator, n, horizon), horizon=horizon)
        above += record['low'] > 0
        covered += record['low'] <= 0 <= record['high']
        smallest = min(smallest, record['p_not_positive'])
    assert above / draws <= 0.075                                                                   # nominal 5%; the replaced bootstrap gave 9% to 25%
    assert covered / draws >= 0.85                                                                  # nominal 90%
    assert smallest > 0                                                                             # a p-value is never exactly zero, whatever the family size


@pytest.mark.parametrize('n,horizon', [(59, 10), (59, 20), (131, 30)])
def test_no_interval_and_no_p_value_is_given_below_three_batches(n, horizon):
    record = metrics.batch_interval(np.random.default_rng(1).normal(loc=0.2, size=n), horizon=horizon)
    assert record['batches'] < metrics.MINIMUM_BATCHES and math.isnan(record['low']) and math.isnan(record['high']) and math.isnan(record['p_not_positive'])
    family = metrics.holm({'a': record['p_not_positive'], **{f'm{k}': 0.5 for k in range(999)}})
    assert family['a']['adjusted'] == 1.0 and family['a']['rejected'] is False and family['a']['family_size'] == 1000      # "could not be tested" is never a rejection
    assert not hasattr(metrics, 'block_bootstrap')                                                  # the method that produced p = 0 from two blocks is gone


# ====================================================================================================== A1 / B4: the same sessions for every model
def test_a_session_a_model_does_not_rank_counts_as_zero_for_that_model_everywhere():
    data = synthetic(strength=0.0, seed=6)
    early = data.row_session < 150
    data.X[early, NAMES.index('return126')] = np.nan                                                # the descriptor does not exist yet: the baseline cannot rank
    data.y[targets.PRIMARY] = np.where(np.isfinite(data.y[targets.PRIMARY]), data.y[targets.PRIMARY] + 0.02 * np.nan_to_num(data.X[:, NAMES.index('return126')]), np.nan)
    design = tournament.design(data)
    columns = list(range(len(NAMES)))
    baseline = lab_module.summarize(tournament.run({'name': 'm', 'cls': models.SingleFeature, 'grid': [{'feature': 'return126'}], 'target': targets.PRIMARY, 'columns': columns}, data, design), data)
    ranking = baseline['dev']['ranking']
    assert 0 < ranking['sessions_with_a_ranking'] < ranking['sessions']                             # it ranked some sessions and not others
    series = np.asarray(baseline['dev_ic_series'])
    assert len(series) == ranking['sessions'] and (series == 0).sum() >= ranking['sessions'] - ranking['sessions_with_a_ranking']
    assert baseline['dev_mean_ic'] == pytest.approx(series.sum() / ranking['sessions'])             # averaged over every session, like every other model
    assert ranking['mean_ic_on_ranked_sessions_only'] > baseline['dev_mean_ic'] > 0                 # the old number flattered the baseline
    assert baseline['fold_ics'][0] == 0.0                                                           # a fold it could not rank is not a positive fold
    zero = lab_module.summarize(tournament.run({'name': 'z', 'cls': models.Zero, 'grid': [{}], 'target': targets.PRIMARY, 'columns': columns}, data, design), data)
    assert zero['dev_mean_ic'] == 0.0 and selection.strongest_baseline({'zero': zero, 'm': baseline}) == 'm'
    assert selection.strongest_baseline({'zero': zero, 'worse': {'dev_mean_ic': -0.02}}) == 'zero'  # a candidate is never tested against less than zero


def _series_record(mean, *, n=131, holdout=59, horizon=5, seed=0, zero_first=0, folds=None, holdout_mean=None):
    generator = np.random.default_rng(seed)
    dev = mean + generator.normal(scale=0.04, size=n)
    dev[:zero_first] = 0.0
    hold = (mean if holdout_mean is None else holdout_mean) + generator.normal(scale=0.04, size=holdout)
    return {'dev_mean_ic': float(dev.mean()), 'holdout_mean_ic': float(hold.mean()), 'fold_ics': folds or [float(dev.mean())] * 5, 'horizon': horizon, 'dev_identity_p': 0.001,
            'dev_ic_series': dev.tolist(), 'holdout_ic_series': hold.tolist()}


def test_a_candidate_is_compared_with_a_baseline_over_every_session_not_only_those_the_baseline_ranked():
    baseline = _series_record(0.05, zero_first=27, seed=1)                                          # ranks nothing for the first 27 sessions
    assert 0.03 < baseline['dev_mean_ic'] < 0.045
    candidate = _series_record(0.047, seed=2)                                                       # above the baseline's all-session mean, below its ranked-only mean
    status, reasons = selection.status(candidate, {'momentum': baseline}, holm_rejected=False)
    assert status != 'REJECTED' and not any('is not above' in r for r in reasons)
    paired = metrics.paired_difference(candidate['dev_ic_series'], baseline['dev_ic_series'], horizon=5)
    assert paired['n'] == 131                                                                       # the pairing covers every development session


# ====================================================================================================== B2: every naive baseline
def test_a_challenger_must_beat_every_naive_baseline_not_only_the_one_that_scored_highest():
    candidate = _series_record(0.11, seed=3)
    steady = _series_record(0.0400, seed=4)
    noisy = _series_record(0.0396, seed=5)
    wild = np.random.default_rng(6).normal(scale=0.6, size=131)                                     # a near-tied baseline the candidate does not clearly beat
    noisy['dev_ic_series'] = (np.asarray(noisy['dev_ic_series']) + wild - wild.mean()).tolist()
    assert selection.strongest_baseline({'steady': steady, 'noisy': noisy}) == 'steady'
    assert selection.status(candidate, {'steady': steady}, holm_rejected=False)[0] == 'CHALLENGER'
    status, reasons = selection.status(candidate, {'steady': steady, 'noisy': noisy}, holm_rejected=False)
    assert status == 'EXPERIMENTAL' and 'interval not above zero against: noisy' in reasons


# ====================================================================================================== B5 / B6: the sufficiency gate
def test_a_model_that_fails_the_gate_is_experimental_whatever_it_scored_and_a_missing_gate_record_is_an_error():
    baseline = {'momentum': _series_record(0.05, seed=1)}
    below = _series_record(0.01, seed=2)
    assert selection.status(below, baseline, holm_rejected=False)[0] == 'REJECTED'
    status, reasons = selection.status(below, baseline, holm_rejected=False, sufficient=False)
    assert status == 'EXPERIMENTAL' and any('EXPERIMENTAL_INSUFFICIENT_DATA' in r for r in reasons) and any('is not above' in r for r in reasons)
    from firm_lab.modeling import report as report_module

    class Stub:
        results = {'mlp/x': {'family': 'D_neural'}, 'ridge/x': {'family': 'B_linear'}, 'ensemble/specialist_gating': {'family': 'ensemble', 'members': ['ridge/x']},
                   'ensemble/mixed': {'family': 'ensemble', 'members': ['ridge/x', 'mlp/x']}}
        sufficiency_record = {}
        gate_fits = {'fold_5': {'parameters': 15}}
    for key in ('mlp/x', 'ensemble/specialist_gating', 'ensemble/mixed'):
        with pytest.raises(ValueError, match='SUFFICIENCY_RECORD_MISSING'):
            report_module._sufficient(Stub, key)                                                    # fitted as a network, or holding one: never sufficient by default
    assert report_module._sufficient(Stub, 'ridge/x') is True
    Stub.sufficiency_record = {'mlp/x': {'sufficient': False}, 'ensemble/specialist_gating': {'sufficient': False}}
    assert report_module._sufficient(Stub, 'ensemble/mixed') is False and report_module._sufficient(Stub, 'ensemble/specialist_gating') is False


# ====================================================================================================== A3: the stacker
def test_the_stacker_gives_no_learned_weight_to_a_member_that_was_constant_in_the_inner_block():
    generator = np.random.default_rng(8)
    y = generator.normal(size=300)
    live = y + generator.normal(scale=0.5, size=300)
    predictions = np.column_stack([live, np.full(300, 0.01), np.full(300, 0.01), generator.normal(size=300)])
    weights = lab_module.Lab._nonnegative_weights(predictions, y)
    assert weights[1] == weights[2] == 0.0 and weights[0] > 0.8 and weights.sum() == pytest.approx(1.0)
    nothing = lab_module.Lab._nonnegative_weights(np.full((300, 3), 0.01), y)
    assert np.allclose(nothing, 1 / 3)                                                              # nothing to learn from: equal weights, said plainly


# ====================================================================================================== B13: ties
def test_tied_predictions_give_the_same_answer_in_any_row_order():
    y = np.array([1, 0, 1, 0, 1, 0, 0, 1])
    score = np.array([0.9, 0.9, 0.5, 0.5, 0.5, 0.2, 0.2, 0.2])
    forward, backward = metrics.average_precision(y, score), metrics.average_precision(y[::-1], score[::-1])
    assert forward == pytest.approx(backward)
    try:
        from sklearn.metrics import average_precision_score
        assert forward == pytest.approx(average_precision_score(y, score))
    except ImportError:
        pass
    realised = np.array([5.0, -5.0, 1.0, 2.0, 3.0, 4.0, 0.0, -1.0, -2.0, -3.0, 9.0, -9.0])
    prediction = np.array([1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, -1.0, -1.0, -1.0, -1.0])
    session = np.zeros(12)
    a = metrics.top_bottom(realised, prediction, session, k=3)
    order = np.arange(12)[::-1]
    b = metrics.top_bottom(realised[order], prediction[order], session, k=3)
    assert a['top_minus_bottom'] == pytest.approx(b['top_minus_bottom']) == pytest.approx(np.mean([5, -5, 1, 2]) - np.mean([-2, -3, 9, -9]))
    assert a['top_hit_rate'] == pytest.approx(0.75)                                                 # three of the four tied at the top were positive


def test_a_forecast_that_is_constant_within_each_fold_has_no_ranking_skill_by_auc():
    data = synthetic(strength=0.0, seed=9)
    design = tournament.design(data)
    result = tournament.run({'name': 'base_rate', 'cls': models.BaseRate, 'grid': [{}], 'target': targets.CLASSIFICATION, 'columns': [0]}, data, design)
    record = tournament.score(result, data, part='dev')['classification']
    assert record['roc_auc'] == pytest.approx(0.5)                                                  # pooled over folds it was not 0.5: an artefact of the level drifting
    flip = tournament.run({'name': 'coin_flip', 'cls': models.CoinFlip, 'grid': [{}], 'target': targets.CLASSIFICATION, 'columns': [0]}, data, design)
    assert tournament.score(flip, data, part='dev')['classification']['log_loss'] == pytest.approx(math.log(2))


# ====================================================================================================== B14 / B15: edge cases of the rules
def test_the_rules_do_not_answer_yes_or_reject_on_missing_or_tied_evidence():
    one = {'ridge': {'dev': {'low': 0.01, 'high': 0.05, 'estimate': 0.03}, 'holdout_difference': 0.02}}
    assert selection.fibonacci_verdict({})[0] == 'INCONCLUSIVE' and selection.fibonacci_verdict(one)[0] == 'INCONCLUSIVE'      # the rule needs both reference models
    unmeasured = {'ridge': one['ridge'], 'lightgbm': {'dev': {'low': 0.01, 'high': 0.05, 'estimate': 0.03}, 'holdout_difference': None}}
    assert selection.fibonacci_verdict(unmeasured)[0] == 'INCONCLUSIVE'
    no_interval = {k: {'dev': {'low': float('nan'), 'high': float('nan'), 'estimate': 0.03}, 'holdout_difference': 0.02} for k in ('ridge', 'lightgbm')}
    assert selection.fibonacci_verdict(no_interval)[0] == 'INCONCLUSIVE'
    assert selection.loss_status([1.0] * 5, [1.0] * 5, 1.0, 1.0)[0] == 'EXPERIMENTAL'               # a tie is not "worse than the baseline"
    assert selection.loss_status([1.0] * 5, [1.1] * 5, None, 1.1)[0] == 'EXPERIMENTAL'              # an unscored holdout cannot make a challenger
    assert selection.loss_status([], [], None, None)[0] == 'EXPERIMENTAL'


# ====================================================================================================== A7 / B16: the registry
def test_the_registry_refuses_a_different_record_under_the_same_identity_a_replace_and_a_forbidden_head_status(tmp_path):
    path = _modeling_db(tmp_path)
    with registry.Registry(path) as store:
        assert store.add_model(_model_record()) is True and store.add_model(_model_record()) is False
        with pytest.raises(ValueError, match='REGISTRY_ROW_CONFLICT'):
            store.add_model(_model_record(metrics=[{'dev_mean_ic': 0.5}]))                          # the same identity cannot quietly keep an older, different record
        with pytest.raises(ValueError, match='RESEARCH_STATUS_REQUIRED'):
            store.add_model(_model_record(model_id='h' * 64, status_by_target={'excess_return_10': 'PRODUCTION'}))
        assert store.add_model(_model_record(model_id='h' * 64, status_by_target={'excess_return_10': 'REJECTED'})) is True
    assert registry.model_id('a', 't', 'd', [], 'c', 'run-1') != registry.model_id('a', 't', 'd', [], 'c', 'run-2')       # a rerun is a new run with its own rows
    db = sqlite3.connect(path)
    for table in registry.REGISTRY_TABLES:
        row = db.execute(f'SELECT id FROM {table} LIMIT 1').fetchone()
        if row:
            with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
                db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, '{{}}', 'x')", (row[0],))    # replace would delete without firing the delete trigger
    assert json.loads(db.execute("SELECT payload FROM modeling_models WHERE id = ?", ('m' * 64,)).fetchone()[0])['status'] == 'EXPERIMENTAL'
    db.close()


# ====================================================================================================== B7 / B8: the page and the projection
REQUIRED = ('report_id', 'plan_version', 'time_policy', 'code_hash', 'dataset', 'validation', 'tables', 'ablation', 'best_research_models')


def test_a_partial_or_malformed_stored_report_never_takes_the_page_down(tmp_path):
    good = _report()
    for key in sorted(good):
        for value in ('missing', None, [], 'text', 7, 10 ** 400):
            broken = {k: v for k, v in good.items() if k != key or value != 'missing'}
            if value != 'missing':
                broken[key] = value
            html = modeling_lab.render_modeling({'modeling': {'exists': True, 'report': broken, 'models': 2, 'registry_statuses': {'EXPERIMENTAL': 2}}})
            assert html.startswith(modeling_lab.STAMP), (key, value)                                # the warning is always there, and nothing raises
            page = firm_lab_page.render({'firm_lab': {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0,
                                                      'modeling': {'exists': True, 'report': broken, 'models': 2, 'registry_statuses': {}}}})
            assert 'id="fl-modeling"' in page and 'Firm fills' in page                              # the rest of the Firm Lab page still renders
    html = modeling_lab.render_modeling({'modeling': {'exists': True, 'report': {k: v for k, v in good.items() if k != 'dataset'}}})
    assert 'could not be shown' in html and 'Feature-family ablation' not in html                   # degraded: nothing from a broken report is displayed
    for odd in (None, [], 'x', {'modeling': []}, {'modeling': 'x'}, {'modeling': {'exists': True, 'report': []}}):
        assert modeling_lab.render_modeling(odd).startswith(modeling_lab.STAMP)
    research = tmp_path / 'firm_lab.db'
    for payload in ('[]', 'null', '"text"', '{"tables": []}', json.dumps({k: v for k, v in good.items() if k != 'best_research_models'})):
        path = _lab_file(tmp_path, good)
        db = sqlite3.connect(path)
        with db:
            db.execute('UPDATE modeling_reports SET payload = ?', (payload,))
        db.close()
        assert modeling_view.summary(research)['missing_reason'] == 'LABORATORY_REPORT_INCOMPLETE', payload
        path.unlink()
    path = _lab_file(tmp_path, good)
    db = sqlite3.connect(path)
    with db:
        db.execute("UPDATE modeling_models SET payload = '[]' WHERE id = 'm0'")
    db.close()
    assert modeling_view.summary(research)['exists'] is False                                       # a registry row that is not a record: nothing is shown
    path.unlink()
    bad = _report()
    bad['tables']['excess_return_10'][1]['status'] = 'PRODUCTION'
    _lab_file(tmp_path, bad)
    assert modeling_view.summary(research)['missing_reason'] == 'UNEXPECTED_MODEL_STATUS'           # a status inside the report is checked like a registry row


def test_registry_rows_of_another_run_or_of_no_run_are_not_counted_with_the_newest_report(tmp_path):
    path = _lab_file(tmp_path, _report(), statuses=('EXPERIMENTAL', 'REJECTED'))
    db = sqlite3.connect(path)
    with db:
        db.execute('INSERT INTO modeling_models VALUES (?,?,?)', ('first-run', json.dumps({'status': 'CHALLENGER'}), '2026-10-03T21:36:00+00:00'))      # no run named
        db.execute('INSERT INTO modeling_models VALUES (?,?,?)', ('other-run', json.dumps({'status': 'CHALLENGER', 'report_id': 'older'}), '2026-10-03T21:36:00+00:00'))
    db.close()
    state = modeling_view.summary(tmp_path / 'firm_lab.db')
    assert state['models'] == 2 and state['registry_statuses'] == {'EXPERIMENTAL': 1, 'REJECTED': 1} and state['models_from_other_runs'] == 2
    assert 'CHALLENGER' not in json.dumps(state['registry_statuses'])                               # an earlier run's challenger does not appear in this run's count


# ====================================================================================================== A8, B17, B18: claims and latent inputs
def test_no_calculator_reads_a_field_that_was_linked_from_a_later_filing_and_the_documents_say_what_the_code_does():
    for path in sorted((ROOT / 'firm_lab' / 'research_features').glob('*.py')):
        text = path.read_text()
        assert 'fiscal_period_end' not in text and 'periodic_accession' not in text, path.name      # stored on the 8-K row, known only once the 10-Q exists
    plan = (ROOT / 'docs' / 'firm_lab' / 'CHECKPOINT7_TOURNAMENT_PLAN.md').read_text()
    assert tournament.PLAN_VERSION == 'checkpoint7-tournament-plan-v3.1' and '## 12. Plan v2' in plan and '## 13. Plan v3' in plan and 'checkpoint7-tournament-plan-v3.1' in plan
    for phrase in ('batch', 'every naive baseline', 'counts as 0', 'every registered model', 'strongest naive baseline', 'read twice'):
        assert phrase in plan.split('## 12. Plan v2')[1], phrase                                    # each change after the first run is recorded with its reason
    for phrase in ('identities shuffled', 'No prediction changed', 'not the worst case', 'spread of 0'):
        assert phrase in plan.split('## 13. Plan v3')[1], phrase
    assert 'never opens the registered database' not in (ROOT / 'firm_lab' / 'modeling' / 'cli.py').read_text()
    assert 'development sessions' in tournament.average_pair_correlation.__doc__ and 'bootstrap' not in metrics.batch_interval.__doc__.lower()
    assert 'not the worst case' in metrics.batch_interval.__doc__ and 'worst-case' not in metrics.__doc__                 # the interval is not described as more than it is
    page = (ROOT / 'agents' / 'desk' / 'modeling_lab.py').read_text()
    assert 'STATUS_NOTE' in page.split('def _render')[1]                                            # what a status means is shown, not left as dead text
    assert modeling.WARNING == 'MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE'
    closure = (ROOT / 'docs' / 'firm_lab' / 'CHECKPOINT7_CLOSURE.md').read_text()                  # the report the plan and the page point to exists
    for row in ('20-session CatBoost', 'Future volatility: ridge, LightGBM', '10-session LightGBM, CatBoost', '10-session GRU, both multi-task heads, gating, family rank average',
                'coin_flip', 'FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE', 'Firm Lab fills: 0', 'Firm trading trial: NOT REGISTERED',
                'October research stop superseded: NO', 'Control A: UNCHANGED', 'Official Lane B: PAUSED', 'Real execution: DISABLED', 'Automatic external funding enabled: NO'):
        assert row in closure, row                                                                  # every status that moved between runs is named, and the state lines are exact
    assert 'Trial 18' not in closure and 'PRODUCTION' not in closure


# ====================================================================================================== the verification review (plan v3)
def _persistent_null(generator, sessions=131, instruments=22):
    """Labels whose cross-section persists (each instrument has its own drift) and a score that never changes: a ranking
    with no information that looks the same in every session. The case the batch interval alone gets wrong."""
    drift = generator.normal(scale=0.01, size=instruments)
    y = (drift[None, :] + generator.normal(scale=0.02, size=(sessions, instruments))).ravel()
    score = np.tile(generator.normal(size=instruments), sessions)
    return y, score, np.repeat(np.arange(sessions), instruments), np.tile(np.arange(instruments), sessions)


def test_a_ranking_that_persists_by_chance_is_caught_by_the_identity_shuffle_where_the_interval_alone_is_not():
    generator = np.random.default_rng(42)
    draws, by_interval, by_shuffle, by_both = 300, 0, 0, 0
    for _ in range(draws):
        y, score, session, instrument = _persistent_null(generator)
        series = metrics.filled(metrics.session_ic(y, score, session)[1])
        interval = metrics.batch_interval(series, horizon=5)['low'] > 0
        shuffle = metrics.identity_permutation_p(y, score, session, instrument, draws=2000)['p'] <= metrics.IDENTITY_LEVEL
        by_interval, by_shuffle, by_both = by_interval + interval, by_shuffle + shuffle, by_both + (interval and shuffle)
    assert by_interval / draws > 0.15                                                               # the interval alone calls chance an edge far too often here
    assert by_shuffle / draws <= 0.09 and by_both / draws <= 0.09                                   # the shuffle holds its level (5%; 300 draws), and so does the pair
    y, score, session, instrument = _persistent_null(generator)
    informed = metrics.ranking(y, y + generator.normal(scale=0.02, size=len(y)), session, horizon=5, instrument=instrument)
    assert informed['identity_permutation_p'] == pytest.approx(1 / (1 + informed['identity_permutation_draws']))          # a real link is found, and p is never zero


def test_the_identity_shuffle_is_the_mean_rank_correlation_of_the_shuffled_predictions():
    generator = np.random.default_rng(5)
    y, score, session, instrument = _persistent_null(generator, sessions=40, instruments=9)
    score = score + generator.normal(scale=0.5, size=len(score))
    record = metrics.identity_permutation_p(y, score, session, instrument, draws=200, seed=3)
    assert record['observed'] == pytest.approx(metrics.filled(metrics.session_ic(y, score, session)[1]).mean())
    orders = np.random.default_rng(3).permuted(np.tile(np.arange(9), (200, 1)), axis=1)
    as_good = 0
    for order in orders:
        shuffled = score.reshape(40, 9)[:, order].ravel()                                           # every session's predictions handed to other instruments, the same way
        as_good += metrics.filled(metrics.session_ic(y, shuffled, session)[1]).mean() >= record['observed'] - 1e-12
    assert record['p'] == pytest.approx((1 + as_good) / 201)
    partial = metrics.identity_permutation_p(y[:-1], score[:-1], session[:-1], instrument[:-1])
    assert math.isnan(partial['p']) and 'not every instrument' in partial['note']                   # an incomplete panel gets no p-value, not a wrong one


def test_a_challenger_must_also_beat_its_own_predictions_with_identities_shuffled():
    baseline = {'steady': _series_record(0.04, seed=4)}
    candidate = _series_record(0.11, seed=3)
    assert selection.status(candidate, baseline, holm_rejected=False)[0] == 'CHALLENGER'
    status, reasons = selection.status(dict(candidate, dev_identity_p=0.20), baseline, holm_rejected=False)
    assert status == 'EXPERIMENTAL' and any('identities shuffled' in r for r in reasons)
    unmeasured = {k: v for k, v in candidate.items() if k != 'dev_identity_p'}
    assert selection.status(unmeasured, baseline, holm_rejected=True)[0] == 'EXPERIMENTAL'          # no p-value is not a pass
    assert selection.status(dict(candidate, dev_identity_p=float('nan')), baseline, holm_rejected=True)[0] == 'EXPERIMENTAL'


def test_the_zero_rule_also_covers_the_spread_the_tuning_score_and_a_fold_with_nothing_predicted():
    data = synthetic(strength=0.02, seed=6)
    data.X[data.row_session < 150, NAMES.index('return126')] = np.nan
    design = tournament.design(data)
    columns = list(range(len(NAMES)))
    late = tournament.run({'name': 'm', 'cls': models.SingleFeature, 'grid': [{'feature': 'return126'}], 'target': targets.PRIMARY, 'columns': columns}, data, design)
    record = tournament.score(late, data, part='dev')['ranking']
    spread = record['top_bottom']
    assert spread['sessions'] == record['sessions'] > spread['sessions_with_a_ranking'] == record['sessions_with_a_ranking']      # every session is counted
    rows, prediction = tournament.gather(late, 'dev')
    ranked_only = metrics.top_bottom(data.y[targets.PRIMARY][rows], prediction, data.row_session[rows], k=5)
    series = [v for v in ranked_only['series_top_minus_bottom'] if v != 0.0]
    assert spread['top_minus_bottom'] == pytest.approx(sum(series) / record['sessions'])            # unranked sessions pull the spread toward 0
    # tuning: a configuration that ranks nothing scores 0, in the same units as one that ranks
    y, session = data.y[targets.PRIMARY][rows], data.row_session[rows]
    assert tournament._score(models.REGRESSION, y, np.zeros(len(rows)), session) == 0.0
    assert -1 <= tournament._score(models.REGRESSION, y, prediction, session) <= 1
    # a fold in which nothing could be predicted is a fold of zeros, not a missing fold
    ridge = tournament.run({'name': 'ridge', 'cls': models.Ridge, 'grid': [{'alpha': 100.0}], 'target': targets.PRIMARY, 'columns': columns}, data, design)
    ridge['blocks'][0]['predicted'][:] = False
    ridge['blocks'][0]['prediction'][:] = np.nan
    summary = lab_module.summarize(ridge, data)
    assert len(summary['fold_ics']) == 5 and summary['fold_ics'][0] == 0.0 and len(summary['dev_ic_series']) == summary['dev']['ranking']['sessions']
    baseline = lab_module.summarize(late, data)
    assert selection.status(summary, {'m': baseline}, holm_rejected=False)[0] in ('REJECTED', 'EXPERIMENTAL', 'CHALLENGER')      # the comparison is aligned: nothing raises


def test_an_exported_file_is_append_only_and_checking_a_file_never_changes_it(tmp_path):
    from firm_lab.modeling import cli, timeview
    path = _modeling_db(tmp_path)
    report = {'report_id': 'r1', 'code_hash': registry.code_hash(), 'plan_version': tournament.PLAN_VERSION}
    with registry.Registry(path) as store:
        store.add_model(_model_record(report_id='r1', code_hash=registry.code_hash()))
        store.add_report('r1', report)
    db = sqlite3.connect(path)
    with db:
        db.execute("INSERT INTO modeling_datasets VALUES ('d1', '{\"a\": 1}', 'x')")
    with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
        db.execute("INSERT OR REPLACE INTO modeling_datasets VALUES ('d1', '{\"a\": 2}', 'y')")       # refused: the stored row stays
    assert db.execute("SELECT payload FROM modeling_datasets WHERE id = 'd1'").fetchone()[0] == '{"a": 1}'
    db.close()
    before = timeview.file_sha256(path)
    assert cli.verify(path)['matches'] is True and timeview.file_sha256(path) == before             # verify reads; it does not write
    out = tmp_path / 'firm_lab_modeling_lab.db'
    cli.export(path, out)
    exported = sqlite3.connect(out)
    for table in ('modeling_models', 'modeling_reports'):
        identity = exported.execute(f'SELECT id FROM {table} LIMIT 1').fetchone()[0]
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            exported.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, '{{\"status\": \"ELIGIBLE_FOR_FUTURE_REVIEW\"}}', 'x')", (identity,))
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            exported.execute(f"UPDATE {table} SET payload = '{{}}'")
    exported.close()


def test_an_inherited_gate_row_says_so_and_a_huge_number_cannot_take_the_page_down(tmp_path):
    report = _report()
    report['sufficiency']['ensemble/family_equal_weight'] = {'parameters': 4417, 'effective_independent_observations': 65.2, 'observations_per_parameter': 0.0148,
                                                             'seed_ic_range': 0.013, 'label': 'EXPERIMENTAL_INSUFFICIENT_DATA', 'inherited_from': ['mlp/excess_return_10']}
    html = modeling_lab.render_modeling({'modeling': {'exists': True, 'report': report, 'models': 2, 'registry_statuses': {}}})
    row = html.split('ensemble/family_equal_weight</b>')[1].split('</tr>')[0]
    assert 'inherited from mlp/excess_return_10' in row and '4,417' not in row                      # not shown with its member's parameter count as if its own
    report['tables']['excess_return_10'][1]['dev_mean_ic'] = 10 ** 400
    path = _lab_file(tmp_path, report)
    state = modeling_view.summary(tmp_path / 'firm_lab.db')
    page = firm_lab_page.render({'firm_lab': {'exists': False, 'mode': 'BUILD_OBSERVE', 'fills': 0, 'modeling': state}})
    assert 'id="fl-modeling"' in page and modeling.WARNING in page                                  # a corrupt number degrades the cell or the section, never the page


# ====================================================================================================== the delta review of plan v3 (six minor findings)
def test_a_part_with_nothing_predicted_is_a_part_of_zeros_not_a_crash():
    from firm_lab.modeling import report as report_module
    data = synthetic(strength=0.02, seed=7)
    design = tournament.design(data)
    columns = list(range(len(NAMES)))
    for cls, target in ((models.Ridge, targets.PRIMARY), (models.Logistic, targets.CLASSIFICATION)):
        result = tournament.run({'name': 'x', 'cls': cls, 'grid': [{}], 'target': target, 'columns': columns}, data, design)
        for block in result['blocks'][:-1]:                                                         # nothing could be predicted on development sessions
            block['predicted'][:] = False
            block['prediction'][:] = np.nan
        summary = lab_module.summarize(result, data)
        assert summary['dev_mean_ic'] == 0.0 and summary['fold_ics'] == [0.0] * 5 and summary['dev']['n'] == 0
        assert 'regression' not in summary['dev'] and 'classification' not in summary['dev']        # no error is made up for rows that were never predicted
        assert summary.get('dev_log_loss') is None

        class Stub:
            results = {'x': result}
        row = report_module._row('x', Stub, summary, role='CANDIDATE', status='EXPERIMENTAL', reasons=[])
        assert row['dev_mean_ic'] == 0.0 and row.get('dev_rmse') is None and row.get('dev_log_loss') is None
        assert row['holdout_mean_ic'] is not None                                                   # the part that was predicted is still scored


def test_the_identity_gate_does_not_turn_on_the_luck_of_the_shuffles():
    generator = np.random.default_rng(12)
    y, score, session, instrument = _persistent_null(generator, sessions=60, instruments=22)
    score = score + 0.9 * np.tile(np.argsort(np.argsort(y.reshape(60, 22).mean(axis=0))), 60) / 22           # a weak real link: p near the level
    values = [metrics.identity_permutation_p(y, score, session, instrument, seed=seed)['p'] for seed in range(1, 9)]
    assert metrics.identity_permutation_p.__kwdefaults__['draws'] >= 100_000
    assert max(values) - min(values) < 0.004, values                                                # 2,000 shuffles moved a p near 0.05 by about 0.01 between seeds
    assert len({v <= metrics.IDENTITY_LEVEL for v in values}) == 1 or abs(np.mean(values) - metrics.IDENTITY_LEVEL) < 0.002


def test_the_identity_gate_accepts_only_a_p_value_and_a_partly_predicted_session_gets_none():
    baseline = {'steady': _series_record(0.04, seed=4)}
    candidate = _series_record(0.11, seed=3)
    for bad in (-0.1, 0.0, False, True, float('inf'), float('-inf')):
        assert selection.status(dict(candidate, dev_identity_p=bad), baseline, holm_rejected=True)[0] == 'EXPERIMENTAL', bad
    assert selection.status(dict(candidate, dev_identity_p=0.05), baseline, holm_rejected=False)[0] == 'CHALLENGER'
    generator = np.random.default_rng(5)
    y, score, session, instrument = _persistent_null(generator, sessions=30, instruments=9)
    partly = score.astype(float).copy()
    partly[4] = np.nan                                                                              # one instrument unpredicted in one session
    record = metrics.identity_permutation_p(y, partly, session, instrument)
    assert math.isnan(record['p']) and 'partly' in record['note']                                   # the shuffled statistic would not be the reported mean: no p-value
    whole = score.astype(float).copy()
    whole[:9] = np.nan                                                                              # a whole session unpredicted counts as 0, as in the mean
    record = metrics.identity_permutation_p(y, whole, session, instrument)
    assert record['observed'] == pytest.approx(metrics.filled(metrics.session_ic(y, whole, session)[1]).mean()) and 0 < record['p'] <= 1


def test_the_holm_level_shown_is_the_level_used_and_a_dataset_row_cannot_be_quietly_replaced(tmp_path):
    import inspect
    from firm_lab.modeling import report as report_module
    assert 'metrics.holm(values, level=HOLM_LEVEL)' in inspect.getsource(report_module.assemble) and report_module.HOLM_LEVEL == 0.10
    path = _modeling_db(tmp_path)
    registry.Registry(path).db.close()
    db = sqlite3.connect(path)
    with db:
        db.execute("INSERT INTO modeling_datasets VALUES ('d1', '{\"a\": 1}', 'x')")
        assert db.execute("INSERT OR IGNORE INTO modeling_datasets VALUES ('d1', '{\"a\": 1}', 'y')").rowcount == 0       # the same dataset again: nothing to do
    for statement in ("INSERT INTO modeling_datasets VALUES ('d1', '{\"a\": 2}', 'y')", "INSERT OR REPLACE INTO modeling_datasets VALUES ('d1', '{\"a\": 2}', 'y')",
                      "INSERT OR IGNORE INTO modeling_datasets VALUES ('d1', '{\"a\": 2}', 'y')"):
        with pytest.raises(sqlite3.DatabaseError, match='APPEND_ONLY'):
            db.execute(statement)                                                                   # a different dataset under a stored identity is an error, not silence
    assert db.execute("SELECT payload, created_at FROM modeling_datasets WHERE id = 'd1'").fetchone() == ('{"a": 1}', 'x')
    assert db.execute("INSERT INTO modeling_datasets VALUES ('d2', '{\"a\": 3}', 'x')").rowcount == 1
    db.close()
