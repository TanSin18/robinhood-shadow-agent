# Robinhood AI Trading Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify Sections 1–8 of the v4 Robinhood AI Trading Agent with Stage 1 shadow mode and default-deny real-broker safety.

**Architecture:** A modular Python application coordinates three OpenAI Agents SDK roles, a deterministic risk engine, a broker protocol with paper and Robinhood adapters, SQLite persistence, evaluation/replay, and local observability adapters. All external dependencies sit behind injected interfaces so the complete safety and evaluation behavior is testable offline.

**Tech Stack:** Python 3.12+, Pydantic 2, OpenAI Agents SDK, SQLite, pytest, PyYAML, OpenTelemetry, optional Arize Phoenix and MLflow.

**Spec:** `docs/superpowers/specs/2026-09-27-robinhood-ai-trading-agent-design.md`

## Global Constraints

- Stage 1 shadow mode is the default and real order, cancel, exercise, transfer, money-moving, and unknown Robinhood tools are denied before invocation.
- Never request or persist passwords or verification codes.
- All model outputs use Pydantic validation; retry once, then log and skip.
- All prompts are immutable versioned files; decision records include prompt versions, model, and config hash.
- All v4 risk values live in one editable config file and the LLM cannot override verdicts.
- SQLite application paths are append-only; history is never deleted.
- No functionality is reported working without a passing behavior test.
- Starting cash remains unset until the operator edits config; samples use labeled mock values.

## Review Focus

- A newly added Robinhood write tool must remain blocked because the policy is exact-allowlist/default-deny; Task 3 tests an unknown tool.
- Timestamps with time zones around quote freshness and replay cutoffs must not admit future/stale data; Tasks 4 and 8 use UTC-aware boundaries.
- Restarting after a persisted order must not place a duplicate; Tasks 5 and 9 exercise idempotency.
- Option expiry must not create cash or naked exposure outside the modeled contract multiplier; Task 5 checks ITM and OTM outcomes.
- API spend must be subtracted exactly once from every scoreboard line; Task 7 tests literal expected totals.

---

### Task 1: Project foundation, config, and schemas

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `README.md`, `config/settings.yaml`
- Create: `agents/schemas.py`, `config/loader.py`, package `__init__.py` files
- Test: `tests/test_config_and_schemas.py`

**Interfaces:**
- Produces: `AppConfig`, `RiskConfig`, `EvidenceItem`, `ResearchPacket`, `TradeProposal`, `CriticOutput`, `DecisionRecord`, and `load_config(path)`.

- [ ] Write failing tests proving Stage 1/paper defaults, missing starting cash blocks runtime validation, config hashes are stable, confidence is bounded, and malformed structured fields fail.
- [ ] Run `pytest tests/test_config_and_schemas.py -q`; expect import failures for the not-yet-created modules.
- [ ] Implement typed schemas and YAML loading with `Decimal` monetary values and UTC-aware timestamps.
- [ ] Run the focused test and the complete suite; expect all green.
- [ ] Commit foundation and record the task result in the execution ledger.

### Task 2: SQLite append-only repository and versioned prompts

**Files:**
- Create: `data/store.py`, `data/schema.sql`
- Create: `prompts/research_v1.md`, `prompts/portfolio_v1.md`, `prompts/critic_v1.md`, `prompts/registry.py`
- Test: `tests/test_store_and_prompts.py`

**Interfaces:**
- Consumes: Task 1 schemas.
- Produces: `SQLiteStore`, `PromptRegistry`, append/read APIs, immutable strategy-version records, and validation-failure logging.

- [ ] Write failing tests that append two history records, reject mutation of a frozen version, preserve prompt version strings, and list every required table.
- [ ] Run the focused tests; expect missing store/registry imports.
- [ ] Implement migrations and narrow append/read methods without delete/update history APIs.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit storage and prompt registry.

### Task 3: Robinhood Stage 1 policy and broker interface

**Files:**
- Create: `broker/base.py`, `broker/policy.py`, `broker/robinhood.py`
- Test: `tests/test_stage1_robinhood_policy.py`

**Interfaces:**
- Produces: `Broker`, `BrokerError`, `Stage1ToolPolicy.authorize(tool_name)`, and `RobinhoodBroker.call_tool(name, args)`.

- [ ] Write failing tests proving `get_equity_quotes` reaches an injected invoker, `place_equity_order`, `cancel_equity_order`, and `exercise_option` never reach it, and `move_money_new_tool` is denied by default.
- [ ] Run `pytest tests/test_stage1_robinhood_policy.py -q`; expect missing broker modules.
- [ ] Implement an exact allowlist of known read/preview/review/search tools. Apply policy before invocation and require an explicit future live unlock object for any write path.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit the broker safety boundary.

### Task 4: Deterministic risk engine

**Files:**
- Create: `risk/engine.py`, `risk/models.py`
- Test: `tests/test_risk_engine.py`

**Interfaces:**
- Consumes: `TradeProposal`, `RiskConfig`.
- Produces: `RiskContext`, `RiskVerdict`, `RiskReason`, and `RiskEngine.evaluate(proposal, context)`.

- [ ] Write parameterized failing tests with one blocked and one allowed case for each v4 rule: account, whitelist, order/quote, position, position count, option risk, daily orders, round trip, daily loss, 10% drawdown, 15% lock, duplicate, kill switch, no auto-approve, and injected instructions.
- [ ] Run the risk tests; expect missing engine imports.
- [ ] Implement ordered pure-Python checks, alert/close actions, and immutable verdicts.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit the deterministic risk engine.

