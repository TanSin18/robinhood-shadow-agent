"""Checkpoint 8: the documents say what the code does.

Each document that states a date, a rule, a reason name or a threshold is compared with the constant it describes. A
document that drifts from the code fails here, not in front of a reader."""
import re
from pathlib import Path

from firm_lab import history
from firm_lab.history import calendar, regimes, splits, store, sufficiency, targets, universe, validate

DOCS = Path(__file__).resolve().parents[1] / 'docs' / 'firm_lab'
POLICY = (DOCS / 'historical_market_data_policy.md').read_text()
HOLDOUT = (DOCS / 'CHECKPOINT8_HOLDOUT_DESIGN.md').read_text()
UNIVERSE = (DOCS / 'historical_universe.md').read_text()
SPEC = (DOCS / 'CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md').read_text()
SOURCES = (DOCS / 'CHECKPOINT8_SOURCES_PIT.md').read_text()
PROVIDER = (DOCS / 'CHECKPOINT8_PROVIDER_DECISION.md').read_text()


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
    assert '`SEALED_SEGMENT`' in HOLDOUT


def test_the_policy_document_lists_every_rejection_reason_and_every_change_class():
    table = re.findall(r'^ *\| `([A-Z_]+)` \|', POLICY, re.M)
    classes = {store.EXTENDED, store.SCALE_ONLY, store.VALUE_CHANGE, store.TOTAL_RETURN_READJUSTED, store.METADATA_ONLY}
    assert [name for name in table if name not in classes] == list(validate.REASONS)       # the same reasons, in the same order
    assert classes <= set(table)
    assert f'Policy version `{history.POLICY_VERSION}`' in POLICY and f'`{history.FILE_NAME}`' in POLICY and f'`{history.DATABASE_ROLE}`' in POLICY
    for name in ('INVALID_BAR_BLOCK', 'INVALID_CAPTURE_TIME', 'CAPTURE_TIME_NOT_MONOTONIC', 'SOURCE_REQUIRED', 'CONFLICTING_SECURITY_IDENTITY', 'MALFORMED_SECURITY',
                 'UNEXPECTED_FILE_LAYOUT', 'VENDOR_FILE_INSIDE_A_REPOSITORY', 'SURVIVOR_ONLY_SOURCE', 'UNIVERSE_IS_STALE', 'DELISTED_EXIT', 'PAST_HISTORY'):
        assert f'`{name}`' in POLICY, name
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
    for name in ('SURVIVOR_ONLY_SOURCE', 'UNIVERSE_IS_STALE', 'UNIVERSE_HASH_REQUIRED', 'UNIVERSE_RECORDS_DO_NOT_MATCH_MANIFEST'):
        assert f'`{name}`' in UNIVERSE, name


def test_the_second_amendment_states_the_measurement_rules_in_code_and_lowers_no_bar():
    amendment = SPEC[SPEC.index('**Amendment 2'):]
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
