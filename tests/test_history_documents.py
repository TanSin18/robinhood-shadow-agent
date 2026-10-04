"""Checkpoint 8: the documents say what the code does.

Each document that states a date, a rule, a reason name or a threshold is compared with the constant it describes. A
document that drifts from the code fails here, not in front of a reader."""
import re
from pathlib import Path

from firm_lab import history
from firm_lab.history import calendar, dataset, features, regimes, splits, store, sufficiency, targets, universe, validate

DOCS = Path(__file__).resolve().parents[1] / 'docs' / 'firm_lab'


class Text(str):
    """A document in which a phrase is found wherever the lines happen to break."""
    def __contains__(self, phrase):
        return ' '.join(str(phrase).split()) in ' '.join(self.split())

POLICY = Text((DOCS / 'historical_market_data_policy.md').read_text())
HOLDOUT = Text((DOCS / 'CHECKPOINT8_HOLDOUT_DESIGN.md').read_text())
UNIVERSE = Text((DOCS / 'historical_universe.md').read_text())
SPEC = (DOCS / 'CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md').read_text()
SOURCES = Text((DOCS / 'CHECKPOINT8_SOURCES_PIT.md').read_text())
PROVIDER = Text((DOCS / 'CHECKPOINT8_PROVIDER_DECISION.md').read_text())


def test_the_holdout_document_states_the_reserved_chronology():
    r = splits.reservation()
    assert f'Split version `{splits.SPLIT_VERSION}`' in HOLDOUT
    assert f'| `DEVELOPMENT` | {r["segments"]["DEVELOPMENT"][0]} to {r["segments"]["DEVELOPMENT"][1]} |' in HOLDOUT
    purge = r['segments'][splits.PURGED]
    assert f'| `PURGE` | {purge[0]} to {purge[1]} ({splits.PURGE} sessions) |' in HOLDOUT and len(calendar.sessions(*purge)) == splits.PURGE
    assert f'| `HISTORICAL_HOLDOUT` | {splits.HOLDOUT_FIRST} to {splits.HOLDOUT_LAST} | **Sealed.**' in HOLDOUT
    assert f'| `BURNED_CHECKPOINT7` | {splits.BURNED_FIRST} to {splits.BURNED_LAST} | Never a test set. Samples through {splits.burned_last_sample()};' in HOLDOUT
    tail = calendar.sessions(calendar.offset(splits.burned_last_sample(), 1), splits.BURNED_LAST)
    assert f'the last {len(tail)} sessions ({tail[0]} to {tail[-1]}) are a purge' in HOLDOUT and len(tail) == targets.MAX_HORIZON + 1
    assert f'| `FORWARD_HOLDOUT` | {splits.FORWARD_FIRST} onward | **Sealed.**' in HOLDOUT
    assert f'Its last sample session is {splits.holdout_last_sample()}.' in HOLDOUT and f'Its last sample session is {splits.burned_last_sample()}.' in HOLDOUT
    assert 'old Checkpoint 7 holdout reused as pristine: NO' in HOLDOUT and r['checkpoint7_holdout_reused_as_pristine'] is False
    assert '**Label values can be read in two segments only: `DEVELOPMENT` and `BURNED_CHECKPOINT7`.**' in HOLDOUT
    assert [name for name in (splits.DEVELOPMENT, splits.PURGED, splits.HISTORICAL_HOLDOUT, splits.BURNED, splits.FORWARD_HOLDOUT, splits.BURN_IN)
            if splits.labels_allowed(name)] == r['label_values_readable_in'] == [splits.DEVELOPMENT, splits.BURNED]
    assert f'at least {splits.MINIMUM_FOLDS} folds, each validated on at least {splits.MINIMUM_FOLD_SESSIONS} sessions' in HOLDOUT
    assert 'No model metric of any kind was computed in Checkpoint 8, on any segment.' in HOLDOUT
    assert dataset.FEATURES_FROM == splits.BURNED_FIRST and f'computed only\nfrom bars on or after {splits.BURNED_FIRST}' in HOLDOUT
    assert 'blanks the label value **and every feature value**' in HOLDOUT and 'it is a rule with tests, not a lock' in HOLDOUT
    assert '`SEALED_SEGMENT`' in HOLDOUT


