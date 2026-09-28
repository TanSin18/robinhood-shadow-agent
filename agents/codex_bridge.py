"""Authenticated read-only Codex transport and Agents SDK custom model.

No credentials are read by this application. The CLI uses its own credential store.
Raw MCP responses live in memory; only redacted event metadata is persisted.
"""
from __future__ import annotations

import asyncio
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from agents.models.interface import Model, ModelResponse
from agents.usage import Usage
from agents.strict_schema import ensure_strict_json_schema
from broker.policy import Stage1ToolPolicy
from broker.base import BrokerError
from data.store import SQLiteStore
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

ET = ZoneInfo('America/New_York')
PRICING = {'gpt-5.6-luna': (Decimal('.20'), Decimal('.02'), Decimal('1.20')),
           'gpt-5.6-terra': (Decimal('2'), Decimal('.20'), Decimal('12'))}


class BudgetExceeded(ValueError):
    pass


class CostLedger:
    def __init__(self, path, limit):
        self.path, self.limit = Path(path), Decimal(limit)
        SQLiteStore(path)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS cost_reservations (id TEXT PRIMARY KEY, day TEXT, amount TEXT, settled INTEGER, payload TEXT)')

    def reserve(self, now, amount):
        if amount <= 0 or not amount.is_finite():
            raise ValueError('invalid budget reservation')
        day, key = now.astimezone(ET).date().isoformat(), uuid4().hex
        with sqlite3.connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            spent = sum((Decimal(r[0]) for r in db.execute('SELECT amount FROM cost_reservations WHERE day=?', (day,))), Decimal(0))
            if spent + amount > self.limit:
                raise BudgetExceeded('daily estimated cost budget exhausted')
            db.execute('INSERT INTO cost_reservations VALUES (?, ?, ?, 0, ?)', (key, day, str(amount), '{}'))
        return key

    def finish(self, key, cost, payload):
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE cost_reservations SET amount=?, settled=1, payload=? WHERE id=? AND settled=0', (str(cost), json.dumps(payload), key))


@dataclass
class BridgeResult:
    output: dict
    reads: list[dict]
    usage: dict
    tool_names: list[str]


