# Agent Decision Room Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the repeated Agent activity event cards with a truthful, responsive decision room that shows ordered agent handoffs, structured candidate decisions, deterministic risk checks and the final operator action.

**Architecture:** Extend the existing append-only `local_traces` records with structured candidate decisions and a deterministic risk event, then project those records into a stable server-side decision-room view model. Render semantic HTML first, add a small local interaction layer for review/stage/lane selection, and apply a tokenized responsive visual system without adding frameworks, remote assets or services.

**Tech Stack:** Python 3.14, SQLite, Pydantic-backed agent outputs, server-rendered HTML, local CSS, local vanilla JavaScript, pytest, Node-based DOM-contract tests, Codex in-app browser verification.

**Spec:** `docs/superpowers/specs/2026-09-28-agent-decision-room-design.md`

## Global Constraints

- Stage 1 remains paper-only; no Robinhood order, cancel, exercise, transfer or money-moving capability may be added.
- Preserve the real-order default-deny regression and all approval, cash, holdings, volatility, freshness and position risk checks.
- Keep `#activity` as the compatible deep link even though navigation copy becomes “Decision room.”
- Show structured work products, sources and uncertainty; never expose private chain-of-thought, prompts, secrets, raw authenticated payloads or unmasked account identifiers.
- Never infer a candidate state by parsing prose. Missing historical structure must render as “Not recorded.”
- Use no framework, chart library, remote font, CDN, external asset host or new persistent service.
- Use server-rendered HTML, local CSS, small local JavaScript and inline/local SVG only.
- Default to the latest review; do not render twenty complete review cards at once.
- The Risk Engine must be visually and semantically distinct from Research, Portfolio and Critic.
- Status must use text plus shape/icon, never color alone.
- Body copy is at least 16px with at least 1.5 line height; interactive targets are at least 44×44px with 8px separation on phones.
- Verify 375px, 768px, 1024px and 1440px layouts with no page-level horizontal overflow.
- Preserve loopback and exact Tailnet host/origin protections, CSRF behavior, escaping and same-origin-only browser requests.
- Auto-refresh must not steal focus and must preserve valid review, stage and lane selection.

## Review Focus

- A malformed or hostile trace value must fail soft, remain escaped and never prevent the rest of the dashboard from rendering; Task 1 and Task 3 pin this behavior.
- One instrument appearing in several stage records must resolve to one highest-precedence state (`proposed`, `blocked`, `rejected`, `advanced`, `reviewed`) without crossing lanes; Task 1 and Task 2 pin this behavior.
- Retries and out-of-order writes must not duplicate entities or reverse the logical flow; Task 1 pins stage consolidation and ordering.
- An auto-refresh during a selected historical review must restore that review/stage/lane if they still exist and announce a fallback when they do not; Task 4 pins this behavior.
- Long option identifiers, long reason text and large source lists must wrap inside a 375px viewport without hiding controls or causing page-level horizontal scroll; Task 5 and Task 6 pin this behavior.

---

## File structure

- Create `agents/decision_room.py` — validate, normalize and project append-only trace records into ordered review/stage/lane view models.
- Modify `agents/dashboard.py` — read trace row metadata, call the decision-room projection and expose it under `state['decision_room']`.
- Modify `agents/daily_cycle.py` — emit public structured candidate decisions and a deterministic `risk_evaluated` event.
- Modify `agents/dashboard_view.py` — render the review header, stage flow, selection board, inspector, technical record and mobile navigation.
- Create `agents/static/decision-room.js` — review/stage/lane selection, session preservation and accessible status announcement.
- Modify `agents/static/dashboard.js` — call the decision-room initializer after existing view navigation and before auto-refresh.
- Modify `agents/static/dashboard.css` — apply the approved tokens, desktop flow, vertical phone stepper, selection rows and four-item mobile navigation.
- Modify `agents/inbox_web.py` — serve the new local JavaScript asset with the existing CSP and cache policy.
- Modify `tests/test_dashboard.py` — projection-to-HTML, escaping, semantics, honest fallbacks and integrated dashboard contracts.
- Create `tests/test_decision_room.py` — focused projection and candidate precedence tests.
- Modify `tests/test_daily_cycle.py` — future trace contract and deterministic risk-event tests.
- Modify `tests/test_dashboard_resources.py` — asset availability and repeated-refresh leak coverage for the new script.
- Modify `tests/test_stage1_robinhood_policy.py` — add `test_stage1_policy_denies_every_real_write_capability`, asserting denial of order placement, cancellation, replacement, option exercise, transfers and money movement.
- Modify `outputs/dashboard-guide.md` — explain the Decision room in non-technical language after behavior is verified.

### Task 1: Ordered decision-room projection

**Files:**
- Create: `agents/decision_room.py`
- Modify: `agents/dashboard.py:80-110,188-205,320-326`
- Create: `tests/test_decision_room.py`
- Modify: `tests/test_dashboard.py:55-105`

**Interfaces:**
- Consumes: trace records shaped as `{payload fields..., '_row_id': int, '_created_at': str}` plus approval cards from `PaperInbox.cards()`.
- Produces: `project_decision_room(records: list[dict], cards: list[dict]) -> list[dict]`, returning newest-first reviews with `review_id`, `timestamp`, `status`, `data_mode`, `stages`, `lanes`, `default_stage`, `outcome`, `technical_events`.
- Produces: `normalize_candidate_decisions(events: list[dict]) -> dict[str, list[dict]]`, keyed by lane `A` and `B`.

- [ ] **Step 1: Write failing projection tests**

```python
from agents.decision_room import project_decision_room


def test_projects_logical_stage_order_and_created_at_fallback():
    records = [
        {'trace_id':'c1','event':'stage_completed','role':'critic',
         '_row_id':5,'_created_at':'2026-09-28T14:00:05+00:00',
         'output':{'counterargument':'Check liquidity.','rejected_instruments':['OPT-1']}},
        {'trace_id':'c1','event':'cycle_started','_row_id':1,
         '_created_at':'2026-09-28T14:00:00+00:00'},
        {'trace_id':'c1','event':'risk_evaluated','_row_id':6,
         '_created_at':'2026-09-28T14:00:06+00:00','status':'blocked',
         'candidate_decisions':[{'instrument':'OPT-1','lane':'B','state':'blocked',
             'reason_code':'stale_quote','reason':'Current option quote is unavailable.',
             'source_refs':[]}]},
    ]
    review = project_decision_room(records, [])[0]
    assert [stage['key'] for stage in review['stages']] == [
        'evidence','research','portfolio','critic','risk','final'
    ]
    assert review['timestamp'] == '2026-09-28T14:00:06+00:00'
    assert review['lanes']['B'][0]['state'] == 'blocked'


def test_candidate_precedence_never_parses_prose_or_crosses_lanes():
    records = [{
        'trace_id':'c1','event':'stage_completed','role':'research','_row_id':1,
        '_created_at':'2026-09-28T14:00:01+00:00',
        'output':{'summary':'VTI and OPT-1 are discussed only in prose.'},
        'candidate_decisions':[
            {'instrument':'VTI','lane':'A','state':'reviewed','reason_code':'compared',
             'reason':'Compared by Research.','source_refs':[]},
            {'instrument':'VTI','lane':'A','state':'advanced','reason_code':'strategy_signal',
             'reason':'Deterministic signal qualified.','source_refs':['signal:VTI']},
            {'instrument':'VTI','lane':'A','state':'proposed','reason_code':'portfolio_pick',
             'reason':'Portfolio proposed VTI.','source_refs':[]},
        ]}]
    review = project_decision_room(records, [])[0]
    assert [(row['instrument'], row['state']) for row in review['lanes']['A']] == [('VTI','proposed')]
    assert review['lanes']['B'] == []
```

