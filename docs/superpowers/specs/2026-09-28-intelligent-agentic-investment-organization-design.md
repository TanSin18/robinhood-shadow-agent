# Intelligent Agentic Investment Organization — Authoritative Specification

Date: 2026-09-28

Specification version: **1.4.2**

Status: **Approved by the operator on 2026-09-28 for Phase 0 implementation and proof only, including the bounded-cash risk acceptance in this revision. Phase 0 remains unproven. Phase 1 remains blocked until the Phase 0 gate passes and preregistration v1.5.0 is separately approved.**

Safety state: **Stage 1 shadow/paper only. Real orders, cancels, transfers, deposits, withdrawals, and money-moving tools remain unavailable.**

### Operator-approved amendment and scheduling — 2026-09-28

The operator explicitly approves exactly eleven read methods: `get_accounts`,
`get_portfolio`, `get_equity_positions`, `get_equity_quotes`,
`get_equity_historicals`, `get_option_chains`, `get_option_instruments`,
`get_option_quotes`, `get_equity_orders`, `get_option_orders`, and
`get_crypto_orders`. Their pinned input schemas are stored in
`broker/read_schemas_v1.4.2.json`; its SHA-256 is frozen in preregistration.
The three order-history methods are authorized by this amendment, not by their
earlier premature appearance in the implementation.

Raw histories are deterministic tripwire/health data only: never model input,
general research evidence, or detailed UI content. Only the verified Agentic
account is queried, using its distinct verified `rhs_account_number` for crypto.
Monitoring completes before discretionary market discovery. An incomplete scan
or unexpected change pages and latches the kill switch without advancing the
checkpoint. The first comparison baseline requires a complete bounded scan;
subsequent queries start sixty seconds before the last accepted checkpoint and
refresh tracked IDs individually. All pagination, record and call ceilings and
the rationale for that initial lookback are registered in `preregistration.yaml`.

The operator's separate UI exception allows U2–U3 development only on
`ui/agent-desk`, using existing six-stage `project_decision_room` data and no Talk
box. U1 is the first Phase 1 item under v1.5.0; U4–U5 span Phase 1–2; U6–U7 are
Phase 2. No UI merge or dashboard restart precedes the frozen Phase 0 scheduled
proof. The binding execution sequence is in
`docs/superpowers/plans/2026-09-28-phase0-ui-scheduling-addendum.md`.

## 1. Authority, purpose, and success standard

This document replaces earlier architecture notes wherever they conflict. The accompanying root-level `preregistration.yaml` freezes the experiment's quantitative rules. Together they are the design authority for the next build.

The system's purpose is to test whether a disciplined agent organization adds measurable after-cost value over deterministic discovery, a seeded random selection, VTI, and cash. It does not promise profit. It must prefer an honest no-trade decision to a weak trade, preserve an immutable official experiment, and expose enough evidence for the operator to understand and challenge every result.

The architecture remains:

```text
Data Desk and deterministic discovery
  -> corporate-action normalization
  -> holdings review
  -> AI-needed gate
  -> Research Agent, only when needed
  -> code-computed EQS and citation validation
  -> Portfolio Agent
  -> blind Critic
  -> code-defined entry trigger
  -> deterministic Risk Engine
  -> paper approval inbox
  -> paper broker
  -> Evaluation Desk and lessons
```

The OpenAI Agents SDK coordinates exactly one Research Agent, one Portfolio Agent, and one separate Critic when AI is needed. Deterministic Python owns authentication policy, tool allowlists, corporate-action normalization, discovery, market calculations, entry timing, data freshness, evidence scoring, risk, sizing, approvals, fills, evaluation, persistence, and scheduling. No model receives a broker write tool or emits an executable order.

A feature is not "working" merely because it is configured. It is working only when the acceptance test named in this specification passes against the current code and the result is durably recorded.

## 2. Non-negotiable phase gate

The phases are sequential release gates. No Phase 1 or Phase 2 production code may begin until every Phase 0 acceptance condition passes. Documentation and tests may be prepared in advance, but later-phase runtime behavior must remain unreachable.

### Phase 0 — operational safety and one genuine read-only cycle

Phase 0 fixes all known high-severity operational issues:

1. Real-order and money-moving blocking enforced in tested code.
2. Scheduler day-skip and one-minute-window failures.
3. Quote-staleness filtering and final price refresh.
4. Budget reservation and predictable headroom.
5. Pushover delivery for failures and required actions.
6. Robinhood authentication owned by the Python application outside Codex.
7. Fixture/test data isolation so it cannot mark a live day complete.
8. Live split/reverse-split and ticker-change normalization, plus automatic entry breakers.
9. AI-needed gating so no-candidate/no-qualitative-review days cost $0.
10. One installed, scheduled, authenticated, read-only cycle proven end to end on a market day.

Phase 0 is complete only when all tests in Section 18.1 pass and `scripts.verify_operations` returns success from a scheduled background run. A manually started interactive run is diagnostic evidence, not completion evidence.

### Phase 1 — accountable decisions

Phase 1 adds validated agent schemas, code-computed EQS, citation checks, pre-mortems, Critic veto/rebuttal rules, holdings-first review, multi-action decisions, failure-pattern memory, and the deterministic no-AI and seeded-random baselines.

### Phase 2 — evaluation depth and operator control

Phase 2 adds probability calibration, exact replay, the qualified options pipeline, historical and complex corporate-action normalization, walk-forward and Monte Carlo evaluation, champion/challenger management, and the full decision-room dashboard.

## 3. Phase 0 architecture and acceptance

### 3.1 Isolated Robinhood OAuth and read-only broker proxy

One minimal broker-proxy process authenticates directly to Robinhood's official Trading MCP. It runs as the dedicated non-admin macOS user `robinhoodproxy`, must not depend on Codex's interactive session or browser cookies, and stores OAuth only in that user's Keychain. The main application and all agents run as the operator user, communicate with the proxy over a local Unix-domain socket, and never receive an OAuth token.

- OAuth access and refresh tokens are stored only in the `robinhoodproxy` user's macOS Keychain under a dedicated service name. The operator user is not granted access to that Keychain item or the proxy user's files. The main application contains no Keychain storage object, Robinhood OAuth client, token accessor, or configured Keychain-item identifier.
- The proxy and operator users are the only members of the `robinhoodreaders` group. The socket parent directory is owned by `robinhoodproxy:robinhoodreaders` with mode `0770`; the socket is mode `0660`. The server also verifies the peer UID equals the registered operator UID, so group membership grants filesystem reachability without authorizing an unexpected local user. Proxy Keychain and state files remain private to `robinhoodproxy` and are never group-readable.
- The proxy runs as a LaunchAgent in the dedicated user's logged-in session so its Keychain is unlocked by macOS rather than by storing a Keychain password in configuration. After reboot, an unavailable dedicated-user session produces a visible operational hold; the application never weakens Keychain isolation to recover automatically.
- The operator completes login, consent, MFA, and any verification personally. The application never requests, displays, logs, stores, or relays passwords or verification codes.
- The preferred path requests and proves a provider-issued read-only OAuth scope.
- If Robinhood does not offer or grant a read-only scope, the proxy may store a full-scope token only under the operator-approved `full_scope_bounded_cash_fallback` path. The token stays inside the proxy process. The exact eleven-tool read allowlist is enforced independently by proxy capability construction, exact socket dispatch, and the broker/risk boundary.
- After connection, the service records the granted scopes and remote catalog, then constructs an effective local inventory containing exactly the eleven reads below. The three order-history reads exist only for the account-state tripwire; they cannot place, preview, review, replace, or cancel an order. An expected read missing from the remote service or any write method reaching the effective local inventory fails closed.
- The proxy source defines no order-write, cancel, exercise, transfer, deposit, withdrawal, preview, review, or settings method, route, mapping, or socket request. Its socket accepts an exact method enum, rejects Unicode confusables and namespaced or suffixed variants, bounds payload size and collection cardinality, and closes on malformed framing. Its automatic connection metadata contains only non-secret version, selected-path, catalog-hash, authorization-expiry state, and effective-capability evidence; it is not an additional callable method.

The only Robinhood MCP tools visible to the market-data process are:

```text
get_accounts
get_portfolio
get_equity_positions
get_equity_quotes
get_equity_historicals
get_option_chains
get_option_instruments
get_option_quotes
get_equity_orders
get_option_orders
get_crypto_orders
```

All order placement, replacement, cancellation, exercise, transfer, deposit, withdrawal, and settings mutation tools are absent from the proxy interface and default-denied at three layers: proxy capability construction, exact socket RPC dispatch, and the broker/Stage 1 risk boundary. Tool-name substring filtering alone is not sufficient. A full-scope OAuth token therefore does not create an effective write capability for the application.

