"""Registered Responses transport for isolated diagnostics, not deployment.

No tools, brokerage credentials, automatic repairs or automatic model fallback.
One run reserves both possible attempts of all three stages before generation.
Crashes leave the reservation in place; uncertain calls retain their full bound.
"""
import json
import os
import threading
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import yaml
from jsonschema import validate, ValidationError

from agents.preregistration import load_phase0_registration
from agents.codex_bridge import BridgeResult, CostLedger
from agents.strict_schema import ensure_strict_json_schema
from data.database_role import require_database_role
from data.store import SQLiteStore

REGISTRATION = Path(__file__).resolve().parents[1]/'preregistration.yaml'


def policy():
    load_phase0_registration(REGISTRATION)
    raw = yaml.safe_load(REGISTRATION.read_text())
    return raw['agent_contract']['assigned_models'], raw['cost']


def validate_registered_models(config):
    models, _ = policy()
    if any(getattr(config, role+'_model_name') != model for role, model in models.items()):
        raise ValueError('MODEL_CONFIG_MISMATCH')


def configured_bridge(path, config):
    validate_registered_models(config)
    key = os.environ.get('OPENAI_API_KEY')
    if not key: raise ValueError('API_ACCESS_NOT_CONFIGURED')
    from openai import OpenAI
    client = OpenAI(api_key=key,base_url='https://api.openai.com/v1',max_retries=0,timeout=120.0)
    return BoundedInference(path,client=client)


class BoundedInference:
    def __init__(self, path, *, client):
        self.path = Path(path)
        require_database_role(self.path, 'whatif')
        self.models, self.cost = policy()
        self.client = client.with_options(max_retries=0, timeout=120.0)
        self.store = SQLiteStore(self.path)
        self.ledger = CostLedger(self.path, D(str(self.cost['what_if_run_llm_ceiling'])))
        self.lock = threading.RLock()
        self.closed = False
        self.attempts = {r:0 for r in self.models}
        self.charged = D(0)
        self.uncertain_calls = 0
        self.reservation = None
        self.last_result = None

    def bound(self, role):
        envelope = self.cost['stage_token_envelopes_per_attempt'][role]
        model = self.models[role]
        pricing = self.cost['pricing_snapshot']
        return (D(envelope['maximum_input_tokens'])*D(str(pricing['input_usd_per_million_tokens'][model]))
                + D(envelope['maximum_output_tokens_including_reasoning'])*D(str(pricing['output_usd_per_million_tokens'][model])))/D(1000000)

    def run(self, model, instructions, schema, *, read_tools=(), news=False, now=None):
        with self.lock:
            return self._run(model,instructions,schema,read_tools,news,now)

    def _run(self, model, instructions, schema, read_tools, news, now):
        if self.closed: raise ValueError('INFERENCE_CLOSED')
        if read_tools or news: raise ValueError('INFERENCE_TOOLS_FORBIDDEN')
        if model not in self.models.values(): raise ValueError('UNREGISTERED_MODEL')
        role = next(r for r,m in self.models.items() if m == model)
        if self.attempts[role] >= 2: raise ValueError('ATTEMPT_LIMIT')
        now = now or datetime.now(timezone.utc)
        envelope = self.cost['stage_token_envelopes_per_attempt'][role]
        request = dict(model=model,input=instructions,tools=[],tool_choice='none',
            reasoning={'effort':envelope['reasoning_effort']},truncation='disabled',
            text={'format':{'type':'json_schema','name':'agent_result','strict':True,
                            'schema':ensure_strict_json_schema(schema)}})
        try:
            count = self.client.responses.input_tokens.count(**request).input_tokens
        except Exception:
            raise ValueError('INPUT_TOKEN_COUNT_FAILED') from None
        if type(count) is not int or count < 0 or count > envelope['maximum_input_tokens']:
            raise ValueError('INPUT_TOKEN_CAP')
        if self.reservation is None:
            total = sum((2*self.bound(r) for r in self.models),D(0))
            self.reservation = self.ledger.reserve(now,total)
        self.attempts[role] += 1
        bound = self.bound(role)
        self.charged += bound  # Retained unless trusted usage reconciles it.
        self.uncertain_calls += 1
        self.store.append_json('local_traces',{'event':'bounded_attempt_started','role':role,
            'model':model,'attempt':self.attempts[role],'input_tokens':count,
            'reserved_usd':str(bound),'data_mode':'whatif'})
        try:
            response = self.client.responses.create(**request,store=False,service_tier='default',
                max_output_tokens=envelope['maximum_output_tokens_including_reasoning'])
        except Exception:
            raise ValueError('MODEL_REQUEST_FAILED') from None
        if response.model != model: raise ValueError('RESPONSE_MODEL_MISMATCH')
        if getattr(response,'service_tier',None) != 'default':
            raise ValueError('RESPONSE_PRICING_TIER_MISMATCH')
        usage = response.usage
        inputs, outputs = getattr(usage,'input_tokens',None), getattr(usage,'output_tokens',None)
        if any(type(v) is not int or v<0 for v in (inputs,outputs)):
            raise ValueError('INVALID_USAGE')
        if inputs > envelope['maximum_input_tokens'] or outputs > envelope['maximum_output_tokens_including_reasoning']:
            raise ValueError('PROVIDER_ENVELOPE_VIOLATION')
        pricing = self.cost['pricing_snapshot']
        amount = (D(inputs)*D(str(pricing['input_usd_per_million_tokens'][model]))
                  + D(outputs)*D(str(pricing['output_usd_per_million_tokens'][model])))/D(1000000)
        self.charged += amount-bound
        self.uncertain_calls -= 1
        self.store.append_json('api_costs',{'timestamp':now.isoformat(),'model':model,'role':role,
            'attempt':self.attempts[role],'input_tokens':inputs,'output_tokens':outputs,
            'cost_usd':str(amount),'cost_basis':'registered_uncached_upper_estimate','data_mode':'whatif'})
        if response.status=='incomplete' and getattr(response.incomplete_details,'reason',None)=='max_output_tokens':
            raise ValueError('OUTPUT_TRUNCATED_AT_TOKEN_CAP')
        if response.status!='completed': raise ValueError('MODEL_RESPONSE_INCOMPLETE')
        if any(item.type not in {'message','reasoning'} for item in response.output):
            raise ValueError('UNEXPECTED_MODEL_TOOL')
        try:
            output=json.loads(response.output_text)
            validate(output,schema)
        except (ValueError,ValidationError):
            raise ValueError('MODEL_SCHEMA_INVALID') from None
        self.last_result=BridgeResult(output,[],{'input_tokens':inputs,'output_tokens':outputs},[])
        return self.last_result

    def cost_report(self):
        return {'api_cost_estimate_usd':str(self.charged),
                'uncertain_model_calls':self.uncertain_calls,
                'cost_basis':'registered_uncached_estimate_plus_uncertain_reservations'}

    def close(self):
        with self.lock:
            if self.closed: return
            if self.reservation:
                self.ledger.finish(self.reservation,self.charged,{'basis':'known_usage_plus_full_bounds_for_uncertain_calls'})
            self.closed=True
