from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from broker.base import BrokerError
from agents.market_reader import LiveReader as LiveReaderImplementation


NOW = datetime(2026, 9, 28, 14, tzinfo=timezone.utc)


def test_history_collector_uses_verified_crypto_mapping_and_incremental_window():
    from agents.order_history import collect_histories

    calls = []
    def read(tool, args):
        calls.append((tool, args))
        return {'data': {'results' if tool == 'get_crypto_orders' else 'orders': [], 'next': None}}

    account = {'account_number': 'agentic', 'rhs_account_number': 'numeric-crypto', 'agentic_allowed': True}
    result = collect_histories(read, account, now=NOW, since=NOW-timedelta(minutes=5), tracked={})
    assert result == {'equity': [], 'option': [], 'crypto': []}
    assert len(calls) == 3
    assert calls[0][1] == {'account_number': 'agentic', 'created_at_gte': '2026-09-28T13:54:00+00:00'}
    assert calls[2][1] == {'rhs_account_number': 'numeric-crypto', 'created_at_gte': '2026-09-28T13:54:00+00:00'}


def test_history_collector_fails_closed_on_missing_crypto_mapping():
    from agents.order_history import collect_histories

    calls = []
    with pytest.raises(BrokerError, match='ORDER_HISTORY_ACCOUNT_UNVERIFIED'):
        collect_histories(lambda *a: calls.append(a),
                          {'account_number': 'agentic', 'agentic_allowed': True},
                          now=NOW, since=NOW, tracked={})
    assert calls == []


def test_history_collector_paginates_with_same_scope_and_rechecks_tracked_ids():
    from agents.order_history import collect_histories

    calls = []
    def read(tool, args):
        calls.append((tool, dict(args)))
        key = 'results' if tool == 'get_crypto_orders' else 'orders'
        if args.get('order_id'):
            return {'data': {key: [{'id': 'old', 'state': 'filled'}]}}
        if tool == 'get_equity_orders' and not args.get('cursor'):
            return {'data': {key: [{'id': 'new', 'state': 'queued'}], 'next': 'opaque'}}
        return {'data': {key: [], 'next': None}}

    account = {'account_number': 'agentic', 'rhs_account_number': 'numeric-crypto', 'agentic_allowed': True}
    histories = collect_histories(read, account, now=NOW, since=NOW,
                                 tracked={'equity': [{'id': 'old', 'state': 'queued'}]})
    assert {r['id'] for r in histories['equity']} == {'new', 'old'}
    assert ('get_equity_orders', {'account_number': 'agentic', 'order_id': 'old'}) in calls
    assert calls[1][1]['created_at_gte'] == calls[0][1]['created_at_gte']
    assert calls[1][1]['cursor'] == 'opaque'


@pytest.mark.parametrize('data', [{}, {'orders': None}, {'orders': [None]}])
def test_history_collector_does_not_treat_missing_data_as_no_orders(data):
    from agents.order_history import collect_histories

    with pytest.raises(BrokerError, match='ORDER_HISTORY_INCOMPLETE'):
        collect_histories(lambda *a: {'data': data},
                          {'account_number': 'agentic', 'rhs_account_number': 'crypto', 'agentic_allowed': True},
                          now=NOW, since=NOW, tracked={})


def test_empty_string_cursor_is_a_complete_final_page():
    from agents.order_history import collect_histories
    result=collect_histories(lambda *a: {'data': {'orders': [], 'next': ''}},
        {'account_number':'agentic','rhs_account_number':'crypto','agentic_allowed':True},
        now=NOW,since=None,tracked={})
    assert result=={'equity': [],'option': [],'crypto': []}


def test_exact_eleven_pins_and_default_deny():
    from broker.policy import Stage1ToolPolicy
    from broker.read_contracts import READ_METHODS,validate_schema_manifest
    approved={'get_accounts','get_portfolio','get_equity_positions','get_equity_quotes',
              'get_equity_historicals','get_option_chains','get_option_instruments',
              'get_option_quotes','get_equity_orders','get_option_orders','get_crypto_orders'}
    assert READ_METHODS==approved
    validate_schema_manifest()
    policy=Stage1ToolPolicy()
    for name in approved:
        assert policy.authorize(name)==name
    for name in ('get_crypto_positions','get_crypto_quotes','get_scans','place_equity_order',
                 'cancel_equity_order','exercise_option','replace_option_order','transfer',
                 'get_accounts_extra','mcp__robinhood_trading__get_accounts','unknown'):
        with pytest.raises(BrokerError,match='default-deny'):
            policy.authorize(name)