Tests start the main cycle with Keychain access replaced by a fail-on-use sentinel and prove the cycle can read only through the socket. Separate proxy tests send every known write name plus malformed, namespaced, suffixed, and confusable variants and prove rejection before MCP dispatch.

#### 3.1.1 Operator-approved bounded-cash fallback

The bounded-cash fallback is a recorded operator risk acceptance, not a claim that full-scope OAuth is intrinsically read-only. `max_agentic_cash_usd` is frozen at **$1,200.00** in the operator-approved, pre-effective v1.4.1 amendment. Git retains the previously committed $600 draft. Any later change requires a new operator-approved preregistration version.

For every cycle, the proxy reads the live Agentic account and portfolio before any discovery or model call. The fallback passes only when all three values are present, finite, and nonnegative; `buying_power == unleveraged_buying_power == cash`; and `cash <= max_agentic_cash_usd`. Equality is exact at the provider's reported currency precision. A missing value, a value above the cap, or either unequal buying-power value records `HOLD_OPERATIONAL: AGENTIC_ACCOUNT_OUTSIDE_BOUNDS`, pages the operator, and permits no new paper entry. Exits in the paper experiment remain allowed. Reports store only pass/fail, reason code, and redacted field names—never amounts or account identifiers.

#### 3.1.2 Cash, position, and order-activity tripwire

The first in-bounds, authenticated Phase 0 read establishes a content-hashed baseline of the Agentic account's cash, positions, and equity/option/crypto order histories. The full snapshot is stored only in the protected local operational database; reports receive neither balances, quantities, order or instrument identifiers, cost basis, nor account identifiers.

Before each later cycle, code compares the new canonical snapshot with the last verified snapshot. A cash increase with unchanged positions and order/activity histories that remains at or below the cap records `ACCOUNT_CASH_INCREASE_BENIGN`, advances the verified baseline, appears in the weekly summary, and does not page or engage the kill switch. A cash decrease, any position change, any new or changed order/activity record, or cash above the cap records `AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE`, pages through Pushover, engages the persistent global kill switch, and displays the revocation runbook. No model runs and no new paper entry or card is created. Rearming requires a durable operator acknowledgement naming the exact pending snapshot hash, change class, and expiry; removing a marker file or restoring the old balance cannot rearm it automatically. The acknowledgement and the newly accepted snapshot become immutable audit records.

#### 3.1.3 Authorization-expiry monitor

Every token write stores a secret-free issuance timestamp and derives `expires_at` from the provider's `expires_in`. The proxy emits deduplicated Pushover pages when a stored authorization crosses three days and one day remaining. A refresh failure pages immediately. An authorization at or past `expires_at` cannot be used and returns `HOLD_OPERATIONAL: AUTH_EXPIRED` before discovery or any model call. Reports expose only the threshold/status and timestamps, never tokens, token hashes, or account data.

#### 3.1.4 Revocation runbook and proof

The dashboard and local runbook provide two separate emergency actions:

1. **Revoke remotely:** use Robinhood's in-app Agentic Trading connection control to disconnect the agent. Robinhood states that an Agentic Trading connection can be disconnected directly in the app. If that control is unavailable or the account shows unrecognized activity, contact Robinhood Support through the app.
2. **Remove locally:** after remote disconnect is confirmed, delete the proxy's OAuth token and client-registration entries from macOS Keychain, stop the proxy, and keep the global kill switch engaged. Local deletion alone is not recorded as remote revocation.

Phase 0 evidence must include one operator-performed Robinhood disconnect, a subsequent proxy read that fails authentication, local credential removal, and one fresh operator-performed authorization that restores the exact eleven-read session. The record contains timestamps, boolean outcomes, selected path, and source/config hashes only. It contains no token, token hash, balance, quantity, order identifier, or account identifier. Login, MFA, consent, disconnect confirmation, and re-authorization remain operator actions; the software never asks for a password or verification code.

### 3.2 Stage 1 real-action invariant

Every runtime mode in this release is paper/shadow. The only fill writer is the paper broker. The Robinhood adapter exposes read methods only and has no write interface. A hostile or malformed model output that requests a real order must produce `REAL_BROKER_ACTION_BLOCKED`, a safety event, and no external write call.

The invariant applies equally to official, recovery, what-if, replay, test, and dashboard requests. No user approval card can override it.

### 3.3 Scheduler reliability

The resident service runs from `launchd` and evaluates the New York trading calendar rather than weekday arithmetic. It uses a claim window from 10:00 through 10:20 ET instead of a single minute.

- One atomic database claim exists per official market date.
- A successful claim is idempotent across repeated scheduler wakeups.
- Weekends and full-market holidays record `NOT_A_TRADING_DAY`, not a missing run.
- Early-close days still run at 10:00 ET.
- One recovery attempt may claim the same date only when the prior claim is terminally failed or stale and the total committed plus planned model cost stays within the official daily ceiling.
- The machine wake schedule, power state, installed job identity, last wake, next wake, claim status, and last terminal cycle are visible in Operations.
- A manual what-if request can never acquire an official claim.

### 3.4 Freshness and source timing

All evidence records carry `observed_at`, `effective_at`, `fetched_at`, `source_id`, and a content-based SHA-256 hash of canonicalized source bytes. A URL, file path, ticker, or timestamp is not a content hash.

Completed daily bars may be used for deterministic discovery if their effective date is the most recent completed session. Live quotes used for a new entry must be no older than 60 seconds when Research begins and must be refreshed again immediately before risk approval. Quotes used to review or price an exit must also be no older than 60 seconds.

Stale data is never silently treated as current:

- A stale candidate is labeled `STALE_REQUIRED_MARKET_DATA` and cannot advance.
- Fresh candidates continue; one stale symbol does not invalidate the entire universe.
- If no candidate has the required fresh data, the lane returns `HOLD_OPERATIONAL`, not `HOLD_CASH`.
- The dashboard shows the age, timestamp, source, refresh result, and exact reason each symbol was excluded.

The Data Desk performs a final code-only quote refresh. It does not invoke an LLM.

### 3.5 Budget headroom

The budget allocator reserves each mandatory stage before starting any optional work. It estimates the maximum remaining cost after every model call, records actual token use and cost by agent and evaluation arm, and follows the fixed degradation order in Section 16. It may reduce optional coverage; it may not skip a mandatory safety stage or silently substitute a model.

### 3.6 Pushover policy

Pushover pages only:

- a failed or unconfirmed official run;
- a safety invariant violation;
- a required operator action, including a pending paper approval or expiring promotion exception;
- loss of the approved authenticated data path that prevents the official cycle.

Successful holds, routine completions, background heartbeats, and ordinary what-if results are logged and shown in the dashboard but do not page. The only routine outbound message is one non-urgent weekly Pushover summary sent Friday at 16:30 ET. It reports official-cycle coverage, lane actions and holdings, after-cost results against no-AI and VTI, measured API cost by lane and trailing year, breaker/auth/data failures, the twelve-month AI stop-rule state, and any operator action still pending. Delivery attempts, provider responses, retries, and final delivery status are durable. Notification credentials remain in macOS Keychain.

### 3.7 Fixture isolation

Fixture and test runs use a separate database path and a namespace that cannot equal `official`. The official database authorizer rejects fixture-tagged writes. Fixture data is visibly watermarked, cannot claim a market date, cannot create official cards or fills, and cannot update the official scoreboard or lessons memory.

### 3.8 Required Phase 0 proof

The proof is one unattended, installed-service cycle on a trading day using proxy-owned OAuth. It must state and prove which path actually ran: `provider_read_only_scope` or `full_scope_bounded_cash_fallback`. It must show:

1. OAuth token retrieval inside the proxy without exposing a secret, the granted scope names, selected path, and proof that the main process completed with fail-on-use Keychain access;
2. exact effective proxy inventory matching the eleven-read allowlist, zero effective write tools, proxy execution under `robinhoodproxy`, private proxy Keychain/files, shared-group socket mode `0660`, registered-operator peer enforcement, and three-layer rejection tests;
3. the bounded-cash predicate passed without recording an amount or account identifier;
4. atomic official-day claim within the recovery window;
5. fresh Robinhood account, position, portfolio, equity quote, history, and option-reference reads as applicable;
6. either a $0 code-only terminal result or the conditionally invoked Research, Portfolio, Critic, and deterministic risk stages;
7. terminal cycle, source hashes, model/prompt/config versions, per-run and year-to-date costs, and trace link in SQLite;
8. correct Pushover behavior;
9. no external write call and a passing hostile real-order-block test;
10. `scripts.verify_operations` exit code 0.
11. one Robinhood-side disconnect, failed post-revoke read, local credential removal, and successful fresh re-authorization recorded under the redaction rules in Section 3.1.4;
12. authorization-expiry metadata plus tested three-day, one-day, refresh-failure, and expired-auth behavior.

## 4. Run modes and experimental isolation

