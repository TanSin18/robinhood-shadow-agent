from types import SimpleNamespace as NS
from decimal import Decimal as D
import sqlite3
import pytest

MODELS = ['gpt-5.4-nano-2026-03-17','gpt-5.4-mini-2026-03-17','gpt-5.4-2026-03-05']
SCHEMA = {'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok'],'additionalProperties':False}

class Client:
    def __init__(self):
        self.calls=[]; self.counts=[]; self.input_count=100; self.fail=False
        self.response=NS(status='completed',model=MODELS[0],service_tier='default',output_text='{"ok":true}',
            output=[],usage=NS(input_tokens=100,output_tokens=50),incomplete_details=None)
        self.responses=NS(input_tokens=NS(count=self.count),create=self.create)
    def with_options(self, **options):
        assert options == {'max_retries':0,'timeout':120.0}
        return self
    def count(self, **request):
        self.counts.append(request); return NS(input_tokens=self.input_count)
    def create(self, **request):
        self.calls.append(request)
        if self.fail: raise RuntimeError('SECRET PROVIDER DETAIL')
        return self.response

def bridge(tmp_path, client):
    from agents.bounded_inference import BoundedInference
    return BoundedInference(tmp_path/'diagnostic.db', client=client)

def test_registered_envelope_and_no_tools(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    result=b.run(MODELS[0],'source dossier',SCHEMA)
    assert result.output=={'ok':True}
    call=c.calls[0]
    assert call['max_output_tokens']==6000 and call['reasoning']=={'effort':'low'}
    assert call['tools']==[] and call['tool_choice']=='none' and call['store'] is False
    assert call['service_tier']=='default'
    assert 'temperature' not in call
    assert c.counts[0]['text']==call['text']
    b.close()
    with sqlite3.connect(b.path) as db:
        assert D(db.execute('SELECT amount FROM cost_reservations').fetchone()[0])==D('.0000825')

def test_unknown_model_and_oversize_input_never_generate(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    with pytest.raises(ValueError,match='UNREGISTERED_MODEL'): b.run('alias','x',SCHEMA)
    c.input_count=24001
    with pytest.raises(ValueError,match='INPUT_TOKEN_CAP'): b.run(MODELS[0],'x',SCHEMA)
    assert not c.calls
    b.close()

def test_truncation_is_distinct_and_cost_recorded(tmp_path):
    c=Client(); c.response.status='incomplete'; c.response.incomplete_details=NS(reason='max_output_tokens')
    b=bridge(tmp_path,c)
    with pytest.raises(ValueError,match='OUTPUT_TRUNCATED_AT_TOKEN_CAP'): b.run(MODELS[0],'x',SCHEMA)
    assert len(c.calls)==1
    b.close()
    assert b.store.read_json('api_costs')[0]['output_tokens']==50

def test_no_hidden_retry_and_unknown_charge_retained(tmp_path):
    c=Client(); c.fail=True; b=bridge(tmp_path,c)
    with pytest.raises(ValueError,match='MODEL_REQUEST_FAILED') as error: b.run(MODELS[0],'x',SCHEMA)
    assert 'SECRET' not in str(error.value) and len(c.calls)==1
    b.close()
    from agents.rehearsal import public_report
    report=public_report({'status':'HOLD_OPERATIONAL',**b.cost_report()})
    assert D(report['api_cost_estimate_usd'])==D('.0123')
    assert report['uncertain_model_calls']==1
    assert report['cost_basis']=='registered_uncached_estimate_plus_uncertain_reservations'
    with sqlite3.connect(b.path) as db:
        assert D(db.execute('SELECT amount FROM cost_reservations').fetchone()[0])==D('.0123')

@pytest.mark.parametrize('mutation',['wrong_model','tool','schema','usage','tier'])
def test_invalid_provider_result_fails_closed(tmp_path,mutation):
    c=Client()
    if mutation=='wrong_model': c.response.model='other'
    if mutation=='tool': c.response.output=[NS(type='function_call')]
    if mutation=='schema': c.response.output_text='{"ok":"not boolean"}'
    if mutation=='usage': c.response.usage.output_tokens=-1
    if mutation=='tier': c.response.service_tier='priority'
    b=bridge(tmp_path,c)
    with pytest.raises(ValueError): b.run(MODELS[0],'x',SCHEMA)
    b.close()

def test_attempt_cap_and_closed_bridge(tmp_path):
    c=Client(); b=bridge(tmp_path,c)
    b.run(MODELS[0],'x',SCHEMA); b.run(MODELS[0],'x',SCHEMA)
    with pytest.raises(ValueError,match='ATTEMPT_LIMIT'): b.run(MODELS[0],'x',SCHEMA)
    b.close()
    with pytest.raises(ValueError,match='CLOSED'): b.run(MODELS[1],'x',SCHEMA)
    assert len(c.calls)==2

def test_config_mismatch_is_not_silently_overridden(tmp_path):
    from agents.bounded_inference import validate_registered_models
    from config.loader import load_config
    config=load_config('config/settings.yaml')
    with pytest.raises(ValueError,match='MODEL_CONFIG_MISMATCH'): validate_registered_models(config)
    correct=config.model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    validate_registered_models(correct)

def test_whole_run_reserved_before_dispatch_and_official_database_rejected(tmp_path):
    from data.database_role import require_database_role
    from agents.bounded_inference import BoundedInference
    from agents.codex_bridge import BudgetExceeded
    path=tmp_path/'live.db'; require_database_role(path,'live')
    with pytest.raises(ValueError): BoundedInference(path,client=Client())
    c=Client(); b=bridge(tmp_path,c)
    b.ledger.reserve(__import__('datetime').datetime.now(__import__('datetime').timezone.utc),D('.04'))
    with pytest.raises(BudgetExceeded): b.run(MODELS[0],'x',SCHEMA)
    assert c.calls==[]

def test_registered_bridge_integrates_with_isolated_cycle(tmp_path):
    from test_rehearsal import source, NOW
    from agents.rehearsal import prepare, official_digest
    from agents.daily_cycle import FixtureReader, FixtureBridge, run_cycle
    from agents.bounded_inference import BoundedInference
    import json
    official,config=source(tmp_path)
    state=official.state('A','agent_alone')
    state['positions']['VTI']={'quantity':'1','average_cost':'100','multiplier':1}
    state['marks']['VTI']='100'
    with official.connect() as db:
        db.execute('UPDATE paper_accounts SET payload=? WHERE lane=? AND track=?',(json.dumps(state),'A','agent_alone'))
    config=config.model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    inbox=prepare(official.path,tmp_path/'run',config)
    before=official_digest(official.path)
    fake=FixtureBridge(config,NOW)
    class PipelineClient(Client):
        def create(self,**request):
            response=super().create(**request)
            response.model=request['model']
            response.output_text=json.dumps(fake.run('','',{}).output)
            return response
    c=PipelineClient(); b=BoundedInference(inbox.path,client=c)
    result=run_cycle(inbox,config,b,NOW,data_mode='whatif',reader=FixtureReader(config,NOW),clock=lambda:NOW)
    b.close()
    assert result['status']=='COMPLETED'
    assert len(c.calls)==3 and [x['model'] for x in c.calls]==MODELS
    assert [x['reasoning']['effort'] for x in c.calls]==['low','medium','medium']
    assert [x['max_output_tokens'] for x in c.calls]==[6000,3000,2000]
    assert result['cap_waiver'] is False
    assert official_digest(official.path)==before

def test_missing_api_access_does_not_fall_back(tmp_path,monkeypatch):
    from agents.bounded_inference import configured_bridge
    from config.loader import load_config
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    config=load_config('config/settings.yaml').model_copy(update={r+'_model_name':m for r,m in zip(('research','portfolio','critic'),MODELS)})
    with pytest.raises(ValueError,match='API_ACCESS_NOT_CONFIGURED'):
        configured_bridge(tmp_path/'missing.db',config)
    assert not (tmp_path/'missing.db').exists()