def test_runtime_schema_mutation_is_rejected(monkeypatch):
    from broker.read_contracts import SCHEMAS,validate_schema_manifest
    monkeypatch.setitem(SCHEMAS,'get_accounts',{'type':'object'})
    with pytest.raises(ValueError,match='schemas changed'):
        validate_schema_manifest()


def test_history_baseline_scans_all_pages_and_terminal_ids_are_rechecked():
    from agents.order_history import collect_histories
    calls = []
    def read(tool, args):
        calls.append((tool, args))
        return {'data': {'orders': [{'id': 'old', 'state': 'filled', 'price': '2'}] if args.get('order_id') else [], 'next': None}}
    account = {'account_number': 'agentic', 'rhs_account_number': 'crypto', 'agentic_allowed': True}
    collect_histories(read, account, now=NOW, since=None, tracked={})
    assert all('created_at_gte' not in args for _, args in calls)
    calls.clear()
    result = collect_histories(read, account, now=NOW, since=NOW,
                               tracked={'equity': [{'id': 'old', 'state': 'filled'}]})
    assert result['equity'][0]['price'] == '2'
    assert any(args.get('order_id') == 'old' for _, args in calls)


@pytest.mark.parametrize('mode', ['repeat', 'endless', 'missing_id'])
def test_history_partial_coverage_fails_closed(mode):
    from agents.order_history import collect_histories
    count = 0
    def read(tool, args):
        nonlocal count
        count += 1
        return {'data': {'orders': [], 'next': ('repeat' if mode == 'repeat' else str(count)) if mode != 'missing_id' else None}}
    with pytest.raises(BrokerError, match='ORDER_HISTORY_INCOMPLETE'):
        collect_histories(read, {'account_number': 'agentic', 'rhs_account_number': 'crypto', 'agentic_allowed': True},
                          now=NOW, since=NOW, tracked={'equity': [{'id': 'missing', 'state': 'filled'}]} if mode == 'missing_id' else {})
    assert count <= 20


@pytest.mark.parametrize('kind', ['equity', 'option', 'crypto'])
@pytest.mark.parametrize('field', ['quantity', 'price'])
def test_price_and_quantity_change_pages_and_latches(tmp_path, kind, field):
    from test_account_tripwire import evaluate
    from agents.account_tripwire import TripwireViolation
    import sqlite3
    path = tmp_path / 'agent.db'
    original = {'id': 'secret-order', 'state': 'filled', 'price': '1', 'quantity': '2'}
    evaluate(path, **{kind+'_orders': [original]})
    with pytest.raises(TripwireViolation):
        evaluate(path, **{kind+'_orders': [{**original, field: '3'}]})
    assert (tmp_path / 'INCIDENT_STOP').exists()
    with sqlite3.connect(path) as db:
        title, body = db.execute('SELECT title,body FROM notification_outbox').fetchone()
        assert 'secret-order' not in title + body


def test_order_payload_is_never_written_to_shared_evidence_cache(tmp_path):
    from broker.read_gateway import EffectiveReadGateway
    captured = []
    client = SimpleNamespace(call_read=lambda *args: {'structuredContent': {'data': {'orders': [{'id': 'secret'}]}}})
    gateway = EffectiveReadGateway(client, SimpleNamespace(), captured.append,
        evidence_cache=SimpleNamespace(put=captured.append), max_agentic_cash_usd=1200)
    gateway._read('get_equity_orders', {'account_number': 'agentic'})
    assert captured == []


def test_crypto_scope_comes_only_from_verified_account_mapping(tmp_path):
    from broker.read_gateway import CapabilityError, EffectiveReadGateway, SCHEMAS
    config = SimpleNamespace(risk=SimpleNamespace(agentic_account_id='agentic'))
    account = {'account_number': 'agentic', 'rhs_account_number': 'numeric-crypto', 'agentic_allowed': True}
    client = SimpleNamespace(
        list_remote_tools=lambda: [{'name': k, 'inputSchema': v} for k,v in SCHEMAS.items()],
        call_read=lambda tool,args: {'structuredContent': {'data': {'accounts': [account]} if tool=='get_accounts' else {'orders': []}}})
    gateway = EffectiveReadGateway(client,config,lambda code: None,max_agentic_cash_usd=1200)
    gateway.preflight(scope_path='provider_read_only_scope')
    gateway.call('get_crypto_orders', {'rhs_account_number': 'numeric-crypto'})
    with pytest.raises(CapabilityError):
        gateway.call('get_crypto_orders', {'rhs_account_number': config.risk.agentic_account_id})


