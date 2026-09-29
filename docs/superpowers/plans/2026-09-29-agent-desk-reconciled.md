# Agent Desk Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every paper decision accountable to a reconciled portfolio, complete evidence, deterministic sizing and an honest visible outcome.

**Architecture:** Preserve one official runner and the isolated eleven-read proxy. Repair costs and the Critic handoff first, then introduce transactional accounting and extract code-owned seats without adding autonomous manager models. New behavior stays unreachable on the primary until the operator approves its registration and deployment.

**Tech Stack:** Python, Pydantic, OpenAI Agents SDK, SQLite transactions/authorizer, existing local Agent Desk, pytest.

**Spec:** Active `preregistration.yaml` v1.4.2 and `docs/superpowers/specs/2026-09-28-intelligent-agentic-investment-organization-design.md`; reviewer direction `2026-09-29-agent-desk-final-plan.reference.md`; proposed amendments in `preregistration-v1.5.0.draft.yaml` (NOT active).

## Global Constraints

- Operator confirmed Claude's 12:10 ET six decisions on 2026-09-29 for the draft
  only. Task 1 branch work is authorized; primary deployment is not. Fractional
  paper equities: $1 minimum, 6 decimals; options whole contracts. One new entry
  per lane (2 total), unlimited required reductions/closes. No advisory rebuttal;
  reconsider only after 30 resolved official decisions and fresh approval.

- Task 1 development and draft updates only. No installed runtime, model, budget, config, DB or service changes.
- Read canonical `docs/review/CLAUDE_REVIEW.md` before each task. Prepend progress/questions to CODEX_STATUS after each checkpoint; inspect and push sanitized changes.
- Exactly one scheduled runner. Stage 1 paper only; real writes default-denied.
- Only Agentic account scope; no account identifiers in reports or UI.
- Scheduled proof is present (2026-09-29); shared-cost repair and separately verified revocation evidence still block blanket Phase 0 completion.
- Never rewrite today's official decision to make a repaired replay look successful.
- Preserve Research, Portfolio and Critic until a separately approved architecture amendment replaces one. Roster art cannot silently retire a registered stage.
- Exits/reductions precede new entries. Entry blocks never authorize an oversized close, fabricated quote or real order.
- Per-lane $500 paper capital is separate from the real Agentic snapshot and every evaluation arm.
- Broker order histories stay in health/tripwire code, never model context.
- Numeric policy in the active registration wins over this unapproved plan.

## Review Focus

1. Shared prompts contain common tokens and absent lanes; never charge a lane not represented (Task 1).
2. A stock invokes AI while an ETF signal is present; the ETF must remain outside AI voting (Task 2).
3. Old fills cannot reconstruct exact lots; never manufacture a cost basis (Task 3).
4. A halted/early-close session and stale option marks must not fabricate exit fills (Tasks 3/6).
5. A preview and a pulse race an official cycle; neither may acquire its claim or mutate its record (Tasks 4/6).

## Baseline and release gates

Read CODEX_STATUS for deployed composition and evidence. The reviewer export is
older: runtime relocation, UI deployment, dated transport and 624 passing tests
are already present. No repeat relocation or UI swap. `8766` is currently down;
starting it is a separate action, not implied by these documents.

Every task follows: failing regression -> minimal implementation -> focused
tests -> full suite -> independent review -> sanitized commit/push -> explicit
operator deployment approval. Use disposable databases. An isolated replay is
not an official rerun. Do not consume paid API budget without approval.

### Task 1: Shared-cost accounting and evidence closure

**Files:** create `agents/cost_allocation.py`, `tests/test_cost_allocation.py`;
modify `agents/bounded_inference.py`, `agents/budget.py`, `agents/daily_cycle.py`;
review `agents/readiness.py` and `docs/review/CODEX_STATUS.md`.

**Interface:** `allocate_cost(amount: Decimal, lane_tokens: dict[str, int]) -> dict[str, Decimal]`.
Input token counts come from the frozen per-lane candidate blocks; a represented
lane has at least one such block. Common prompt tokens are split equally among
represented lanes, with rounding remainder to the
lexicographically first lane. Save counts, tokenizer/model version, packet
hashes and shared-token policy. These are allocation weights, not invented API
billing usage; provider usage determines the total. Keep sub-cent precision.