def test_the_policy_document_lists_every_rejection_reason_and_every_change_class():
    table = re.findall(r'^ *\| `([A-Z_]+)` \|', POLICY, re.M)
    classes = {store.EXTENDED, store.SCALE_ONLY, store.VALUE_CHANGE, store.TOTAL_RETURN_READJUSTED, store.METADATA_ONLY}
    assert [name for name in table if name not in classes] == list(validate.REASONS)       # the same reasons, in the same order
    assert classes <= set(table)
    assert f'Policy version `{history.POLICY_VERSION}`' in POLICY and f'`{history.FILE_NAME}`' in POLICY and f'`{history.DATABASE_ROLE}`' in POLICY
    for name in ('INVALID_BAR_BLOCK', 'INVALID_CAPTURE_TIME', 'CAPTURE_TIME_NOT_MONOTONIC', 'SOURCE_REQUIRED', 'CONFLICTING_SECURITY_IDENTITY', 'MALFORMED_SECURITY',
                 'UNEXPECTED_FILE_LAYOUT', 'VENDOR_FILE_INSIDE_A_REPOSITORY', 'SURVIVOR_ONLY_SOURCE', 'UNIVERSE_IS_STALE', 'CAPTURE_TIME_IN_THE_FUTURE',
                 targets.REASONS[targets.DELISTED_EXIT], targets.REASONS[targets.PAST_HISTORY], targets.REASONS[targets.HAS_BREAK], 'SYSTEM', 'SUPPLIED', 'sparse'):
        assert f'`{name}`' in POLICY, name
    assert f'read its last {dataset.INPUT_WINDOW_BARS} bars' in POLICY and dataset.INPUT_WINDOW_BARS == features.LONGEST_FIXED_LOOKBACK == 253
    assert 'are used for every row of a dataset or for none' in POLICY and 'is tier C and is not a strict sample' in POLICY
    from firm_lab.history import adjust
    assert adjust.SPLIT_VALUE_MEANS == 'new_per_old' and "a split's value is new shares per old share" in POLICY
    assert 'Either way of writing' not in POLICY
    assert adjust.DIVIDEND_VALUE_MEANS == 'unadjusted' and "a dividend's value\n  is the amount paid per share on the day" in POLICY
    assert "taken from the decimals of **that\n  bar's own row**" in POLICY and '`splits_unchecked`' in POLICY
    assert f'`{targets.TARGET_VERSION}`' in POLICY and 'the label starts at the close of T+1' in POLICY
    assert '`security_months_undecided_by_volume_recount`' in POLICY and '`security_months_undecided_by_volume_recount`' in UNIVERSE
    assert adjust.VOLUME_PRECISION_BOUND == 0.005 and 'Where the range is wider than 0.5% of the volume either way' in POLICY
    assert adjust.TICK_BOUND == 0.0005 and 'is coarser than a twentieth of a cent' in POLICY and adjust.PRECISION_BOUND == 5e-4
    assert dataset.CORE_FEATURES == ('return20', 'realized_vol20') and 'the core features are the\n  20-session return and the 20-session realized volatility' in POLICY
    assert 'VOLUME_REPRINT_TOO_COARSE' not in POLICY + UNIVERSE and 'NO_DOLLAR_VOLUME' in universe.REASONS
    for name in (adjust.UNSIZED, adjust.NO_ACTION, adjust.NO_FACTOR, 'SPLIT_VALUE_CONVENTION_CONTRADICTED', 'DIVIDEND_AMOUNT_BASIS_CONTRADICTED'):
        assert f'`{name}`' in POLICY, name
    assert dataset.contradictions({'old_per_new': 1}, {}) == ['SPLIT_VALUE_CONVENTION_CONTRADICTED']
    assert 'within five sessions of the security\'s last bar' in POLICY and targets.DELISTING_WINDOW == 5
    assert 'It is not a\n  stored column.' in POLICY                                         # eligible_from is computed from the calendar
    assert 'These hashes are integrity checks, not authentication.' in POLICY
    assert 'It does not protect against a person with the file and\n  a SQL prompt.' in POLICY


