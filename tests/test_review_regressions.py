import json
from datetime import datetime, timedelta, timezone, date
from decimal import Decimal as D
from zoneinfo import ZoneInfo

from agents.daily_cycle import FixtureBridge, run_cycle, market_snapshot, apply_decision, Decision, Critique
from broker.models import Quote
from test_inbox_lanes import setup_runtime, issue
from test_risk_engine import make_proposal, NOW

MONDAY=datetime(2026,9,28,14,tzinfo=timezone.utc)


class CapturingBridge(FixtureBridge):
    def __init__(self,config,now,hold=False):
        super().__init__(config,now)
        self.requests=[]
        self.hold=hold
        self.refreshes=0

    def run(self,model,instructions,schema,**kwargs):
        if 'refreshed' in schema.get('properties',{}):
            from agents.codex_bridge import BridgeResult
            self.refreshes+=1
            quote={'symbol':'VTI','bid_price':'100','ask_price':'100.20','venue_bid_time':(MONDAY+timedelta(seconds=90)).isoformat(),'venue_ask_time':(MONDAY+timedelta(seconds=90)).isoformat()}
            return BridgeResult({'refreshed':True},[{'tool':'get_equity_quotes','data':{'results':[{'quote':quote}]}}],{'input_tokens':0,'output_tokens':0},['get_equity_quotes'])
        request=json.loads(instructions.rsplit('\n',1)[-1])
        if isinstance(request,list):
            request=json.loads(request[0]['content'])
        self.requests.append(request)
        result=super().run(model,instructions,schema,**kwargs)
        if self.hold and self.index==2:
            result.output['picks']=[]
        return result


def test_quote_retrieved_after_cycle_start_is_eligible(tmp_path):
    inbox,config=setup_runtime(tmp_path)
    bridge=CapturingBridge(config,MONDAY+timedelta(seconds=5))
    from agents.daily_cycle import FixtureReader
    run_cycle(inbox,config,bridge,MONDAY,data_mode='fixture',reader=FixtureReader(config,MONDAY+timedelta(seconds=5)),clock=lambda:MONDAY+timedelta(seconds=10))
    assert bridge.requests[1]['eligible_instruments']==['VTI']
    assert bridge.requests[1]['candidates'][0]['instrument']=='VTI'
    assert bridge.requests[0]['strategy_assessment']['signals'][0]['instrument']=='VTI'
    assert bridge.requests[1]['strategy_signals'][0]['strategy']=='momentum_rotation_126d_trend200_top1'


def test_daily_cycle_enforces_strategy_signal_before_paper_proposal(tmp_path):
    inbox,config=setup_runtime(tmp_path)
    quote=Quote(ticker='VTI',bid=D(100),ask=D('100.20'),timestamp=MONDAY)
    snapshot={'contracts':{},'quotes':{'VTI':quote},'vols':{'VTI':(D('.20'),MONDAY)}}
    decision=Decision(picks=[{'instrument':'VTI','side':'buy','thesis':'Model-only idea.',
                              'good_if':'Price rises.','invalidation':'Price falls.','confidence':.8}],
                      reason='Buy without a deterministic signal.')
    results=apply_decision(
        inbox,config,decision,
        Critique(counterargument='Could fall.',rejected_instruments=[]),
        snapshot,MONDAY,'signal-gate',strategy_signals={})
    assert results == [{'status':'REJECTED_NO_STRATEGY_SIGNAL','instrument':'VTI'}]
    assert inbox.cards() == []