- [ ] Write and run this failing test, plus zero/negative count rejection and no-B-data coverage:
  ```python
  def test_cost_conservation_and_weighting():
      assert allocate_cost(Decimal('0.04'), {'A': 300, 'B': 100}) == {
          'A': Decimal('0.03'), 'B': Decimal('0.01')}
  ```
- [ ] Persist allocation at each attempt, including schema repairs and uncertain
  charged attempts. Settle by explicit role/attempt IDs, never array position.
  Reserve per-lane worst-case before dispatch; if actual usage cannot be trusted,
  retain the bound. No cross-lane budget borrowing.
- [ ] Run `python -m pytest tests/test_cost_allocation.py tests/test_phase0_budget.py tests/test_bounded_inference.py -q`.
  Test duplicate settlement, process crash, unrepresented lane and all-common
  input. Assert allocated totals equal charged totals exactly.
- [ ] Request a sanitized performed-drill receipt from the proxy owner; do not
  bypass its OS identity or expose token fingerprints. Add a readiness regression
  so missing drill evidence cannot be masked by scheduled-cycle success.
- [ ] Full suite, review, commit `fix: reconcile shared inference cost attribution`;
  update status and push. Active registration unchanged.

### Task 2: SOXX handoff, explicit decisions and stabilization regressions

**Files:** create `agents/decision_packet.py`, `tests/test_decision_packet.py`;
modify `agents/daily_cycle.py`, `agents/decision_room.py`, `agents/inbox.py`,
`agents/inbox_web.py`, `agents/maintenance.py`; UI branch uses
`agents/desk/` existing view/render modules and matching tests.

**Interface:** `build_critic_packet(selection: dict, evidence: dict, paper_context: dict) -> dict`.
Allowlist fields: selection ID/direction/public thesis/exit plan, cited evidence,
lane identity, timestamped bid/ask, paper held/pending quantities, settled cash,
fractional policy, preliminary risk calculation and all calculation inputs.
Exclude Portfolio's reasoning/rationale and raw broker histories. Preliminary
quantity is non-executable; Risk recalculates after final quote/trigger/approval.

- [ ] Regression test:
  ```python
  def test_critic_is_informed_not_primed():
      packet = build_critic_packet(
          {'instrument': 'SOXX', 'reasoning': 'secret narrative'},
          {'bid': '560', 'ask': '561'},
          {'lane': 'A', 'fractional_allowed': True, 'settled_cash': '500'})
      assert 'secret narrative' not in json.dumps(packet)
      assert packet['paper_context']['fractional_allowed'] is True
  ```
- [ ] Add regressions proving ETF signals never enter an AI packet even when a
  separate stock causes AI invocation; META stock is Lane A; options require a
  contract ID and cannot migrate into A. Missing fractional policy is unknown,
  not an inferred permission. No Critic => no AI approval card.
- [ ] Record `CRITIC_VETO`, whitelist and duplicate-lane blocks separately; record
  sizing as `NOT_REACHED` after veto, not zero shares or a passed risk check.
  Legacy records expose the original Critic report without invented fields.
- [ ] Add exact Decimal fill test: midpoint 100, limit 100.50, ask 100.10,
  slippage .001 => fill 100.2001 if all risk/cash checks pass. Quantity includes
  slippage/fees, not ask-only affordability. Test over-limit and insufficient cash.
- [ ] Test exchange-close expiry including early close; GET leaves database digest
  unchanged; maintenance expires cards; approval-time validation rejects expired
  cards even if the timer has not run. Do not backdate or extend existing cards.
- [ ] Run packet, risk, inbox, cycle freshness and dashboard tests; full suite.
  Replay today's stored evidence in isolated mode with immutable parent ID;
  no new official claims/cards/fills/memory. Any new model call needs authorization.
- [ ] Review, commit `fix: expose complete blind decision context`; push; await
  operator release approval. Do not activate new Phase 1 decision policy here.

### Task 3: Transactional book

