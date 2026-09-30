import json
import sqlite3
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from test_inbox_lanes import setup_runtime
from test_risk_engine import make_proposal
from broker.models import Quote

NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def test_module_entrypoint_uses_canonical_class_identity(monkeypatch):
    import runpy
    import agents.rehearsal as rehearsal
    calls = []
    monkeypatch.setattr(rehearsal, 'main', lambda: calls.append('canonical') or 0)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module('agents.rehearsal', run_name='__main__')
    assert stopped.value.code == 0
    assert calls == ['canonical']


def source(tmp_path):
    from data.database_role import require_database_role
    inbox, config = setup_runtime(tmp_path)
    require_database_role(inbox.path, 'live')
    inbox.store.append_json('run_states', {'cycle_id': 'parent-1', 'status': 'COMPLETED',
                                         'data_mode': 'live_readonly'})
    return inbox, config


def test_rehearsal_reuses_cycle_without_claim_or_writes(tmp_path):
    from agents.rehearsal import prepare, official_digest
    from agents.daily_cycle import FixtureReader, run_cycle
    official, config = source(tmp_path)
    before = official_digest(official.path)
    rehearsal = prepare(official.path, tmp_path / 'rehearsal', config)
    class NoModel:
        def run(self, *args, **kwargs):
            raise AssertionError('ETF gate should not invoke AI')
    result = run_cycle(rehearsal, config, NoModel(), NOW, data_mode='whatif',
                       reader=FixtureReader(config, NOW), clock=lambda: NOW)
    assert result['status'] == 'COMPLETED'
    assert result['data_mode'] == 'whatif'
    assert result['parent_official_run_id'] == 'parent-1'
    assert result['trigger'] == 'rehearsal'
    assert result['agents'] == [] and result['api_cost_estimate_usd'] == '0'
    assert official_digest(official.path) == before
    with sqlite3.connect(rehearsal.path) as db:
        for table in ('cycle_runs', 'approval_inbox', 'fills', 'daily_values', 'lessons'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_rehearsal_rejects_existing_output_and_missing_parent(tmp_path):
    from agents.rehearsal import prepare, RehearsalBlocked
    official, config = setup_runtime(tmp_path)
    with pytest.raises(RehearsalBlocked):
        prepare(official.path, tmp_path / 'bad', config)
    official, config = source(tmp_path)
    with pytest.raises(RehearsalBlocked):
        prepare(official.path, official.path.parent, config)


def test_direct_sql_and_api_cannot_issue_or_score(tmp_path):
    from agents.rehearsal import prepare, RehearsalBlocked
    official, config = source(tmp_path)
    rehearsal = prepare(official.path, tmp_path / 'rehearsal', config)
    with sqlite3.connect(rehearsal.path) as db:
        for table in ('fills', 'cards', 'daily_values', 'lessons', 'orders', 'decision_records'):
            with pytest.raises(sqlite3.IntegrityError, match='REHEARSAL_WRITE_BLOCKED'):
                db.execute(f'INSERT INTO {table}(created_at,payload_json) VALUES (?,?)', ('now', '{}'))
        with pytest.raises(sqlite3.IntegrityError, match='REHEARSAL_WRITE_BLOCKED'):
            db.execute('INSERT INTO cycle_runs(day,status,payload) VALUES (?,?,?)', ('2026-09-28','COMPLETED','{}'))
    with pytest.raises(RehearsalBlocked): rehearsal.decide('fake', 'YES', NOW)
    with pytest.raises(RehearsalBlocked): rehearsal.issue(None, None, None, None, NOW)


def test_risk_probe_is_not_a_card_and_rejects_stale_data(tmp_path):
    from agents.rehearsal import prepare, official_digest
    official, config = source(tmp_path)
    before = official_digest(official.path)
    rehearsal = prepare(official.path, tmp_path / 'rehearsal', config)
    p = make_proposal(quantity=Decimal('.49'))
    quote = Quote(ticker='VTI',bid=Decimal('100'),ask=Decimal('100.2'),timestamp=NOW-timedelta(minutes=5))
    result = rehearsal.evaluate_proposal(p, quote, Decimal('.20'), NOW, NOW)
    assert result['status'] == 'RISK_BLOCKED'
    assert 'stale_quote' in result['reasons']
    assert 'card_id' not in result
    assert official_digest(official.path) == before


def test_newer_data_does_not_override_official_stop(tmp_path):
    from agents.rehearsal import prepare, RehearsalBlocked
    official, config = source(tmp_path)
    (official.path.parent / 'STOP_TRADING').write_text('operator pause')
    with pytest.raises(RehearsalBlocked, match='OFFICIAL_SAFETY_STOP'):
        prepare(official.path, tmp_path / 'rehearsal', config)


def test_order_history_never_enters_public_rehearsal_report():
    from agents.rehearsal import public_report
    result = public_report({'status':'COMPLETED','data_mode':'whatif',
        'account_last4':'1234','decision':{'reason':'Account 1234 holds 99 shares'},
        'collector_evidence':{'raw_orders':[{'id':'private'}]}, 'quote_count':14})
    assert '1234' not in json.dumps(result) and 'private' not in json.dumps(result)
    assert result['quote_count'] == 14


def test_rehearsal_connection_cannot_attach_official_database(tmp_path):
    from agents.rehearsal import prepare
    official, config = source(tmp_path)
    rehearsal = prepare(official.path, tmp_path/'rehearsal', config)
    with rehearsal.connect() as db:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute('ATTACH DATABASE ? AS official', (str(official.path),))
        with pytest.raises(sqlite3.DatabaseError):
            db.execute('DROP TRIGGER deny_fills_INSERT')


def test_stale_live_input_yields_operational_hold_without_models(tmp_path):
    from agents.rehearsal import prepare
    from agents.daily_cycle import FixtureReader, run_cycle
    official, config = source(tmp_path)
    rehearsal=prepare(official.path,tmp_path/'rehearsal',config)
    result=run_cycle(rehearsal,config,None,NOW,data_mode='whatif',
                     reader=FixtureReader(config,NOW-timedelta(minutes=5)),clock=lambda:NOW)
    assert result['decision']['type']=='HOLD_OPERATIONAL'
    assert result['quote_freshness']['stale_or_future']==1
    assert result['agents']==[]


def test_ai_needed_stops_before_uncertified_budget_call(tmp_path):
    from agents.rehearsal import prepare
    from agents.daily_cycle import FixtureReader,run_cycle
    official,config=source(tmp_path)
    state=official.state('A','agent_alone')
    state['positions']['VTI']={'quantity':'1','average_cost':'100','multiplier':1}
    state['marks']['VTI']='100'
    with official.connect() as db:
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',
                   (json.dumps(state),'A','agent_alone'))
    rehearsal=prepare(official.path,tmp_path/'rehearsal',config)
    result=run_cycle(rehearsal,config,None,NOW,data_mode='whatif',
                     reader=FixtureReader(config,NOW),clock=lambda:NOW)
    assert result['status']=='HOLD_OPERATIONAL'
    assert result['ai_gate']['blocker']=='REHEARSAL_MODEL_CAP_NOT_CERTIFIED'
    assert result['agents']==[] and result['api_cost_estimate_usd']=='0'


