import json
import sqlite3
from decimal import Decimal as D
import pytest
from test_bounded_inference import Client, MODELS, SCHEMA, bridge
from test_phase0_budget import NOW


def test_attempts_have_unique_ids_and_uncertain_bound_is_allocated(tmp_path):
    c = Client()
    b = bridge(tmp_path, c)
    b.set_cost_context({'A': [{'instrument': 'SOXX', 'lane': 'A'}]})
    b.run(MODELS[0], 'frozen packet', SCHEMA)
    c.fail = True
    with pytest.raises(ValueError, match='MODEL_REQUEST_FAILED'):
        b.run(MODELS[0], 'repair packet', SCHEMA)
    rows = b.allocation_records()
    assert len(rows) == 2
    assert len({r['attempt_id'] for r in rows}) == 2
    assert {k:D(v) for k,v in rows[0]['allocations'].items()} == {'A': D('0.0000825')}
    assert D(rows[1]['allocations']['A']) == D('.0123')
    assert rows[1]['cost_basis'] == 'uncertain_reserved_bound'
    assert all(r['weight_basis'] == 'input_tokens_only' for r in rows)
    assert all(r['role'] == 'research' for r in rows)
    b.close()


def test_schema_failed_attempt_is_charged_separately_from_repair(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':[{'instrument':'AAPL','lane':'A'}]})
    c.response.output_text='{"ok":"invalid"}'
    with pytest.raises(ValueError,match='MODEL_SCHEMA_INVALID'):
        b.run(MODELS[0],'dossier',SCHEMA)
    c.response.output_text='{"ok":true}'
    b.run(MODELS[0],'dossier repair',SCHEMA)
    rows=b.allocation_records()
    assert len(rows)==2 and sum(D(r['cost_usd']) for r in rows)==D('.000165')
    b.close()


def test_failed_settlement_rolls_back_all_lanes(tmp_path):
    from agents.budget import BudgetAllocator, BudgetUnavailable
    a=BudgetAllocator(tmp_path/'budget.db')
    reservations=[{'id':a.reserve(NOW,lane=l,stage='research',amount=D('.03')),'lane':l,'stage':'research'} for l in ('A','B')]
    with pytest.raises(BudgetUnavailable):
        a.settle_attempts('bad',reservations,[dict(role='research',attempt_id='1',allocations={'A':'.01','B':'.04'})])
    with sqlite3.connect(a.path) as db:
        assert db.execute('SELECT count(*) FROM ai_budget_reservations WHERE settled=1').fetchone()[0]==0


def test_context_cannot_be_empty_or_contain_unknown_lane(tmp_path):
    b=bridge(tmp_path,Client())
    for context in ({},{'A':[]},{'C':[{}]}):
        with pytest.raises(ValueError,match='INVALID_COST_CONTEXT'):
            b.set_cost_context(context)
    b.close()


def test_each_stage_counts_its_own_common_content_not_reference_subtraction(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':[{'instrument':'AAPL'}],'B':[{'instrument':'OPT'}]},common_input='actual common critic instructions')
    def count(**request):
        from types import SimpleNamespace
        value=100 if request['input']=='actual common critic instructions' else (300 if 'AAPL' in request['input'] else 100)
        return SimpleNamespace(input_tokens=value)
    c.responses.input_tokens.count=count
    b.run(MODELS[0],'whole actual packet',SCHEMA)
    row=b.allocation_records()[0]
    assert row['common_tokens']==100
    assert row['lane_tokens']=={'A':300,'B':100}
    # A=(300+50)/500, B=(100+50)/500, independent of whole-request count.
    assert D(row['allocations']['A'])==D('.00005775')
    assert D(row['allocations']['B'])==D('.00002475')
    b.close()


def test_split_stage_inputs_uses_only_actual_blocks_and_keeps_shared_text():
    from agents.cost_allocation import split_stage_input
    request={'research':{'summary':'shared'},'eligible_instruments':['AAPL','OPT'],
             'decision':{'picks':[{'instrument':'AAPL','thesis':'actual pick'}],'reason':'shared reason'}}
    blocks, common=split_stage_input(request,{'AAPL':'A','OPT':'B'})
    assert blocks=={'A':['AAPL',{'instrument':'AAPL','thesis':'actual pick'}],'B':['OPT']}
    assert common=={'research':{'summary':'shared'},'eligible_instruments':[],
                    'decision':{'picks':[],'reason':'shared reason'}}


def test_settlement_uses_attempt_keys_not_order_and_is_idempotent(tmp_path):
    from agents.budget import BudgetAllocator
    a = BudgetAllocator(tmp_path/'budget.db')
    reservations = [{'id':a.reserve(NOW,lane=lane,stage=role,amount=D('.03')),
                     'lane':lane,'stage':role} for lane in ('A','B') for role in ('research','critic')]
    attempts = [dict(role='critic',attempt_id='c1',allocations={'A':'.01'}),
                dict(role='research',attempt_id='r2',allocations={'A':'.0023'}),
                dict(role='research',attempt_id='r1',allocations={'A':'.01'})]
    a.settle_attempts('run1', reservations, attempts)
    a.settle_attempts('run1', reservations, attempts)
    with sqlite3.connect(a.path) as db:
        rows = db.execute('SELECT lane,stage,amount,settled FROM ai_budget_reservations').fetchall()
        assert {(l,s):D(v) for l,s,v,_ in rows} == {('A','research'):D('.0123'),('A','critic'):D('.01'),('B','research'):D(0),('B','critic'):D(0)}
        assert all(r[3] for r in rows)
    changed = [*attempts[:-1],dict(role='research',attempt_id='r1',allocations={'A':'.02'})]
    with pytest.raises(ValueError, match='ALLOCATION_CONFLICT'):
        a.settle_attempts('run1',reservations,changed)


@pytest.mark.parametrize('failed_stage',[None,0,1,2,'no_candidates','aux_count','settle_conflict','settle_invalid','settle_budget','close','bug'])
def test_official_cycle_allocates_all_three_roles_to_a_only(tmp_path,failed_stage,monkeypatch):
    from test_rehearsal import source
    from agents.cycle_lifecycle import CycleLifecycle
    from agents.daily_cycle import FixtureReader, FixtureBridge, run_cycle
    from agents.scheduled_inference import ScheduledInference
    from broker.models import Position
    inbox, config = source(tmp_path)
    config = config.model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    state = inbox.state('A','agent_alone')
    state['positions']['VTI'] = Position(ticker='VTI',asset_class='etf',quantity=D(1),average_cost=D(100)).model_dump(mode='json')
    state['marks']['VTI']='100'
    with inbox.connect() as db:
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),'A','agent_alone'))
    fake = FixtureBridge(config,NOW)
    if failed_stage=='no_candidates':
        monkeypatch.setattr('agents.daily_cycle.agent_candidate_packet',lambda *args: [])
    class PipelineClient(Client):
        def count(self,**request):
            if failed_stage=='aux_count' and 'text' not in request:
                raise RuntimeError('auxiliary count down')
            return super().count(**request)
        def create(self,**request):
            if len(self.calls)==failed_stage:
                raise RuntimeError('provider failure')
            response=super().create(**request)
            response.model=request['model']
            response.output_text=json.dumps(fake.run('','',{}).output)
            # Registered prices produce exactly .0223001 across the three roles.
            counts={MODELS[0]:(1003,1504),MODELS[1]:(1000,1001),MODELS[2]:(1000,831)}
            response.usage.input_tokens,response.usage.output_tokens=counts[request['model']]
            return response
    life=CycleLifecycle(inbox.path)
    claim=life.acquire(NOW,scheduled=True)
    b=ScheduledInference(inbox.path,client=PipelineClient(),lifecycle=life,cycle_id=claim['cycle_id'])
    if str(failed_stage).startswith('settle_'):
        from agents.budget import BudgetUnavailable
        def fail_settle(*args,**kwargs):
            events=inbox.store.read_json('run_states')
            assert any(r.get('cycle_id')==claim['cycle_id'] and r.get('accounting_status')=='PENDING' for r in events)
            if failed_stage=='settle_budget': raise BudgetUnavailable('test')
            raise ValueError('ALLOCATION_CONFLICT' if failed_stage=='settle_conflict' else 'INVALID_ATTEMPT_ALLOCATION')
        monkeypatch.setattr('agents.budget.BudgetAllocator.settle_attempts',fail_settle)
    if failed_stage=='close':
        def fail_close():
            assert any(r.get('cycle_id')==claim['cycle_id'] for r in inbox.store.read_json('run_states'))
            raise RuntimeError('close failed')
        monkeypatch.setattr(b,'close',fail_close)
    if failed_stage=='bug':
        def bug(*args,**kwargs): raise KeyError('PRIVATE_ACCOUNT_AND_TOKEN')
        monkeypatch.setattr('agents.daily_cycle.Runner.run_sync',bug)
    try:
        result=run_cycle(inbox,config,b,NOW,reader=FixtureReader(config,NOW),clock=lambda:NOW,lifecycle=life,cycle_id=claim['cycle_id'])
        ordinary=failed_stage is None or failed_stage in ('aux_count','settle_conflict','settle_invalid','settle_budget','close')
        assert result['status']==('COMPLETED' if ordinary else 'HOLD_OPERATIONAL')
        report=result['cost_allocation']
        assert report['lanes']['B']['agent_alone']=='0'
        assert report['lanes']['A']['deterministic_no_ai']=='0'
        assert D(report['lanes']['A']['agent_alone'])==D(result['api_cost_estimate_usd'])
        if failed_stage is None:
            assert D(report['total_unique_cost_usd'])==D('.0223001')
        expected_attempts=3 if ordinary else (0 if failed_stage in ('no_candidates','bug') else failed_stage+1)
        assert len(result['cost_allocation_attempts'])==expected_attempts
        from agents.dashboard import dashboard_snapshot
        snapshot=dashboard_snapshot(inbox,NOW)
        history=next(r for r in snapshot['history'] if r.get('authoritative'))
        assert history['details']['accounting_status']==result['accounting_status']
        if failed_stage=='no_candidates':
            assert result['reason']=='COST_NO_REPRESENTED_LANE'
            assert inbox.store.read_json('api_costs')==[]
        with inbox.connect() as db:
            rows=db.execute('SELECT amount,settled FROM ai_budget_reservations').fetchall()
            settlement_failed=str(failed_stage).startswith('settle_') or failed_stage=='close'
            if settlement_failed:
                assert not any(row[1] for row in rows)
                assert result['accounting_status']=='COST_SETTLEMENT_FAILED'
                assert db.execute("SELECT count(*) FROM safety_incidents WHERE code='COST_SETTLEMENT_FAILED'").fetchone()[0]==1
                assert db.execute("SELECT count(*) FROM notification_deliveries d JOIN safety_incidents s ON d.event_id=s.id WHERE channel='pushover' AND s.code='COST_SETTLEMENT_FAILED'").fetchone()[0]==1
            else:
                assert all(row[1] for row in rows)
                assert sum(D(row[0]) for row in rows)==D(report['total_unique_cost_usd'])
            if failed_stage=='aux_count':
                from agents.safety_events import safety_stopped
                from agents.accounting_events import enqueue_allocation_warning
                enqueue_allocation_warning(inbox.path,claim['cycle_id'],NOW)
                assert not safety_stopped(inbox.path)
                assert all(r['weight_basis']=='fallback_candidate_count' for r in result['cost_allocation_attempts'])
                assert db.execute("SELECT count(*) FROM notification_deliveries WHERE channel='pushover' AND event_id LIKE 'allocation-unavailable:%'").fetchone()[0]==1
            if failed_stage=='bug':
                from agents.safety_events import safety_stopped
                assert safety_stopped(inbox.path)
                assert db.execute("SELECT count(*) FROM safety_incidents WHERE code='INFERENCE_FAILED'").fetchone()[0]==1
                private_log=inbox.path.parent/'private-errors.jsonl'
                assert 'PRIVATE_ACCOUNT_AND_TOKEN' not in private_log.read_text()
                assert 'KeyError' in private_log.read_text()
                assert private_log.stat().st_mode & 0o077==0
    finally:
        if failed_stage!='close': b.close()
        life.close()