**Files:** create `data/ledger_schema.sql`, `agents/organization/ledger.py`,
`agents/organization/open_items.py`, `tests/test_ledger.py`; adapt `agents/inbox.py`
and `broker/paper.py` only on approved development branch.

**Interfaces:** `post_fill(db, fill: dict) -> str`, `print_book(db, lane: str, arm: str, run_mode: str) -> dict`.
All keyed rows carry lane/arm/run_mode; unique fill/order idempotency; lots store
options strike/expiry/type/multiplier. Tables: accounts, lots, marks, ledger_orders,
ledger_fills, pending_limits, open_items, cycle_receipts, handoffs. Use prefixed
tables where current append-only `orders`/`fills` would collide; migrate only via
explicit versioned transaction and rollback plan.

- [ ] Test atomic posting:
  ```python
  def test_missing_lot_rolls_back_close(book_db):
      before = print_book(book_db, 'A', 'agent_alone', 'official')
      with pytest.raises(ValueError, match='MISSING_LOT'):
          post_fill(book_db, {'side': 'sell', 'lot_id': 'absent'})
      assert print_book(book_db, 'A', 'agent_alone', 'official') == before
  ```
- [ ] Build disposable fixtures for buy, partial close, partial fill, duplicate
  order, worthless option expiry and ITM option without exercise funding.
  No synthetic exercise if marks or contract terms are missing: incident/open item.
- [ ] Implement NAV at bid with multiplier and explicit stale mark tags. Apply
  settlement, expiry, corporate actions, marks, then open items in that order;
  new risk requires current marks. Model processes have no ledger write API.
- [ ] Build a read-only reconstruction report. Exact provenance => proposed
  backfill; otherwise dated opening book with unreconstructed history retained.
  Operator chooses migration; never copy development DB over official DB.
- [ ] `python -m pytest tests/test_ledger.py -q`; include SQLite cross-mode
  authorizer and crash/rollback tests. Full suite, review, commit and push.

### Task 4: Seats and recorded handoffs (golden-equivalent extraction)

**Files:** create `agents/organization/{orchestrator,scout,quant,pm,critic,risk,card,execution,auditor}.py`,
`tests/test_organization.py`; modify `agents/daily_cycle.py`; UI-only roster in
`agents/desk/roster.py` on the UI branch. Separate package avoids collision with
the deployed UI overlay's existing `agents.desk` namespace.

**Interfaces:** `run_official_open(context: dict) -> dict`,
`record_handoff(db, event: dict) -> None`. Context contains run ID, mode,
registration hash and ledger snapshot reference, not secrets.

- [ ] Freeze fixture outcomes before extraction:
  ```python
  def test_seat_extraction_keeps_decisions(golden_context):
      assert run_official_open(golden_context)['decisions'] == golden_context['expected_decisions']
  ```
- [ ] Extract without changing decisions. Required code seat missing => terminal
  operational-hold receipt. Optional AI skipped => NOT_NEEDED, not failed.
- [ ] Each actual sender/recipient hop writes a sequenced event. UI edges use
  only recorded hops; legacy six-stage projections remain dashed and static.
  Store character names only in UI mapping/assets. No fictional role log keys.
- [ ] Keep Research as a registered stage within the conditional AI workflow;
  UI maps Pip to Research. Market data is a faceless code tool. Code Scout is
  never labelled LLM; the primary ranking-value experiment stays intact.
- [ ] Full golden replay, missing-seat and read-only UI tests; review/commit/push.

### Task 5: Arms, forecasts and holdings board

**Files:** create `eval/arms.py`, `eval/forecast_resolution.py`,
`agents/organization/holdings.py`, `tests/test_arms.py`, `tests/test_forecasts.py`;
extend `eval/scoreboard.py` and UI Book view.

**Interfaces:** `resolve_forecast(forecast: dict, observations: list[dict]) -> dict`,
`run_arm(arm: str, snapshot: dict, seed: str) -> dict`.

- [ ] Baseline test independent of Phase 2 backtests:
  ```python
  def test_baseline_probability_is_not_entry_gate(eligible_snapshot):
      result = run_arm('deterministic_no_ai', eligible_snapshot, 'fixed-seed')
      assert result['hypothetical_probability'] == '0.5'
      assert result['entry_allowed'] is True
  ```
  No registered gross-edge assumption is permitted. Registered spread/slippage/cash/
  liquidity/breaker gates remain mandatory, not bypassed with probability.
