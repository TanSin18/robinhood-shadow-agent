"""Checkpoint 7 modeling core: targets, chronological splits, train-only preprocessing, metrics and the status rules.

What is proven here: a label is built only from the sessions it names and is aligned with the benchmark; a split never
trains on the future, purges overlapping labels and keeps the holdout apart; preprocessing learns from training rows
only; overlap is respected by the statistics; and no rule can hand out a production or live status."""
import math

import numpy as np
import pytest

np = pytest.importorskip('numpy')

from firm_lab import modeling
from firm_lab.modeling import metrics, selection, splits, targets
from firm_lab.modeling.preprocess import Preprocessor


# ====================================================================================================== targets
def _closes(n=40):
    sessions = [f'S{k:03d}' for k in range(n)]
    return sessions, {'VTI': [100 * 1.001 ** k for k in range(n)], 'AAA': [50 * 1.003 ** k for k in range(n)],
                      'BBB': [20 + (k % 7) for k in range(n)]}


def _build(sessions, closes, monkeypatch):
    monkeypatch.setattr(targets, 'session_close', lambda s: f'{s}T20:00:00+00:00')
    return targets.build(sessions, closes)


def test_the_primary_target_is_the_ten_session_excess_price_return_on_aligned_sessions(monkeypatch):
    sessions, closes = _closes()
    labels = _build(sessions, closes, monkeypatch)
    record = labels[('AAA', 'S005')]
    own = closes['AAA'][15] / closes['AAA'][5] - 1
    market = closes['VTI'][15] / closes['VTI'][5] - 1
    assert record['excess_return_10'] == pytest.approx(own - market) and record['instrument_return_10'] == pytest.approx(own)
    assert record['benchmark_return_10'] == pytest.approx(market) and record['target_end_session_10'] == 'S015' and record['target_start_session'] == 'S005'
    assert record['target_end_session_5'] == 'S010' and record['target_end_session_20'] == 'S025' and record['benchmark'] == 'VTI'
    assert record['positive_excess_10'] == 1 and record['target_version'] == targets.TARGET_VERSION == 'forward-excess-price-return-v1'
    assert ('VTI', 'S005') not in labels                                                           # the benchmark is not a sample of itself
    assert targets.PRIMARY == 'excess_return_10' and targets.HORIZONS == (5, 10, 20)


def test_a_label_whose_window_runs_past_the_stored_history_does_not_exist(monkeypatch):
    sessions, closes = _closes(40)
    labels = _build(sessions, closes, monkeypatch)
    last = labels[('AAA', 'S039')]
    assert all(last[name] is None for name in targets.ALL)
    edge = labels[('AAA', 'S029')]                                                                 # ten sessions remain, twenty do not
    assert edge['excess_return_10'] is not None and edge['excess_return_20'] is None and edge['close_mae_10'] is not None
    assert labels[('AAA', 'S030')]['excess_return_10'] is None and labels[('AAA', 'S034')]['excess_return_5'] is not None


def test_risk_targets_are_close_based_and_the_sign_target_follows_the_return(monkeypatch):
    sessions, closes = _closes()
    closes['BBB'] = [100, 90, 95, 110, 105, 80, 120, 100, 100, 100, 100] + [100] * 29
    labels = _build(sessions, closes, monkeypatch)
    record = labels[('BBB', 'S000')]
    assert record['close_mae_10'] == pytest.approx(-0.20) and record['close_mfe_10'] == pytest.approx(0.20)       # closes only: 80 and 120 against 100
    logs = [math.log(b / a) for a, b in zip(closes['BBB'][:10], closes['BBB'][1:11])]
    mean = sum(logs) / 10
    assert record['future_realized_vol_10'] == pytest.approx(math.sqrt(sum((x - mean) ** 2 for x in logs) / 9) * math.sqrt(252))
    assert record['positive_excess_10'] == int(record['excess_return_10'] > 0) == 0                 # flat against a rising benchmark
    # a later close changes only labels whose window reaches it
    changed = dict(closes, BBB=closes['BBB'][:30] + [500] + closes['BBB'][31:])
    after = _build(sessions, changed, monkeypatch)
    assert after[('BBB', 'S005')] == labels[('BBB', 'S005')] and after[('BBB', 'S020')]['excess_return_10'] != labels[('BBB', 'S020')]['excess_return_10']


