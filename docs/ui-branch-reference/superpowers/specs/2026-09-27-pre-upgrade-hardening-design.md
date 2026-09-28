# Pre-Upgrade Hardening — Design

Date: 2026-09-27

Status: Approved design; written specification awaiting user review

Extends:

- `2026-09-27-robinhood-ai-trading-agent-design.md`
- `2026-09-27-agentic-shadow-cycle-upgrade-design.md`

This specification is a prerequisite for the agentic shadow-cycle upgrade. Where it conflicts with the earlier upgrade design, this document controls. In particular, it replaces the two-times-per-day LLM schedule with one full LLM cycle at 10:00 ET, sets the $500-account budget and model split, and replaces the assumed host-injected MCP adapter with a proven Codex CLI bridge.

## Intent and success criteria

Make the current Stage 1 system operationally usable and safe for a $500 shadow account before adding broader agentic behavior. The hardening milestone succeeds only when:

1. a real authenticated Robinhood read-only cycle completes through the existing Codex OAuth session;
2. no Stage 1 execution path can expose a Robinhood order, cancel, exercise, transfer, or unknown future write tool;
3. the deterministic risk engine independently validates actual holdings, settled cash, and volatility-scaled sizing before any paper broker call;
4. the daily LLM budget, models, schedule, universe, and two paper asset lanes are explicit configuration;
5. approval cards persist until an explicit YES, NO, or configured expiry and can be answered through a loopback-only local inbox;
6. the scoreboard charges model/API costs only to the two agent evaluation tracks, never to VTI or cash;
7. `GOOD IF` is supplied by the proposal rather than invented by the renderer; and
8. weekly results are generated automatically, stored by ISO week, and remain available for longitudinal comparison; and
9. every behavior has an automated regression test and all pre-existing safety tests still pass.

## Selected authentication approach

### Selected: `codex exec` as a least-privilege authenticated bridge

Use `codex exec` for scheduled model calls and Robinhood MCP access. The current machine was probed successfully on 2026-09-27 with:

- Codex CLI `0.153.4`;
- the configured remote MCP server `https://agent.robinhood.com/mcp/trading`;
- the existing stored OAuth session;
- `--sandbox read-only`;
- `--ignore-user-config` plus an explicit one-server configuration;
- `mcp_servers.robinhood-trading.enabled_tools=["get_accounts"]`; and
- a JSON output schema.

The real probe called `get_accounts` exactly once and returned three accounts, including the dedicated Agentic account ending in `6613`. It performed no broker write.

The bridge must execute Codex with an argument vector, never a shell command string. It must use `--ignore-user-config` because the installed CLI rejects the desktop-only `computer-history` transport in the shared configuration. Authentication still comes from Codex's credential store. Each invocation explicitly declares only the Robinhood server and the exact read tools required for that invocation.

Research runs may receive a narrow read-only MCP allowlist. Portfolio and Critic runs receive no MCP server at all. Every bridge invocation uses an isolated empty working directory, `--skip-git-repo-check`, `--ephemeral`, `--sandbox read-only`, and a Pydantic-derived output schema. Tool-call events and final output are parsed without persisting raw brokerage payloads or full account identifiers.

### Rejected: Python-owned MCP OAuth and Keychain tokens

Do not implement application-owned OAuth now. The existing Codex OAuth session works, while custom OAuth would add token refresh, revocation, scope, callback, storage, and redaction code. macOS Keychain would reduce plaintext exposure but would not remove those failure modes.

If the Codex CLI bridge stops being supported or cannot meet future latency requirements, application-owned OAuth is a separate reviewed project. The application must never request a Robinhood password or verification code.

## Architecture

