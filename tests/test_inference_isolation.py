import pytest
from broker.base import BrokerError

def test_inference_rejects_even_read_only_broker_capabilities(tmp_path,monkeypatch):
    from agents.codex_bridge import CodexBridge
    def forbidden(*a,**k): raise AssertionError('Inference process must not start')
    monkeypatch.setattr('subprocess.run',forbidden)
    monkeypatch.setattr('subprocess.Popen',forbidden)
    with pytest.raises(BrokerError):
        CodexBridge(tmp_path/'costs.db').run('gpt-5.6-luna','test',{'type':'object'},read_tools=('get_accounts',))

def test_active_server_rejected_before_model_turn():
    from agents.isolated_session import verify_inference_inventory
    class Fake:
        def request(self,method,params,*,timeout):
            assert method=='mcpServerStatus/list'
            return {'data':[{'name':'unexpected','runtimeStatus':'connected','tools':{}}]}
    with pytest.raises(BrokerError): verify_inference_inventory(Fake(),'thread')

def test_action_events_are_rejected():
    from agents.isolated_session import collect_turn
    class Fake:
        notifications=[]
        def read_event(self,timeout):
            return {'method':'item/started','params':{'threadId':'t','turnId':'r','item':{'type':'mcpToolCall'}}}
    with pytest.raises(BrokerError): collect_turn(Fake(),'t','r')

def test_unexpected_notification_reports_only_sanitized_method():
    from agents.isolated_session import validate_notification
    with pytest.raises(BrokerError, match=r'unexpected/event$') as error:
        validate_notification({'method':'unexpected/event','params':{'secret':'never persist me'}})
    assert 'never persist me' not in str(error.value)
    with pytest.raises(BrokerError, match=r'<invalid>$'):
        validate_notification({'method':'bad method with spaces','params':{'secret':'never persist me'}})

def test_correlated_output_and_usage():
    from agents.isolated_session import collect_turn
    class Fake:
        notifications=[
            {'method':'item/completed','params':{'threadId':'t','turnId':'r','item':{'type':'agentMessage','text':'{"ok":true}'}}},
            {'method':'thread/tokenUsage/updated','params':{'threadId':'t','turnId':'r','tokenUsage':{'last':{'inputTokens':10,'cachedInputTokens':2,'outputTokens':3}}}},
            {'method':'turn/completed','params':{'threadId':'t','turn':{'id':'r','status':'completed','error':None}}},
        ]
    output,usage=collect_turn(Fake(),'t','r')
    assert output=={'ok':True} and usage['input_tokens']==10