class CodexBridge:
    def __init__(self, path, limit=Decimal('.40'), executable=None,
                 dashboard_base_url='http://127.0.0.1:8765'):
        self.store = SQLiteStore(path)
        self.ledger = CostLedger(path, limit)
        self.executable = executable or shutil.which('codex') or '/Applications/ChatGPT.app/Contents/Resources/codex'
        self.dashboard_base_url = dashboard_base_url
        self.last_result = None
        self.isolation_evidence=[]

    def command(self, model, schema_path, read_tools, *, news=False):
        if read_tools:
            raise BrokerError('Inference cannot access brokerage capabilities')
        from agents.isolated_session import command
        return command(self.executable,model=model)

    def parse(self, raw, read_tools):
        # Legacy event reader is retained for historical traces, never live dispatch.
        if read_tools: raise BrokerError('Inference cannot accept broker reads')
        final, usage, reads, names = None, None, [], []
        for line in raw.splitlines():
            event = json.loads(line)
            if event['type'] in {'turn.failed', 'error'}:
                raise ValueError('Codex turn failed; inspect local authenticated CLI status')
            if event['type'] == 'turn.completed':
                usage = event.get('usage')
            item = event.get('item', {})
            if event['type'] != 'item.completed':
                continue
            if item.get('type') == 'command_execution':
                raise ValueError('unexpected shell execution in read-only bridge')
            if item.get('type') == 'agent_message':
                final = item.get('text')
            if item.get('type') == 'mcp_tool_call':
                raise BrokerError('Unexpected MCP event in inference')
        if final is None or usage is None:
            raise ValueError('missing structured output or usage evidence')
        return BridgeResult(json.loads(final), reads, usage, names)

    def run(self, model, instructions, schema, *, read_tools=(), news=False, now=None):
        if read_tools:
            raise BrokerError('Inference cannot access brokerage tools; use the deterministic reader')
        now = now or datetime.now(timezone.utc)
        if model not in PRICING:
            raise ValueError('model has no reviewed pricing')
        from agents.isolated_session import command, start, verify_inference_inventory, collect_turn, cli_identity
        from agents.rpc_transport import RpcTransport
        from agents.safety_events import record_incident, safety_stopped
        from broker.read_gateway import CapabilityError
        if safety_stopped(self.ledger.path): raise BrokerError('Safety stop is active')
        try:
            with RpcTransport(command(self.executable,model=model)) as rpc:
                thread=start(rpc,model)
                isolation=verify_inference_inventory(rpc,thread)
                isolation['cli_sha256']=cli_identity(self.executable)
                if safety_stopped(self.ledger.path): raise BrokerError('Safety stop is active')
                reservation=self.ledger.reserve(now,Decimal('.06') if model.endswith('luna') else Decimal('.14'))
                # A request may be charged even if the connection then fails; retain its hold.
                response=rpc.request('turn/start',{'threadId':thread,'input':[{'type':'text','text':instructions,'text_elements':[]}],'outputSchema':ensure_strict_json_schema(schema)},timeout=30)
                output,usage=collect_turn(rpc,thread,response['turn']['id'])
                result=BridgeResult(output,[],usage,[])
        except CapabilityError:
            record_incident(self.ledger.path,'UNEXPECTED_CAPABILITY',now=now,
                            dashboard_base_url=self.dashboard_base_url)
            raise
        input_rate, cache_rate, output_rate = PRICING[model]
        inputs, outputs = int(result.usage['input_tokens']), int(result.usage['output_tokens'])
        cached = int(result.usage.get('cached_input_tokens', 0))
        cost = ((inputs-cached)*input_rate + cached*cache_rate + outputs*output_rate)/Decimal(1_000_000)
        payload = {'timestamp':now.isoformat(), 'model':model, 'input_tokens':inputs, 'cached_input_tokens':cached, 'output_tokens':outputs, 'cost_usd':str(cost), 'cost_basis':'estimated_api_equivalent', 'pricing_version':'2026-09-27', 'tools':result.tool_names, 'isolation':isolation, 'news_enabled':False, 'search_cost_coverage':'disabled; no searches performed'}
        self.ledger.finish(reservation, cost, payload)
        self.store.append_json('api_costs', payload)
        self.store.append_json('local_traces', {'trace_id':reservation, 'event':'codex_readonly_run', 'payload':payload})
        self.last_result = result
        self.isolation_evidence.append(isolation)
        return result


class CodexSDKModel(Model):
    """Keeps SDK Runner, Agent schemas and tracing while using saved Codex auth."""
    def __init__(self, bridge, model, read_tools=(), news=False):
        self.bridge, self.model, self.read_tools, self.news = bridge, model, read_tools, news

    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing, **kwargs):
        if tools or handoffs or output_schema is None:
            raise ValueError('bridge requires structured final output and no SDK side-effect tools')
        result = await asyncio.to_thread(self.bridge.run, self.model, (system_instructions or '') + '\n' + (input if isinstance(input,str) else json.dumps(input)), output_schema.json_schema(), read_tools=self.read_tools, news=self.news)
        text = json.dumps(result.output)
        message = ResponseOutputMessage(id=uuid4().hex, type='message', role='assistant', status='completed', content=[ResponseOutputText(type='output_text', text=text, annotations=[])])
        return ModelResponse(output=[message], usage=Usage(requests=1, input_tokens=result.usage['input_tokens'], output_tokens=result.usage['output_tokens'], total_tokens=result.usage['input_tokens']+result.usage['output_tokens']), response_id=None)

    async def stream_response(self, *args, **kwargs):
        raise NotImplementedError('Use non-streaming SDK Runner')
        yield  # pragma: no cover