```text
launchd at 10:00 ET
        |
        v
DailyCycleGate -- trading day? -- already completed today? -- budget available?
        |
        v
CodexExecRunner
        +--> Research Agent: GPT-5.6 Luna + exact read-only Robinhood MCP tools
        +--> Portfolio Agent: GPT-5.6 Terra, no MCP
        +--> Critic: GPT-5.6 Terra, no MCP
        |
        v
typed proposal + critic
        |
        v
deterministic RiskEngine
        |
        +--> Asset Lane A: stocks/ETFs, $500 reference capital
        |       +--> agent-alone counterfactual
        |       +--> approval counterfactual
        |
        +--> Asset Lane B: defined-risk options, $500 reference capital
                +--> agent-alone counterfactual
                +--> approval counterfactual
        |
        v
SQLite approval inbox --> localhost web page --> YES / NO / expiry
        |
        v
scoreboard, trace, evaluator, samples

Friday 16:30 ET report gate
        +--> deterministic WeeklyReportBuilder
        +--> SQLite weekly snapshot + reports/weekly/YYYY-Www.md

Existing five-minute supervisor loop
        +--> deterministic schedule/status/expiry/stall checks only
        +--> no model invocation
```

The two counterfactual evaluation tracks do not pool or double deploy capital. Each asset lane has one $500 reference account duplicated into agent-alone and approval variants solely to measure the value of approvals under the same proposal stream.

## Configuration

Replace the single model key with explicit keys:

```yaml
starting_cash_usd: 500.00
daily_api_budget_usd: 0.40
research_model_name: gpt-5.6-luna
portfolio_model_name: gpt-5.6-terra
critic_model_name: gpt-5.6-terra
full_llm_cycle_time_et: "10:00"
weekly_report_day_et: Friday
weekly_report_time_et: "16:30"
approval_expiry_minutes: 30
paper_lanes:
  stocks_etfs_starting_cash_usd: 500.00
  options_starting_cash_usd: 500.00
risk:
  target_position_fraction: 0.10
  target_volatility_fraction: 0.20
```

Research uses Luna because it is the inexpensive high-volume model. Portfolio and Critic use Terra because it is materially stronger while remaining compatible with a $0.40 daily ceiling. Model keys remain separate even when Portfolio and Critic use the same configured value.

Configuration validation requires:

- Stage 1 and the paper broker;
- exactly one valid `HH:MM` full-cycle time inside regular market hours;
- a valid weekly report weekday and time;
- positive $500 lane balances;
- daily budget exactly `$0.40` in the shipped $500 profile;
- positive target and volatility fractions;
- target position fraction no greater than the hard position limit;
- approval expiry greater than zero; and
- distinct non-empty Research, Portfolio, and Critic model keys.

The exact seeded trading whitelist is:

```text
SPY QQQ VTI SOXX XLE XLU GLD TLT AAPL MSFT NVDA AMZN GOOGL META
```

No implicit symbols may be added by the model, scanner results, sample data, or current holdings. Configuration changes remain human-owned.

## Daily schedule and budget

Launchd invokes the daily cycle at 10:00 America/New_York. The Python gate checks the NYSE trading calendar and a persisted `(local_trading_date, strategy_version)` idempotency key before any model call. A restart may retry an incomplete cycle, but a completed cycle cannot run twice that day.

The existing five-minute process is retained for deterministic functions only: health, stale pending-card expiry, service status, paper-order state, and stall detection. It cannot call a model or create a proposal.

The bridge parses Codex usage events and records input, cached-input, reasoning-output, and output tokens per agent call. A versioned local pricing table computes a conservative API-equivalent estimated cost. The daily budget gate reserves the maximum configured cost before each call and reconciles it afterward. Once actual plus reserved estimated cost reaches `$0.40`, no further model call is permitted that day.

Because Codex currently uses ChatGPT-managed authentication rather than an API key, the ledger must label this value `estimated_api_equivalent_cost_usd`. It must not falsely describe it as an externally billed API charge. The scoreboard's API-cost column uses the recorded cost measure consistently and labels estimates in the report metadata.

## Live prices and current news

The Research invocation obtains brokerage prices, portfolio data, positions, volatility inputs, fundamentals, filings, earnings data, and tradability through the exact Robinhood MCP read-tool allowlist. It must never infer a live price from web content when the Robinhood quote is absent or stale.

The same Research invocation enables Codex live web search for current news with `--search` or the equivalent per-run `web_search="live"` override. Portfolio and Critic invocations explicitly set `web_search="disabled"` and receive no MCP server. This keeps external retrieval inside the inexpensive Research call.

