# Phase 0 Operational Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Satisfy the approved v1.4.0 Phase 0 gate without enabling Phase 1 behavior or any real Robinhood write capability.

**Architecture:** Preserve the already-tested paper system, but replace the Codex-child market reader with an application-owned OAuth 2.0 + PKCE MCP client whose secrets live in macOS Keychain. Deterministic Python constructs an exact eight-read capability, normalizes live corporate actions, applies freshness, cost, cash and loss gates, and persists auditable results; launchd owns the sole official claim.

**Tech Stack:** Python 3.14, MCP Python SDK 2.2, httpx2, keyring/macOS Keychain, Pydantic, SQLite, pytest, launchd, Pushover.

**Spec:** `docs/superpowers/specs/2026-09-28-intelligent-agentic-investment-organization-design.md`

## Global Constraints

- v1.4.0 is approved only through Phase 0. No Phase 1 or Phase 2 runtime behavior is implemented in this plan.
- Stage 1 remains paper-only. Real orders, replacement, cancellation, exercise, transfer, deposit, withdrawal and broker/settings mutation have no allowed external dispatch path.
- The observed Robinhood protected-resource metadata advertises only scope `internal`; Phase 0 therefore proves `full_scope_zero_cash_fallback`, never mislabels it read-only OAuth.
- The Agentic account must show exactly $0 settled cash, $0 unsettled cash and $0 buying power. Any nonzero value records `STAGE1_AGENTIC_ACCOUNT_NOT_EMPTY`, blocks entries and pages the operator; the application never moves funds.
- The effective application capability contains exactly eight reads: `get_accounts`, `get_portfolio`, `get_equity_positions`, `get_equity_quotes`, `get_equity_historicals`, `get_option_chains`, `get_option_instruments`, `get_option_quotes`.
- OAuth tokens and dynamic client information are stored only in macOS Keychain. Login, consent, MFA and verification are completed by the operator in Robinhood's browser UI. The application never asks for or records passwords or verification codes.
- Official run time is 10:00–10:20 ET on exchange trading days. Manual and what-if runs never satisfy the installed scheduled proof.
- The official LLM ceiling stays $0.40 per run/day. Code-only days cost $0. The monthly allowance is $1.65 per lane; carried allowance is capped at $5.00; annual enforced spend is $19.80 per lane.
- Approval cards expire at the official exchange close, including early closes. Phase 0 does not implement Phase 1 selection or fill logic beyond preserving the current paper safety boundary.
- Existing dirty changes belong to the user. Work in this explicitly selected local checkout, stage only reviewed Phase 0 files, and never reset or discard unrelated work.
- The existing safety pause remains active during implementation and installation. Resumption is not part of this plan.

## Review Focus

1. A broad-scope token, malicious tool name or newly added remote write tool must produce zero external write calls at capability construction, dispatch and broker boundaries.
2. Keychain or refresh failure must not fall back to Codex cookies, browser state, environment tokens or plaintext files.
3. A nonzero Agentic-account cash field, missing field, malformed number or ambiguous account match must fail closed before discovery or inference.
4. A stale quote for one symbol must not poison fresh symbols; a stale-only lane must be `HOLD_OPERATIONAL`, never a successful cash hold.
5. Recovery, delayed launch, fixture, what-if and duplicate workers must not create a second official claim, card or fill.

---

### Task 1: Record v1.4.0 approval and freeze the Phase 0 boundary

**Files:**
- Create: `agents/preregistration.py`
- Modify: `preregistration.yaml`
- Modify: `docs/superpowers/specs/2026-09-28-intelligent-agentic-investment-organization-design.md`
- Create: `tests/test_preregistration_phase0.py`

**Interfaces:**
- Produces: `load_phase0_registration(path: Path) -> Phase0Registration`, rejecting an unapproved, changed or wrong-version registration before an official claim.
- Consumes: canonical root `preregistration.yaml` bytes and the approved version `1.4.0`.

