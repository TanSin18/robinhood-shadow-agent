"""run_cycle wiring for v1.5 desk-policy ETF entries (explicitly enabled only)."""
from datetime import timedelta

from agents.daily_cycle import FixtureReader, run_cycle
from test_inbox_lanes import setup_runtime
from test_phase0_budget import NOW

SIGNAL = {'instrument': 'VTI', 'lane': 'A', 'side': 'buy', 'strategy': 'momentum_rotation_126d_trend200_top1',
          'strength': '0.5', 'thesis': 'Registered trend.', 'good_if': 'Trend holds.', 'invalidation': 'Trend breaks.'}


def run(tmp_path, monkeypatch, *, enabled, volume=True, interim=True):
    import agents.etf_issuer as issuer
    monkeypatch.setattr(issuer, 'LIQUIDITY_INTERIM_LIVE_SPREAD', interim)
    inbox, config = setup_runtime(tmp_path)
    from data.database_role import require_database_role
    require_database_role(inbox.path, 'live')
    class Reader(FixtureReader):
        def collect(self, now, held):
            reads = super().collect(now, held)
            if volume:
                for r in reads:
                    if r['tool'] == 'get_equity_historicals':
                        for item in r['data']['results']:
                            for b in item['bars']:
                                b['volume'] = '2000000'
            return reads
    class NoModel:
        def run(self, *a, **k): raise AssertionError('no model for ETF desk policy')
    monkeypatch.setattr('agents.daily_cycle.evaluate_daily_signals', lambda *a: {'signals': [SIGNAL], 'strategies': {}})
    from agents.cycle_lifecycle import CycleLifecycle
    lifecycle = CycleLifecycle(inbox.path)
    claim = lifecycle.acquire(NOW, scheduled=True)
    try:
        result = run_cycle(inbox, config, NoModel(), NOW, data_mode='live_readonly', reader=Reader(config, NOW),
                           clock=lambda: NOW, lifecycle=lifecycle, cycle_id=claim['cycle_id'],
                           desk_policy_enabled=enabled)
    finally:
        lifecycle.close()
    return inbox, result


def test_disabled_keeps_capability_gap_and_records_spreads(tmp_path, monkeypatch):
    inbox, result = run(tmp_path, monkeypatch, enabled=False)
    assert result['decision']['type'] == 'HOLD_CAPABILITY_GAP'
    assert result['desk_results'] == []
    with inbox.connect() as db:
        assert db.execute('SELECT count(*) FROM liquidity_observations').fetchone()[0] >= 1


def test_enabled_issues_three_arm_desk_entry(tmp_path, monkeypatch):
    inbox, result = run(tmp_path, monkeypatch, enabled=True)
    assert result['decision']['type'] == 'DESK_ENTRY'
    arms = {r['arm']: r['status'] for r in result['desk_results']}
    assert arms == {'agent_alone': 'filled', 'deterministic_no_ai': 'filled', 'with_approvals': 'PENDING'}
    assert result['api_cost_estimate_usd'] == '0' and result['agents'] == []


def test_enabled_but_no_volume_evidence_blocks_honestly(tmp_path, monkeypatch):
    inbox, result = run(tmp_path, monkeypatch, enabled=True, volume=False)
    assert result['decision']['type'] == 'DESK_ENTRY_BLOCKED'
    assert {r['reason'] for r in result['desk_results']} == {'LIQUIDITY_EVIDENCE_MISSING'}
    assert inbox.cards() == []