def test_the_universe_document_states_the_rule_in_code():
    rule = universe.RULE
    assert f'Universe version `{universe.UNIVERSE_VERSION}`' in UNIVERSE
    assert f'At least {rule["minimum_history_bars"]} bars of history up to R.' in UNIVERSE
    assert f'close of at least ${rule["minimum_unadjusted_close"]:.2f}' in UNIVERSE
    assert f'at least {rule["minimum_bars_in_window"]} of the last {rule["liquidity_window_sessions"]} exchange sessions' in UNIVERSE
    assert f'The first {rule["size"]:,} are members.' in UNIVERSE and rule['price_table'] == 'stocks'
    assert 'the present-day security master does\nnot decide who is screened' in UNIVERSE
    for name in ('SURVIVOR_ONLY_SOURCE', 'UNIVERSE_IS_STALE', 'UNIVERSE_HASH_REQUIRED', 'UNIVERSE_RECORDS_DO_NOT_MATCH_MANIFEST', 'RULE_NEEDS_ITS_OWN_VERSION'):
        assert f'`{name}`' in UNIVERSE, name


def test_the_second_amendment_states_the_measurement_rules_in_code_and_lowers_no_bar():
    amendment = SPEC[SPEC.index('**Amendment 2'):SPEC.index('**Amendment 3')]
    third = SPEC[SPEC.index('**Amendment 3'):SPEC.index('**Amendment 4')]
    fourth = SPEC[SPEC.index('**Amendment 4'):SPEC.index('**Amendment 5')]
    fifth = SPEC[SPEC.index('**Amendment 5'):]
    assert 'No bar was\nlowered and none was added.' in fifth and f'`{targets.TARGET_VERSION}`' in fifth
    assert 'No bar was\nlowered and none was added.' in fourth and 'Print precision is judged per bar' in fourth and 'A removed bar is a restated bar' in fourth
    assert 'No bar was\nlowered and none was added.' in third and 'for every row of a dataset or for none' in third
    assert 'A restated bar is tier C' in third and f'({splits.MINIMUM_FOLDS} x {splits.MINIMUM_FOLD_SESSIONS})' in third and 'reads 253 bars' in third
    assert len(set(re.findall(r'^\| ([HPEFO][0-9]) ', SPEC, re.M))) == 25 and 'lists all 25 bars' in third
    assert 'No bar was\nlowered and none was added.' in amendment
    assert f'at least {sufficiency.MINIMUM_SHARED_WINDOWS} non-overlapping windows' in amendment
    assert 'at least half of all pairs' in amendment and sufficiency.MINIMUM_PAIR_COVERAGE == 0.5
    assert f'shares at least {sufficiency.MINIMUM_MEDIAN_SHARED} windows' in amendment
    assert f'at least {regimes.EPISODE_MINIMUM_SESSIONS} sessions in the class; runs separated by fewer than {regimes.EPISODE_BRIDGE_SESSIONS}' in amendment
    assert f'at least {regimes.EPISODE_MINIMUM_SESSIONS} sessions in its class, and runs fewer than {regimes.EPISODE_BRIDGE_SESSIONS}' in SOURCES
    assert sufficiency.E_AT_LONGEST_HORIZON == ('multi_task',) and 'a multi-task network is judged at its longest horizon' in amendment
    # the bars themselves are where the first commit put them
    assert sufficiency.REFERENCE_IC == 0.03 and sufficiency.WEAK_IC == 0.05 and sufficiency.PER_PARAMETER == 10 and sufficiency.required_observations() == 6889


def test_the_provider_document_asks_for_a_decision_and_claims_no_purchase():
    assert 'OPERATOR PURCHASE DECISION REQUIRED' in PROVIDER and 'RECOMMENDED_PROVIDER = Sharadar' in PROVIDER
    assert 'nothing was purchased, no key exists and no feed was activated' in PROVIDER
    assert 'stlouisfed' not in SOURCES.lower() and 'FRED and ALFRED are not used' in SOURCES