There are exactly three public run modes:

| Mode | Purpose | May affect official result? | May create cards/fills? | May write lessons? |
|---|---|---:|---:|---:|
| `official` | Scheduled champion experiment | Yes | Paper only, after all gates | Official resolved lessons only |
| `what_if` | Operator-directed same-day research | No | No | Separate research notes only |
| `replay` | Reproduce a frozen prior input | No | No | No |

Isolation is enforced below the UI:

- Official records live in the official SQLite database and require an unforgeable in-process `OfficialRunContext` created only by the scheduler claim service.
- What-if and replay records live in a separate research database connection.
- SQLite authorizer callbacks reject non-official writes to official cycle, card, fill, value, scoreboard, lesson, and promotion tables.
- API routes bind their mode server-side; clients cannot submit a field that upgrades a request to official.
- Every what-if record requires a non-null `parent_official_run_id` foreign key to the immutable official run it explores. If no eligible official parent exists, the API rejects the what-if request rather than creating an orphan.
- Paper broker methods require an official context and a valid approval for a card from the same immutable snapshot.
- What-if and replay services are constructed without card, paper-fill, lesson, or official-scoreboard repositories.
- Cross-database copy operations are absent from runtime code.

On-demand reviews after the official cycle remain read-only what-if runs. They may use newer information, but the UI must display their parent official run and compare them to that immutable snapshot without altering the day's paper results. A "Run official cycle again" control does not exist.

## 5. Data Desk, universe, and deterministic discovery

The 14-symbol list is retired as the primary universe. It may remain as a smoke-test fixture only.

### 5.1 Corporate-action normalization

Phase 0 is limited to live operational normalization required for a genuine read-only cycle. Before live discovery, holdings review, signal calculation, or agent input, the Data Desk maps records to permanent security identifiers and applies known-as-of-time:

- splits and reverse splits to current price, share quantity, volume, cost basis, indicators, and option deliverables; and
- ticker changes so permanent identity is preserved and old and new issuers that reused a symbol are never joined.

Phase 2 adds historical split/reverse-split normalization for backtests and replays, plus cash mergers, stock mergers, delistings, historical holdings conversion, terminal-value rules, and all related no-lookahead tests. Until that Phase 2 work passes, affected historical records are excluded with a visible `CORPORATE_ACTION_SCOPE_NOT_IMPLEMENTED` label rather than silently transformed or dropped.

Every implemented transformation stores announcement/effective timestamps, source ID, content hash, factor or terms, pre-normalized values, and normalized values. An unresolved or contradictory implemented action produces `CORPORATE_ACTION_UNRESOLVED` and excludes the affected instrument. Agents receive normalized values and permanent IDs only.

### 5.2 Historical-constituent source and current fallback

The named point-in-time source is **Norgate Data, “S&P 500 Current & Past” membership via its historical index constituent data**, including delisted securities at the required subscription level. Access is not assumed or currently proven by this specification.

Until Phase 2 records a valid license/access check, source coverage, membership timestamps, delisted-security coverage, and content hashes, the system must use `current_constituents_only`, label **every backtest** `SURVIVORSHIP-BIASED`, and make no point-in-time or survivorship-free claim. Once validated, each simulated date may use only the Norgate membership state known for that date. Current-mega-cap studies retain their survivorship-bias label regardless.

Each official live date receives an immutable universe snapshot containing the currently observed S&P 500 membership plus reviewed, unlevered, non-inverse liquid ETFs representing broad equity, sector, Treasury-duration, gold, and defensive exposures. The eligibility rules exclude OTC securities, penny stocks below $5, leveraged/inverse products, halted or unsupported instruments, securities without at least 253 completed daily observations, median 20-session dollar volume below $50 million, and median quoted spread above 0.30% for entry consideration.

Strategies and VTI use dividend-adjusted total-return data. Reports state the actual history length and constituent-source mode.

### 5.3 Deterministic funnel

Code, not an LLM, reduces the universe:

1. eligibility and data-quality filters;
2. holdings requiring review;
3. registered strategy signals;
4. liquidity and friction filters;
5. volatility-scaled capacity;
6. diversification and correlation constraints;
7. deterministic rank with a complete per-factor explanation.

At most 30 candidates enter the shortlist, at most 20 receive live quote verification, and at most 8 stock candidates receive full AI research. Limits are deterministic tie-broken by symbol. Every excluded instrument records its stage and reason.

Registered strategy signals are deterministic Python: trend/momentum ETF rotation, large one-day mean reversion while above the 200-day moving average, and pre-registered filing/event screens for individual stocks. ETFs and macroeconomic selection remain deterministic.

### 5.4 No lookahead and caching

Robinhood MCP supplies live read-only broker evidence. Stooq or Yahoo supplies dividend-adjusted daily history. SEC EDGAR supplies filings and full-text changes. FRED supplies macro series. Each fetch is cached locally with source, request, observation, effective, publication, and retrieval timestamps plus content hash.

A simulation may access only records whose publication/effective time was available at the simulated decision time. Later revisions remain separate versions. Earnings transcript and filing AI signals are forward-tested only and never inserted into historical backtests.

## 6. AI scope and least privilege

### 6.1 AI-needed gate

The default official cycle is deterministic and costs $0 in model API usage. Research, Portfolio, and Critic are instantiated only when code records at least one of these reasons:

1. `QUALIFIED_AI_ELIGIBLE_CANDIDATE` — deterministic discovery produced an individual-stock candidate whose required qualitative filing, transcript, or sourced-news analysis cannot be resolved by code; or
2. `HOLDING_QUALITATIVE_REVIEW_REQUIRED` — a held stock has a new material filing/transcript/news source, a disclosed event, or a scheduled thesis-review deadline requiring qualitative reassessment.

An ETF-only or macro-only shortlist, an empty shortlist, unchanged holdings, and holdings requiring only deterministic price/time/expiry checks do not invoke a model. Their completed run records exactly $0 model cost. The gate stores the reason, qualifying IDs, and evidence that triggered it. A model cannot request its own invocation.

The AI stages are also sequentially conditional: the gate may invoke Research; Portfolio runs only if at least one Research dossier passes schema, citations, EQS, and hard-failure checks; Critic runs only if Portfolio returns at least one ranked selection. Skipped downstream stages record `NOT_NEEDED` and $0. Preflight reserves the possible downstream cost without forcing the call.

If AI is invoked for one lane, model cost is attributed only to that lane and the candidates or holdings processed. Shared agent-call cost is allocated by input-token share with the residual cent assigned deterministically to the lowest lane ID. The dashboard reports actual model cost for each run, lane, calendar year, and trailing 365 days.

### 6.2 Permitted AI work

AI use is intentionally narrow:

| Instrument/evidence | AI may do | AI may not do |
|---|---|---|
| Individual stocks | Compare cited filings, transcripts, filing diffs, and sourced news; write a pre-mortem; estimate a calibrated thesis probability | Build the universe, invent facts, calculate price indicators, size positions, call broker/settings tools |
| ETFs | No AI in the official cycle | Generate ETF or macro signals, rankings, forecasts, explanations, or sizing |
| Macro | No AI in the official cycle | Create, alter, or narrate the deterministic regime signal |
| Options | Analyze cited event and filing risk only when an already-qualified individual-stock underlying triggers the AI-needed gate | Choose contracts, calculate Greeks/payoffs, infer missing chain fields, size, roll, exercise, or submit orders |
| Holdings | Assess whether cited qualitative stock thesis evidence changed | Override price/time/expiry/invalidation exits or delay a safety exit |

Research and Critic receive no execution, settings, approval, database-write, or external browsing tools. They receive immutable dossiers assembled by code. Untrusted text is data, never instruction.

Before any model sees news, filing, or transcript text, code flags instruction-like language, embedded tool requests, role/system impersonation, encoded payloads, and attempts to alter policy. Flagged passages are quarantined from model input and recorded as `PROMPT_INJECTION_SUSPECTED`; a material source quarantine causes Research to abstain.

## 7. Structured agents and one-retry rule

Every agent has a versioned prompt, a distinct Pydantic output schema, an assigned dated model snapshot, validated inference parameters, timeout, token limit, and cost allocation. Exact prompt text, model identifier, reasoning effort, tool/input schema, input dossier, attempts, validation errors, output, and token/cost usage are persisted. Floating aliases such as `gpt-5.6-luna` are prohibited. Any assigned-model change requires a new preregistration version, operator approval, and a scoreboard version boundary.

If output fails schema or citation validation, that agent receives exactly one repair attempt. The second attempt is logged as a separate attempt with the first validation error. A second failure ends the lane as `HOLD_OPERATIONAL: SCHEMA_INVALID_AFTER_RETRY`. If the assigned model is unavailable, the run fails visibly; there is no silent fallback.

