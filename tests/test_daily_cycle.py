from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from test_inbox_lanes import setup_runtime


def test_portfolio_schema_has_no_provider_unsupported_decimal_regex():
    import json
    from agents.daily_cycle import Decision
    from agents.agent_output import AgentOutputSchema
    assert '(?' not in json.dumps(AgentOutputSchema(Decision).json_schema())


def test_realized_vol_requires_twenty_returns_and_excludes_interpolated_bars():
    from agents.daily_cycle import realized_volatility
    bars=[{'begins_at':(datetime(2026,8,1,tzinfo=timezone.utc)+timedelta(days=i)).isoformat(),'close_price':str(100+i+(i%2)),'interpolated':False} for i in range(21)]
    assert D(0) < realized_volatility(bars) < D(1)
    bars[-1]['interpolated']=True
    assert realized_volatility(bars) is None


def test_agent_candidate_packet_excludes_unranked_option_catalog_noise():
    from agents.daily_cycle import agent_candidate_packet
    choices=[
        {'instrument':'VTI','contract':None},
        {'instrument':'chosen-call','contract':{'type':'call'}},
        {'instrument':'catalog-noise','contract':{'type':'call'}},
        {'instrument':'held-option','contract':{'type':'put'}},
    ]
    packet=agent_candidate_packet(choices,{'VTI':{},'chosen-call':{}},{'held-option'})
    assert [item['instrument'] for item in packet]==['VTI','chosen-call','held-option']


def test_once_per_trading_day_scheduler_and_intraday_code_only(tmp_path):
    from agents.daily_cycle import claim_daily_cycle
    inbox,_=setup_runtime(tmp_path)
    et=ZoneInfo('America/New_York')
    assert not claim_daily_cycle(inbox,datetime(2026,9,28,9,59,tzinfo=et))
    assert claim_daily_cycle(inbox,datetime(2026,9,28,10,0,tzinfo=et))
    assert not claim_daily_cycle(inbox,datetime(2026,9,28,10,0,tzinfo=et))
    assert not claim_daily_cycle(inbox,datetime(2026,9,28,14,30,tzinfo=et))
    assert not claim_daily_cycle(inbox,datetime(2026,11,26,10,0,tzinfo=et))


def test_complete_fixture_cycle_uses_three_agents_and_creates_pending_card(tmp_path):
    from agents.daily_cycle import run_fixture_cycle
    inbox,config=setup_runtime(tmp_path)
    result=run_fixture_cycle(inbox,config,datetime(2026,9,28,14,tzinfo=timezone.utc))
    assert result['agents']==['Research Agent','Portfolio Agent','Critic']
    assert result['data_mode']=='fixture'
    assert result['status']=='COMPLETED'
    assert result['strategy_assessment']['signals'][0]['instrument']=='VTI'
    assert result['strategy_assessment']['qualification']=='DAILY_SHADOW_SIGNAL_ONLY'
    assert inbox.cards()[0]['status']=='PENDING'
    assert D(inbox.state('A','with_approvals')['settled_cash'])==500
    activity = [event for event in inbox.store.read_json('local_traces')
                if event.get('trace_id') == result['cycle_id']]
    assert [event['event'] for event in activity] == [
        'cycle_started', 'data_collected', 'strategy_evaluated',
        'stage_started', 'stage_completed',
        'stage_started', 'stage_completed',
        'stage_started', 'stage_completed',
        'final_refresh', 'risk_evaluated', 'cycle_terminal',
    ]
    assert all(event.get('timestamp') for event in activity)
    assert activity[1]['quote_count'] > 0
    assert activity[2]['signals'][0]['instrument'] == 'VTI'


def test_fixture_trace_records_candidate_states_and_deterministic_risk(tmp_path):
    from agents.daily_cycle import run_fixture_cycle

    inbox, config = setup_runtime(tmp_path)
    result = run_fixture_cycle(
        inbox,
        config,
        datetime(2026, 9, 28, 14, tzinfo=timezone.utc),
    )
    events = [
        event
        for event in inbox.store.read_json('local_traces')
        if event.get('trace_id') == result['cycle_id']
    ]
    risk = next(event for event in events if event['event'] == 'risk_evaluated')
    decisions = [
        decision
        for event in events
        for decision in event.get('candidate_decisions', [])
    ]

    assert any(
        item['instrument'] == 'VTI'
        and item['lane'] == 'A'
        and item['state'] == 'proposed'
        for item in decisions
    )
    assert risk['real_execution'] == 'blocked'
    assert all(item['lane'] in {'A', 'B'} for item in decisions)
    assert all('reason_code' in item and 'reason' in item for item in decisions)


def test_prose_symbol_does_not_become_candidate_decision():
    from agents.daily_cycle import candidate_decisions

    rows = candidate_decisions(
        [],
        {},
        {'compared_symbols': []},
        {'picks': [], 'reason': 'VTI sounds interesting'},
        {'rejected_instruments': [], 'counterargument': 'META may reverse'},
        [],
        [],
    )

    assert rows == []


def test_weekly_report_runs_once_with_history_and_no_model_calls(tmp_path):
    from eval.weekly import report_if_due
    inbox,_=setup_runtime(tmp_path)
    et=ZoneInfo('America/New_York')
    assert report_if_due(inbox,datetime(2026,10,2,16,29,tzinfo=et),tmp_path/'reports') is None
    report=report_if_due(inbox,datetime(2026,10,2,16,30,tzinfo=et),tmp_path/'reports')
    assert report.exists()
    assert 'No completed cycles' in report.read_text()
    assert 'unavailable' in report.read_text()
    assert report_if_due(inbox,datetime(2026,10,3,12,tzinfo=et),tmp_path/'reports') is None


def test_weekly_report_does_not_backfill_before_first_cycle(tmp_path):
    from eval.weekly import report_if_due
    inbox,_=setup_runtime(tmp_path)
    with inbox.connect() as db:
        db.execute('INSERT INTO cycle_runs VALUES (?,?,?)',('2026-09-27','COMPLETED','{}'))
    assert report_if_due(inbox,datetime(2026,9,27,22,tzinfo=timezone.utc),tmp_path/'reports') is None


def test_daily_schedule_tracks_eastern_time_across_dst(tmp_path):
    from agents.daily_cycle import claim_daily_cycle
    inbox, _ = setup_runtime(tmp_path)
    assert not claim_daily_cycle(inbox, datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc))
    assert claim_daily_cycle(inbox, datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc))
    assert not claim_daily_cycle(inbox, datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc))
    assert claim_daily_cycle(inbox, datetime(2027, 3, 15, 14, 0, tzinfo=timezone.utc))