# ====================================================================================================== splits
def _design(**kw):
    args = dict(horizon=20, embargo=5, folds=5, minimum_train=80, holdout_fraction=0.2)
    args.update(kw)
    return splits.walk_forward(63, 357, **args)


def test_walk_forward_is_chronological_purged_and_keeps_the_holdout_apart():
    design = _design()
    assert splits.check(design) == [] and len(design['folds']) == 5 and design['version'] == 'expanding-walk-forward-purged-v1'
    previous_end = None
    for fold in design['folds']:
        assert max(fold.train) + 20 < min(fold.validation)                                         # every training label closed before the block began
        assert fold.purged and min(fold.purged) == max(fold.train) + 1 and max(fold.purged) == min(fold.validation) - 1
        assert len(fold.purged) == 20 and not set(fold.train) & set(fold.validation) and min(fold.train) == 63
        assert previous_end is None or min(fold.validation) == previous_end + 1                    # consecutive blocks, no session predicted twice
        previous_end = max(fold.validation)
    holdout = design['holdout']
    assert max(holdout.validation) == 357 and len(holdout.validation) == 59
    assert design['gap_before_holdout'] == 25 and max(holdout.train) == design['development_end'] == min(holdout.validation) - 26
    assert all(max(f.validation) <= design['development_end'] for f in design['folds'])            # no fold is validated inside the gap or the holdout
    used = set().union(*(set(f.train) | set(f.validation) for f in design['folds']))
    assert not used & set(holdout.validation)                                                      # development never touches a holdout session


def test_the_purge_and_embargo_rules_are_exact():
    assert splits.may_train(10, 31, 40, horizon=20, embargo=5) and not splits.may_train(11, 31, 40, horizon=20, embargo=5)       # 11 + 20 reaches 31
    assert not splits.may_train(65, 31, 40, horizon=20, embargo=5) and splits.may_train(66, 31, 40, horizon=20, embargo=5)       # after the last label plus the embargo
    block = splits.block('b', range(0, 100), 31, 40, horizon=20, embargo=5)
    assert block.train == tuple(range(0, 11)) and block.purged == tuple(range(11, 31))             # past only: nothing after the block trains it
    both = splits.block('b', range(0, 100), 31, 40, horizon=20, embargo=5, past_only=False)
    assert both.train == tuple(range(0, 11)) + tuple(range(66, 100))


def test_a_design_that_would_leak_is_reported_and_too_little_data_is_refused():
    design = _design()
    leaky = splits.Block('fold_1', tuple(range(63, 150)), tuple(range(155, 170)), ())               # the last training labels reach into the block
    assert 'a training label window reaches the validation block' in ' '.join(splits.check({**design, 'folds': [leaky] + design['folds'][1:]}))
    future = splits.Block('fold_1', tuple(range(63, 100)) + (200,), tuple(range(143, 170)), ())
    assert 'trained on the future' in ' '.join(splits.check({**design, 'folds': [future] + design['folds'][1:]}))
    near = splits.Block('fold_5', design['folds'][4].train, tuple(range(250, 290)), ())
    assert 'too close to the final holdout' in ' '.join(splits.check({**design, 'folds': design['folds'][:4] + [near]}))
    with pytest.raises(ValueError, match='INSUFFICIENT_SESSIONS_FOR_WALK_FORWARD'):
        splits.walk_forward(0, 99, horizon=20, embargo=5, folds=5, minimum_train=80)
    inner = splits.inner(tuple(range(63, 163)), horizon=20, embargo=5)
    assert max(inner.train) + 20 < min(inner.validation) and max(inner.validation) == 162 and len(inner.validation) == 25
    with pytest.raises(ValueError, match='INSUFFICIENT_SESSIONS_FOR_INNER_SPLIT'):
        splits.inner(tuple(range(0, 30)), horizon=20, embargo=5)


