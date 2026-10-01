"""Model calls under the $2/day cap. Every call reserves its registered worst case first.

``client`` is any callable ``client(model, prompt, schema, envelope) -> (output, input_tokens, output_tokens)``.
``OpenAIResponsesClient`` is the production adapter (same request shape as the registered bounded
transport: no tools, strict JSON schema, no retries, standard tier). Tests inject fakes.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import yaml
from jsonschema import ValidationError, validate

D = Decimal
REGISTRATION = Path(__file__).resolve().parents[2] / 'preregistration.yaml'


class BudgetExhausted(RuntimeError):
    pass


class ModelError(RuntimeError):
    pass


def pricing():
    raw = yaml.safe_load(REGISTRATION.read_text())
    snap = raw['cost']['pricing_snapshot']
    return snap['input_usd_per_million_tokens'], snap['output_usd_per_million_tokens']


def bound_usd(model, envelope, prices=None):
    inp, out = prices or pricing()
    return (D(envelope['max_input_tokens']) * D(str(inp[model])) + D(envelope['max_output_tokens']) * D(str(out[model]))) / D(1000000)


class BudgetedModels:
    def __init__(self, store, spec, client, *, day: str, now: datetime, prices=None):
        self.store, self.spec, self.client, self.day, self.now = store, spec, client, day, now
        self.prices = prices or pricing()

    def remaining(self):
        return self.spec.daily_budget - self.store.spent(self.day)

    def run(self, seat, prompt, schema):
        model, envelope = self.spec.models[seat], self.spec.envelopes[seat]
        reserve = bound_usd(model, envelope, self.prices)
        if reserve > self.remaining():
            raise BudgetExhausted(seat)
        with self.store.connect() as db:
            cur = db.execute("INSERT INTO budget (at,day,seat,model,reserved,status) VALUES (?,?,?,?,?, 'RESERVED')",
                             (self.now.isoformat(), self.day, seat, model, str(reserve)))
            row_id = cur.lastrowid
        try:
            output, tin, tout = self.client(model, prompt, schema, envelope)
        except Exception as error:   # uncertain call: keep the full reservation charged
            with self.store.connect() as db:
                db.execute("UPDATE budget SET status='UNCERTAIN_KEPT_RESERVATION', actual=reserved WHERE id=?", (row_id,))
            raise ModelError(type(error).__name__) from None
        if not isinstance(tin, int) or not isinstance(tout, int) or tin > envelope['max_input_tokens'] or tout > envelope['max_output_tokens']:
            with self.store.connect() as db:
                db.execute("UPDATE budget SET status='ENVELOPE_VIOLATION', actual=reserved WHERE id=?", (row_id,))
            raise ModelError('ENVELOPE_VIOLATION')
        inp, out = self.prices
        actual = (D(tin) * D(str(inp[model])) + D(tout) * D(str(out[model]))) / D(1000000)
        with self.store.connect() as db:
            db.execute("UPDATE budget SET status='SETTLED', actual=? WHERE id=?", (str(actual), row_id))
        try:
            validate(output, schema)
        except ValidationError:
            raise ModelError('SCHEMA_INVALID') from None
        return output


class OpenAIResponsesClient:
    """Production adapter (not used by tests). Requires OPENAI_API_KEY in the service environment."""

    def __init__(self, client=None):
        if client is None:
            import os
            from openai import OpenAI
            key = os.environ.get('OPENAI_API_KEY')
            if not key:
                raise ModelError('API_ACCESS_NOT_CONFIGURED')
            client = OpenAI(api_key=key, base_url='https://api.openai.com/v1', max_retries=0, timeout=120.0)
        self.client = client

    def __call__(self, model, prompt, schema, envelope):
        from agents.strict_schema import ensure_strict_json_schema
        request = dict(model=model, input=prompt, tools=[], tool_choice='none', reasoning={'effort': envelope['reasoning']},
                       truncation='disabled', text={'format': {'type': 'json_schema', 'name': 'seat_result', 'strict': True,
                                                               'schema': ensure_strict_json_schema(schema)}})
        count = self.client.responses.input_tokens.count(**request).input_tokens
        if count > envelope['max_input_tokens']:
            raise ModelError('INPUT_TOKEN_CAP')
        response = self.client.responses.create(**request, store=False, service_tier='default',
                                                max_output_tokens=envelope['max_output_tokens'])
        if response.model != model:
            raise ModelError('RESPONSE_MODEL_MISMATCH')
        return json.loads(response.output_text), response.usage.input_tokens, response.usage.output_tokens
