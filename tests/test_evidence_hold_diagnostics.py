from datetime import timedelta

import pytest

from agents.daily_cycle import FixtureReader, market_snapshot, run_cycle
from data.corporate_actions import CorporateActionError, normalize_live_quote
from test_inbox_lanes import setup_runtime
from test_phase0_budget import NOW


@pytest.mark.parametrize('bid,ask', [('0', '.2'), ('-1', '1'), ('1', '0'), ('NaN', '1'), ('1', 'Infinity'), ('2', '1')])
def test_unusable_prices_are_not_corporate_action_failures(bid, ask):
    with pytest.raises(CorporateActionError) as caught:
        normalize_live_quote({'quote': {'instrument_id': 'contract-1',
            'bid_price': bid, 'ask_price': ask}}, known_at=NOW)
    assert caught.value.code == 'INVALID_QUOTE_PRICE'


def test_zero_bid_option_exclusion_retains_contract_identity(tmp_path):
    _, config = setup_runtime(tmp_path)
    reads = FixtureReader(config, NOW).collect(NOW, {})
    reads.append({'tool': 'get_option_quotes', 'data': {'results': [{'quote': {
        'instrument_id': 'contract-1', 'bid_price': '0', 'ask_price': '.2',
        'updated_at': NOW.isoformat()}}]}})
    snapshot = market_snapshot(reads, config, NOW, require_live_identity=True)
    assert {'instrument': 'contract-1', 'reason': 'INVALID_QUOTE_PRICE'} in snapshot['exclusions']
    assert 'contract-1' not in snapshot['quotes']


def cycle(tmp_path, monkeypatch, *, signal=False, invalid_option=False, stale=False, empty=False, missing_history=False):
    inbox, config = setup_runtime(tmp_path)
    from data.database_role import require_database_role
    require_database_role(inbox.path, 'live')
    class Reader(FixtureReader):
        def collect(self, now, held):
            reads = super().collect(now, held)
            if empty:
                reads = [r for r in reads if r['tool'] not in {'get_equity_quotes', 'get_option_quotes'}]
            if missing_history:
                reads = [r for r in reads if r['tool'] != 'get_equity_historicals']
            if invalid_option:
                reads.append({'tool': 'get_option_quotes', 'data': {'results': [{'quote': {
                    'instrument_id': 'contract-1', 'bid_price': '0', 'ask_price': '.2',
                    'updated_at': NOW.isoformat()}}]}})
            return reads
    class NoModel:
        def run(self, *args, **kwargs):
            raise AssertionError('No model permitted for ETF-only review')
    monkeypatch.setattr('agents.daily_cycle.evaluate_daily_signals', lambda *args: {
        'signals': [{'instrument': 'VTI', 'lane': 'A', 'side': 'buy', 'strategy': 'test_etf'}] if signal else [],
        'strategies': {}})
    from agents.cycle_lifecycle import CycleLifecycle
    lifecycle = CycleLifecycle(inbox.path)
    claim = lifecycle.acquire(NOW, scheduled=True)
    try:
        result = run_cycle(inbox, config, NoModel(), NOW, data_mode='live_readonly',
            reader=Reader(config, NOW), clock=lambda: NOW + timedelta(seconds=120 if stale else 0),
            lifecycle=lifecycle, cycle_id=claim['cycle_id'])
    finally:
        lifecycle.close()
    assert result['api_cost_estimate_usd'] == '0'
    assert result['results'] == [] and result['agents'] == []
    return result


def test_unrelated_bad_option_does_not_poison_fresh_universe(tmp_path, monkeypatch):
    result = cycle(tmp_path, monkeypatch, invalid_option=True)
    assert result['decision']['type'] == 'HOLD_CASH'
    assert result['quote_freshness']['fresh'] > 0
    assert result['corporate_action_exclusions'][0]['reason'] == 'INVALID_QUOTE_PRICE'


def test_etf_signal_reports_unimplemented_execution_not_stale_data(tmp_path, monkeypatch):
    result = cycle(tmp_path, monkeypatch, signal=True, invalid_option=True)
    assert result['decision']['type'] == 'HOLD_CAPABILITY_GAP'
    assert result['decision']['reason_code'] == 'DETERMINISTIC_ENTRY_PATH_NOT_IMPLEMENTED'
    assert result['decision']['signal_instruments'] == ['VTI']
    assert 'fresh' not in result['decision']['reason'].lower()


@pytest.mark.parametrize('empty', [False, True])
def test_no_usable_candidates_is_operational_not_cash_hold(tmp_path, monkeypatch, empty):
    result = cycle(tmp_path, monkeypatch, stale=not empty, empty=empty)
    assert result['decision']['type'] == 'HOLD_OPERATIONAL'
    assert result['decision']['reason_code'] == 'NO_FRESH_ELIGIBLE_CANDIDATES'


def test_fresh_quotes_without_sizing_history_are_operational_hold(tmp_path, monkeypatch):
    result = cycle(tmp_path, monkeypatch, missing_history=True)
    assert result['quote_freshness']['fresh'] > 0
    assert result['decision']['type'] == 'HOLD_OPERATIONAL'
    assert result['decision']['reason_code'] == 'NO_FRESH_ELIGIBLE_CANDIDATES'