# ====================================================================================================== preprocessing
def test_preprocessing_is_learned_from_training_rows_only_and_is_deterministic():
    generator = np.random.default_rng(1)
    train = generator.normal(size=(200, 4))
    train[:190, 2] = np.nan                                                                        # available in 5% of training rows: dropped
    train[:10, 1] = np.nan
    train[:, 3] = 7.0                                                                              # constant: dropped
    validation = generator.normal(loc=50, scale=9, size=(50, 4))
    a = Preprocessor().fit(train)
    state = a.state()
    out = a.transform(validation)
    assert a.keep.tolist() == [0, 1] and a.flagged.tolist() == [1] and out.shape == (50, 3)        # two kept columns and one missing-value flag
    assert a.state() == state                                                                      # transforming other rows changes nothing that was learned
    b = Preprocessor().fit(train)
    assert b.state() == state and np.array_equal(b.transform(validation), out)                     # same rows in, same state out
    assert Preprocessor().fit(np.vstack([train, validation])).state() != state                     # had the other rows been seen, the state would differ
    clipped = a.transform(np.array([[1e9, np.nan, 0.0, 7.0]]))
    assert clipped[0, 0] == pytest.approx((a.high[0] - a.mean[0]) / a.std[0]) and clipped[0, 2] == 1.0 and clipped[0, 1] == pytest.approx((a.median[1] - a.mean[1]) / a.std[1])
    with pytest.raises(ValueError, match='PREPROCESSOR_NOT_FITTED'):
        Preprocessor().transform(validation)
    raw = Preprocessor(impute=False, scale=False, indicators=False, clip=(0.0, 100.0)).fit(train).transform(np.array([[1.0, np.nan, 3.0, 7.0]]))
    assert raw[0, 0] == 1.0 and np.isnan(raw[0, 1])                                                # the tree setting keeps "unavailable" as it is


# ====================================================================================================== metrics
def test_rank_correlation_auc_and_calibration_agree_with_hand_calculations():
    assert metrics.rank([10, 20, 20, 5]).tolist() == [2.0, 3.5, 3.5, 1.0]
    assert metrics.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 100]) == pytest.approx(1.0) and metrics.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert math.isnan(metrics.spearman([1, 2, 3, 4], [5, 5, 5, 5]))                                 # a constant ranks nothing
    assert metrics.roc_auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]) == pytest.approx(0.75)
    assert metrics.average_precision([1, 0, 1, 0], [0.9, 0.8, 0.7, 0.1]) == pytest.approx((1 + 2 / 3) / 2)
    record = metrics.classification(np.array([1, 0, 1, 0]), np.array([0.8, 0.2, 0.8, 0.2]))
    assert record['brier'] == pytest.approx(0.04) and record['log_loss'] == pytest.approx(-math.log(0.8)) and record['roc_auc'] == 1.0
    assert record['calibration_error'] == pytest.approx(0.2) and [b['n'] for b in record['reliability']] == [2, 2]
    regression = metrics.regression(np.array([0.01, -0.02, 0.03]), np.array([0.02, -0.01, -0.01]))
    assert regression['mae'] == pytest.approx(0.02) and regression['directional_accuracy'] == pytest.approx(2 / 3)
    assert metrics.regression(np.array([0.01, -0.02]), np.zeros(2))['r2_vs_zero'] == pytest.approx(0.0)
    assert metrics.pinball(np.array([1.0, 3.0]), np.array([2.0, 2.0]), 0.9) == pytest.approx((0.1 * 1 + 0.9 * 1) / 2)
    assert metrics.coverage(np.array([1, 2, 3, 4]), np.array([0, 0, 4, 0]), np.array([2, 1, 5, 9]))['coverage'] == 0.5