Web search is constrained to a reviewed domain list covering primary filings, issuer investor-relations sites, exchange/fund-provider sources, and selected established news wires. Every news fact requires a source URL and observation timestamp. Search output is untrusted data: embedded instructions are flagged, never executed, and cause the affected evidence item to be rejected. Search events and citations are retained in the sanitized research ledger; page bodies are not copied wholesale into SQLite.

If live search is unavailable, the Research result records missing news coverage. It may still support a proposal using complete non-news evidence, but it cannot claim that current news was checked. The Portfolio Agent sees the missing-evidence flag and may choose no trade.

## Deterministic risk rules

### Actual holdings and closing claims

Extend `RiskContext` with actual position quantities by instrument. For every sell, the risk engine requires:

- a held position for the exact instrument; and
- `proposal.quantity <= held_quantity`.

Otherwise it blocks with `INSUFFICIENT_POSITION`. If `is_closing` is true while the side is not `sell`, it blocks with `INVALID_CLOSING`. A valid closing order is a sell backed by sufficient actual quantity. Setting `is_closing=true` never bypasses position, cash, duplicate, kill-switch, account, instrument, quote, or injection rules.

These checks occur in `RiskEngine.evaluate` before any paper broker method is called. Paper broker checks remain defense in depth, not the primary control.

### Settled cash

For each opening buy, compute risk notional as:

```text
quantity × limit price × contract multiplier
```

The contract multiplier is `1` for stocks/ETFs and `100` for options unless the typed proposal explicitly supplies another positive supported multiplier. If notional exceeds `RiskContext.settled_cash`, block with `INSUFFICIENT_SETTLED_CASH` before the paper broker.

Unsettled cash does not count. The risk engine uses the lane's actual settled-cash snapshot, not a model-provided value.

### Volatility-scaled sizing

For opening buys, the allowed fraction is:

```text
scaled_fraction = target_position_fraction
                  × (target_volatility_fraction / realized_volatility_20d)
allowed_fraction = min(scaled_fraction, max_position_fraction)
allowed_notional = account_value × allowed_fraction
```

The proposed post-trade position value must not exceed `allowed_notional`. Missing, zero, negative, non-finite, or stale 20-day realized volatility blocks with `INVALID_REALIZED_VOLATILITY`. Closing orders are exempt from volatility sizing but remain subject to actual-position validation.

Realized volatility is supplied by deterministic market-data preparation and is represented as a decimal fraction: `0.20` means 20% annualized volatility.

### Defined-risk options

Lane B accepts options only when:

- Stage 1 remains paper-only;
- `option_strategy` is present and belongs to the configured defined-risk set;
- `max_loss_usd` is present, positive, and no greater than the lane's settled cash;
- `naked_short_call` is false; and
- the order has a positive contract multiplier.

The first supported set is long calls, long puts, call debit spreads, and put debit spreads represented as a quoted defined-risk strategy instrument. Credit spreads, naked options, exercise instructions, and live option orders remain blocked. The approval card always shows maximum loss.

## Paper asset lanes and evaluation tracks

Introduce an `AssetLane` value: `STOCKS_ETFS` or `DEFINED_RISK_OPTIONS`. A deterministic router rejects proposals whose asset class does not match their lane.

Each lane owns two paper brokers initialized from the same `$500` reference capital:

- `agent_alone`: executes every risk-allowed paper proposal immediately;
- `with_approvals`: executes only after the matching inbox card receives YES before expiry.

For controlled counterfactual comparison, the approval track uses the proposal-time paper quote stored with the card. Human response latency is recorded separately and is not modeled as a second price-discovery process in this milestone. A future execution-latency experiment may use a fresh deterministic quote, but it must not silently change this comparison.

NO and expiry create an explicit skipped fill for the approval track. They do not undo the agent-alone counterfactual.

## Persistent approval inbox

Add a normalized SQLite `approval_inbox` table with a unique `card_id`, lane, proposal/order/quote payloads, body, local trace URL, issued and expiry timestamps, status, decision timestamp, and response seconds.

Allowed state transitions are:

```text
PENDING --> YES
PENDING --> NO
PENDING --> EXPIRED
```

Transitions are atomic. A resolved or expired card cannot be answered again. Expiry duration comes only from `approval_expiry_minutes`; no component hard-codes 30 minutes.