- [ ] Implement all eight registered arms using the same snapshots, risk and
  timestamps; API cost only AI arms. Record random seed and baseline 20-session
  or invalidation exit. No synthetic performance before sufficient data.
- [ ] Score every researched candidate, including rejected/abstained selections;
  use existing target definitions, shrinkage, Brier and concordance rules.
  Unresolvable => VOID_DATA, excluded from score but counted/paged above 5%.
- [ ] All held stock/options lots get HOLD/REDUCE/CLOSE evidence before new ideas;
  mandatory option DTE/moneyness/events review. No rolls. Block new entries when
  critical option fields are missing; retain safe exit handling and incidents.
- [ ] Preserve 12-month stop rule and shadow-only Kelly gates. Full suite,
  calibration/arm isolation review, commit and push. Release requires v1.5.

### Task 6: Code-only pulse

**Files:** create `agents/organization/pulse.py`, `tests/test_pulse.py`;
modify `agents/maintenance.py` and service schedule only after separate approval.

**Interfaces:** `run_pulse(context: dict) -> dict`, `run_close_sweep(context: dict) -> dict`,
`run_halt(context: dict) -> dict`.

- [ ] Test no second meeting:
  ```python
  def test_pulse_skips_active_official_claim(active_claim_context):
      result = run_pulse(active_claim_context)
      assert result['status'] == 'SKIPPED_OFFICIAL_ACTIVE'
      assert result['model_calls'] == 0
  ```
- [ ] Two-minute trading-session pulse only held/pending/armed-trigger marks;
  existing history/tripwire call caps unchanged. Never hold a DB transaction
  during network I/O. Receipts separate from official claim row.
- [ ] Execute only already-approved/rule-mandated paper actions, idempotently;
  discretionary new action creates a bounded approval request, no silent trade.
  Record origin and original decision run ID for every fill across arms.
- [ ] Close sweep at exchange close minus ten minutes, including early closes;
  expire cards at actual close. Sleeping/late/stale pulses display unknown/gaps,
  not healthy green or fabricated historical fills.
- [ ] Test pulse/approval/official race, holiday, early close, stale option mark,
  provider failure and crash retry. Full suite, review/commit/push; no power
  changes or service installation without operator approval.

### Task 7: Wide watch / narrow tradable universe

**Files:** create `research/universe.py`, `research/scanners/`,
`tests/test_universe.py`; extend approval-card schemas and Quant only after approval.

**Interface:** `admit_symbol(request: dict, evidence: dict, policy: dict) -> dict`.

- [ ] Test no implicit admission:
  ```python
  def test_scanner_pick_cannot_admit_itself():
      assert admit_symbol({'symbol': 'NEW', 'operator_approved': False}, {}, {})['status'] == 'APPROVAL_REQUIRED'
  ```
- [ ] Dated S&P 500 watch file plus core ETFs; current membership always labelled
  survivorship-biased for backtests unless verified point-in-time data exists.
  Seed tradable list remains unchanged until cards; proposed limits 1 admission
  per day and 25 names need policy approval. No LLM-minted symbols or social lists.
- [ ] Admission validates identity/history/spread/dollar-volume/sector/issuer/data
  budget, and rejects duplicate names. Removal needs flat holdings or linked exit.
- [ ] TradeLog-Pro integration is blocked until exact repository, license,
  scanner list, parameters and point-in-time input provenance are approved.
  No speculative clone/download/port now. Record source_scanner and tested variants.
- [ ] Full universe/admission/no-lookahead tests, review/commit/push; deployment
  requires an approved registration covering this phase.

## Later work, explicitly outside this release

Harsher fills/rolls follow reliable lots and pulse; Filings/News and scoped Ask/
Tune follow injection defenses, evidence/cost isolation and explicit approval.
Do not activate dark seats or add broker reads. Real-money execution is not
authorized by this plan. Review CODEX_STATUS questions before implementation.
