import sqlite3
from decimal import Decimal as D
import pytest
from test_bounded_inference import Client, MODELS, SCHEMA
from test_phase0_budget import NOW


def owned(tmp_path):
    from data.database_role import require_database_role
    from agents.cycle_lifecycle import CycleLifecycle
    path=tmp_path/'official.db'
    require_database_role(path,'live')
    life=CycleLifecycle(path)
    claim=life.acquire(NOW,scheduled=True)
    return path,life,claim['cycle_id']


def test_scheduled_bridge_requires_current_claim_and_blocks_lost_owner(tmp_path):
    from agents.scheduled_inference import ScheduledInference
    path,life,key=owned(tmp_path)
    c=Client()
    try:
        with pytest.raises(ValueError,match='OWNERSHIP'):
            ScheduledInference(path,client=c,lifecycle=life,cycle_id='wrong')
        b=ScheduledInference(path,client=c,lifecycle=life,cycle_id=key)
        b.run(MODELS[0],'dossier',SCHEMA)
        assert b.store.read_json('api_costs')[0]['data_mode']=='live_readonly'
        assert len(b.isolation_evidence)==1
        life.finish(key,'FAILED',{},NOW)
        with pytest.raises(ValueError,match='OWNERSHIP'):
            b.run(MODELS[0],'dossier',SCHEMA)
        b.close()
        assert len(c.calls)==1
    finally: life.close()


def test_scheduled_factory_rejects_model_mismatch_before_keychain(tmp_path):
    from agents.scheduled_inference import configured_scheduled_bridge
    from config.loader import load_config
    path,life,key=owned(tmp_path)
    try:
        with pytest.raises(ValueError,match='MODEL_CONFIG_MISMATCH'):
            configured_scheduled_bridge(path,load_config('config/settings.yaml'),lifecycle=life,cycle_id=key)
    finally: life.close()


def test_claim_lost_during_token_count_never_starts_generation(tmp_path):
    from agents.scheduled_inference import ScheduledInference
    path,life,key=owned(tmp_path)
    client=Client()
    original=client.responses.input_tokens.count
    def lose_claim(**request):
        life.finish(key,'FAILED',{},NOW)
        return original(**request)
    client.responses.input_tokens.count=lose_claim
    b=ScheduledInference(path,client=client,lifecycle=life,cycle_id=key)
    try:
        with pytest.raises(ValueError,match='OWNERSHIP'):
            b.run(MODELS[0],'x',SCHEMA)
        assert not client.calls
    finally:
        b.close()
        life.close()


def test_code_only_scheduled_factory_never_retrieves_key(tmp_path,monkeypatch):
    from agents.scheduled_inference import configured_scheduled_bridge
    from config.loader import load_config
    import subprocess
    def forbidden(*args,**kwargs): raise AssertionError('unexpected key access')
    monkeypatch.setattr(subprocess,'run',forbidden)
    path,life,key=owned(tmp_path)
    config=load_config('config/settings.yaml').model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    try:
        b=configured_scheduled_bridge(path,config,lifecycle=life,cycle_id=key)
        b.close()
        assert b.cost_report()['api_cost_estimate_usd']=='0'
    finally: life.close()


def test_scheduled_budget_reserves_full_run_and_respects_prior_spend(tmp_path):
    from agents.scheduled_inference import ScheduledInference
    from agents.codex_bridge import BudgetExceeded
    path,life,key=owned(tmp_path)
    c=Client()
    try:
        b=ScheduledInference(path,client=c,lifecycle=life,cycle_id=key)
        b.ledger.reserve(NOW,D('.24'))
        with pytest.raises(BudgetExceeded): b.run(MODELS[0],'x',SCHEMA,now=NOW)
        assert not c.calls
        b.close()
    finally: life.close()


def test_official_owned_cycle_uses_registered_three_stage_transport(tmp_path):
    import json
    from test_rehearsal import source
    from agents.cycle_lifecycle import CycleLifecycle
    from agents.daily_cycle import FixtureReader, FixtureBridge, run_cycle
    from agents.scheduled_inference import ScheduledInference
    inbox,config=source(tmp_path)
    config=config.model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    state=inbox.state('A','agent_alone')
    from broker.models import Position
    state['positions']['VTI']=Position(ticker='VTI',asset_class='etf',quantity=D('1'),average_cost=D('100')).model_dump(mode='json')
    state['marks']['VTI']='100'
    with inbox.connect() as db:
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),'A','agent_alone'))
    fake=FixtureBridge(config,NOW)
    class PipelineClient(Client):
        def create(self,**request):
            response=super().create(**request)
            response.model=request['model']
            response.output_text=json.dumps(fake.run('','',{}).output)
            return response
    life=CycleLifecycle(inbox.path)
    claim=life.acquire(NOW,scheduled=True)
    client=PipelineClient()
    b=ScheduledInference(inbox.path,client=client,lifecycle=life,cycle_id=claim['cycle_id'])
    try:
        result=run_cycle(inbox,config,b,NOW,reader=FixtureReader(config,NOW),
            clock=lambda:NOW,lifecycle=life,cycle_id=claim['cycle_id'])
        assert result['status']=='COMPLETED'
        assert result['agents']==['Research Agent','Portfolio Agent','Critic']
        assert len(b.isolation_evidence)==3
        assert [x['model'] for x in client.calls]==MODELS
        assert all(x['tools']==[] for x in client.calls)
        assert b.closed and D(result['api_cost_estimate_usd'])<D('.40')
        assert all(x['data_mode']=='live_readonly' for x in inbox.store.read_json('api_costs'))
    finally:
        b.close()
        life.close()