The loopback web application binds to `127.0.0.1`, lists pending cards, and accepts same-origin POST actions for YES and NO. It rejects non-loopback Host headers, cross-origin requests, unknown decisions, duplicate decisions, and expired cards. It does not expose Robinhood credentials or accept any real-trade instruction.

Issuing a proposal persists the card and returns immediately. The daily cycle never invents a human decision and never auto-approves.

## Proposal and approval-card schema

Add required proposal field:

```text
good_if: non-empty plain-language condition
```

`ApprovalCardRenderer` prints the proposal's exact `good_if` value. It must not synthesize “Good if the thesis holds.” `BAD IF` continues to use the proposal's invalidation condition.

The `$500` sample card must show internally consistent quantity, price, maximum loss, cash after the trade, and holdings after the trade. The card stays at or below 150 words and links only to the local trace viewer.

The Portfolio prompt receives a new immutable version requiring `good_if`, lane, defined-risk metadata where relevant, and quantities consistent with a $500 reference account. Old prompt versions remain available for replay but cannot produce current-schema live cycle decisions.

## Scoreboard semantics

Scoreboard calculations are:

```text
Agent alone net P&L
  = gross P&L - non-API trading costs - recorded model/API cost

Agent + my approvals net P&L
  = gross P&L - non-API trading costs - recorded model/API cost

VTI benchmark net P&L
  = VTI gross P&L

Cash benchmark net P&L
  = 0
```

VTI and cash lines always report API cost `$0.00`. Their summaries must not say they paid AI costs. The same daily model cost is charged once to each independent agent counterfactual because each track is evaluated as a complete strategy, but it is never subtracted more than once within a track.

Reports distinguish Lane A and Lane B results, plus a combined view that does not pool the counterfactual copies as real capital.

## Scheduled weekly reports and longitudinal results

Add a deterministic `WeeklyReportBuilder` that reads only persisted decisions, paper fills, daily values, benchmark values, approval outcomes, risk verdicts, model-cost records, and lane balances. It performs no model call and no Robinhood call.

The five-minute supervisor invokes the report gate. At or after Friday 16:30 America/New_York, the gate writes exactly one report for the ending ISO week. If the service was down, the next supervisor tick catches up the most recent missing week once. A persisted `(iso_year, iso_week, strategy_version)` key prevents duplicates across restarts.

Each report is stored both as:

- an immutable SQLite `weekly_reports` snapshot containing the calculated metrics and source date range; and
- a plain-English Markdown artifact at `reports/weekly/YYYY-Www.md`.

The report includes separate Lane A and Lane B sections, agent-alone and approval counterfactuals, VTI and cash benchmarks, estimated model/API-equivalent cost, non-model trading costs, calibration, approval value, risk-rule counts, proposal/hold/failure counts, weekly and since-inception returns, and a compact history table. VTI and cash never absorb model costs in either weekly or since-inception calculations.

A week with no completed cycle still produces an honest zero-activity report rather than silently disappearing. Historical weekly snapshots are append-only and are never recalculated using later prices or altered cost assumptions.

## Storage and observability

Persist:

- daily-cycle idempotency and status;
- weekly-report idempotency and immutable weekly metric snapshots;
- sanitized Codex invocation metadata;
- MCP tool names and success/failure without raw OAuth data;
- per-agent token usage and estimated cost;
- lane and evaluation-track identifiers on orders/fills/values;
- volatility inputs and calculated size caps in risk records;
- approval state transitions and response latency; and
- local trace identifiers.

Account identifiers are masked outside the minimum broker-call boundary. Raw Codex event streams and raw brokerage payloads are temporary and deleted after validated, redacted records are committed. Phoenix and MLflow remain loopback/local only.

## Error handling and fail-closed behavior

- If Codex authentication or Robinhood OAuth is unavailable, the cycle records `SKIPPED_AUTH` and makes no proposal.
- If MCP initialization fails, required-server mode fails the Research call rather than continuing without data.
- If the CLI exposes a tool not in the invocation allowlist, it is unavailable to the model.
- If structured output fails Pydantic validation after one correction attempt, the cycle fails closed.
- If the daily budget cannot reserve the next model call, the cycle records `SKIPPED_BUDGET`.
- If a risk input is missing, invalid, or stale, the proposal is blocked rather than filled by the paper broker.
- If the local inbox is down, cards remain pending in SQLite and no approval-track fill occurs.
- If a YES arrives after expiry, the card becomes or remains expired and no fill occurs.
- Stage 1 never provides a live Robinhood write tool, regardless of card decision.