Add tests in the same file for malformed candidate entries, unknown lanes/states, retry consolidation by stage key, awareness-required timestamps, hostile HTML text preservation for later escaping, pending-card outcome enrichment and the Review Focus precedence ordering.

- [ ] **Step 2: Run the projection tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_decision_room.py tests/test_dashboard.py::test_agent_activity_shows_structured_findings_not_hidden_reasoning`

Expected: FAIL because `agents.decision_room` and `project_decision_room` do not exist.

- [ ] **Step 3: Implement the normalized view model**

```python
# agents/decision_room.py
from __future__ import annotations
from datetime import datetime, timezone

STAGE_ORDER = ('evidence', 'research', 'portfolio', 'critic', 'risk', 'final')
STATE_PRIORITY = {'reviewed': 1, 'advanced': 2, 'rejected': 3, 'blocked': 4, 'proposed': 5}
VALID_LANES = {'A', 'B'}
REASON_LABELS = {
    'research_compared':'Compared by the Research Agent.',
    'strategy_signal':'A deterministic strategy signal advanced this candidate.',
    'portfolio_pick':'Proposed by the Portfolio Agent.',
    'critic_rejected':'Rejected by the Critic.',
    'current_quote_missing':'Current price evidence was unavailable.',
    'risk_blocked':'A deterministic risk rule blocked the proposal.',
    'not_recorded':'Reason not recorded.',
}
DECIDING_STAGE = {
    'reviewed':'Research Agent', 'advanced':'Evidence', 'proposed':'Portfolio Agent',
    'rejected':'Critic', 'blocked':'Risk Engine',
}


