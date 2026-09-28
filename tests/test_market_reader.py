from datetime import datetime,timezone
from decimal import Decimal
from agents.market_reader import LiveReader as DirectLiveReader
from test_inbox_lanes import setup_runtime


def test_live_reader_uses_local_proxy_client_not_codex_session(tmp_path):
    from broker.read_gateway import SCHEMAS

    _, config = setup_runtime(tmp_path)

    class Tool:
        def __init__(self, name, input_schema):
            self.name = name
            self.inputSchema = input_schema

    class Client:
        def __init__(self):
            self.opened = False
            self.closed = False
            self.calls = []
        def open(self):
            self.opened = True
        def authorization_evidence(self):
            return {
                'selected_path': 'full_scope_bounded_cash_fallback',
                'granted_scope_names': ['internal'],
                'keychain_retrieval': 'available',
            }
        def list_remote_tools(self):
            return [Tool(name, schema) for name, schema in SCHEMAS.items()]
        def call_read(self, name, arguments):
            self.calls.append((name, arguments))
            if name == 'get_accounts':
                data = {'accounts': [{
                    'account_number': config.risk.agentic_account_id,
                    'agentic_allowed': True,
                    'unsettled_funds': '0',
                }]}
            elif name == 'get_portfolio':
                data = {
                    'cash': '500',
                    'pending_deposits': '0',
                    'buying_power': {
                        'buying_power': '500',
                        'unleveraged_buying_power': '500',
                    },
                }
            else:
                data = {}
            return {'structuredContent': {'data': data}}
        def close(self): self.closed = True

    client = Client()
    reader = DirectLiveReader(tmp_path / 'agent.db', config, client=client)
    try:
        assert client.opened is True
        assert reader.evidence['selected_path'] == 'full_scope_bounded_cash_fallback'
        assert reader.evidence['account_bounds']['status'] == 'VERIFIED'
        assert reader.evidence['effective_write_tool_count'] == 0
    finally:
        reader.close()
    assert client.closed is True


def test_live_reader_refuses_codex_auth_fallback(tmp_path):
    import pytest
    from broker.base import BrokerError

    _, config = setup_runtime(tmp_path)
    with pytest.raises(BrokerError, match='Codex-session Robinhood authentication is disabled'):
        DirectLiveReader(tmp_path / 'agent.db', config, executable='/usr/bin/false')


def test_live_reader_tripwire_checks_positions_and_all_order_histories(tmp_path):
    import pytest
    from agents.account_tripwire import TripwireViolation

    _, config = setup_runtime(tmp_path)
    reader = DirectLiveReader.__new__(DirectLiveReader)
    reader.path = tmp_path / 'agent.db'
    reader.config = config
    reader.max_agentic_cash_usd = Decimal('1200')
    base_reads = [
        {'tool': 'get_accounts', 'data': {'accounts': [{
            'account_number': config.risk.agentic_account_id,
            'rhs_account_number': 'numeric-crypto', 'agentic_allowed': True}]}},
        {'tool': 'get_portfolio', 'data': {'cash': '500'}},
        {'tool': 'get_equity_positions', 'data': {'positions': []}},
    ]
    reader.reader = type('Reader', (), {'collect': lambda _self, _now, _held, **kwargs: list(base_reads)})()

    class Gateway:
        changed = False
        rhs_account_number = 'numeric-crypto'
        def call(self, tool, arguments):
            del arguments
            for result in base_reads:
                if result['tool']==tool:
                    return result
            orders = ([{'id': 'unexpected-order', 'state': 'queued'}]
                      if self.changed and tool == 'get_equity_orders' else [])
            return {'tool': tool, 'data': {'orders': orders}}

    reader.gateway = Gateway()
    reader.evidence = {}
    now = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
    reader.collect(now, {})
    reader.gateway.changed = True

    with pytest.raises(TripwireViolation, match='AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE'):
        reader.collect(now, {})

def test_refresh_is_quote_only_and_bounded(tmp_path):
    from agents.market_reader import MarketReader
    _,config=setup_runtime(tmp_path)
    class Gateway:
        def call(self,tool,args):
            assert tool in {'get_equity_quotes','get_option_quotes'}
            assert max(map(len,args.values()))<=20
            return {'tool':tool}
    reader=MarketReader(Gateway(),config)
    assert [r['tool'] for r in reader.refresh(datetime.now(timezone.utc),['VTI'],[])]==['get_equity_quotes']

def test_collector_checks_account_before_more_reads(tmp_path):
    import pytest
    from agents.market_reader import MarketReader
    from broker.base import BrokerError
    _,config=setup_runtime(tmp_path)
    class Gateway:
        def call(self,tool,args):
            assert tool=='get_accounts'
            return {'tool':tool,'data':{'accounts':[{'account_number':'wrong','agentic_allowed':True}]}}
    with pytest.raises(BrokerError): MarketReader(Gateway(),config).collect(datetime.now(timezone.utc),{})


def test_collector_requests_enough_history_for_252_day_momentum(tmp_path):
    from agents.market_reader import MarketReader
    _, config = setup_runtime(tmp_path)
    calls = []

    class Gateway:
        def call(self, tool, args):
            calls.append((tool, args))
            if tool == 'get_accounts':
                return {'tool': tool, 'data': {'accounts': [
                    {'account_number': config.risk.agentic_account_id, 'agentic_allowed': True}]}}
            if tool == 'get_option_chains':
                return {'tool': tool, 'data': {'chains': []}}
            if tool == 'get_equity_quotes':
                return {'tool': tool, 'data': {'results': []}}
            if tool == 'get_equity_historicals':
                return {'tool': tool, 'data': {'results': []}}
            return {'tool': tool, 'data': {}}

    now = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)
    MarketReader(Gateway(), config).collect(now, {})
    historical = [args for tool, args in calls if tool == 'get_equity_historicals']
    assert historical
    assert all((now - datetime.fromisoformat(args['start_time'])).days >= 550 for args in historical)