def test_crash_before_close_retains_budget_and_durable_attempt_bound(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':[{'instrument':'AAPL'}]})
    c.fail=True
    with pytest.raises(ValueError,match='MODEL_REQUEST_FAILED'):
        b.run(MODELS[0],'input',SCHEMA)
    # Reopen without close/finish, as a new process after an interrupted attempt.
    from data.store import SQLiteStore
    records=SQLiteStore(b.path).read_json('local_traces')
    allocated=[r for r in records if r['event']=='attempt_cost_allocation']
    assert len(allocated)==1 and D(allocated[0]['cost_usd'])==D('.0123')
    assert allocated[0]['attempt_id']
    with sqlite3.connect(b.path) as db:
        assert D(db.execute('SELECT amount FROM cost_reservations').fetchone()[0])==D('.1696')
    b.close()


def test_receipt_allocation_conserves_two_lane_actual_and_unknown_costs(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.set_cost_context({'A':[{'instrument':'AAPL'}],'B':[{'instrument':'OPT'}]},common_input='shared')
    b.run(MODELS[0],'stage input',SCHEMA)
    c.fail=True
    with pytest.raises(ValueError,match='MODEL_REQUEST_FAILED'):
        b.run(MODELS[1],'next stage',SCHEMA)
    from fractions import Fraction
    for row in b.allocation_records():
        assert sum(Fraction(v) for v in row['allocations'].values())==Fraction(row['cost_usd'])
        assert set(row['allocations'])=={'A','B'}
    assert sum(D(row['cost_usd']) for row in b.allocation_records())==D(b.cost_report()['api_cost_estimate_usd'])
    b.close()