def _aware(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _stage_key(record):
    if record.get('event') in {'data_collected', 'strategy_evaluated'}:
        return 'evidence'
    if record.get('event') in {'stage_started', 'stage_completed'}:
        return record.get('role') if record.get('role') in {'research','portfolio','critic'} else None
    if record.get('event') == 'risk_evaluated':
        return 'risk'
    if record.get('event') == 'cycle_terminal':
        return 'final'
    return None


def normalize_candidate_decisions(events):
    chosen = {'A': {}, 'B': {}}
    for event in events:
        raw_rows = event.get('candidate_decisions') or []
        if not isinstance(raw_rows, list):
            continue
        for raw in raw_rows:
            if not isinstance(raw, dict):
                continue
            lane, state, instrument = raw.get('lane'), raw.get('state'), raw.get('instrument')
            if lane not in VALID_LANES or state not in STATE_PRIORITY or not isinstance(instrument, str) or not instrument:
                continue
            reason_code = raw.get('reason_code') if isinstance(raw.get('reason_code'), str) else 'not_recorded'
            reason = raw.get('reason') if isinstance(raw.get('reason'), str) and raw.get('reason') else REASON_LABELS.get(reason_code, REASON_LABELS['not_recorded'])
            refs = raw.get('source_refs') if isinstance(raw.get('source_refs'), list) else []
            item = {
                'instrument': instrument[:160], 'lane': lane, 'state': state,
                'reason_code': reason_code[:80], 'reason': reason[:1200],
                'deciding_stage': DECIDING_STAGE[state],
                'rank': raw.get('rank') if isinstance(raw.get('rank'), int) else None,
                'strategy_signal': raw.get('strategy_signal') if isinstance(raw.get('strategy_signal'), str) else None,
                'data_freshness': raw.get('data_freshness') if isinstance(raw.get('data_freshness'), str) else None,
                'source_refs': [ref[:240] for ref in refs if isinstance(ref, str)][:20],
            }
            prior = chosen[lane].get(instrument)
            if prior is None or STATE_PRIORITY[state] > STATE_PRIORITY[prior['state']]:
                chosen[lane][instrument] = item
    return {lane: sorted(items.values(), key=lambda row: (-STATE_PRIORITY[row['state']], row['rank'] if row['rank'] is not None else 10**9, row['instrument']))
            for lane, items in chosen.items()}
```

Add these exact stage definitions and projection rules:

```python
STAGE_META = {
    'evidence': ('Evidence', 'Collect read-only evidence and deterministic signals.'),
    'research': ('Research Agent', 'Compare supplied candidates and evidence.'),
    'portfolio': ('Portfolio Agent', 'Choose zero or more sized paper proposals.'),
    'critic': ('Critic', 'Challenge unsupported assumptions and selections.'),
    'risk': ('Risk Engine', 'Apply deterministic cash, holdings and risk rules.'),
    'final': ('Final outcome', 'Record the paper outcome and operator action.'),
}


def _event_time(record):
    return _aware(record.get('timestamp')) or _aware(record.get('_created_at'))


def _record_incomplete(record):
    return (('candidate_decisions' in record and not isinstance(record.get('candidate_decisions'), list)) or
            ('output' in record and not isinstance(record.get('output'), dict)) or
            ('payload' in record and not isinstance(record.get('payload'), dict)))


def _public_summary(record, key):
    output = record.get('output') if isinstance(record.get('output'), dict) else {}
    payload = record.get('payload') if isinstance(record.get('payload'), dict) else {}
    decision = payload.get('decision') if isinstance(payload.get('decision'), dict) else {}
    values = {
        'evidence': f"{record.get('quote_count', 0)} quotes and {record.get('volatility_count', 0)} volatility series recorded.",
        'research': output.get('summary'),
        'portfolio': output.get('reason'),
        'critic': output.get('counterargument'),
        'risk': 'Deterministic risk checks completed.' if record.get('status') == 'completed' else 'Deterministic risk checks did not run.',
        'final': payload.get('reason') or decision.get('reason'),
    }
    return str(values.get(key) or 'Not recorded')[:2000]


PUBLIC_DETAIL_FIELDS = {
    'evidence': ('read_tools','quote_count','volatility_count','history_counts','signals','blocked'),
    'research': ('summary','compared_symbols','news_checked','news','missing_evidence'),
    'portfolio': ('picks','reason'),
    'critic': ('counterargument','rejected_instruments'),
    'risk': ('status','results','real_execution'),
    'final': ('status','results','reason','api_cost_estimate_usd','completed_at'),
}


def _public_details(record, key):
    if key in {'research','portfolio','critic'}:
        source = record.get('output')
    elif key == 'final':
        source = record.get('payload')
    else:
        source = record
    if not isinstance(source, dict):
        return {}
    return {field: source[field] for field in PUBLIC_DETAIL_FIELDS[key] if field in source}


def project_decision_room(records, cards):
    groups = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        cycle_id = record.get('trace_id')
        if not isinstance(cycle_id, str) or not cycle_id:
            continue
        groups.setdefault(cycle_id, []).append(record)
    pending_by_id = {card['id']: card for card in cards
                     if isinstance(card, dict) and isinstance(card.get('id'), str)}
    reviews = []
    for cycle_id, events in groups.items():
        ordered = sorted(events, key=lambda item: (_event_time(item) or datetime.min.replace(tzinfo=timezone.utc), item.get('_row_id', 0)))
        latest = {}
        for event in ordered:
            key = _stage_key(event)
            if key:
                latest[key] = ({**latest[key], **event}
                               if key == 'evidence' and key in latest else event)
        terminal = latest.get('final') or {}
        payload = terminal.get('payload') if isinstance(terminal.get('payload'), dict) else {}
        terminal_state = str(payload.get('status') or '').upper()
        last_recorded_step = max((STAGE_ORDER.index(key) + 1 for key in latest), default=0)
        terminal_recorded = 'final' in latest
        stages = []
        for step, key in enumerate(STAGE_ORDER, 1):
            event = latest.get(key)
            status = ('waiting' if event is None and not terminal_recorded and step > last_recorded_step else
                      'unavailable' if event is None else
                      'blocked' if key == 'final' and (terminal_state.startswith('FAILED') or terminal_state.startswith('NOT_ISSUED')) else
                      'blocked' if key == 'risk' and event.get('status') == 'blocked' else
                      'active' if event.get('event') == 'stage_started' else
                      'completed')
            label, mandate = STAGE_META[key]
            stages.append({'key':key,'step':step,'label':label,'mandate':mandate,
                           'status':status,'status_label':status.replace('_',' ').title(),
                           'tone':'warn' if status in {'blocked','unavailable'} else 'neutral',
                           'summary':_public_summary(event or {}, key),
                           'details':_public_details(event or {}, key)})
        payload_results = payload.get('results') if isinstance(payload.get('results'), list) else []
        result_ids = {item.get('card_id') for item in payload_results
                      if isinstance(item, dict) and isinstance(item.get('card_id'), str)}
        pending = [pending_by_id[key] for key in result_ids if key in pending_by_id and pending_by_id[key].get('status') == 'PENDING']
        lanes = normalize_candidate_decisions(ordered)
        default_stage = next((stage['key'] for stage in stages if stage['status'] in {'blocked','active','unavailable'}), 'final')
        recorded = [_event_time(event) for event in ordered if _event_time(event)]
        reviews.append({'review_id':cycle_id,'timestamp':max(recorded).isoformat() if recorded else None,
                        'status':str(payload.get('status') or 'unconfirmed').lower(),
                        'data_mode':next((event.get('data_mode') for event in reversed(ordered) if event.get('data_mode')), 'not_recorded'),
                        'stages':stages,'lanes':lanes,'default_stage':default_stage,
                        'record_incomplete':any(_record_incomplete(event) for event in ordered),
                        'outcome':{'pending_count':len(pending),'reason':_public_summary(terminal,'final')},
                        'technical_events':[{'event':event.get('event'),'timestamp':(_event_time(event).isoformat() if _event_time(event) else None)} for event in ordered]})
    return sorted(reviews, key=lambda review: _aware(review['timestamp']) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
```

Do not parse `summary`, `reason` or `counterargument` to synthesize candidate decisions. Add a test with `output={'summary':'safe','prompt':'secret','api_key':'secret'}` and assert that `summary` is retained while `prompt` and `api_key` are absent from the projected details.

In `dashboard_snapshot`, replace `inbox.store.read_json('local_traces')` with a read inside the existing database context:

```python
raw_activity = []
if 'local_traces' in tables:
    for row in db.execute('SELECT id,created_at,payload_json FROM local_traces ORDER BY id'):
        try:
            payload = json.loads(row['payload_json'])
        except (TypeError, json.JSONDecodeError):
            payload = {'event':'malformed','status':'unavailable'}
        if isinstance(payload, dict):
            raw_activity.append({**payload, '_row_id':row['id'], '_created_at':row['created_at']})
```

Return `decision_room=project_decision_room(raw_activity, cards)` and retain `activity` as a temporary alias during Task 3 so unrelated tests remain operable.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_decision_room.py tests/test_dashboard.py::test_agent_activity_shows_structured_findings_not_hidden_reasoning`

Expected: PASS; no malformed record prevents a valid review from projecting.

- [ ] **Step 5: Commit Task 1**

```bash
git add agents/decision_room.py agents/dashboard.py tests/test_decision_room.py tests/test_dashboard.py
git commit -m "feat: project structured decision room"
```

### Task 2: Emit structured candidate and risk events

**Files:**
- Modify: `agents/daily_cycle.py:38-65,215-330`
- Modify: `tests/test_daily_cycle.py:43-70`
- Modify: `tests/test_stage1_robinhood_policy.py`

**Interfaces:**
- Consumes: `choices`, `strategy_assessment['signals']`, typed `Research`, `Decision`, `Critique`, final refresh missing instruments and `apply_decision` results.
- Produces: `candidate_decisions(...) -> list[dict]` and one `risk_evaluated` trace event per completed risk phase.
- Produces trace candidate entries matching Task 1 fields: `instrument`, `lane`, `state`, `reason_code`, `reason`, optional `rank`, optional `strategy_signal`, `source_refs`.

- [ ] **Step 1: Write failing trace-contract tests**

```python
def test_fixture_trace_records_candidate_states_and_deterministic_risk(tmp_path):
    from agents.daily_cycle import run_fixture_cycle
    inbox, config = setup_runtime(tmp_path)
    result = run_fixture_cycle(inbox, config, datetime(2026,9,28,14,tzinfo=timezone.utc))
    events = [event for event in inbox.store.read_json('local_traces')
              if event.get('trace_id') == result['cycle_id']]
    risk = next(event for event in events if event['event'] == 'risk_evaluated')
    decisions = [decision for event in events for decision in event.get('candidate_decisions', [])]
    assert any(item['instrument'] == 'VTI' and item['lane'] == 'A' and item['state'] == 'proposed'
               for item in decisions)
    assert risk['real_execution'] == 'blocked'
    assert all(item['lane'] in {'A','B'} for item in decisions)
    assert all('reason_code' in item and 'reason' in item for item in decisions)


def test_prose_symbol_does_not_become_candidate_decision():
    from agents.daily_cycle import candidate_decisions
    rows = candidate_decisions([], {}, {'compared_symbols':[]},
                               {'picks':[], 'reason':'VTI sounds interesting'},
                               {'rejected_instruments':[], 'counterargument':'META may reverse'}, [], [])
    assert rows == []
```

Update the expected fixture event order to include `risk_evaluated` immediately before `cycle_terminal`. Add a named assertion that the Stage 1 policy still rejects `place_order`, `cancel_order`, option exercise and money-moving tools.

- [ ] **Step 2: Run the trace tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_daily_cycle.py::test_fixture_trace_records_candidate_states_and_deterministic_risk tests/test_daily_cycle.py::test_prose_symbol_does_not_become_candidate_decision tests/test_stage1_robinhood_policy.py`

Expected: FAIL because `candidate_decisions` and `risk_evaluated` do not exist.

- [ ] **Step 3: Implement deterministic candidate mapping**

```python
def candidate_decisions(choices, signals, research, decision, critic, missing, results):
    by_instrument = {str(choice['instrument']): choice for choice in choices
                     if isinstance(choice, dict) and choice.get('instrument') and choice.get('lane') in {'A','B'}}
    rows = []
    def add(instrument, state, code, reason, source_refs=()):
        candidate = by_instrument.get(str(instrument))
        if candidate:
            rows.append({'instrument':str(instrument),'lane':candidate['lane'],'state':state,
                         'reason_code':code,'reason':reason,
                         'data_freshness':f"{candidate['quote_age_seconds']:.0f} seconds old" if isinstance(candidate.get('quote_age_seconds'), (int,float)) else None,
                         'source_refs':list(source_refs)})
    for symbol in research.get('compared_symbols') or []:
        add(symbol,'reviewed','research_compared','Compared by the Research Agent.')
    for signal in signals or []:
        instrument = signal.get('instrument') if isinstance(signal, dict) else None
        add(instrument,'advanced','strategy_signal','A deterministic strategy signal advanced this candidate.',
            (f"signal:{instrument}",) if instrument else ())
    for pick in decision.get('picks') or []:
        if isinstance(pick, dict):
            add(pick.get('instrument'),'proposed','portfolio_pick',pick.get('thesis') or 'Proposed by the Portfolio Agent.')
    for symbol in critic.get('rejected_instruments') or []:
        add(symbol,'rejected','critic_rejected','Rejected by the Critic.')
    for symbol in missing or []:
        add(symbol,'blocked','current_quote_missing','Current price evidence was unavailable.')
    for result in results or []:
        if isinstance(result, dict) and result.get('status') == 'RISK_BLOCKED':
            reason = ', '.join(str(item) for item in result.get('reasons') or []) or 'A deterministic risk rule blocked the proposal.'
            add(result.get('ticker') or result.get('instrument'),'blocked','risk_blocked',reason)
    return rows
```

Call the helper with structured model fields only. Add candidate rows to deterministic strategy events with these exact calls:

```python
signal_rows = candidate_decisions(choices, strategy_assessment['signals'],
                                  {'compared_symbols':[]}, {'picks':[]},
                                  {'rejected_instruments':[]}, [], [])
strategy_blocked = {name: details.get('blocked', {})
                    for name, details in strategy_assessment['strategies'].items()}
trace_event('strategy_evaluated', signals=strategy_assessment['signals'],
            blocked=strategy_blocked, candidate_decisions=signal_rows)

refresh_rows = candidate_decisions(choices, [], {'compared_symbols':[]}, {'picks':[]},
                                   {'rejected_instruments':[]}, missing, [])
```

Refactor the existing nested `run(role, schema, request)` helper so it keeps populating `completed[role]`, emits `stage_started`, invokes the typed agent, and returns the typed output without emitting `stage_completed`:

```python
def run(role, schema, request):
    check_owner()
    model = getattr(config, role + '_model_name')
    name = {'research':'Research Agent','portfolio':'Portfolio Agent','critic':'Critic'}[role]
    agents.append(name)
    trace_event('stage_started', role=role, agent=name)
    agent = Agent(name=name, instructions=prompts.load(role,'hardening_v2').text,
                  model=CodexSDKModel(bridge,model), output_type=schema)
    output = Runner.run_sync(agent,json.dumps(request,default=str),max_turns=1).final_output
    completed[role] = output.model_dump(mode='json')
    return output
```

Replace the three existing inline requests with these named equivalents. Immediately after each `run()` call, build that role's rows and emit exactly one `stage_completed` event:

```python
research_request = {
    'symbols':sorted(config.risk.instrument_whitelist), 'now':observed_at.isoformat(),
    'candidates':model_candidates, 'strategy_assessment':strategy_assessment,
    'news_enabled':False,
}
research = run('research', Research, research_request)
research_rows = candidate_decisions(choices, [], completed['research'], {'picks':[]},
                                    {'rejected_instruments':[]}, [], [])
trace_event('stage_completed', role='research', agent='Research Agent',
            output=completed['research'], candidate_decisions=research_rows)

portfolio_request = {
    'research':research.model_dump(mode='json'), 'market_open':market_open,
    'eligible_instruments':eligible, 'strategy_signals':strategy_assessment['signals'],
    'candidates':model_candidates, 'paper_accounts':accounts,
}
decision = run('portfolio', Decision, portfolio_request)
portfolio_rows = candidate_decisions(choices, [], {'compared_symbols':[]},
                                     completed['portfolio'], {'rejected_instruments':[]}, [], [])
trace_event('stage_completed', role='portfolio', agent='Portfolio Agent',
            output=completed['portfolio'], candidate_decisions=portfolio_rows)

critic_request = {
    'research':research.model_dump(mode='json'),
    'decision':decision.model_dump(mode='json'), 'market_open':market_open,
    'eligible_instruments':eligible, 'strategy_signals':strategy_assessment['signals'],
}
critic = run('critic', Critique, critic_request)
critic_rows = candidate_decisions(choices, [], {'compared_symbols':[]}, {'picks':[]},
                                  completed['critic'], [], [])
trace_event('stage_completed', role='critic', agent='Critic',
            output=completed['critic'], candidate_decisions=critic_rows)
```

Attach `refresh_rows` to the existing `final_refresh` event as `candidate_decisions=refresh_rows`. After `apply_decision`, compute `risk_rows = candidate_decisions(choices, [], {'compared_symbols':[]}, {'picks':[]}, {'rejected_instruments':[]}, [], results)` and emit:

```python
trace_event('risk_evaluated', status='completed', results=results,
            real_execution='blocked', candidate_decisions=risk_rows)
```

On market-closed reviews, emit `risk_evaluated` with `status='not_run'`, `real_execution='blocked'` and an empty decision list so the Risk stage remains truthful.

- [ ] **Step 4: Run trace and safety tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_daily_cycle.py tests/test_stage1_robinhood_policy.py tests/test_decision_room.py`

Expected: PASS; the trace records structured states and real write tools remain blocked.

- [ ] **Step 5: Commit Task 2**

```bash
git add agents/daily_cycle.py tests/test_daily_cycle.py tests/test_stage1_robinhood_policy.py
git commit -m "feat: trace candidate and risk decisions"
```

### Task 3: Render semantic Decision room HTML

**Files:**
- Modify: `agents/dashboard_view.py:9-35,188-205,240-282`
- Modify: `tests/test_dashboard.py:55-105,585-615`

**Interfaces:**
- Consumes: `state['decision_room']` from Task 1.
- Produces: `decision_room_view(reviews: list[dict]) -> str`, `decision_stage_view(review_index: int, stage: dict, active: bool) -> str`, `selection_board_view(review_index: int, lanes: dict) -> str`.
- Produces stable attributes consumed by Task 4: `data-review`, `data-review-choice`, `data-stage-choice`, `data-stage-panel`, `data-lane-choice`, `data-lane-panel`, `data-decision-room-status`.

- [ ] **Step 1: Write failing semantic-render tests**

```python
def test_decision_room_renders_entities_flow_selections_and_honest_fallbacks(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)
    with serving(inbox) as url:
        page = read(url + '/#activity')
    activity = page.split('data-view="activity"',1)[1].split('data-view="history"',1)[0]
    assert 'Decision room' in activity
    assert 'aria-label="Review flow"' in activity
    assert [activity.index(label) for label in ('Evidence','Research Agent','Portfolio Agent','Critic','Risk Engine','Final outcome')] == sorted(
        activity.index(label) for label in ('Evidence','Research Agent','Portfolio Agent','Critic','Risk Engine','Final outcome'))
    assert 'Lane A · Stocks &amp; ETFs' in activity
    assert 'Lane B · Defined-risk options' in activity
    assert 'data-decision-state="proposed"' in activity
    assert 'Structured work products are shown. Private chain-of-thought is not recorded.' in activity
    assert '<script>bad()</script>' not in activity
    assert '&lt;script&gt;bad()&lt;/script&gt;' in activity


def test_historical_review_does_not_invent_unrecorded_selection_details(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    inbox.store.append_json('local_traces', {
        'trace_id':'historic','event':'stage_completed','role':'research',
        'output':{'summary':'VTI mentioned in prose','compared_symbols':['VTI']}})
    with serving(inbox) as url:
        page = read(url + '/#activity')
    assert 'Detailed selection states were not recorded for this review.' in page
    assert 'data-decision-state="proposed"' not in page
```

Add tests for pending approval action, failed boundary, risk reason translation, one visible review by default, ordered-list semantics, one H1, sequential headings and distinct `data-entity-kind="agent"` versus `data-entity-kind="deterministic"`.

Create the fixture helper in `tests/test_dashboard.py` rather than production code:

```python
def seed_decision_room_trace(inbox):
    common = {'trace_id':'cycle-room-1','data_mode':'live_readonly'}
    events = [
        {**common,'event':'data_collected','timestamp':NOW.isoformat(),'quote_count':14,'volatility_count':14},
        {**common,'event':'stage_completed','role':'research','timestamp':(NOW+timedelta(seconds=2)).isoformat(),
         'output':{'summary':'Compared the eligible universe.','compared_symbols':['VTI'],'missing_evidence':[]},
         'candidate_decisions':[{'instrument':'VTI','lane':'A','state':'reviewed','reason_code':'research_compared','reason':'Compared by Research.','source_refs':[]}]},
        {**common,'event':'stage_completed','role':'portfolio','timestamp':(NOW+timedelta(seconds=4)).isoformat(),
         'output':{'reason':'VTI advanced.','picks':[{'instrument':'VTI'}]},
         'candidate_decisions':[{'instrument':'VTI','lane':'A','state':'proposed','reason_code':'portfolio_pick','reason':'Broad-market paper proposal.','source_refs':['signal:VTI']}]},
        {**common,'event':'stage_completed','role':'critic','timestamp':(NOW+timedelta(seconds=5)).isoformat(),
         'output':{'counterargument':'Confirm price freshness.','rejected_instruments':[]}},
        {**common,'event':'risk_evaluated','timestamp':(NOW+timedelta(seconds=6)).isoformat(),'status':'completed','real_execution':'blocked'},
        {**common,'event':'cycle_terminal','timestamp':(NOW+timedelta(seconds=7)).isoformat(),
         'payload':{'status':'COMPLETED','reason':'Paper proposal created.','results':[]}},
    ]
    for event in events:
        inbox.store.append_json('local_traces', event)
```

- [ ] **Step 2: Run render tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py -k 'decision_room or historical_review or agent_activity'`

Expected: FAIL because the page still renders `activity-cycle` cards and has no Decision room structure.

- [ ] **Step 3: Implement the review header and ordered flow**

```python
def decision_stage_view(review_index, stage, active=False):
    selected = 'true' if active else 'false'
    kind = 'deterministic' if stage['key'] in {'evidence','risk','final'} else 'agent'
    panel_id = f'review-{review_index}-stage-{stage["key"]}'
    return f'''<li class="decision-stage" data-stage="{esc(stage['key'])}" data-entity-kind="{kind}">
      <button type="button" data-stage-choice="{esc(stage['key'])}" aria-pressed="{selected}" aria-controls="{panel_id}">
        <span class="stage-step" aria-hidden="true">{esc(stage['step'])}</span>
        <span><strong>{esc(stage['label'])}</strong><small>{esc(stage['mandate'])}</small></span>
        {text_badge(stage['status_label'], stage['tone'])}
      </button>
    </li>'''


def decision_room_view(reviews):
    if not reviews:
        return '<div class="empty"><h3>No reviews recorded yet</h3><p>The next eligible review will show each handoff here.</p><a href="/#controls">Check readiness</a></div>'
    options = ''.join(f'<option value="{esc(review["review_id"])}">{esc(when(review.get("timestamp")))} · {esc(review["status"].replace("_"," ").title())}</option>' for review in reviews)
    panels = []
    for index, review in enumerate(reviews):
        stages = ''.join(decision_stage_view(index, stage, stage['key'] == review['default_stage']) for stage in review['stages'])
        inspector = ''.join(stage_inspector_view(index, stage, stage['key'] == review['default_stage'])
                            for stage in review['stages'])
        attention = ('<a class="button" href="/#decisions">Review pending approval</a>'
                     if review['outcome']['pending_count'] else '')
        incomplete = ('<p class="notice warn">Activity record incomplete. Unsafe or malformed fields were omitted.</p>'
                      if review['record_incomplete'] else '')
        panels.append(f'''<article data-review="{esc(review['review_id'])}" data-default-stage="{esc(review['default_stage'])}" {'hidden' if index else ''}>
          <header class="review-header"><div><h3>{esc(when(review.get('timestamp')))}</h3><p>{esc(review['outcome']['reason'])}</p></div><div>{text_badge(review['status'].replace('_',' ').title())}{attention}</div></header>
          {incomplete}
          <ol class="decision-flow" aria-label="Review flow">{stages}</ol>
          <div class="decision-layout"><div>{selection_board_view(index, review['lanes'])}</div><aside class="stage-inspector">{inspector}</aside></div>
          <details><summary>Inspect technical record</summary><pre>{esc(json.dumps(review['technical_events'], indent=2))}</pre></details>
        </article>''')
    return f'''<div data-decision-room><label for="review-choice">Review</label><select id="review-choice" data-review-choice>{options}</select>
      <p class="privacy-note">Structured work products are shown. Private chain-of-thought is not recorded.</p>
      <p class="sr-only" data-decision-room-status aria-live="polite"></p>{''.join(panels)}</div>'''
```

Use semantic `<ol aria-label="Review flow">`, actual buttons, `<section aria-labelledby>`, `<dl>` for facts and `<details>` for technical output. Replace old `activity_event_view` / `activity_cycle_view` primary rendering; keep no hidden duplicate event wall.

Render only the allowlisted `stage['details']` fields in the inspector:

```python
def stage_inspector_view(review_index, stage, active=False):
    panel_id = f'review-{review_index}-stage-{stage["key"]}'
    heading_id = f'{panel_id}-heading'
    facts = []
    for key, value in stage['details'].items():
        label = key.replace('_',' ').title()
        rendered = (json.dumps(value, indent=2, default=str)
                    if isinstance(value, (dict,list)) else str(value))
        facts.append(f'<div><dt>{esc(label)}</dt><dd><pre>{esc(rendered)}</pre></dd></div>')
    body = ''.join(facts) or '<div><dt>Recorded detail</dt><dd>Not recorded</dd></div>'
    return f'''<section id="{panel_id}" data-stage-panel="{esc(stage['key'])}" aria-labelledby="{heading_id}" {'' if active else 'hidden'}>
      <h3 id="{heading_id}">{esc(stage['label'])}</h3><p>{esc(stage['summary'])}</p><dl>{body}</dl>
    </section>'''
```

Change navigation text and page title from “Agent activity” to “Decision room” while retaining `data-nav="activity"`, `data-view="activity"` and `#activity`.

- [ ] **Step 4: Implement the selection board and inspector**

```python
STATE_LABELS = {
    'proposed':'Proposed', 'advanced':'Advanced', 'blocked':'Blocked',
    'rejected':'Rejected', 'reviewed':'Reviewed',
}

def decision_row_view(row):
    return f'''<article class="decision-row" data-decision-state="{esc(row['state'])}">
      <div><strong>{esc(row['instrument'])}</strong>{text_badge(STATE_LABELS[row['state']])}</div>
      <p>{esc(row['reason'])}</p>
      <dl><div><dt>Decided by</dt><dd>{esc(row.get('deciding_stage') or 'Not recorded')}</dd></div>
          <div><dt>Evidence</dt><dd>{len(row.get('source_refs') or []) or 'Not recorded'}</dd></div></dl>
    </article>'''


GROUP_ORDER = ('proposed','advanced','blocked','rejected','reviewed')
LANE_LABELS = {'A':'Lane A · Stocks & ETFs', 'B':'Lane B · Defined-risk options'}


def selection_board_view(review_index, lanes):
    tabs = ''.join(
        f'<button type="button" data-lane-choice="{lane}" aria-pressed="{"true" if lane == "A" else "false"}">{esc(LANE_LABELS[lane])}</button>'
        for lane in ('A','B'))
    panels = []
    structured_count = sum(len(lanes.get(lane) or []) for lane in ('A','B'))
    for lane in ('A','B'):
        rows = lanes.get(lane) or []
        groups = []
        for state in GROUP_ORDER:
            state_rows = [row for row in rows if row.get('state') == state]
            if not state_rows and state != 'proposed':
                continue
            body = ''.join(decision_row_view(row) for row in state_rows)
            if not state_rows:
                body = '<p class="empty-group">No paper proposal from this review.</p>'
            group_id = f'review-{review_index}-{lane}-{state}'
            groups.append(f'<section aria-labelledby="{group_id}"><h4 id="{group_id}">{esc(STATE_LABELS[state])}</h4>{body}</section>')
        panels.append(f'<div data-lane="{lane}" data-lane-panel="{lane}" {"" if lane == "A" else "hidden"}><h3>{esc(LANE_LABELS[lane])}</h3>{"".join(groups)}</div>')
    notice = '' if structured_count else '<p class="historical-notice">Detailed selection states were not recorded for this review.</p>'
    return f'<section class="selection-board"><h2>Selections</h2><div class="selection-tabs" role="group" aria-label="Trading lane">{tabs}</div>{notice}{"".join(panels)}</section>'
```

The fixed visible order is Proposed, Advanced, Blocked, Rejected, Reviewed; empty groups stay hidden except Proposed. Render “Not recorded” for unsupported fields and the historical-detail notice when no structured decisions exist.

- [ ] **Step 5: Run server-rendered dashboard tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py tests/test_decision_room.py`

Expected: PASS; hostile content is escaped and the latest review is understandable without technical JSON.

- [ ] **Step 6: Commit Task 3**

```bash
git add agents/dashboard_view.py tests/test_dashboard.py
git commit -m "feat: render agent decision room"
```

### Task 4: Local interaction and mobile navigation

**Files:**
- Create: `agents/static/decision-room.js`
- Modify: `agents/static/dashboard.js:1-76`
- Modify: `agents/dashboard_view.py:23-31`
- Modify: `agents/inbox_web.py:43-58`
- Modify: `tests/test_dashboard.py:621-759`
- Modify: `tests/test_dashboard_resources.py:25-68`

**Interfaces:**
- Consumes the data attributes from Task 3.
- Produces: `window.ShadowDecisionRoom.init(root, storage)` in browsers and `module.exports = {chooseReview, chooseStage, chooseLane, init}` in Node tests.
- Persists only identifiers `shadow-review`, `shadow-stage`, `shadow-lane` in `sessionStorage`; no market, account or browsing data is stored.

- [ ] **Step 1: Write failing interaction tests**

```javascript
const assert = require('node:assert/strict');
const room = require('./agents/static/decision-room.js');

const state = room.chooseStage({available:['evidence','research','risk'], selected:'research'}, 'risk');
assert.equal(state.selected, 'risk');
assert.deepEqual(room.chooseLane({available:['A','B'], selected:'A'}, 'B'), {available:['A','B'], selected:'B'});
assert.equal(room.chooseReview({available:['latest','older'], selected:'older'}, 'missing').selected, 'latest');
```

Add a DOM harness test that confirms review/stage/lane panels and `aria-pressed` update together, invalid stored identifiers fall back to latest/first-blocked, the status live region announces fallback, and initialization never calls `fetch`.

Extend the repeated-resource test to request `/assets/decision-room.js` 150 times with JavaScript MIME type.

- [ ] **Step 2: Run interaction/resource tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py -k 'decision_room_interaction or mobile_navigation' tests/test_dashboard_resources.py`

Expected: FAIL because the new asset and interaction API do not exist.

- [ ] **Step 3: Implement pure selection reducers and DOM binding**

```javascript
'use strict';
(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ShadowDecisionRoom = api;
})(typeof window === 'undefined' ? {} : window, function() {
  const choose = (state, requested) => ({...state,
    selected: state.available.includes(requested) ? requested : state.available[0]});
  const chooseReview = choose;
  const chooseStage = choose;
  const chooseLane = choose;
  function init(root, storage) {
    if (!root) return;
    const status = root.querySelector('[data-decision-room-status]');
    const read = key => { try { return storage.getItem(`shadow-${key}`); } catch (_) { return null; } };
    const write = (key, value) => { try { storage.setItem(`shadow-${key}`, value); } catch (_) {} };
    const activate = (scope, key, requested) => {
      const direct = Array.from(scope.querySelectorAll(`[data-${key}]`));
      const panels = Array.from(scope.querySelectorAll(`[data-${key}-panel]`));
      const choices = Array.from(scope.querySelectorAll(`[data-${key}-choice]`));
      const choiceValue = node => node.dataset[`${key}Choice`];
      const available = key === 'review'
        ? direct.map(node => node.dataset[key]).filter(Boolean)
        : choices.map(choiceValue).filter(Boolean);
      const selected = choose({available, selected:available[0]}, requested).selected;
      const targets = key === 'review' ? direct : panels;
      targets.forEach(node => {
        const value = key === 'review' ? node.dataset[key] : node.dataset[`${key}Panel`];
        node.hidden = value !== selected;
      });
      if (key !== 'review') choices.forEach(node =>
        node.setAttribute('aria-pressed', String(choiceValue(node) === selected)));
      write(key, selected);
      return selected;
    };
    const currentReview = () => root.querySelector('[data-review]:not([hidden])');
    const activateWithinReview = (panel, key, requested) => activate(panel, key, requested);
    const reviewChoice = root.querySelector('[data-review-choice]');
    const requestedReview = read('review');
    const selectedReview = activate(root, 'review', requestedReview);
    if (reviewChoice) reviewChoice.value = selectedReview;
    let panel = currentReview();
    const requestedStage = read('stage') || panel?.dataset.defaultStage;
    const selectedStage = panel ? activateWithinReview(panel, 'stage', requestedStage) : null;
    const requestedLane = read('lane') || 'A';
    const selectedLane = panel ? activateWithinReview(panel, 'lane', requestedLane) : null;
    if (status && ((requestedReview && requestedReview !== selectedReview) ||
                   (requestedStage && requestedStage !== selectedStage) ||
                   (requestedLane && requestedLane !== selectedLane))) {
      status.textContent = 'Saved view was unavailable. Showing the latest available review and stage.';
    }
    root.addEventListener('click', event => {
      const stage = event.target.closest('[data-stage-choice]');
      const lane = event.target.closest('[data-lane-choice]');
      panel = currentReview();
      if (stage && panel?.contains(stage)) activateWithinReview(panel, 'stage', stage.dataset.stageChoice);
      if (lane && panel?.contains(lane)) activateWithinReview(panel, 'lane', lane.dataset.laneChoice);
    });
    reviewChoice?.addEventListener('change', () => {
      const selected = activate(root, 'review', reviewChoice.value);
      panel = currentReview();
      if (panel) {
        activateWithinReview(panel, 'stage', panel.dataset.defaultStage || 'final');
        activateWithinReview(panel, 'lane', read('lane') || 'A');
      }
      reviewChoice.value = selected;
      if (status) status.textContent = 'Review changed. Decision flow and selections updated.';
    });
  }
  return {chooseReview, chooseStage, chooseLane, init};
});
```

Implement `init` with event delegation scoped to `[data-decision-room]`. Never assign provider/user strings with `innerHTML`. Store only validated identifiers that already exist in the DOM. The current review’s first incomplete/blocked stage is its `data-default-stage`; otherwise select Final.

- [ ] **Step 4: Serve and initialize the new asset**

In `shell`, load the scripts in this order:

```html
<script src="/assets/decision-room.js" defer></script>
<script src="/assets/dashboard.js" defer></script>
```

In `dashboard.js`, initialize after navigation setup:

```javascript
const decisionRoom = document.querySelector('[data-decision-room]');
if (decisionRoom && window.ShadowDecisionRoom) {
  window.ShadowDecisionRoom.init(decisionRoom, window.sessionStorage);
}
```

Update `inbox_web.py` to allow exactly `dashboard.css`, `dashboard.js` and `decision-room.js`; retain local-file resolution, CSP and no-store headers.

- [ ] **Step 5: Replace wrapping phone navigation with four primary destinations**

Render Overview, Approvals and Decision room as direct links plus:

```html
<details class="more-nav"><summary>More</summary><div>
  <a data-nav="history" href="/#history">History</a>
  <a data-nav="results" href="/#results">Results</a>
  <a data-nav="controls" href="/#controls">Controls</a>
</div></details>
```

Keep all six direct links in the desktop rail by rendering a desktop nav and a phone nav with mutually exclusive media-query visibility. The disclosure uses native keyboard behavior and no custom focus trap.

- [ ] **Step 6: Run interaction and resource tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py tests/test_dashboard_resources.py`

Expected: PASS; no interaction performs a remote request or trading action.

- [ ] **Step 7: Commit Task 4**

```bash
git add agents/static/decision-room.js agents/static/dashboard.js agents/dashboard_view.py agents/inbox_web.py tests/test_dashboard.py tests/test_dashboard_resources.py
git commit -m "feat: add decision room interactions"
```

### Task 5: Apply the research-desk visual system and responsive flow

**Files:**
- Modify: `agents/static/dashboard.css:1-110`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_dashboard_resources.py`

**Interfaces:**
- Consumes semantic classes and data attributes from Task 3 and Task 4.
- Produces responsive layouts at the spec breakpoints and visible agent/deterministic distinctions without changing data or actions.

- [ ] **Step 1: Write failing CSS-contract tests**

```python
def test_decision_room_css_has_approved_tokens_and_phone_stepper():
    css = Path('agents/static/dashboard.css').read_text()
    for token in ('--canvas:#f3f6f4','--ink:#172a24','--forest:#245443',
                  '--evidence:#2f668c','--caution:#996a20','--failure:#a33f3f'):
        assert token in css.lower()
    assert '.decision-flow' in css
    assert '[data-entity-kind="deterministic"]' in css
    assert '@media(max-width:640px)' in css.replace(' ', '')
    assert 'prefers-reduced-motion:reduce' in css.replace(' ', '')


def test_decision_rows_wrap_unbroken_identifiers():
    css = Path('agents/static/dashboard.css').read_text()
    block = css.split('.decision-row',1)[1]
    assert 'overflow-wrap:anywhere' in block.replace(' ', '')
```

Add HTML contract assertions that phone nav targets are at least structurally separate, visual SVGs are `aria-hidden="true"`, and entity status remains present as text.

- [ ] **Step 2: Run CSS-contract tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py -k 'decision_room_css or decision_rows_wrap' tests/test_dashboard_resources.py`

Expected: FAIL because the approved tokens and decision-room selectors are absent.

- [ ] **Step 3: Implement tokens and desktop Decision room**

```css
:root{
  --canvas:#f3f6f4;--paper:#fff;--ink:#172a24;--forest:#245443;
  --evidence:#2f668c;--caution:#996a20;--failure:#a33f3f;
  --muted:#596963;--line:#d4ded9;--focus:#8a5b14;
}
.decision-flow{display:grid;grid-template-columns:repeat(6,minmax(144px,1fr));gap:18px;list-style:none;padding:0;margin:24px 0}
.decision-stage{position:relative;min-width:0}
.decision-stage:not(:last-child)::after{content:"";position:absolute;top:30px;left:calc(100% + 4px);width:10px;border-top:2px solid var(--line)}
.decision-stage button{width:100%;min-height:116px;text-align:left;justify-content:flex-start;align-items:flex-start}
.decision-stage[data-entity-kind="deterministic"] button{border-radius:2px;background:linear-gradient(90deg,transparent 23px,rgba(36,84,67,.06) 24px)}
.decision-layout{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(300px,.65fr);gap:24px}
.decision-row{overflow-wrap:anywhere;border-top:1px solid var(--line);padding:16px 0}
```

Do not use the generic dark/OLED result, gradients as decoration, shadows on every surface, fake avatars or animation on page load. If a subtle deterministic grid uses a CSS gradient, keep it functional and low contrast as shown above.

- [ ] **Step 4: Implement the phone stepper and navigation**

```css
@media(max-width:640px){
  .desktop-nav{display:none}.phone-nav{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
  .phone-nav a,.phone-nav summary{min-height:44px;display:grid;place-items:center;padding:8px}
  .decision-flow{display:grid;grid-template-columns:1fr;gap:0;margin-left:12px}
  .decision-stage{padding:0 0 18px 24px;border-left:2px solid var(--line)}
  .decision-stage:not(:last-child)::after{display:none}
  .decision-stage button{min-height:88px}
  .decision-layout{grid-template-columns:1fr}
  .review-header,.selection-tabs{align-items:stretch;flex-direction:column}
  .decision-row{max-width:100%;overflow-wrap:anywhere}
}
@media(prefers-reduced-motion:reduce){*{transition:none!important;scroll-behavior:auto!important}}
```

Keep base text at 16px/1.6, use `font-variant-numeric:tabular-nums` for times/costs and preserve the existing 3px visible focus ring.

- [ ] **Step 5: Run CSS and full dashboard tests and verify GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py tests/test_dashboard_resources.py tests/test_decision_room.py`

Expected: PASS; structural and style contracts are present.

- [ ] **Step 6: Commit Task 5**

```bash
git add agents/static/dashboard.css tests/test_dashboard.py tests/test_dashboard_resources.py
git commit -m "style: build responsive decision room"
```

### Task 6: Integrated accessibility, security and visual verification

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_inbox_web.py`
- Modify: `outputs/dashboard-guide.md`

**Interfaces:**
- Consumes the completed Decision room and existing local/Tailnet dashboard service.
- Produces fresh automated evidence plus inspected desktop and phone layouts.

- [ ] **Step 1: Add the final integration tests before any final fixes**

```python
import re


def test_decision_room_keeps_security_and_accessibility_contracts(tmp_path):
    inbox, _ = setup_runtime(tmp_path)
    seed_decision_room_trace(inbox)
    with serving(inbox) as url:
        page = read(url + '/#activity')
    room = page.split('data-view="activity"',1)[1].split('data-view="history"',1)[0]
    assert 'aria-live="polite"' in room
    assert '<ol' in room and 'aria-label="Review flow"' in room
    assert 'Private chain-of-thought is not recorded.' in room
    assert 'Real orders blocked' in page
    assert 'agentic-1' not in page
    assert re.search(r'<(?:script|img|link)[^>]+(?:src|href)="https?://', room) is None
```

Add a Tailnet-host request test using the exact configured host and HTTPS Origin, confirming `/assets/decision-room.js` receives 200 while an unconfigured host receives 403. Re-run the existing CSRF, origin, CSP, escaping and pause-control tests unchanged.

- [ ] **Step 2: Run the integration tests and verify RED or justified pre-existing GREEN**

Run: `.venv/bin/python -m pytest -q tests/test_dashboard.py::test_decision_room_keeps_security_and_accessibility_contracts tests/test_inbox_web.py`

Expected: PASS because Tasks 3–5 own the referenced behavior. Any failure returns to the owning task and requires a new focused failing test before a production fix.

- [ ] **Step 3: Update the operator guide**

Add this exact structure to `outputs/dashboard-guide.md`:

```markdown
## Decision room

Open **Decision room** to see the latest review from evidence collection through Research, Portfolio, Critic, deterministic risk checks and the final outcome. Select an entity to inspect its recorded work product. Use Lane A or Lane B to see which instruments were reviewed, advanced, rejected, blocked or proposed. “Not recorded” means the older run did not store that structured fact; it is not an error or an inferred answer.
```

Retain the paper-only and real-orders-blocked explanation.

- [ ] **Step 4: Run focused safety and dashboard verification**

Run:

```bash
.venv/bin/python -m pytest -q \
  tests/test_decision_room.py tests/test_dashboard.py tests/test_dashboard_resources.py \
  tests/test_inbox_web.py tests/test_daily_cycle.py tests/test_stage1_robinhood_policy.py
```

Expected: PASS with zero failures.

- [ ] **Step 5: Run the complete suite**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS with zero failures. Report all warnings and any skipped tests; do not hide unrelated failures.

- [ ] **Step 6: Restart only the dashboard service and verify both routes**

Run:

```bash
launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8765/#activity | rg -q 'Decision room'
curl --fail --silent --show-error --max-time 15 \
  https://tanmays-macbook-air.tail4c3ace.ts.net:8443/#activity | rg -q 'Decision room'
```

Expected: both commands exit 0; do not change or reset the unrelated port-443 Funnel configuration.

- [ ] **Step 7: Inspect the real UI at desktop and phone sizes**

Using the in-app browser, inspect `http://127.0.0.1:8765/#activity` at 1440×900 and 375×812. For each size, capture accessibility state and screenshot, then verify:

- one review dominates the page;
- the flow order is Evidence, Research, Portfolio, Critic, Risk, Final;
- agent and deterministic stages are visibly distinct;
- candidate rows remain inside the viewport;
- the phone nav exposes Overview, Approvals, Decision room and More;
- More exposes History, Results and Controls;
- keyboard-visible labels and paper-only status remain present;
- there is no page-level horizontal scroll (`document.documentElement.scrollWidth <= document.documentElement.clientWidth`).

Reset the temporary viewport override after inspection.

- [ ] **Step 8: Commit Task 6**

```bash
git add tests/test_dashboard.py tests/test_inbox_web.py outputs/dashboard-guide.md
git commit -m "test: verify decision room experience"
```

### Task 7: Final branch review and delivery

**Files:**
- Review all files changed by Tasks 1–6.
- Do not create functionality in this task; fixes require their own RED→GREEN evidence.

**Interfaces:**
- Consumes: the complete implementation, spec and task ledger.
- Produces: a final review package, resolved Critical/Important findings and a user-facing verification report.

- [ ] **Step 1: Build a review package from the merge base**

Run the `superpowers:executing-plans` or `superpowers:subagent-driven-development` review-package command selected at execution time with:

```text
Spec: docs/superpowers/specs/2026-09-28-agent-decision-room-design.md
Plan: docs/superpowers/plans/2026-09-28-agent-decision-room.md
Review focus: malformed traces, state precedence, retries/order, refresh selection, mobile overflow
```

Expected: one package containing the complete diff, test evidence and ledger rulings.

- [ ] **Step 2: Run one fresh whole-branch review**

Review for spec compliance, truthful data projection, security regression, accessibility, phone usability and maintainability. Sort findings as Critical, Important or Minor. Critical/Important findings require one test-first fix pass; Minor findings are recorded without scope expansion.

- [ ] **Step 3: Re-run final verification after review fixes**

Run:

```bash
.venv/bin/python -m pytest -q
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8765/#activity | rg -q 'Decision room'
```

Expected: zero test failures and a successful live dashboard probe.

- [ ] **Step 4: Deliver evidence without readiness overclaim**

Report:

- exact passing test count and warnings;
- real-order policy test result;
- desktop and 375px browser verification result;
- loopback and private Tailnet probe result;
- latest review’s available structured stages and any historical “Not recorded” limitations;
- files and commits changed;
- confirmation that this changes visibility only and does not authorize live trading.

Do not call the overall trading system unattended-ready solely because this UI upgrade passes.

## Plan self-review

- Spec coverage: every spec section maps to Tasks 1–6; final independent review is Task 7.
- Placeholder scan: every implementation step, error boundary and verification command is named explicitly.
- Type consistency: Task 1 defines the decision-room and candidate interfaces consumed unchanged by Tasks 2–5.
- Review Focus: all five listed failure classes have explicit tests in their owning tasks.
- Scope: one cohesive dashboard subsystem; no trading-strategy, broker-authority, scheduler or notification behavior is added.
