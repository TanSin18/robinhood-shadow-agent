import json
import sqlite3
from datetime import datetime,timezone
import pytest
from test_inbox_lanes import setup_runtime

NOW=datetime(2026,9,28,14,tzinfo=timezone.utc)

def test_failed_incident_db_write_cannot_make_pause_resumable(tmp_path,monkeypatch):
    from agents.dashboard import set_paused
    from agents import safety_events
    inbox,_=setup_runtime(tmp_path); set_paused(inbox,'pause')
    marker=(tmp_path/'STOP_TRADING').read_bytes()
    original=sqlite3.connect
    def failed(*args,**kwargs): raise sqlite3.OperationalError('database is locked')
    with monkeypatch.context() as m:
        m.setattr(safety_events.sqlite3,'connect',failed)
        with pytest.raises(sqlite3.OperationalError): safety_events.record_incident(inbox.path,'UNEXPECTED_CAPABILITY',now=NOW)
    assert (tmp_path/'STOP_TRADING').read_bytes()==marker
    with pytest.raises(ValueError,match='incident'): set_paused(inbox,'resume')
    assert safety_events.safety_stopped(inbox.path)

def test_ambiguous_activity_not_overruled_by_one_fixture_marker(tmp_path):
    from data.database_role import require_database_role,DatabaseRoleError
    inbox,_=setup_runtime(tmp_path)
    inbox.store.append_json('run_states',{'data_mode':'fixture'})
    with inbox.connect() as db: db.execute('INSERT INTO cycle_runs VALUES (?,?,?)',('2026-09-28','STARTED','{}'))
    with pytest.raises(DatabaseRoleError): require_database_role(inbox.path,'fixture')

@pytest.mark.parametrize('method',['mcpServer/startupStatus/updated','app/list/updated','unknown/newAction'])
def test_dynamic_capability_notification_blocks_inference(method):
    from agents.isolated_session import collect_turn
    from broker.base import BrokerError
    class Fake:
        notifications=[{'method':method,'params':{'name':'unexpected','status':'ready'}},
            {'method':'item/completed','params':{'threadId':'t','turnId':'r','item':{'type':'agentMessage','text':'{}'}}},
            {'method':'thread/tokenUsage/updated','params':{'threadId':'t','turnId':'r','tokenUsage':{'last':{'inputTokens':1,'cachedInputTokens':0,'outputTokens':1}}}},
            {'method':'turn/completed','params':{'threadId':'t','turn':{'id':'r','status':'completed'}}}]
    with pytest.raises(BrokerError): collect_turn(Fake(),'t','r')

def test_dynamic_collector_server_never_reaches_tool_dispatch(tmp_path):
    from test_read_gateway import Spy,gateway
    from broker.base import BrokerError
    spy=Spy(); spy.notifications=[]
    g,_=gateway(tmp_path,spy); g.preflight('thread')
    spy.notifications.append({'method':'mcpServer/startupStatus/updated','params':{'name':'unexpected','status':'ready'}})
    before=len(spy.calls)
    with pytest.raises(BrokerError): g.call('get_accounts',{})
    assert not any(method=='mcpServer/tool/call' for method,params in spy.calls[before:])

def test_missing_event_identity_is_not_correlated():
    from agents.isolated_session import collect_turn
    from broker.base import BrokerError
    class Fake:
        notifications=[{'method':'item/completed','params':{'item':{'type':'agentMessage','text':'{}'}}}]
    with pytest.raises(BrokerError): collect_turn(Fake(),'t','r')

def test_expired_option_settles_before_current_quote_requirement(tmp_path):
    from datetime import date
    from decimal import Decimal as D
    from agents.daily_cycle import FixtureBridge,FixtureReader,run_cycle
    from broker.models import Quote
    from data.database_role import require_database_role
    from test_risk_engine import make_proposal,NOW as ISSUED
    inbox,cfg=setup_runtime(tmp_path); require_database_role(inbox.path,'fixture')
    proposal=make_proposal(ticker='AAPL-C',asset_class='option',quantity=D(1),limit_price=D('.20'),multiplier=100,underlying_ticker='AAPL',option_strategy='long_call',max_loss_usd=D(20),option_type='call',strike=D(250),expiry=date(2026,10,2))
    inbox.issue(proposal,Quote(ticker='AAPL-C',bid=D('.199'),ask=D('.20'),timestamp=ISSUED),D('.20'),ISSUED,ISSUED)
    after=datetime(2026,10,5,14,tzinfo=timezone.utc)
    class Reader(FixtureReader):
        def collect(self,*args):
            reads=super().collect(*args)
            reads.append({'tool':'get_equity_historicals','data':{'results':[{'symbol':'AAPL','bars':[{'begins_at':'2026-10-02T13:30:00+00:00','close_price':'251'}]}]}})
            return reads
    result=run_cycle(inbox,cfg,FixtureBridge(cfg,after),after,data_mode='fixture',reader=Reader(cfg,after))
    assert result['status']=='COMPLETED'
    assert inbox.state('B','agent_alone')['positions']=={}
    assert D(inbox.state('B','agent_alone')['settled_cash'])==580