- [ ] Write a failing behavior test that an official Phase 0 preflight accepts `approved_for_phase_0` v1.4.0 and rejects `pending_operator_review`, `approved_for_phase_1`, a missing operator approval record, or a changed canonical hash.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_preregistration_phase0.py` and confirm failure because the loader does not exist.
- [ ] Add a narrow preregistration loader, mark v1.4.0 approved for Phase 0 with the operator's 2026-09-28 approval, and update the spec status without claiming implementation.
- [ ] Re-run the focused test, YAML parse and `git diff --check`; commit only governance/loader/test files.

### Task 2: Application-owned OAuth, Keychain persistence and direct MCP session

**Files:**
- Create: `broker/oauth.py`
- Create: `broker/mcp_client.py`
- Create: `scripts/authorize_robinhood.py`
- Modify: `pyproject.toml`
- Modify: `config/loader.py`
- Modify: `config/settings.yaml`
- Create: `tests/test_robinhood_oauth.py`
- Create: `tests/test_mcp_client.py`

**Interfaces:**
- Produces: `KeychainOAuthStorage(TokenStorage)` using service `com.openai.robinhood-shadow.oauth` and separate `tokens`/`client_info` accounts.
- Produces: `RobinhoodMCPClient.open(interactive: bool)`, `list_remote_tools()`, `call_read(tool, arguments)` and `close()`.
- Produces: authorization evidence with endpoint, granted scope names, selected path and secret-free Keychain retrieval status.

- [ ] Write failing tests with an in-memory Keychain backend for token/client round trips, malformed stored JSON, refresh persistence, scope classification, redacted exceptions and a noninteractive missing-auth failure.
- [ ] Write failing direct-client tests against an in-process synthetic MCP/OAuth endpoint: PKCE metadata, exact resource binding, paginated remote catalog, refresh-token use, tool results, denied elicitation and no secret in logs/errors.
- [ ] Run the two focused files and verify failures are missing interfaces.
- [ ] Implement OAuth with the installed MCP SDK's `OAuthClientProvider`, authorization-code PKCE and refresh support. `scripts.authorize_robinhood` may open the system browser and a loopback callback only in interactive mode; it prints no URL query containing a code and never reads credentials.
- [ ] Add explicit `keyring>=25,<26` and `mcp>=2.2,<3` dependencies. Configuration fixes the HTTPS endpoint, loopback callback, service name and scope `internal`; arbitrary endpoint overrides are forbidden in official mode.
- [ ] Re-run focused tests and the suite; commit.

### Task 3: Exact eight-read gateway and Stage 1 zero-cash invariant

**Files:**
- Modify: `broker/policy.py`
- Modify: `broker/read_gateway.py`
- Modify: `broker/robinhood.py`
- Modify: `agents/market_reader.py`
- Modify: `agents/daily_cycle.py`
- Create: `tests/test_direct_read_gateway.py`
- Modify: `tests/test_read_gateway.py`
- Modify: `tests/test_stage1_robinhood_policy.py`
- Modify: `tests/test_market_reader.py`

**Interfaces:**
- Consumes: `RobinhoodMCPClient.call_read` and full remote tool catalog.
- Produces: `EffectiveReadGateway` exposing no public generic-write API and an immutable evidence record: remote catalog hash, exact local eight-tool inventory, zero effective writes, scope path and account-cash result.

- [ ] Add failing parametrized tests for order, replace, cancel, exercise, transfer, deposit, withdrawal, settings mutation, unknown tool, prefixed tool and Unicode/confusable names. Assert the synthetic upstream invocation list stays empty at each of the three enforcement layers.
- [ ] Add failing tests proving a remote superset is recorded but filtered to the exact eight, a missing required read fails, schema drift fails, pagination loops fail, and neither tool descriptions nor substrings grant authority.
- [ ] Add failing account tests for nonzero/missing/nonfinite settled cash, unsettled cash or buying power, duplicate Agentic accounts and an account without `agentic_allowed`; assert `STAGE1_AGENTIC_ACCOUNT_NOT_EMPTY` or the precise data blocker and one Pushover outbox row.
- [ ] Run focused tests red, then replace `LiveReader`'s Codex child with the direct MCP client. The old transport remains test/replay compatibility only and is unreachable from official live configuration.
- [ ] Re-run focused tests and the full Stage 1 policy suite; commit.

### Task 4: Trading calendar, recovery claims and run-mode isolation

**Files:**
- Modify: `agents/operator.py`
- Modify: `agents/cycle_lifecycle.py`
- Modify: `agents/daily_cycle.py`
- Modify: `data/database_role.py`
- Modify: `data/connections.py`
- Modify: `scripts/install_shadow_services.py`
- Modify: `tests/test_cycle_lifecycle.py`
- Modify: `tests/test_service_schedule.py`
- Modify: `tests/test_database_role.py`

**Interfaces:**
- Produces: `MarketSchedule.classify(now) -> TRADING_WINDOW | NOT_A_TRADING_DAY | BEFORE_WINDOW | MISSED_WINDOW` using a versioned exchange calendar.
- Produces: `CycleLifecycle.acquire(..., recovery=False)` with one normal claim and at most one cost-bounded recovery after failed/stale state.
- Produces: scheduler-created `OfficialRunContext` required by official writes.

- [ ] Add failing holiday, weekend, early-close, DST, 10:00/10:19:59/10:20 boundaries, delayed wake, duplicate, stale-worker and one-recovery tests; no weekday-only arithmetic may satisfy them.
- [ ] Add failing tests that fixture/what-if/replay database roles and API contexts cannot claim or write official tables, cards, fills, scoreboard or lessons.
- [ ] Implement exchange-calendar-backed classification using a pinned calendar dependency, cost-aware recovery and database authorizer enforcement. Keep launchd as a frequent code-only guard plus 10:00 calendar trigger; never infer timezone from `TZ` alone.
- [ ] Re-run focused tests, fixture tests and service-definition lint; commit.

### Task 5: Source envelopes, live corporate actions and quote freshness

**Files:**
- Create: `data/evidence.py`
- Create: `data/corporate_actions.py`
- Modify: `agents/market_reader.py`
- Modify: `agents/daily_cycle.py`
- Modify: `agents/dashboard.py`
- Create: `tests/test_evidence_envelopes.py`
- Create: `tests/test_corporate_actions.py`
- Modify: `tests/test_cycle_budget_and_freshness.py`

**Interfaces:**
- Produces: `EvidenceEnvelope(observed_at, effective_at, fetched_at, source_id, content_hash, payload)` where the hash covers canonical source bytes.
- Produces: `normalize_live_security(record, actions, known_at)` for split, reverse split and ticker change with permanent security identity and audit record.
- Consumes: direct MCP reads before discovery, holdings review and any model packet.

- [ ] Add failing tests for content-based hashes, later revisions, future-known actions, ordinary split, reverse split, ticker change, symbol reuse, unresolved action and normalized option deliverables.
- [ ] Add failing mixed-freshness tests: stale candidate excluded, fresh candidate continues, stale-only lane becomes `HOLD_OPERATIONAL`, and final code-only quote refresh occurs before risk/card creation.
- [ ] Implement the immutable envelope/cache and live normalizer without merger/delisting/history behavior. Persist exact exclusions and surface them in the dashboard.
- [ ] Re-run focused tests and fixture cycle tests; commit.

### Task 6: Automatic breakers, AI-needed gate and Phase 0 budget allocator

**Files:**
- Modify: `risk/models.py`
- Modify: `risk/engine.py`
- Create: `risk/breakers.py`
- Create: `agents/budget.py`
- Modify: `agents/daily_cycle.py`
- Modify: `config/loader.py`
- Create: `tests/test_breakers.py`
- Create: `tests/test_phase0_budget.py`
- Modify: `tests/test_risk_engine.py`

**Interfaces:**
- Produces: `BreakerState.evaluate(valuation, history, rearm) -> BreakerDecision`, safety-only and entry-only except the 15% global lock.
- Produces: `AIInvocationGate.evaluate(discovery, holdings) -> code_only | invoke(reason, ids)`.
- Produces: `BudgetAllocator` enforcing $0.40/day, $1.65/month/lane, $5 carry and $19.80/year with the registered degradation order.

- [ ] Add failing tests for global kill, 3% daily, 5% weekly, 10% peak-to-trough operator-rearm, 15% hard lock, missing valuation and exits remaining allowed up to verified holdings.
- [ ] Add failing tests proving no qualified stock/qualitative holding makes zero model calls and exactly $0 cost; ETF/macro-only remains deterministic.
- [ ] Add failing budget tests for monthly credits, $5 carry cap, $6.65 post-credit maximum, no borrowing/cross-lane shifting, year reset, fixed degradation order and operational hold when the safe minimum cannot fit.
- [ ] Implement minimal deterministic state and integrate it before model reservation and again before card issuance. Do not add Phase 1 baselines, schemas, rebuttal or calibration.
- [ ] Re-run focused risk/budget/daily-cycle suites; commit.

### Task 7: Pushover policy, weekly summary and readiness evidence

**Files:**
- Modify: `agents/notification_outbox.py`
- Modify: `agents/notifications.py`
- Modify: `agents/maintenance.py`
- Modify: `eval/weekly.py`
- Modify: `agents/readiness.py`
- Modify: `agents/dashboard.py`
- Modify: `scripts/verify_operations.py`
- Modify: `tests/test_notification_outbox.py`
- Modify: `tests/test_reporting_repairs.py`
- Modify: `tests/test_operational_readiness.py`

**Interfaces:**
- Consumes: durable cycle, auth, breaker, card and cost records.
- Produces: pages only for failure, safety/auth loss and required action; one nonurgent Friday 16:30 ET summary; secret-free Phase 0 proof assessment.

- [ ] Add failing event-matrix tests proving routine hold/completion/heartbeat/what-if events never page, pending paper approval and auth/safety failures do, and each event is durably deduplicated.
- [ ] Add failing weekly-summary tests for exact coverage, holdings/actions, after-cost no-AI/VTI placeholders honestly marked unavailable in Phase 0, measured costs, failures and actions, with at most one delivery per calendar week.
- [ ] Extend readiness to require v1.4 approval, application-owned Keychain OAuth evidence, `full_scope_zero_cash_fallback`, exact eight local reads, zero cash, three-layer denial tests, direct reads, source hashes, scheduler context, correct notification outcome and a terminal scheduled cycle.
- [ ] Re-run focused tests and `scripts.verify_operations` against synthetic passing/failing receipts; commit.

### Task 8: Install paused services, authorize, prove one scheduled cycle, and stop at the gate

**Files:**
- Modify: `README.md`
- Create/update sanitized evidence under: `outputs/phase0-*`

**Interfaces:**
- Consumes: all Tasks 1–7 and the operator's browser authorization.
- Produces: installed-service receipt and `scripts.verify_operations` exit code 0, or one exact external blocker with the system still paused.

- [ ] Run the complete suite and regression gate; generate a fresh JUnit/test manifest bound to source/config/preregistration hashes.
- [ ] Validate launchd definitions, install while paused, confirm daily/inbox/maintenance identity and HTTP health, and confirm the official live database has no fixture contamination.
- [ ] Run `scripts.authorize_robinhood` interactively. The operator handles Robinhood UI; do not request or capture credentials. Record only Keychain success, scope names and selected path.
- [ ] Perform one manual read-only diagnostic to verify OAuth refresh, remote catalog, exact local eight reads and $0 Agentic-account state. It cannot satisfy the scheduled gate.
- [ ] Leave the installed service paused until the next eligible 10:00–10:20 ET window, then permit only the scheduled paper/read-only cycle under the approved run context. A code-only $0 terminal outcome is acceptable.
- [ ] Run `.venv/bin/python -m scripts.verify_operations --run-tests`. Expected: exit 0 only with matching installed scheduled evidence; otherwise exit 2 with the precise remaining blocker.
- [ ] Conduct a fresh whole-change self-review because multi-agent delegation is disabled by the active execution policy. Fix Critical/Important findings with RED→GREEN tests and rerun the suite.
- [ ] Stop. Do not begin Phase 1 even after a passing gate.

### Gate deliverable before any Phase 1 work: preregistration v1.5.0

This is a governance deliverable after Phase 0 proof, not Phase 1 runtime implementation.

- Pre-register one immutable numeric gross-edge input per deterministic strategy, its derivation source/date and `SURVIVORSHIP-BIASED` label; baseline admission must work without Phase 2 backtests.
- Add `OUTPUT_TRUNCATED_AT_TOKEN_CAP` as a distinct outcome. Use isolated dry runs of the finalized Phase 1 prompt/schema packets to measure per-stage input/output usage, set caps at observed p95 + 50%, recompute reservations, and keep the run ceiling at $0.40. Any later prompt/model/schema change requires remeasurement and a preregistration bump.
- Register the one-Portfolio-call plus one-Critic-call advisory-rebuttal token envelopes and reservation. If the full rebuttal sequence cannot be reserved before it begins, drop the selection with `ADVISORY_REBUTTAL_BUDGET_UNAVAILABLE`.
- Commit v1.5.0 as `pending_operator_review`, send the spec/YAML/diff, and wait for operator approval before any Phase 1 code.