Research uses `gpt-5.4-nano-2026-03-17`, Portfolio uses `gpt-5.4-mini-2026-03-17`, and Critic uses `gpt-5.4-2026-03-05`. Critic's exact model identifier must differ from Portfolio's. Configuration validation fails if an ID lacks a `YYYY-MM-DD` suffix, differs from the preregistration, or Portfolio and Critic match.

Snapshot availability is sourced from the official OpenAI model pages for [GPT-5.4 nano](https://developers.openai.com/api/docs/models/gpt-5.4-nano), [GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini), and [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4). Research uses `reasoning.effort: low`; Portfolio and Critic each use `reasoning.effort: medium`. Temperature is not registered and must not be sent. Configuration validation rejects temperature, any unregistered inference parameter, and any parameter unsupported by the assigned snapshot. Availability must still be checked in the application's account before Phase 1; an unavailable assigned snapshot fails visibly rather than falling back.

Reasoning tokens are billed as output tokens and share the `max_output_tokens` envelope with visible output and formatting tokens. The registered per-attempt hard envelopes and standard uncached-price estimates are:

| Stage | Input cap | Output cap including reasoning | Effort | Maximum estimated cost |
|---|---:|---:|---|---:|
| Research | 24,000 | 6,000 | low | $0.0123 |
| Portfolio | 12,000 | 3,000 | medium | $0.0225 |
| Critic | 8,000 | 2,000 | medium | $0.0500 |

A full three-stage run is therefore estimated at no more than **$0.0848** with one attempt per stage or **$0.1696** if every stage uses its one permitted repair attempt. These are preregistered ceiling estimates, not promised bills; the dashboard reports estimate and actual cost per run. The envelopes are hard: unused monetary headroom cannot silently buy more tokens. Pricing and token accounting are frozen from the official model pages plus the OpenAI [reasoning](https://developers.openai.com/api/docs/guides/reasoning) and [token-counting](https://developers.openai.com/api/docs/guides/token-counting) guidance dated 2026-09-28.

### 7.1 Research schema

Research emits one dossier per candidate:

```text
candidate_id
instrument_type
status: QUALIFIED | REJECTED | INSUFFICIENT_EVIDENCE
research_rank
thesis
time_horizon_days
invalidation_event_or_price
supporting_claims[] {claim_id, text, source_ids[], probability, uncertainty_tag}
contrary_claims[] {claim_id, text, source_ids[], probability, uncertainty_tag}
premortem {loss_scenario, exact_mechanism, observable_warning, source_ids[]}
event_disclosures[]
missing_critical_evidence[]
forecast_type
target_id
forecast_probability
```

Research must return a schema-valid record, forecast, and independent rank for every candidate it receives, including `REJECTED` and `INSUFFICIENT_EVIDENCE` candidates. It must return `INSUFFICIENT_EVIDENCE` when a critical field, source, current quote, disclosed earnings event, filing, or required corroboration is missing. Narrative confidence cannot compensate for missing evidence.

Research's forecast horizon is fixed at 20 trading sessions until Research has at least 50 resolved official `RESEARCH_SECTOR_ALPHA` forecasts. Before that gate, any other `time_horizon_days` or target ID fails schema validation. After the gate, Research may select only 5, 10, 20, or 60 sessions, and the selected registered target remains immutable.

Code randomizes candidate order before building the Research packet using the stored seed `sha256(registration_id | official_run_id | research_packet_content_hash | "research-order")`. It removes screener rank, screener score, and fields whose only purpose is to reveal either one. Research sees stable candidate IDs and the underlying evidence/features needed for analysis, but not the permutation's original positions. The stored packet, seed, order, and field-denial test make the blinding replayable.

### 7.2 Portfolio schema

Portfolio receives only Research dossiers that pass code-computed EQS and citation validation. It emits a ranked conviction list, not orders, entry instructions, prices, timing, or quantities:

```text
selection_id
lane
candidate_id
rank
direction: BULLISH | BEARISH | NEUTRAL | EXIT | REDUCE
conviction_score_0_to_100
forecast_type
target_id
forecast_probability
time_horizon_days
exit_plan {invalidation, target, max_holding_days, time_exit, event_exit}
evidence_ids[]
reason_code
```

Portfolio may return an empty ranked list and a per-lane `NO_CONVICTION` reason. The deterministic Decision Compiler converts an empty qualified list to lane-specific `HOLD_CASH`. No trade is a successful discipline outcome, not an idle failure.

After Critic resolution, the Decision Compiler applies `fresh_midpoint_not_worse_than_selection_v1` from `preregistration.yaml` to each surviving defined-risk long selection. It begins only after Critic passes and the final quote is fresh, uses the first fresh midpoint after Portfolio as its reference, permits entry only while the current midpoint is no worse than the registered maximum-limit-distance tolerance, and sets `entry_limit = fresh_midpoint × (1 + maximum_limit_distance_fraction)`, where `fresh_midpoint` is from the quote when the trigger fires and the card is issued. The trigger expires at 15:30 ET. Intraday evaluations are code-only. Only after it fires does the Risk Engine calculate quantity from settled cash, volatility, liquidity, breakers, and position caps. Neither Portfolio nor Critic can set or revise price, timing, or quantity.

The official record stores two separate objects: `agent_selection` (candidate, direction, rank, conviction, probability, evidence, exit plan, selection timestamp) and `code_timing` (trigger ID/version, inputs, trigger timestamp, reference price, expiry, fired/not-fired state). Evaluation scores selection value and timing value separately as specified in Section 13.

`HOLD_OPERATIONAL` is emitted by orchestration, not Portfolio. It indicates the decision could not be made safely and is never counted as `HOLD_CASH`.

### 7.3 Critic schema and blindness

Code constructs Critic input from the ranked selection fields, validated evidence, source references, EQS result, and deterministic calculations. It explicitly excludes Portfolio's hidden reasoning, messages, narrative rationale beyond the public thesis, and prior Critic outputs.

The Critic emits:

```text
selection_id
verdict: PASS | HARD_VETO | ADVISORY
category
claim_ids[]
evidence_ids[]
objection
required_resolution
forecast_type
target_id
forecast_probability
```

The Critic cannot add a candidate, set price or timing, or influence quantity. It uses a different required model from Portfolio. ETF and macro-only decisions never invoke it; when an AI-reviewed stock thesis informs an option-underlying selection, it audits only the cited qualitative evidence and logic while contract selection and all market calculations remain deterministic.

## 8. EQS, citations, and failure-pattern memory

### 8.1 Evidence Quality Score

Code computes EQS before Portfolio sees a dossier. The formula and thresholds are frozen in `preregistration.yaml`:

- authoritative source quality: 25%;
- freshness: 20%;
- claim-to-citation coverage: 25%;
- independent corroboration: 15%;
- completeness and explicit uncertainty: 15%.

Each component is calculated from Data Desk metadata, not model self-rating. A score of at least 75 is required to advance. Any critical missing field or hard failure blocks advancement regardless of the numerical score.

Every factual claim must cite a Data Desk `source_id`. Code verifies quoted prices, dates, earnings times, filing dates, and numerical fields against the canonical source record. Unsupported factual claims are removed; if one is material to the thesis, the candidate is vetoed.

Uncertainty tags are closed: `VERIFIED_RECENT`, `VERIFIED_HISTORICAL`, `STALE_OR_INFERRED`, and `MISSING_CRITICAL`. A model cannot assign `VERIFIED_*`; code derives it.

### 8.2 Historical failure patterns

The Failure Pattern Index contains only:

- resolved outcomes from this system's own immutable official decisions; or
- an externally sourced pattern with a stored citation and content hash.

It may warn that a new thesis resembles a prior failure. It may not contain uncited model-generated folklore. What-if and replay runs cannot write it. Lessons enter official memory only after outcome resolution and deterministic attribution.

## 9. Critic resolution and final vetoes

Hard veto categories are closed and frozen in `preregistration.yaml`. They include stale required data, missing critical evidence, uncited or numerically false material claims, undisclosed scheduled events within the holding period, liquidity failure, prompt-injection quarantine of material evidence, missing exit plan, invalid options fields, and deterministic risk violations.

A hard veto drops the affected selection before trigger evaluation. It cannot be rebutted or overridden in the dashboard.

For an advisory objection, Portfolio receives one structured rebuttal opportunity. The rebuttal may cite only the existing immutable evidence packet; it cannot fetch new evidence or change the snapshot. Code presents the rebuttal and original evidence to the Critic for one resolution. Any objection still marked unresolved drops the action. No further dialogue occurs.

The Risk Engine may only override toward safety: reduce code-computed size, reject an entry, allow or accelerate an exit, or convert a lane to an operational hold. It cannot create a trade, enlarge it, weaken a veto, reinterpret evidence, or accept a price/timing/quantity from an agent.

## 10. Holdings-first decisions, exits, and lane semantics

Every official cycle reviews all holdings before considering a new purchase. A durable `holdings_review_complete` gate is required to enter discovery.

For each position, the system evaluates thesis validity, deterministic invalidation, stop/target state, maximum holding time, corporate events, concentration, current quote freshness, and whether the original source evidence changed. If any option is held, the options holdings review is mandatory and additionally checks expiry, DTE, spread, liquidity, Greeks, exercise/assignment exposure, auto-exercise threshold, and the pre-registered expiry action.

The deterministic Decision Compiler may emit multiple actions from holdings rules and surviving selections, such as `CLOSE` one holding, `REDUCE` another, and `OPEN` a new position. Actions are ordered: exits and reductions first; new entries only after their projected settlement/cash effects are conservatively applied.

Exits are always permitted by the risk engine up to actual held quantity. This means an exit is exempt from entry whitelist, edge, diversification, turnover, and buy-block rules, but it must still be a valid sell-to-close or close action, cannot exceed the held quantity, and remains paper-only. The risk engine cannot force a sale of something not held.

Lane A covers stocks and ETFs. Lane B covers defined-risk options. `HOLD_CASH` applies separately to each lane. `HOLD_OPERATIONAL` may apply to one lane without mislabeling the other. A Lane B candidate blocked by missing options data, affordability, or risk cannot be re-expressed as a Lane A trade within the same run.

### 10.1 Approval expiry and paper fills

A paper approval card expires at the official exchange close for its market date, including the earlier close on shortened sessions. It never carries into the next market date. Approval after expiry is rejected.

On YES, code fetches a new quote and requires it to be no older than 60 seconds at the approval timestamp. A paper buy fills at the fresh ask plus registered slippage and a paper sell fills at the fresh bid minus registered slippage, including the contract multiplier where applicable. The persisted code-defined entry limit is `fresh_midpoint × (1 + maximum_limit_distance_fraction)` using the trigger/card-issuance quote. All price, limit, and slippage arithmetic uses exact base-10 decimals, not binary floating point. A new-entry fill may not exceed that limit or the risk bounds; if the slippage-adjusted price is worse, the card records `PRICE_MOVED_BEYOND_LIMIT` and produces no fill. The quote ID, observed time, approval time, bid, ask, slippage formula, entry limit, computed fill, and no-fill reason are immutable. No model participates in approval-time pricing.

## 11. Deterministic risk and sizing

Before any paper approval card, code verifies actual paper positions and settled paper cash independently of the broker adapter.

- A closing sale quantity must be positive and no greater than the verified held quantity.
- A buy's full conservative notional plus friction must not exceed settled cash.
- Unsettled proceeds cannot fund a purchase.
- Fractional-share support must be explicit for the instrument.
- The maximum position, open-position, daily-loss, weekly-loss, peak-to-trough drawdown, quote-age, and limit-distance rules remain hard bounds.
- Position size begins with target fraction multiplied by target annual volatility divided by 20-day realized annualized volatility, then caps at the position limit, settled cash, liquidity capacity, and lane capacity.
- A red-flag filing veto blocks buys. Earnings and filing scores may only multiply deterministic size by a factor from 0 through 1; they can reduce or eliminate size and can never increase it, improve rank, create eligibility, or relax a trigger.

### 11.1 Automatic breakers

The global kill switch and three automatic loss breakers are evaluated before every new entry and again before card issuance:

- global kill switch: persistent, fail-closed, blocks all new entries while engaged;
- daily breaker: a 3% loss from the prior market-day close blocks new entries for the rest of the current market date;
- weekly breaker: a 5% loss from the prior Friday close blocks new entries through the end of the current market week;
- peak-to-trough breaker: a 10% drawdown from the high-water mark blocks new entries until the operator completes the documented review and explicitly rearms it; market recovery is reported but is not a rearm prerequisite;
- hard drawdown lock: a 15% drawdown engages the global kill switch and requires an operator incident review before rearming.

Loss and drawdown are measured after API costs for each lane and for the combined paper portfolio; a breach in either scope blocks new entries globally. Breaker evaluation uses the last durable valuation and a fresh code-only mark. Missing valuation data fails closed. All exits and reductions up to verified holdings remain allowed while any breaker or kill switch is active. The state, threshold, observed value, trigger time, reset condition, and rearm actor are immutable audit records.

Zero-turnover bias is explicit. Open/add trades with a planned holding period under five trading days are rejected unless they belong to a pre-registered event strategy and meet the stricter edge-to-friction and expected-return thresholds in `preregistration.yaml`. Exits are exempt.

Shadow Kelly is an evaluation field only as specified in Section 14. It is not an input to the paper broker or approval quantity.

### 11.2 Probability shrinkage and net edge

The net-edge calculation uses `p_used`, not an uncalibrated raw agent probability. For each agent/target pair with fewer than 50 resolved official forecasts, or whose Brier score is not yet strictly better than its prior-sample base-rate baseline:

`p_used = base_rate + 0.5 × (p_agent_raw - base_rate)`

`base_rate` is calculated only from prior resolved official samples with the identical target definition and is `0.5` when none exist. Once the agent/target has at least 50 resolved forecasts and Brier strictly better than base rate, `p_used = p_agent_raw`. Every calculation stores both values, the base rate, resolved-sample count, Brier comparison, and shrinkage rule version.

The deterministic no-AI and seeded-random arms have no agent probability. They log a **hypothetical** net edge using the prior resolved base rate for the identical target, or `0.5` when none exists, but that probability-derived number is not an admission gate. Those two baselines skip only the $0.50 minimum-net-edge and 2% expected-net-return checks. Quote freshness, registered-strategy eligibility and invalidation, liquidity, volatility and position caps, settled cash, verified holdings, every breaker, the global kill switch, and every other deterministic risk rule still apply. The 5× friction-ratio gate also remains mandatory and uses registered deterministic strategy gross edge divided by total modeled round-trip friction; a strategy without a computable registered gross edge is blocked.

This distinction is an acceptance test, not a narrative exception: a baseline candidate with hypothetical `p = 0.5`, hypothetical net edge of `-$0.50`, registered strategy gross edge of `$5.00`, modeled round-trip friction of `$0.50`, sufficient settled cash and liquidity, and every breaker/risk check clear must be allowed to open. The logged record must show both the negative hypothetical net edge and the passing 10× friction ratio.

## 12. Lane B qualified options pipeline

Lane B allows only long calls, long puts, and fully defined-risk multi-leg structures after the implementation supports atomic paper representation of every leg. Naked short options, uncovered exercise/assignment risk, and undefined-risk structures are prohibited.

Every option candidate or held option must contain all of these fields:

**Identity and contract terms**

- broker contract ID;
- underlying instrument ID and symbol;
- call/put and strategy structure;
- strike;
- expiration date and DTE;
- contract multiplier;
- exercise style;
- settlement type;
- tradability/state;
- all leg IDs, sides, ratios, and strikes for a multi-leg structure.

**Market and time**

- bid, ask, midpoint, absolute spread, percentage spread, and quote timestamp for every leg;
- underlying bid, ask, midpoint/last, and quote timestamp;
- volume and open interest for every leg;
- implied volatility, IV rank or percentile with lookback definition;
- delta, gamma, theta, and vega with calculation/source timestamp.

**Account, payoff, and events**

- settled buying power;
- current held quantity and average premium when applicable;
- quantity, total premium/debit, fees, estimated slippage, maximum loss, maximum gain or `UNBOUNDED_UPSIDE`, and breakeven(s);
- earnings/event date, timing confidence, and whether it occurs before expiry;
- planned entry, invalidation, target, maximum holding period, time exit, expiry action, exercise/assignment handling, and auto-exercise threshold;
- liquidity threshold result and maximum affordable contracts.

Missing any required field pauses Lane B with `REQUIRED_OPTIONS_FIELD_MISSING` and the dashboard lists each exact missing field and affected contract. Code never asks a model to infer it. Lane A continues independently, but a blocked Lane B idea cannot migrate into Lane A.

## 13. Counterfactual evaluation

Every official decision snapshot produces these arms where applicable:

1. `agent_alone` — model decisions without human approval filtering;
2. `agent_with_approvals` — the actual official paper arm;
3. `deterministic_no_ai` — top qualified discovery candidate sized by the same rules;
4. `seeded_random` — one candidate sampled from the same qualified shortlist;
5. `vti` — total-return VTI benchmark;
6. `cash` — uninvested cash;
7. `exposure_matched_vti` — VTI scaled to the agent arm's gross exposure for attribution;
8. `lane_b_delta_equivalent_underlying` — for every Lane B position, a virtual position in the underlying stock with signed shares equal to entry net delta × multiplier × contracts.

All arms use the identical source snapshot, timestamps, eligible set, price convention, settlement rules, sizing caps, and deterministic risk engine. The random seed is deterministically derived from registration ID, official date, lane, and snapshot hash and is stored each day.

The deterministic no-AI and seeded-random arms share one immutable exit rule: exit at the registered strategy invalidation or at the close of the twentieth session after entry, whichever comes first. Both use the same registered entry/exit spread, slippage, fees, and estimated-tax model. Neither an agent nor an operator may substitute a later exit after observing the outcome.

The Lane B underlying benchmark freezes entry delta and does not rebalance, uses the option's actual code-timed entry and exit timestamps, applies underlying spread/slippage/tax but no model API cost, and reports both dollar P&L and return normalized to Lane B maximum-loss capital. It is an attribution benchmark, not a tradable recommendation.

Every Portfolio selection creates a shadow `selection_reference` ledger before Critic or downstream admission decisions, including selections later hard-vetoed, advisory-dropped, trigger-not-fired, or risk-blocked. It uses the first eligible fresh midpoint after the Portfolio timestamp and an evaluation-only theoretical size from the ordinary volatility, liquidity, and position caps while ignoring Critic, trigger, approval, cash, breaker, and portfolio-admission blocks. If a valid reference price or theoretical size cannot be recovered by the next session close, the ledger resolves as `VOID_DATA` with the missing fields and exact reason. A void is retained and counted, but is neither success nor failure and is excluded from Brier and concordance scoring.

Each selection also creates a linked code-timing ledger where applicable:

- `selection_reference` is the always-created evaluation-only ledger above and never waits for the entry trigger;
- `code_timed` uses the same candidate, direction, exit plan, risk rules, and sizing method but enters only if and when the registered code trigger fires.

The return of `selection_reference` versus the deterministic and random selections measures candidate-selection value. `code_timed` minus `selection_reference` on matched selections measures timing value. Hard-veto, advisory resolution, trigger, and risk outcomes are annotations on the shadow ledger, not reasons to omit it. These ledgers write official evaluation and Critic-calibration records but are database- and API-isolated from cards, fills, holdings, cash, the official paper arm, and its P&L scoreboard. They store separate IDs, timestamps, prices, trigger version, costs, and disposition reason and may never overwrite the official paper arm.

Every candidate delivered to Research is resolved on the fixed primary ranking outcome, including candidates Research rejects or marks insufficient. The outcome is the candidate's 20-session total return from the first eligible fresh midpoint after the Research timestamp through the twentieth-session close, minus modeled entry/exit spread and slippage, minus the matched sector ETF's return over the same timestamps and friction convention. Live splits/reverse splits and ticker changes use Phase 0 normalization. An outcome affected by a merger, delisting, or unimplemented historical transformation remains visibly pending until Phase 2 can normalize it; it is never dropped, guessed, or scored from contaminated data.

For each Research batch with at least two resolved candidates, code compares Research's blinded rank and the screener's original rank using pairwise concordance: 1 for each correctly ordered pair, 0.5 for a tied realized outcome, and 0 for an incorrectly ordered pair. Each batch contributes equal weight. The **primary AI-value ranking test** is whether mean Research concordance is strictly greater than mean screener concordance over the same resolved batches. A one-candidate batch still receives an outcome but supplies no ranking pair.

Actual API cost is attributed only to the arm that incurred it. Agent costs are subtracted only from `agent_alone` and `agent_with_approvals`. VTI, cash, deterministic, and random arms never receive model API costs. Shared non-model market-data costs, if any, are reported separately and allocated by a pre-registered method rather than hidden.

Probabilities are stored for proposals, abstentions, rejections, Critic objections, and Portfolio decisions. Each probability stores the forecast type, target ID/version, benchmark, start timestamp, allowed stated horizon, resolution timestamp/rule, cost model, and eventual outcome of `SUCCESS`, `FAILURE`, or `VOID_DATA`. Brier scores and concordance are calculated only from success/failure outcomes after the target resolves. The dashboard reports void count, rate, reasons, and affected selection IDs. Monthly void rate is `VOID_DATA` divided by all `selection_reference` records whose resolution deadline falls in that calendar month. If the rate becomes strictly greater than 5%, Pushover pages once on that month's threshold crossing with the numerator, denominator, affected records, and causes.

## 14. Calibration and shadow Kelly

### 14.1 Forecast target registry

Every `forecast_probability` must reference one of these frozen targets:

| Forecast type | Probability means | Horizon and resolution |
|---|---|---|
| `RESEARCH_SECTOR_ALPHA` | Probability the researched stock beats its mapped sector ETF after modeled entry/exit spread and slippage | Fixed at 20 trading sessions until Research has 50 resolved forecasts; afterward Research may select 5, 10, 20, or 60 sessions. Resolve at that session's close from the first eligible post-Research midpoint. Applies identically to qualified, rejected, and insufficient-evidence candidates. |
| `PORTFOLIO_SELECTION_SUCCESS` | Probability the `selection_reference` ledger finishes above $0 after spread, slippage, estimated tax, and allocated API cost | Resolve at the earlier of the registered exit plan or its stated 5, 10, 20, or 60-session horizon. |
| `CRITIC_SELECTION_FAILURE` | Probability the criticized `selection_reference` fails its registered Portfolio target | Same horizon and always-created shadow outcome record as the corresponding Portfolio selection; `PASS`, `ADVISORY`, and `HARD_VETO` all resolve even when the official action is dropped or blocked. |
| `HOLDING_THESIS_SURVIVAL` | Probability a held stock avoids its deterministic invalidation and beats its mapped sector ETF after modeled exit spread | Fixed next 20 trading sessions or the earlier actual deterministic exit. |
| `OPTION_SELECTION_SUCCESS` | Probability the Lane B `selection_reference` earns a positive return after modeled spread, slippage, fees, estimated tax, and allocated API cost | Resolve at the registered exit or expiry, whichever is earlier. The exposure-equivalent underlying comparison is reported separately and does not redefine this binary target. |

Sector mapping is fixed to the eleven Select Sector SPDR benchmarks: XLC, XLY, XLP, XLE, XLF, XLV, XLI, XLB, XLRE, XLK, and XLU. A missing or ambiguous sector mapping makes the Research probability unscorable and the candidate `INSUFFICIENT_EVIDENCE`; code never substitutes VTI after the forecast is made.

Calibration is evaluated separately for Research, Portfolio, and Critic. The base-rate forecast uses only previously resolved official samples with the same target definition; it never uses the current outcome. Before 50 resolved forecasts for an agent and target, calibration is labeled `INSUFFICIENT_SAMPLE`.

An agent is calibrated for Kelly eligibility only when it has at least 50 resolved forecasts and its Brier score is strictly lower than the corresponding historical base-rate Brier score. Rejections count when their stated probability and outcome resolve.

Shadow Kelly may be calculated only if all conditions hold simultaneously:

1. at least 183 calendar days of official shadow history;
2. at least 30 completed round-trip trades;
3. every probability used for sizing comes from an agent/target with at least 50 resolved forecasts and Brier better than base rate;
4. positive cumulative after-cost performance;
5. maximum drawdown remains within the pre-registered Kelly gate.

Raw Kelly is `p - (1-p)/b`, where `b` is target gain divided by loss if wrong. Logged shadow size is the lesser of quarter Kelly and the ordinary deterministic position limit, further capped by volatility, cash, liquidity, and lane constraints.

The calculation is written only to evaluation tables. No approval, risk, broker, or order schema accepts a Kelly-sized quantity. Static analysis and integration tests must prove there is no code path from shadow Kelly output to a card or fill.

## 15. Backtesting, Monte Carlo, and champion/challenger governance

Strategy parameters and tested variants are pre-registered. The report states the number of variants tested. Walk-forward evaluation fits on one window and tests on the next, includes test periods covering 2008, 2020, and 2022 when history permits, and models bid/ask spread, slippage, estimated taxes, settled cash, dividends, and API cost where AI is used.

Each strategy is evaluated with and without AI signals. The AI version must beat the plain version after its own API cost to claim AI value. Metrics include CAGR, maximum drawdown, Sharpe, turnover, win rate, and after-cost excess versus total-return VTI. Until the Norgate source is licensed and validated, every report and chart is labeled `SURVIVORSHIP-BIASED`; no point-in-time claim is permitted. Single-stock tests remain limited to current mega-caps and report actual history length per ticker.

Monte Carlo uses 10,000 block-bootstrap return paths plus trade reshuffling and reports:

- probability of beating VTI after costs over one year;
- median and 5th-percentile drawdown;
- probability of losing more than $100 on a $500 lane, explained in plain English.

A strategy enters shadow candidacy only if it beats VTI after costs out of sample and Monte Carlo probability of beating VTI is at least 60%. AI variants must also beat their matching plain variants after AI cost.

Champion and challenger see the same official snapshots. Promotion requires the sample, after-cost, drawdown, calibration, and paired-comparison gates frozen in `preregistration.yaml`. A promotion exception may be proposed to the operator and expires after seven days. Even an approved exception cannot apply before eight weeks and 15 completed trades, cannot waive safety/data-integrity gates, and must say in plain language when the sample is too small to be meaningful. It never enables real trading.

Retirement and suspension rules are also frozen. Safety or data-integrity violations suspend immediately. Statistical retirement uses resolved official samples, not manually selected dates. All scoreboard comparisons that span preregistration versions are visibly labeled and may not be presented as a single homogeneous experiment.

### 15.1 Twelve-month AI stop rule

Beginning 365 calendar days after the first official run governed by this preregistration series, and monthly thereafter, AI may continue only when both gates pass over identical resolved official batches:

1. a registered 10,000-run paired bootstrap resampling resolved Research batches with replacement gives `P(Research pairwise concordance > screener pairwise concordance) ≥ 0.80`; and
2. the `agent_with_approvals` arm's cumulative after-cost return is greater than or equal to the `deterministic_no_ai` arm's cumulative after-cost return.

If either gate fails, or there are insufficient resolved ranking pairs to run the registered bootstrap, all Research, Portfolio, and Critic calls are automatically and persistently disabled with `AI_STOP_RULE_TRIGGERED`; the deterministic cycle, holdings rules, risk engine, benchmarks, dashboard, and weekly summary continue. Once triggered it does not self-reenable. Re-enabling AI requires an operator-approved preregistration version bump and begins a newly labeled experiment segment.

## 16. Cost ceilings and fixed degradation order

An official run with no `QUALIFIED_AI_ELIGIBLE_CANDIDATE` and no `HOLDING_QUALITATIVE_REVIEW_REQUIRED` must make zero model calls and record exactly $0 model cost. The official LLM ceiling when AI is needed is $0.40 per run and $0.40 per market date. A recovery attempt shares the remaining official daily ceiling; it does not reset it. A what-if LLM run has a $0.20 ceiling, is reported separately, and never consumes or changes the official experiment. Deterministic discovery, refreshes, holdings checks, breakers, and replay without new inference have no model budget.

The official target is less than $20 of actual API cost per lane per calendar year. Each lane receives a $1.65 allowance at its first official cycle of each calendar month, beginning with the first active month. Unused allowance carries forward within the same calendar year, but accumulated carried allowance is capped at **$5.00 per lane**. The month-opening available balance is `min($5.00, prior month closing unused allowance) + $1.65`, so the largest balance immediately after a monthly credit is $6.65. Future-month allowance cannot be borrowed, excess unused carry is forfeited, and all remaining allowance expires on January 1. The full-year released allowance and actual-spend ceiling remain $19.80 per lane. Preflight requires the planned call to fit both the current available balance and the remaining annual ceiling. Exhausted released allowance records `HOLD_OPERATIONAL: MONTHLY_AI_ALLOWANCE_NOT_AVAILABLE`; exhaustion of the full-year ceiling records `HOLD_OPERATIONAL: ANNUAL_AI_COST_TARGET_EXCEEDED`. The code-only cycle and deterministic benchmark arms still complete. No cost is shifted to the other lane to evade the target.

Using the registered reasoning-aware token envelopes and standard uncached rates in Section 7, official preflight reserves `$0.03` for Research, `$0.05` for Portfolio, and `$0.11` for Critic. Each stage reserve covers its first call plus its one possible schema-repair call. The reservations total `$0.19`; the remaining `$0.21` of the `$0.40` run ceiling is unallocated estimation headroom. Headroom may absorb billing-estimate variation but may not enlarge a stage's token envelope or create an extra attempt. The run reports the preregistered `$0.0848` one-attempt estimate, the `$0.1696` all-repairs estimate when relevant, and actual billed cost.

Before a call, the allocator proves the maximum planned remainder fits. If not, it drops work in this exact order:

1. optional third-and-later corroborating news sources;
2. Research candidates ranked 6 through 8;
3. Research candidate 5;
4. optional cross-candidate narrative synthesis and optional insider enrichment;
5. all new-entry research, leaving holdings review and deterministic baselines only.

It never drops authentication verification, holdings review, quote freshness, source/citation validation, the Critic for an AI proposal, risk checks, schema validation, official persistence, or required-action/failure notifications. If the minimum safe path still cannot fit, the lane records `HOLD_OPERATIONAL: BUDGET_MINIMUM_NOT_AVAILABLE` instead of throwing an opaque failure.

The dashboard shows reserved, committed, actual, and dropped work by stage; actual cost per run and lane; calendar-year actual and trailing-365-day actual; and the official annual target. What-if spend is displayed separately. No fallback model is selected to save money.

## 17. Replay, prompt versions, tracing, and storage

SQLite is the durable system of record. Each official run stores:

- run, registration, settings, strategy, code commit, model, and prompt versions;
- exact immutable agent inputs and validated outputs;
- source records and content hashes;
- permanent security identities, corporate actions, normalization factors, universe membership mode, and exclusion reasons;
- strategy signals, ranks, EQS components, citation checks, and injection flags;
- schema attempts and validation errors;
- Critic packet hash proving Portfolio reasoning exclusion;
- separate agent-selection and code-timing records;
- breaker and kill-switch state transitions;
- risk checks, cards, approvals, paper fills, positions, cash, and settlements;
- all counterfactual arm states, random seeds, costs, forecasts, and outcomes;
- traces, Pushover delivery records, lessons, and promotion decisions.

OpenAI Agents SDK trace events are correlated with the local run ID and persisted in SQLite for the single local dashboard. SQLite and that dashboard are the complete required observability and experiment stack. Phoenix and MLflow are not runtime dependencies, acceptance gates, scheduled services, or official stores. Either may be started manually only for a bounded debugging session, disabled by default, and may neither write official experiment state nor change cycle behavior. Secrets, account identifiers, tokens, raw passwords, and verification codes are redacted before every stored or temporary debug trace.

Replay reconstructs the exact stored inputs, prompt, model, validated reasoning effort, source hashes, and settings. Temperature is absent and rejected. Deterministic replay must be byte-stable. An LLM re-execution is labeled a new research comparison, never a reproduction of identical model output, and obeys the what-if budget and isolation rules.

Every what-if row stores its required `parent_official_run_id`; replay rows store the original run ID and never masquerade as what-if children.

## 18. Verification matrix

No phase may be declared complete without passing current-code tests and producing the named evidence.

### 18.1 Phase 0 required tests

- hostile real order, cancel, exercise, transfer, deposit, and withdrawal attempts are blocked before external dispatch;
- both OAuth paths enforce the exact eleven-read proxy inventory at three layers and reject every write before dispatch;
- the proxy runs as the dedicated non-admin `robinhoodproxy` user and owns its Keychain/files; the main process succeeds with Keychain and proxy-file access set to fail on use; the group socket accepts only the registered operator UID and rejects other users; neither process logs secrets;
- the bounded-cash fallback accepts finite nonnegative cash at or below $1,200 only when buying power and unleveraged buying power exactly equal cash, and otherwise returns `HOLD_OPERATIONAL: AGENTIC_ACCOUNT_OUTSIDE_BOUNDS`;
- an in-cap cash increase with unchanged positions and order histories records `ACCOUNT_CASH_INCREASE_BENIGN` without paging or latching; a cash decrease, position change, new/changed order activity, or above-cap cash pages, latches the global kill switch, shows revocation instructions, and cannot rearm without operator acknowledgement;
- authorization expiry pages once at three days and one day, a refresh failure pages immediately, and expired authorization returns `HOLD_OPERATIONAL: AUTH_EXPIRED`;
- a real test disconnect makes the old credential unable to read, and fresh operator re-authorization restores only the eleven-read proxy session without reporting amounts or identifiers;
- weekend, holiday, early-close, missed-minute, stale-claim, and duplicate scheduler cases;
- fixture run cannot claim or complete an official day or write official tables;
- live split, reverse-split, and ticker-change normalization before discovery and agent input;
- global kill switch plus daily, weekly, peak-to-trough, and hard-lock breakers block entries while allowing exits;
- no qualified AI candidate and no qualitative holdings review produces zero model calls and exactly $0 cost;
- stale quote excluded per symbol; fresh symbols continue; final refresh occurs before approval;
- stale-only lane returns `HOLD_OPERATIONAL`, not `HOLD_CASH`;
- budget reservation follows the fixed order and produces an operational hold when necessary;
- each lane receives exactly $1.65 monthly allowance, accumulated carry never exceeds $5.00, the post-credit balance never exceeds $6.65, future allowance cannot be borrowed, and year-end carry expires;
- Pushover pages only failures and required actions and records delivery status;
- the non-urgent weekly Pushover summary is emitted once with registered contents, while routine events never page;
- installed scheduled cycle proof in Section 3.8.

### 18.2 Phase 1 required tests

- each agent schema valid and exactly one repair attempt recorded;
- every configured model ID is a dated snapshot, floating aliases fail validation, and a model change without a preregistration version bump is rejected;
- Research is registered at low reasoning effort, Portfolio and Critic at medium, temperature is rejected, and unsupported or unregistered inference parameters fail validation before dispatch;
- reasoning tokens count against each stage's registered output envelope; the one-attempt `$0.0848` and all-repair `$0.1696` estimates recalculate from frozen prices and token caps, while actual cost is stored per run;
- unavailable assigned model fails visibly with no substitution;
- EQS is code-computed before Portfolio and low/missing-critical dossiers cannot pass;
- factual numbers and dates match cited source records; uncited material claims veto;
- prompt-injection text quarantined before model input;
- Research abstains on missing critical evidence;
- Critic packet structurally excludes Portfolio reasoning and uses a different model;
- every final hard-veto category and advisory one-rebuttal path;
- Portfolio schema rejects entry price, timing, and quantity fields and emits only ranked conviction selections;
- code entry triggers and Risk Engine sizing are separately persisted and cannot be supplied by an agent;
- matched selection-reference and code-timed ledgers isolate selection value from timing value;
- every Portfolio selection receives an isolated shadow `selection_reference`, including hard veto, unresolved advisory, trigger-not-fired, and risk-blocked dispositions, so every Critic verdict resolves without touching the official paper arm; an unrecoverable record becomes counted `VOID_DATA`, not a fabricated loss;
- holdings review completes before discovery, including mandatory option review;
- multi-action ordering and lane-specific holds;
- closing quantity never exceeds holdings; exits remain permitted despite entry blocks;
- buy notional plus friction never exceeds settled cash;
- no-AI and seeded-random arms share snapshot/sizing/risk; seed persisted;
- a deterministic baseline with hypothetical `p = 0.5` and negative hypothetical net edge opens when its registered 10× friction ratio, liquidity, cash, breaker, and every other deterministic gate pass, proving only probability-based net-edge admission is bypassed;
- both baseline arms exit at registered strategy invalidation or the twentieth-session close, whichever is earlier, under the same friction model;
- API cost subtracted only from agent arms;
- same-day approval cards expire at the official close, including early closes, and cannot carry forward;
- an approved paper action uses a fresh approval-time quote plus registered slippage, while a price beyond the code limit produces no fill;
- with midpoint $100.00, maximum limit distance 0.50%, ask $100.10, and 0.10% buy slippage, the $100.2001 paper fill succeeds because it is within the $100.50 code limit;
- uncalibrated probabilities use and log the registered half-shrinkage toward prior base rate, while calibrated probabilities use and log raw probability;
- deterministic and seeded-random arms use the prior resolved same-target base rate, defaulting to 0.5 with no prior samples, only to log hypothetical net edge;
- failure-pattern memory accepts only resolved official/cited patterns.

### 18.3 Phase 2 required tests

- every Research candidate, including rejections and abstentions, receives the registered forward outcome and a resolvable forecast record;
- Research is forced to the 20-session target until 50 Research forecasts resolve, after which only registered horizons are accepted;
- Research candidate order is reproducibly randomized, its packet contains no screener rank, score, or rank-only proxy, and the seed and permutation replay exactly;
- every probability names a registered target whose benchmark, horizon, costs, and success/failure/void resolution rule is enforced before scoring;
- `VOID_DATA` is excluded from Brier and concordance, remains counted with a reason, and a monthly rate strictly above 5% pages once with the correct numerator and denominator;
- Research and screener rankings are scored on identical resolved candidates using the registered pairwise-concordance test;
- probability persistence for selections, rejections, abstentions, and Critic verdicts and per-agent/per-target Brier calculations;
- base-rate calculation uses only prior resolved samples;
- the twelve-month continuation check uses the registered paired bootstrap and disables AI when either the 0.80 ranking-probability gate or after-cost no-AI gate fails, persists the disablement, and cannot self-reenable;
- every Kelly gate required simultaneously and no Kelly-to-card/fill path;
- what-if/replay API and SQLite authorizer reject official cards, fills, scoreboard, and lessons writes;
- every what-if requires a valid immutable `parent_official_run_id`;
- source hashes change with content and not merely metadata;
- exact deterministic replay reconstruction;
- historical split/reverse-split normalization, cash and stock mergers, delistings, historical holdings conversion, and their no-lookahead rules;
- each Lane B required field can independently pause the lane with its name visible;
- Lane B block cannot produce a Lane A action;
- each Lane B position is compared with its frozen-entry-delta exposure-equivalent underlying benchmark on the same entry/exit timestamps and cost convention;
- total-return/no-lookahead walk-forward includes named regimes and counts variants;
- 10,000-run Monte Carlo metrics and plain-English $500 loss statement;
- AI/no-AI ablation charges costs correctly;
- Norgate source validation gates point-in-time claims; fallback labels every backtest survivorship-biased;
- capital-viability arithmetic and cost totals match their frozen formulas;
- promotion, seven-day exception expiry, minimum sample warning, and retirement rules;
- the default installation runs with SQLite and one dashboard only; optional Phoenix/MLflow debugging cannot write official state or alter a cycle;
- dashboard exposes every stage, source status, exclusion reason, lane, planned/completed/missed state, cost, and operator control without inventing missing data.

## 19. Dashboard and operator controls

The dashboard is an evidence-first decision room, not an agent chat. It shows:

- current safety state, authentication health, scheduler claim, next official run, last result, and notification health;
- the full universe funnel: eligible, excluded, ranked, live-verified, researched, vetoed, risk-blocked, proposed;
- each agent as a structured entity with mandate, inputs, source-backed output, uncertainty, handoff, model/prompt version, duration, and cost, or an explicit `NOT NEEDED · $0` state;
- quote ages, source availability, news enabled/disabled, exact missing evidence, and repair action;
- holdings review before discovery and all action ordering;
- per-lane results, `HOLD_CASH` versus `HOLD_OPERATIONAL`, and exact blockers;
- official, what-if, and replay records with unmistakable isolation labels;
- all benchmark arms, after-cost results, API cost attribution, calibration, and preregistration-version boundaries.
- every Portfolio selection's isolated shadow-ledger disposition and eventual Critic-scoring outcome;
- raw agent probability, shrunk probability used for net edge, prior base rate, and calibration state;
- baseline hypothetical probability/net edge beside the independently enforced friction and safety gates;
- `VOID_DATA` count, monthly rate, reasons, affected selections, and notification state;
- estimated and actual API cost per run, lane, calendar year, and trailing 365 days, monthly allowance released/carried/remaining and its $5 carry cap, with what-if spend separated.

Controls include pause/resume paper activity, refresh data now (code-only), run a what-if review, choose permitted what-if emphasis without changing preregistered official rules, answer YES/NO on pending paper cards, export the review package, and view trace/replay evidence. Controls never expose real-order capability.

News status is explicit: enabled and healthy, enabled but failed with source/error, or disabled with the exact policy reason. Any run with news disabled is labeled in its header, dossiers, and scoreboard record.

### 19.1 Capital viability panel

The dashboard includes a panel titled **Capital viability — arithmetic, not a forecast**. It uses measured costs and plain multiplication only:

- measured calendar-year-to-date and trailing-365-day API cost by lane and total; if fewer than 365 days exist, the annual measure is labeled incomplete and an annualized run rate is shown separately;
- break-even capital at 1% drag = trailing annual API cost divided by `0.01`;
- break-even capital at 2% drag = trailing annual API cost divided by `0.02`;
- for starting capital of $500, $2,000, $10,000, and $50,000, the one-year arithmetic ending value and dollar change at 0%, 5%, 10%, and 15% annual after-cost return: `ending_value = capital × (1 + rate)` and `dollar_change = capital × rate`.

The label appears in the panel title, exported report, and tooltip. These scenarios are not probabilities, targets, expected returns, or investment advice.

## 20. `preregistration.yaml` governance

The root `preregistration.yaml` is loaded read-only by the application. Its canonical bytes are hashed into every official run. The dashboard has no write endpoint for it.

Only the operator may authorize a change. A valid change requires:

1. a new semantic version;
2. an effective date after the change is committed;
3. a plain-language reason in `change_history`;
4. the prior version retained in Git history;
5. a new approval record before the next official run.

If the file changes without these fields or without operator approval, official execution returns `HOLD_OPERATIONAL: PREREGISTRATION_INVALID`. Comparisons crossing versions are segmented and labeled. The file must be committed before the first official cycle governed by this architecture.

## 21. Review boundary

This specification and `preregistration.yaml` define all required work through Phase 2, including exact Phase 0 gates. Their commit does not claim that any requirement is implemented or operationally proven. After this review package is approved, work begins at Phase 0 and stops at its gate until the scheduled read-only proof passes.