def test_hold_still_refreshes_held_position_marks(tmp_path):
    inbox,config=setup_runtime(tmp_path)
    from data.database_role import require_database_role
    require_database_role(inbox.path,'fixture')
    issue(inbox)
    bridge=CapturingBridge(config,MONDAY,hold=True)
    times=iter([MONDAY+timedelta(seconds=5),MONDAY+timedelta(seconds=90),MONDAY+timedelta(seconds=90)])
    from agents.daily_cycle import FixtureReader
    reader=FixtureReader(config,MONDAY)
    run_cycle(inbox,config,bridge,MONDAY,data_mode='fixture',reader=reader,clock=lambda:next(times))
    assert reader.refreshes==1 and bridge.refreshes==0
    values=[v for v in inbox.store.read_json('daily_values') if v.get('lane')=='A' and v.get('track')=='agent_alone']
    assert values[-1]['value'] is not None


def test_held_contract_with_under_seven_days_is_retained(tmp_path):
    inbox,config=setup_runtime(tmp_path)
    raw=FixtureBridge(config,MONDAY).run('', '', {})
    contract={'id':'held-id','chain_symbol':'AAPL','expiration_date':'2026-10-02','strike_price':'250','type':'call','state':'active','tradability':'tradable','trade_value_multiplier':'100'}
    snapshot=market_snapshot(raw.reads,config,MONDAY,held_contracts={'held-id':contract})
    assert snapshot['contracts']['held-id']['expiration_date']=='2026-10-02'


def test_held_closing_option_can_sell_without_volatility(tmp_path):
    inbox,config=setup_runtime(tmp_path)
    p=make_proposal(ticker='held-id',asset_class='option',quantity=D(1),limit_price=D('.20'),multiplier=100,underlying_ticker='AAPL',option_strategy='long_call',max_loss_usd=D(20),option_type='call',strike=D(250),expiry=date(2026,10,2))
    inbox.issue(p,Quote(ticker=p.ticker,bid=D('.199'),ask=D('.20'),timestamp=NOW),D('.20'),NOW,NOW)
    contract={'id':'held-id','chain_symbol':'AAPL','expiration_date':'2026-10-02','strike_price':'250','type':'call','trade_value_multiplier':'100'}
    snapshot={'contracts':{'held-id':contract},'quotes':{'held-id':Quote(ticker='held-id',bid=D('.199'),ask=D('.20'),timestamp=MONDAY)},'vols':{}}
    decision=Decision(picks=[{'instrument':'held-id','side':'sell','thesis':'Close risk.','good_if':'Risk falls.','invalidation':'Quote stale.','confidence':.5}],reason='Close')
    result=apply_decision(inbox,config,decision,Critique(counterargument='Price could rise.',rejected_instruments=[]),snapshot,MONDAY,'close-1')
    assert result[0]['status']=='PENDING'
    assert inbox.state('B','agent_alone')['positions']=={}


def test_yes_records_same_counterfactual_mark_as_agent_alone(tmp_path):
    inbox,_=setup_runtime(tmp_path)
    card=issue(inbox)
    inbox.mark_accounts({'VTI':Quote(ticker='VTI',bid=D(100),ask=D('100.2'),timestamp=NOW)},NOW,'fixture')
    inbox.decide(card['id'],'YES',NOW+timedelta(minutes=1))
    values=[v for v in inbox.store.read_json('daily_values') if v.get('lane')=='A']
    approved=[v for v in values if v['track']=='with_approvals'][-1]
    agent=[v for v in values if v['track']=='agent_alone'][-1]
    assert D(approved['value'])==D(agent['value'])


def test_weekly_catches_up_monday_without_backfilling_before_inception(tmp_path):
    from eval.weekly import report_if_due
    inbox,_=setup_runtime(tmp_path)
    et=ZoneInfo('America/New_York')
    with inbox.connect() as db:
        db.execute('INSERT INTO cycle_runs VALUES (?,?,?)',('2026-09-28','COMPLETED','{}'))
    report=report_if_due(inbox,datetime(2026,10,5,9,tzinfo=et),tmp_path/'reports')
    assert report is not None and '2026-10-02' in report.name
    assert report_if_due(inbox,datetime(2026,10,6,9,tzinfo=et),tmp_path/'reports') is None