## Test strategy

Implementation follows red-green-refactor. Each numbered user requirement has at least one direct regression test:

1. Scoreboard: both agent tracks pay the cost; VTI and cash show zero cost and unchanged values.
2. Configuration/schedule: `$0.40`, three model keys, Luna/Terra split, exactly one 10:00 ET trading-day LLM run, and model-free intraday checks.
3. Risk: false close, oversized sell, missing position, insufficient settled cash, option multiplier cash use, and proof that these fail before a broker double is invoked.
4. Whitelist: all 14 seeded symbols pass; a non-seeded symbol fails.
5. Auth bridge: generated argv contains read-only sandbox, ignored user config, required Robinhood MCP, and exact enabled-tools list; a sanitized integration test runs a real `get_accounts` cycle when the existing OAuth session is available. Real-auth integration is marked separately but must be run and reported for this milestone.
6. Approval inbox: pending persistence across restart, YES, NO, exact configured expiry boundary, duplicate-decision rejection, loopback-only web security, and delayed approval-track fill.
7. Lanes/sizing: `$500` lane initialization, deterministic asset routing, defined-risk option requirements and displayed max loss, volatility formula below/at/above caps, and invalid-volatility rejection.
8. Proposal/card: `good_if` is required and rendered verbatim; the generated sample balances to `$500`.
9. Current data: Research bridge arguments enable live web search plus exact Robinhood read tools; Portfolio and Critic disable both; missing news coverage is visible and sourced news retains URL/timestamp provenance.
10. Weekly reporting: Friday 16:30 ET generation, restart catch-up, duplicate suppression, zero-activity weeks, immutable history, lane separation, and unchanged VTI/cash cost semantics.

Mandatory unchanged safety coverage includes Stage 1 real-order, cancel, exercise, watchlist-write, money-moving, and unknown-tool blocks before invocation.

Final verification requires:

- the complete test suite;
- focused risk, paper broker, approval, scoreboard, daily scheduler, weekly report scheduler, and bridge tests;
- all golden scenarios and replay regression gates;
- Python compilation and lint;
- plist validation;
- one real read-only end-to-end cycle using the existing OAuth session;
- generated `$500` sample card and scoreboard; and
- service restart/status checks with no live broker write tools exposed.

## Rollout gates

1. Ship and verify the Codex bridge with `get_accounts` only.
2. Expand the Research invocation only to the reviewed read tools required by the daily cycle.
3. Run one manual 10:00-equivalent real read-only cycle end to end and inspect its trace, sanitized tool ledger, costs, and proposal/card or hold-cash result.
4. Run three consecutive manual cycles without policy, schema, budget, authentication, data-quality, or risk-input failure.
5. Enable the launchd daily schedule.
6. Verify one scheduled weekly report and its persisted snapshot.
7. Keep all execution in Stage 1 paper mode. Live Robinhood trading remains a separate Stage 2 project and decision.

## User operation

The user starts two local services:

- the existing deterministic supervisor; and
- the loopback approval inbox.

Launchd runs the full model cycle at 10:00 ET on eligible trading days. When a proposal passes deterministic risk, the user opens the local inbox and answers YES or NO within the configured window. If no answer is given, the card expires and only the agent-alone counterfactual remains.

After Friday's close, the deterministic supervisor creates the weekly report automatically. The user can open the latest Markdown report or compare the append-only historical snapshots without starting another model run.

The user never supplies a password, verification code, OAuth token, or API key to this project. Every operational view clearly labels Stage 1, paper execution, the asset lane, the model-cost estimate, and whether the Robinhood data was live read-only or fixture data.

## References

- [Codex MCP configuration and OAuth](https://learn.chatgpt.com/docs/extend/mcp)
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Codex web search](https://learn.chatgpt.com/docs/web-search)
- [OpenAI model selection](https://developers.openai.com/api/docs/guides/model-selection)
