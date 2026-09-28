from datetime import datetime, timedelta, timezone
import pytest
from broker.read_contracts import READ_METHODS
from test_inbox_lanes import setup_runtime

READS = READ_METHODS

class Spy:
    def __init__(self, extra=None):
        from broker.read_gateway import SCHEMAS
        self.calls=[]
        self.inventory={'data':[{'name':'robinhood-trading','runtimeStatus':'connected','authStatus':'oAuth','tools':{k:{'inputSchema':v} for k,v in SCHEMAS.items()}}], 'nextCursor':None}
        if extra: self.inventory['data'] += [extra]
    def request(self, method, params, *, timeout):
        self.calls.append((method,params))
        if method=='mcpServerStatus/list': return self.inventory
        return {'content':[], 'structuredContent':{'data':{'accounts':[]}}}

def gateway(tmp_path, spy):
    from broker.read_gateway import ReadGateway
    _,cfg=setup_runtime(tmp_path)
    incidents=[]
    return ReadGateway(spy,cfg,incidents.append,lambda:datetime(2026,9,28,14,tzinfo=timezone.utc)),incidents

@pytest.mark.parametrize('tool',['place_equity_order','cancel_equity_order','exercise_option','transfer_money','review_equity_order','unknown_tool'])
def test_forbidden_call_never_reaches_upstream(tmp_path,tool):
    from broker.read_gateway import CapabilityError
    spy=Spy(); g,incidents=gateway(tmp_path,spy)
    with pytest.raises(CapabilityError): g.call(tool,{})
    assert spy.calls==[] and incidents

def test_exact_inventory_and_arguments(tmp_path):
    from broker.read_gateway import CapabilityError
    spy=Spy(); g,_=gateway(tmp_path,spy)
    with pytest.raises(CapabilityError): g.call('get_accounts',{})
    g.preflight('thread')
    for name,args in [('get_portfolio',{'account_number':'wrong'}),('get_equity_quotes',{'symbols':['BAD']}),('get_option_quotes',{'instrument_ids':['unknown']}),('get_accounts',{'url':'https://example.org'})]:
        before=len(spy.calls)
        with pytest.raises(CapabilityError): g.call(name,args)
        assert len(spy.calls)==before
    assert g.call('get_accounts',{})['data']=={'accounts':[]}

@pytest.mark.parametrize('mutation',['write','missing','schema','server','auth','cursor'])
def test_unexpected_inventory_fails_closed(tmp_path,mutation):
    from broker.read_gateway import CapabilityError
    spy=Spy(); g,incidents=gateway(tmp_path,spy)
    server=spy.inventory['data'][0]
    if mutation=='write': server['tools']['place_equity_order']={}
    if mutation=='missing': del server['tools']['get_accounts']
    if mutation=='schema': server['tools']['get_accounts']={'inputSchema':{'type':'object'}}
    if mutation=='server': spy.inventory['data'].append({'name':'other','tools':{},'runtimeStatus':'connected'})
    if mutation=='auth': server['authStatus']='notLoggedIn'
    if mutation=='cursor': spy.inventory['nextCursor']='repeat'
    with pytest.raises(CapabilityError): g.preflight('thread')
    assert incidents

def test_disabled_servers_have_no_executable_capabilities(tmp_path):
    spy=Spy({'name':'other','runtimeStatus':'disabled','tools':{}}); g,_=gateway(tmp_path,spy)
    assert g.preflight('thread')['tools']==sorted(READS)

def test_provider_payload_cannot_replace_observed_tool_identity(tmp_path):
    class Spoof(Spy):
        def request(self,method,params,*,timeout):
            if method=='mcpServer/tool/call': return {'structuredContent':{'tool':'get_accounts','arguments':{'fake':True},'data':{'results':[]}}}
            return super().request(method,params,timeout=timeout)
    g,_=gateway(tmp_path,Spoof()); g.preflight('thread')
    read=g.call('get_equity_quotes',{'symbols':['VTI']})
    assert read['tool']=='get_equity_quotes' and read['arguments']=={'symbols':['VTI']}


def test_historical_read_allows_signal_warmup_but_rejects_unbounded_ranges(tmp_path):
    from broker.read_gateway import CapabilityError
    now=datetime(2026,9,28,14,tzinfo=timezone.utc)
    spy=Spy(); g,_=gateway(tmp_path,spy); g.preflight('thread')
    base={'symbols':['VTI'],'end_time':now.isoformat(),'interval':'day',
          'bounds':'regular','adjustment_type':'split'}
    allowed={**base,'start_time':(now-timedelta(days=550)).isoformat()}
    assert g.call('get_equity_historicals',allowed)['tool']=='get_equity_historicals'
    before=len(spy.calls)
    with pytest.raises(CapabilityError):
        g.call('get_equity_historicals',{**base,'start_time':(now-timedelta(days=551)).isoformat()})
    assert len(spy.calls)==before