def test_explicit_diagnostic_waiver_runs_three_stages_without_business_writes(tmp_path):
    from agents.rehearsal import prepare, official_digest
    from agents.daily_cycle import FixtureReader, FixtureBridge, run_cycle
    official, config = source(tmp_path)
    state = official.state('A', 'agent_alone')
    state['positions']['VTI'] = {'quantity':'1','average_cost':'100','multiplier':1}
    state['marks']['VTI'] = '100'
    with official.connect() as db:
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',
                   (json.dumps(state),'A','agent_alone'))
    before = official_digest(official.path)
    rehearsal = prepare(official.path, tmp_path/'rehearsal', config)
    result = run_cycle(rehearsal, config, FixtureBridge(config, NOW), NOW,
        data_mode='whatif', reader=FixtureReader(config,NOW), clock=lambda:NOW,
        diagnostic_cap_waiver=True)
    assert result['status'] == 'COMPLETED'
    assert set(result['completed_stages']) == {'research','portfolio','critic'}
    assert result['diagnostic_noncompliant'] is True
    assert official_digest(official.path) == before
    with sqlite3.connect(rehearsal.path) as db:
        for table in ('daily_values','fills','cards','approval_inbox','cycle_runs','lessons'):
            assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_cap_waiver_cannot_be_used_for_official_run(tmp_path):
    from agents.daily_cycle import run_cycle
    official, config = source(tmp_path)
    with pytest.raises(ValueError, match='diagnostic'):
        run_cycle(official,config,None,NOW,diagnostic_cap_waiver=True)