### Task 5: Paper broker and dual shadow tracks

**Files:**
- Create: `broker/paper.py`, `broker/models.py`
- Test: `tests/test_paper_broker.py`

**Interfaces:**
- Consumes: risk-approved `TradeProposal` and `Quote`.
- Produces: `PaperBroker.submit`, `process_expirations`, `portfolio_value`, and `ShadowExecution.execute_both_tracks`.

- [ ] Write failing tests for buy-at-ask, sell-at-bid, unreachable limit, stale quote, unsettled cash, duplicate client ID, agent-alone versus rejected-human tracks, and ITM/OTM option expiry.
- [ ] Run the focused tests; expect missing paper broker imports.
- [ ] Implement Decimal-based ledgers, settlement lots, fills, positions, and expiry/assignment without midpoint fills.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit paper execution.

### Task 6: Approval cards and agent workflow

**Files:**
- Create: `agents/definitions.py`, `agents/workflow.py`, `agents/approval.py`, `agents/notifications.py`
- Test: `tests/test_agents_and_approval.py`

**Interfaces:**
- Consumes: prompts, schemas, risk engine, store, broker.
- Produces: `build_agents`, `TradingWorkflow.run`, `ApprovalCardRenderer.render`, decision expiry, and an injectable macOS notifier.

- [ ] Write failing tests for one Research Agent, one Portfolio Agent, a separate Critic, retry-once malformed output, skip-after-second-failure, critic attachment, card headings/dollar amounts/150-word maximum, 30-minute expiry as NO, and decision latency.
- [ ] Run focused tests; expect missing modules.
- [ ] Implement Agents SDK definitions with typed outputs and a runner adapter; keep external model calls injectable and disabled in tests.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit agent and approval flow.

### Task 7: Evaluator, scoreboard, reports, and costs

**Files:**
- Create: `eval/evaluator.py`, `eval/scoreboard.py`, `eval/reports.py`
- Create: `reports/strategy_plan.md`
- Test: `tests/test_evaluator_and_reports.py`

**Interfaces:**
- Consumes: stored decisions/fills/daily values/API costs.
- Produces: calibration buckets, attribution, approval value-add, cost/tax totals, `Scoreboard`, `weekly_report.md`, and sample report renderers.

- [ ] Write failing tests with hand-derived literals for calibration, evidence attribution, YES/NO value-add, 35%/15% taxes, and all four scoreboard lines net of API costs exactly once.
- [ ] Run focused tests; expect missing evaluator modules.
- [ ] Implement evaluator queries and plain-English Markdown renderers.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit evaluator and reports.

### Task 8: Golden scenarios, replay, lessons, and champion/challenger

**Files:**
- Create: `eval/golden.py`, `eval/replay.py`, `eval/learning.py`, `tests/fixtures/golden_scenarios.yaml`
- Test: `tests/test_golden_scenarios.py`, `tests/test_replay_and_learning.py`

**Interfaces:**
- Produces: 24 named scenarios, `GoldenGate.run`, `ReplayHarness.run`, append-only lessons/proposals, and `PromotionGate.evaluate`.

- [ ] Write failing tests covering every required named scenario, future-data rejection, lesson append, no live self-edit, and promotion requiring >=4 weeks, >=30 decisions, fixed metric, net win, and human live approval.
- [ ] Run focused tests; expect missing harness modules.
- [ ] Implement deterministic scenario handlers and learning gates.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit evaluation harness and controlled learning.

### Task 9: Local tracing, MLflow, budgets, and resilient operation

**Files:**
- Create: `agents/observability.py`, `eval/experiment.py`, `agents/operator.py`, `config/com.openai.robinhood-shadow.plist.example`
- Test: `tests/test_observability_and_operation.py`

**Interfaces:**
- Produces: localhost-only `TraceManager`, approval trace URLs, token/cost recorder, `MLflowTracker`, daily budget gate, idempotent recovery, market/crypto scheduling, and stall alerts.

- [ ] Write failing tests rejecting non-local trace URLs, linking a card to its trace, stopping at budget, freezing MLflow versions, recovering without duplicates, respecting market/crypto cadence, and alerting after 30 minutes.
- [ ] Run focused tests; expect missing modules.
- [ ] Implement local adapters with explicit unavailable states for optional packages and no silent remote fallback.
- [ ] Run focused and full suites; expect all green.
- [ ] Commit observability and operations.

### Task 10: Regression gate, samples, documentation, and final verification

**Files:**
- Create: `scripts/regression_gate.py`, `scripts/generate_samples.py`
- Create: `reports/sample_approval_card.md`, `reports/sample_scoreboard.md`, `reports/improvement_proposals.md`
- Modify: `README.md`
- Test: `tests/test_regression_gate.py`

**Interfaces:**
- Consumes: complete risk and golden suites.
- Produces: one-command gate and first-deliverable artifacts.

- [ ] Write a failing integration test that proves the gate fails when either a golden or risk result fails and passes only when both pass.
- [ ] Run it; expect missing script imports.
- [ ] Implement the gate, generate labeled mocked samples with a localhost trace link and API-cost line, and document setup without requesting secrets.
- [ ] Run `pytest -q`, the regression gate, and sample generation; capture exact counts and exit codes.
- [ ] Perform a fresh whole-branch review, fix Critical/Important findings with RED→GREEN tests, and rerun the complete verification set.
