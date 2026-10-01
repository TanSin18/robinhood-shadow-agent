"""Seat prompts, output schemas and the code checks that run before the Critic.

Prompt text is part of the experiment: its hash is pinned in the trader database at the first
run, and any change refuses to run (a prompt change is a new trial).
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from agents.ai_trader.tools import number_in_tools

D = Decimal

SCOUT_PROMPT = """You are the Scout on a small paper-trading desk. Read only the tool packet below.
Name zero to three candidates from the TRADABLE list that have a clear, current setup visible in the
tool numbers (trend, momentum, pullback within a trend, volatility contraction, relative strength).
Saying nothing is a good answer when nothing is clear. Never name a ticker outside TRADABLE. Never
use remembered history or news; only the packet. Give each candidate a short setup_tag, at most two
sentences of why, and the tool ids you used as sources."""

PM_PROMPT = """You are the PM. Turn the one candidate below into a ticket using only the tool packet.
Write: thesis (at most three sentences), invalidation_price (a price below the current ask where the
idea is wrong), time_stop_sessions (1 to 20), false_tomorrow_if (what would make the thesis false by
tomorrow), sources (tool ids), and cited_numbers: every number your thesis relies on, each as
{tool_id, field, value} copied exactly from the packet. You do not choose size. Do not invent numbers."""

CRITIC_PROMPT = """You are the Critic. Attack each ticket below against the policy and the tool packet.
Fail a ticket with the matching codes when: it is not on the universe (NOT_IN_UNIVERSE), it has no
sensible invalidation (NO_INVALIDATION), its numbers are not in the tools (NUMBERS_NOT_IN_TOOLS), the
book's weekly loss stop is hit (WEEKLY_LOSS_HIT), it is already held (ALREADY_HELD), the thesis does not
follow from the numbers (THESIS_UNSUPPORTED), or it breaks any other written rule (POLICY_VIOLATION).
Conviction is not evidence. Pass only what the numbers support."""

MANAGE_PROMPT = """You manage open paper positions. For every holding listed, write exactly one card:
hold, trim (with trim_fraction between 0.1 and 0.9) or exit, with a one-sentence reason based only on
the tool packet and the position's own ticket (thesis, invalidation, time stop). You may not add size."""

PROMPTS = {'scout': SCOUT_PROMPT, 'pm': PM_PROMPT, 'critic': CRITIC_PROMPT, 'manage': MANAGE_PROMPT}


def prompts_sha256():
    return hashlib.sha256(json.dumps(PROMPTS, sort_keys=True).encode()).hexdigest()


def _obj(props, required=None):
    return {'type': 'object', 'additionalProperties': False, 'properties': props, 'required': required or list(props)}


S = {'type': 'string'}
TOOL_IDS = {'type': 'array', 'items': S, 'maxItems': 12}
SCHEMAS = {
    'scout': _obj({'candidates': {'type': 'array', 'maxItems': 3, 'items': _obj(
        {'ticker': S, 'setup_tag': S, 'why': S, 'sources': TOOL_IDS})}, 'nothing_today_reason': S}),
    'pm': _obj({'ticker': S, 'setup_tag': S, 'thesis': S, 'invalidation_price': {'type': 'number'},
                'time_stop_sessions': {'type': 'integer'}, 'false_tomorrow_if': S, 'sources': TOOL_IDS,
                'cited_numbers': {'type': 'array', 'maxItems': 12, 'items': _obj(
                    {'tool_id': S, 'field': S, 'value': {'type': 'number'}})}}),
    'critic': _obj({'tickets': {'type': 'array', 'items': _obj(
        {'ticket_id': S, 'verdict': {'type': 'string', 'enum': ['pass', 'fail']},
         'fail_codes': {'type': 'array', 'items': S}, 'reason': S})}}),
    'manage': _obj({'cards': {'type': 'array', 'items': _obj(
        {'ticker': S, 'action': {'type': 'string', 'enum': ['hold', 'trim', 'exit']},
         'trim_fraction': {'type': 'number'}, 'reason': S})}}),
}


def build(seat, *, spec, tools, extra):
    body = {'TRADABLE': list(spec.universe), 'tools': tools, **extra}
    return PROMPTS[seat] + '\n\nPACKET (JSON):\n' + json.dumps(body, sort_keys=True, default=str)


def sentences(text):
    return [s for s in re.split(r'(?<=[.!?])\s+', (text or '').strip()) if s]


def check_ticket(ticket, *, spec, tools, book, entries_today, now_quote, weekly_hit):
    """Deterministic checks before the Critic. Returns fail codes (empty list = pass)."""
    fails = []
    t = ticket.get('ticker')
    if t not in spec.universe:
        fails.append('NOT_IN_UNIVERSE')
    if t in book.positions:
        fails.append('ALREADY_HELD')
    if weekly_hit:
        fails.append('WEEKLY_LOSS_HIT')
    if len(book.positions) >= spec.max_names or entries_today >= spec.entries_per_day:
        fails.append('SIZE_OVER_CAP')
    q = now_quote or {}
    try:
        inv = D(str(ticket.get('invalidation_price')))
        if not q.get('available') or not q.get('fresh') or not (D(0) < inv < D(str(q['ask']))):
            fails.append('NO_INVALIDATION')
    except Exception:
        fails.append('NO_INVALIDATION')
    ts = ticket.get('time_stop_sessions')
    if not isinstance(ts, int) or not 1 <= ts <= spec.time_stop_max:
        fails.append('POLICY_VIOLATION')
    if not ticket.get('thesis') or len(sentences(ticket['thesis'])) > spec.thesis_max_sentences or not ticket.get('false_tomorrow_if'):
        fails.append('POLICY_VIOLATION')
    sources = ticket.get('sources') or []
    if not sources or any(s not in tools for s in sources):
        fails.append('NUMBERS_NOT_IN_TOOLS')
    cited = ticket.get('cited_numbers') or []
    if not cited or any(not number_in_tools(tools, c.get('tool_id'), c.get('field'), c.get('value')) for c in cited):
        fails.append('NUMBERS_NOT_IN_TOOLS')
    return sorted(set(fails))