def test_session_statistics_respect_overlap_and_an_interval_needs_enough_batches():
    generator = np.random.default_rng(3)
    sessions = np.repeat(np.arange(120), 10)
    y = generator.normal(size=1200)
    days, ic = metrics.session_ic(y, y + generator.normal(scale=0.5, size=1200), sessions)
    assert len(days) == 120 and ic.mean() > 0.6
    assert len(metrics.non_overlapping(ic, 10)) == 12                                              # 120 sessions of 10-session labels are 12 windows, not 120
    a = metrics.batch_interval(ic, horizon=10)
    assert a == metrics.batch_interval(ic, horizon=10) and (a['batches'], a['batch_length']) == (6, 20) and a['low'] < a['estimate'] < a['high']
    assert 0 < a['p_not_positive'] < 0.001                                                          # strong, and still never exactly zero
    noise = metrics.batch_interval(generator.normal(size=120), horizon=10)
    assert noise['low'] < 0 < noise['high'] and 0.02 < noise['p_not_positive'] < 0.98               # noise is not declared an edge
    short = metrics.batch_interval(ic[:59], horizon=10)
    assert short['batches'] == 2 and math.isnan(short['low']) and math.isnan(short['p_not_positive']) and 'too few' in short['note']      # no interval is made up
    flat = metrics.batch_interval(np.zeros(120), horizon=10)
    assert flat['p_not_positive'] == 1.0 and flat['low'] == flat['high'] == 0.0                     # a model that ranks nothing shows nothing
    ranking = metrics.ranking(y, y, sessions, horizon=10, k=3)
    assert ranking['mean_ic'] == pytest.approx(1.0) and ranking['non_overlapping_windows'] == 12 and ranking['batches'] == 6 and ranking['top_bottom']['top_minus_bottom'] > 0
    constant = metrics.ranking(y, np.zeros(1200), sessions, horizon=10)
    assert constant['sessions_with_a_ranking'] == 0 and constant['mean_ic'] == 0.0 and constant['ic_series'] == [0.0] * 120      # no ranking counts as zero skill


def test_holm_adjustment_makes_one_lucky_result_among_many_insufficient():
    alone = metrics.holm({'a': 0.04})
    assert alone['a']['rejected'] is True
    many = metrics.holm({'a': 0.04, **{f'm{k}': 0.5 for k in range(9)}})
    assert many['a']['adjusted'] == pytest.approx(0.4) and many['a']['rejected'] is False            # the same result, now one of ten tries
    assert metrics.holm({'a': None, 'b': float('nan')})['a']['adjusted'] == 1.0


# ====================================================================================================== status rules
def _record(ic, holdout, folds, horizon=10, seed=0, n=130):
    generator = np.random.default_rng(seed)
    return {'dev_mean_ic': ic, 'holdout_mean_ic': holdout, 'fold_ics': folds, 'horizon': horizon, 'dev_identity_p': 0.001,
            'dev_ic_series': (ic + generator.normal(scale=0.05, size=n)).tolist(), 'holdout_ic_series': (holdout + generator.normal(scale=0.05, size=59)).tolist()}