def live_reader(tmp_path, read):
    reader = LiveReaderImplementation.__new__(LiveReaderImplementation)
    reader.path = tmp_path/'agent.db'
    reader.config = SimpleNamespace(risk=SimpleNamespace(agentic_account_id='agentic'),
        notifications=SimpleNamespace(dashboard_base_url='http://127.0.0.1:8765'))
    reader.max_agentic_cash_usd = 1200
    reader.evidence = {}
    market = [
        {'tool': 'get_accounts', 'data': {'accounts': [{'account_number': 'agentic', 'rhs_account_number': 'numeric-crypto', 'agentic_allowed': True}]}},
        {'tool': 'get_portfolio', 'data': {'cash': '500'}},
        {'tool': 'get_equity_positions', 'data': {'positions': []}},
    ]
    def broker_read(tool,args):
        for result in market:
            if result['tool']==tool:
                return result
        return read(tool,args)
    reader.gateway = SimpleNamespace(call=broker_read,rhs_account_number='numeric-crypto')
    reader.reader = SimpleNamespace(collect=lambda *args,**kwargs: list(market))
    return reader


@pytest.mark.parametrize('kind', ['equity', 'option', 'crypto'])
def test_live_monitor_history_stays_out_of_reads_and_pages_on_changed_class(tmp_path,kind):
    from agents.account_tripwire import TripwireViolation
    import sqlite3
    active = False
    def read(tool,args):
        return {'data': {'orders': [{'id':'secret-order','state':'queued','price':'2'}]
                         if active and tool==f'get_{kind}_orders' else [], 'next':None}}
    reader=live_reader(tmp_path,read)
    market=reader.collect(NOW,{})
    assert all(not row['tool'].endswith('_orders') for row in market)
    active=True
    with pytest.raises(TripwireViolation):
        reader.collect(NOW+timedelta(minutes=1),{})
    assert (tmp_path/'INCIDENT_STOP').exists()
    with sqlite3.connect(reader.path) as db:
        assert db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0]==1
        assert db.execute('SELECT checked_at FROM order_monitor_checkpoint').fetchone()[0]==NOW.isoformat()


def test_incomplete_live_monitor_pages_and_does_not_checkpoint(tmp_path):
    import sqlite3
    reader=live_reader(tmp_path,lambda *a: {'data': {}})
    with pytest.raises(BrokerError,match='ORDER_HISTORY_INCOMPLETE'):
        reader.collect(NOW,{})
    assert (tmp_path/'INCIDENT_STOP').exists()
    with sqlite3.connect(reader.path) as db:
        assert db.execute('SELECT COUNT(*) FROM order_monitor_checkpoint').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM notification_outbox').fetchone()[0]==1


def test_failing_market_discovery_cannot_suppress_order_tripwire(tmp_path):
    from agents.account_tripwire import TripwireViolation
    active=False
    def read(tool,args):
        return {'data': {'orders': [{'id':'unexpected','state':'queued'}] if active and tool=='get_equity_orders' else []}}
    reader=live_reader(tmp_path,read)
    reader.collect(NOW,{})
    active=True
    def failed_discovery(*args,**kwargs):
        raise RuntimeError('unrelated quote failure')
    reader.reader.collect=failed_discovery
    with pytest.raises(TripwireViolation):
        reader.collect(NOW+timedelta(minutes=1),{})
    assert (tmp_path/'INCIDENT_STOP').exists()


@pytest.mark.parametrize('tool', ['get_accounts','get_portfolio','get_equity_positions'])
def test_required_snapshot_failure_pages_before_discovery(tmp_path,tool):
    reader=live_reader(tmp_path,lambda *a: {'data': {'orders': []}})
    original=reader.gateway.call
    reader.gateway.call=lambda name,args: {'data': {}} if name==tool else original(name,args)
    with pytest.raises(BrokerError):
        reader.collect(NOW,{})
    assert (tmp_path/'INCIDENT_STOP').exists()