def test_v15_preview_issues_desk_entry_only_into_disposable_sandbox(tmp_path, monkeypatch):
    from agents.rehearsal import prepare, official_digest, attach_desk_sandbox
    from agents.daily_cycle import FixtureReader, run_cycle
    import agents.etf_issuer as issuer
    from test_desk_cycle_integration import SIGNAL
    monkeypatch.setattr(issuer, 'LIQUIDITY_INTERIM_LIVE_SPREAD', True)
    monkeypatch.setattr('agents.daily_cycle.evaluate_daily_signals', lambda *a: {'signals': [SIGNAL], 'strategies': {}})
    official, config = source(tmp_path)
    before = official_digest(official.path)
    rehearsal = prepare(official.path, tmp_path / 'rehearsal', config)
    desk = attach_desk_sandbox(rehearsal, config, tmp_path / 'rehearsal')

    class Reader(FixtureReader):
        def collect(self, now, held):
            reads = super().collect(now, held)
            for r in reads:
                if r['tool'] == 'get_equity_historicals':
                    for item in r['data']['results']:
                        for b in item['bars']:
                            b['volume'] = '2000000'
            return reads

    class NoModel:
        def run(self, *args, **kwargs):
            raise AssertionError('ETF desk path must not invoke AI')
    result = run_cycle(rehearsal, config, NoModel(), NOW, data_mode='whatif', reader=Reader(config, NOW),
                       clock=lambda: NOW, desk_policy_enabled=True)
    assert result['decision']['type'] == 'DESK_ENTRY'
    assert {r['arm']: r['status'] for r in result['desk_results']} == {
        'agent_alone': 'filled', 'deterministic_no_ai': 'filled', 'with_approvals': 'PENDING'}
    assert [c['status'] for c in desk.cards()] == ['PENDING']
    assert official_digest(official.path) == before
    with sqlite3.connect(rehearsal.path) as db:
        assert db.execute('SELECT COUNT(*) FROM approval_inbox').fetchone()[0] == 0


def test_rehearsal_without_sandbox_never_issues_desk_entries(tmp_path, monkeypatch):
    from agents.rehearsal import prepare
    from agents.daily_cycle import FixtureReader, run_cycle
    from test_desk_cycle_integration import SIGNAL
    monkeypatch.setattr('agents.daily_cycle.evaluate_daily_signals', lambda *a: {'signals': [SIGNAL], 'strategies': {}})
    official, config = source(tmp_path)
    rehearsal = prepare(official.path, tmp_path / 'rehearsal', config)

    class NoModel:
        def run(self, *args, **kwargs):
            raise AssertionError('no model')
    result = run_cycle(rehearsal, config, NoModel(), NOW, data_mode='whatif',
                       reader=FixtureReader(config, NOW), clock=lambda: NOW, desk_policy_enabled=True)
    assert result['desk_results'] == []
