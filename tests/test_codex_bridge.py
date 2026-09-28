import json
from datetime import datetime, timezone
from decimal import Decimal

import pytest


def test_bridge_blocks_writes_before_process(tmp_path):
    from agents.codex_bridge import CodexBridge
    from broker.base import BrokerError
    bridge = CodexBridge(tmp_path / 'runs.db')
    with pytest.raises(BrokerError):
        bridge.command('gpt-5.6-luna', tmp_path / 'schema.json', ['place_equity_order'])


def test_transport_uses_only_explicit_capabilities(tmp_path):
    from agents.codex_bridge import CodexBridge
    bridge = CodexBridge(tmp_path / 'runs.db')
    from broker.base import BrokerError
    with pytest.raises(BrokerError): bridge.command('gpt-5.6-luna',tmp_path/'schema.json',['get_accounts'])
    args = bridge.command('gpt-5.6-luna', tmp_path / 'schema.json', [])
    assert 'app-server' in args and '--strict-config' in args
    assert 'features.shell_tool=false' in args
    decisions = bridge.command('gpt-5.6-terra', tmp_path / 'schema.json', [])
    assert 'mcp_servers.robinhood-trading.enabled=false' in decisions
    assert 'web_search="disabled"' in decisions


def test_raw_mcp_event_is_authority_and_usage_is_persisted(tmp_path):
    from agents.codex_bridge import CodexBridge
    bridge = CodexBridge(tmp_path / 'runs.db')
    events = [
        {'type':'item.completed','item': {'type':'mcp_tool_call','server':'robinhood-trading','tool':'get_equity_quotes','status':'completed','arguments':{'symbols':['VTI']},'result':{'structured_content':{'data':{'results':[{'symbol':'VTI'}]}}}}},
        {'type':'item.completed','item':{'type':'agent_message','text':'{"ok":true}'}},
        {'type':'turn.completed','usage':{'input_tokens':1000,'cached_input_tokens':0,'output_tokens':100}},
    ]
    from broker.base import BrokerError
    with pytest.raises(BrokerError): bridge.parse('\n'.join(map(json.dumps,events)),['get_equity_quotes'])
    with pytest.raises(BrokerError): bridge.parse('\n'.join(map(json.dumps,events)),[])
    result=bridge.parse('\n'.join(map(json.dumps,events[1:])),[])
    assert result.output=={'ok':True} and result.reads==[]
    assert result.usage['input_tokens'] == 1000


def test_budget_survives_restart_and_reserves_atomically(tmp_path):
    from agents.codex_bridge import CostLedger
    now = datetime(2026,9,28,14,tzinfo=timezone.utc)
    ledger = CostLedger(tmp_path/'runs.db', Decimal('.40'))
    key = ledger.reserve(now, Decimal('.30'))
    with pytest.raises(ValueError, match='budget'):
        CostLedger(tmp_path/'runs.db', Decimal('.40')).reserve(now, Decimal('.11'))
    ledger.finish(key, Decimal('.10'), {'model':'test'})
    assert CostLedger(tmp_path/'runs.db', Decimal('.40')).reserve(now, Decimal('.30'))


def test_bridge_rejects_missing_usage_and_fabricated_success(tmp_path):
    from agents.codex_bridge import CodexBridge
    bridge = CodexBridge(tmp_path/'runs.db')
    with pytest.raises(ValueError):
        bridge.parse('{"type":"item.completed","item":{"type":"agent_message","text":"{\\"connected\\":true}"}}', [])
def test_unknown_model_fails_before_any_process(tmp_path):
    from agents.codex_bridge import CodexBridge
    import pytest
    with pytest.raises(ValueError,match='pricing'):
        CodexBridge(tmp_path/'cost.db').run('unknown','prompt',{})
