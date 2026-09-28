# Robinhood AI Trading Agent — Stage 1 Design

## Authority and intent

This design implements the user-supplied “Codex Build Prompt: Robinhood AI Trading Agent (v4, final).” That prompt is authoritative. The system is a local research, proposal, paper-execution, and evaluation harness built around the OpenAI Agents SDK. It defaults to Stage 1 shadow mode and cannot send real Robinhood orders, cancellations, exercises, transfers, or any other write in that stage.

The operator sees short approval cards and answers YES or NO. The paper broker records both an agent-alone track and an agent-plus-approval track. Nothing moves to live trading without an explicit future unlock and a separate regression-gated configuration version.

## Verified environment boundary

The official Robinhood Trading MCP is visible in the current Codex session:

- Server: `robinhood-trading`
- URL: `https://agent.robinhood.com/mcp/trading`
- Local status: enabled
- Authentication mode: OAuth
- Current tool inventory: 76 `mcp__robinhood_trading__*` tools
- Resources: `trading://api-errors`, `asset-types`, `feature-availability`, `market-hours`, `order-types`, `scanner-filter-specs`, and `time-in-force`

Visibility does not imply that the local application can inherit the Codex host’s OAuth session. The Robinhood adapter therefore accepts a host-provided MCP invoker. Until such an invoker is wired and authenticated, tests and demonstrations use recorded/mock responses. No credentials, passwords, or verification codes are requested or stored.

## Architecture

The initial architecture is one local Python process with focused modules and a SQLite database:

`Research Agent → Portfolio Agent → Critic → Risk Engine → Approval Card → Broker → Evaluator`

- `agents/`: OpenAI Agents SDK definitions, Pydantic outputs, retry-once validation, workflow orchestration, and the market-day runner.
- `risk/`: deterministic rules only. It has no model dependency and returns structured verdicts the model cannot override.
- `broker/`: one protocol with a paper implementation and a Robinhood MCP adapter.
- `eval/`: outcomes, calibration, attribution, scoreboards, replay, lessons, proposals, and champion/challenger gates.
- `prompts/`: immutable, versioned research, portfolio, and critic prompts.
- `config/`: editable risk and runtime configuration. Stage 1 is the default.
- `data/`: SQLite and point-in-time snapshots; ignored by Git except for documented fixtures.
- `reports/`: generated weekly report, strategy plan, improvement proposals, sample approval card, and sample scoreboard.
- `tests/`: unit, integration, golden-scenario, and regression-gate tests.

The alternative of splitting these concerns into services was rejected for Stage 1: it adds deployment and recovery failure modes before evaluator data justifies the complexity. The alternative of letting an LLM call Robinhood directly was rejected because it cannot provide deterministic default-deny safety.

## Agent flow and schemas

The Research Agent returns timestamped facts with source URLs and evidence kinds. Web/news/filing text is always treated as untrusted data; instruction-like text is flagged and excluded from decision instructions. The Portfolio Agent produces a typed draft proposal. A separate Critic invocation produces the strongest counterargument, which is attached before the proposal can enter risk review.

Every structured model result is validated with Pydantic. A malformed result is retried once with a correction instruction; a second failure is stored and skipped. Each decision stores model name, prompt versions, and a hash of the frozen config.

## Stage 1 broker safety

`config/settings.yaml` sets `stage: 1` and `broker: paper`. The Robinhood adapter uses an exact allowlist of non-mutating tools: names beginning with `get_`, plus explicitly listed `preview_*`, `review_*`, `run_scan`, and `search` tools. All other names are denied. This blocks known place, cancel, exercise, alert, watchlist, scanner-write, and any future money-moving tools. Unknown tools are denied by default.

The safety check runs before the host invoker. Tests use the actual Robinhood tool names such as `place_equity_order` and prove the invoker is never reached.

The paper broker uses settled cash, rejects stale quotes, fills marketable buys at ask and sells at bid, fills limits only when the displayed market reaches the limit, rejects duplicate client order IDs, and processes option expiry/assignment with defined maximum loss recorded.

## Deterministic risk contract

All v4 limits live in one config model/file. The engine checks Agentic account identity, instrument whitelist, limit order type, quote age and 0.5% price distance, 25% maximum position, five open positions, defined-risk options/no naked calls, five daily orders, no same-day round trip, 3% daily loss, 10% and 15% peak drawdown actions, duplicates, kill switch, and prompt-injection evidence. It never accepts an auto-approval input.

At 10% drawdown, new buys are blocked and an alert event is emitted. At 15%, only risk-reducing close proposals are allowed, existing positions are proposed for close, and manual unlock is required. All checks also run in shadow mode and are logged as would-have-blocked verdicts.

## Storage and operation

SQLite stores decision records, orders, fills, daily values, API costs, cards, strategy versions/changes, lessons, improvement proposals, locks, alerts, and validation failures. Application APIs only append; schema migrations never delete history.

Idempotency keys and persisted run state prevent duplicate orders after restart. The runner supports market-hours cadence, optional 24/7 shadow crypto cadence, a 30-minute stall/data-failure alert, and a launchd template. Missing starting cash prevents the daemon from starting; tests inject explicit amounts and samples are labeled mocked.

## Evaluation and controlled learning

The evaluator records point-in-time evidence, proposal details, verdicts, human decisions, fills, and horizon outcomes at the requested intervals. It computes calibration, evidence/strategy attribution, approval value-add, spread/fees/tax/API costs, and the four-line net scoreboard.

The replay harness refuses snapshots containing data later than the replay clock. Twenty-four fixed golden scenarios cover the specified adverse conditions and normal controls. Any prompt, model, or config version must pass the complete risk suite and golden suite.

Lessons and improvement proposals are append-only. Approved changes become frozen challengers. Promotion requires the predeclared metric, at least four weeks, at least 30 decisions, and net-after-cost outperformance. Promotion to live always requires a separate human YES.

## Tracing and experiment tracking

OpenAI Agents SDK tracing remains enabled, but the application installs a local trace processor/OTel path so workflow, tool, risk, and cost spans go to a localhost Phoenix endpoint. Configuration rejects non-local collector/viewer URLs. Approval cards link to the local trace. If Phoenix is not installed/running, runs continue with SQLite traces and report observability as unavailable rather than claiming it works.

MLflow uses a local SQLite tracking URI. Strategy runs log immutable parameters and scoreboard metrics. If the optional MLflow package is unavailable, the adapter reports that exact dependency blocker while preserving the application SQLite record.

## Acceptance criteria

The first deliverable includes the MCP visibility finding, Sections 1–8 status, a fresh test run, a specifically named Stage 1 real-order-block test, per-rule risk tests with blocked and allowed cases, paper-fill tests, all golden scenarios, a mocked approval card with a localhost trace link, and a mocked scoreboard with API costs. No network trade or money-moving call is made during development or testing.