def test_statuses_follow_the_rules_fixed_in_advance_and_there_is_no_production_status():
    assert modeling.STATUSES == ('EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW')
    assert not [s for s in modeling.STATUSES if 'PRODUCTION' in s or 'LIVE' in s]
    base = {'momentum': _record(0.02, 0.02, [0.02] * 5, horizon=5, seed=1)}
    assert selection.status(_record(-0.01, 0.1, [0.1] * 5, horizon=5), base, holm_rejected=True)[0] == 'REJECTED'
    assert selection.status(_record(0.01, 0.1, [0.1] * 5, horizon=5), base, holm_rejected=True)[0] == 'REJECTED'      # not above the strongest baseline
    strong = _record(0.12, 0.10, [0.1, 0.12, 0.09, 0.15, 0.11], horizon=5, seed=2)
    assert selection.status(strong, base, holm_rejected=True)[0] == 'ELIGIBLE_FOR_FUTURE_REVIEW'
    assert selection.status(strong, base, holm_rejected=False)[0] == 'CHALLENGER'                                # not established after adjustment
    # the same numbers on the 10-session label: 59 holdout sessions are 2 batches, too few for any interval, so nothing can be eligible
    status, reasons = selection.status(dict(strong, horizon=10), {'momentum': dict(base['momentum'], horizon=10)}, holm_rejected=True)
    assert status == 'CHALLENGER' and 'too few for any interval' in reasons[-1]
    status, reasons = selection.status(strong, base, holm_rejected=True, sufficient=False)
    assert status == 'EXPERIMENTAL' and 'EXPERIMENTAL_INSUFFICIENT_DATA' in reasons[0]                           # a network without enough data cannot be a challenger
    unstable = _record(0.12, 0.10, [0.4, 0.3, -0.1, -0.05, -0.02], horizon=5, seed=2)
    assert selection.status(unstable, base, holm_rejected=True)[0] == 'EXPERIMENTAL'                             # one or two lucky folds are not enough
    assert selection.status(_record(0.12, -0.03, [0.1] * 5, horizon=5, seed=2), base, holm_rejected=True)[0] == 'EXPERIMENTAL'      # the holdout did not agree
    classifier = dict(strong, dev_log_loss=0.70, naive_log_loss=0.69)
    assert selection.status(classifier, base, holm_rejected=True)[0] == 'EXPERIMENTAL'                           # ranks well, but its probabilities are worse than a naive forecast
    assert selection.strongest_baseline({'zero': {'dev_mean_ic': float('nan')}, 'momentum': {'dev_mean_ic': -0.01}}) == 'zero'      # nothing ranked counts as 0, above a negative
    assert selection.loss_status([1.0] * 5, [1.1] * 5, 1.0, 1.1)[0] == 'CHALLENGER' and selection.loss_status([1.2] * 5, [1.1] * 5, 1.0, 1.1)[0] == 'REJECTED'
    assert selection.loss_status([1.0, 1.0, 1.2, 1.2, 1.0], [1.1] * 5, 1.0, 1.1)[0] == 'EXPERIMENTAL'


def test_the_fibonacci_answer_is_decided_by_the_rule_not_by_preference():
    yes = {'ridge': {'dev': {'low': 0.01, 'high': 0.05, 'estimate': 0.03}, 'holdout_difference': 0.02},
           'lightgbm': {'dev': {'low': 0.005, 'high': 0.04, 'estimate': 0.02}, 'holdout_difference': 0.01}}
    assert selection.fibonacci_verdict(yes)[0] == 'YES'
    ruled_out = {k: {'dev': {'low': -0.03, 'high': 0.005, 'estimate': -0.01}, 'holdout_difference': 0.02} for k in ('ridge', 'lightgbm')}
    assert selection.fibonacci_verdict(ruled_out)[0] == 'NO'
    never_positive = {k: {'dev': {'low': -0.05, 'high': 0.03, 'estimate': -0.01}, 'holdout_difference': -0.01} for k in ('ridge', 'lightgbm')}
    assert selection.fibonacci_verdict(never_positive)[0] == 'NO'
    mixed = {'ridge': yes['ridge'], 'lightgbm': {'dev': {'low': -0.02, 'high': 0.04, 'estimate': 0.01}, 'holdout_difference': -0.01}}
    assert selection.fibonacci_verdict(mixed)[0] == 'INCONCLUSIVE'
    wide = {k: {'dev': {'low': -0.03, 'high': 0.05, 'estimate': 0.01}, 'holdout_difference': 0.01} for k in ('ridge', 'lightgbm')}
    assert selection.fibonacci_verdict(wide)[0] == 'INCONCLUSIVE'                                    # a wide interval is not a yes
    assert selection.participation_ratio(np.column_stack([np.arange(50.0)] * 6 + [np.arange(50.0)[::-1]])) == pytest.approx(1.0)
    independent = np.random.default_rng(5).normal(size=(4000, 8))
    assert 7.5 < selection.participation_ratio(independent) <= 8.0
