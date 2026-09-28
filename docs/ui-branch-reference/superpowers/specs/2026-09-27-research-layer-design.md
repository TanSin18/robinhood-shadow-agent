# Research layer with reasoned, human-approved exceptions

Date: 2026-09-27
Status: Conversational design approved with an exception workflow; written-spec review pending. No implementation or activation claim.

## Purpose and scope

Add a reproducible research layer to the existing local Stage 1 trader. Historical, deterministic strategies must earn admission to paper shadow evaluation. AI event signals are evaluated prospectively, never used to manufacture historical performance. Every component and safety boundary requires tests.

User requirements: read-only Robinhood live data; 10–20 years of Stooq/Yahoo daily history where available; SEC full-text filings; FRED macro; timestamped local caches; no lookahead; deterministic momentum/rotation, mean reversion, and volatility sizing; walk-forward backtests with spreads, estimated taxes and settlement; VTI benchmarking; 10,000-run Monte Carlo; structured, sourced forward-only earnings and veto signals; evidence-based promotion.

The user additionally approved overridable shadow confirmation with reasoning and prompted suggestions. Interpretation: exceptions apply to the proposed minimum six months and 30 completed trades. They do not waive the original historical outperformance / 60% Monte Carlo requirements, positive forward confirmation, data-integrity requirements, or trading safety controls. This narrow interpretation is explicit for written review, not an implicit unlimited override.

The historical strategy library initially serves Lane A (stocks/ETFs). The existing options paper lane remains unchanged; stock daily bars do not establish an options backtest. The research layer cannot enable real broker capabilities or change the installed schedules without the later implementation's explicitly reviewed integration steps.

## Architecture

Use a deterministic, chronological account ledger as the backtest authority, with faster array-based Monte Carlo calculations only after ledger validation. An external backtesting framework would reduce initial simulation code but introduce another accounting model to reconcile; this design favors shared explicit rules with the existing paper system. Research remains isolated from the running production database until integration tests pass.

Components: source adapters → immutable cache → as-of data views → deterministic strategy library → walk-forward ledger → metrics and Monte Carlo → qualification registry → paper strategy selector. Forward event JSON feeds a separate buy-veto and bounded-sizing overlay after historical selection. A promotion-recommendation inbox consumes evidence; it cannot write orders or override the risk engine.

Reuse existing SQLite, Pydantic, prompt versioning, read-only Codex transport, risk checks, experiment tracking and approval-inbox security. New typed interfaces must distinguish historical evidence, forward signals, qualification decisions, exception requests and trade approvals. Do not overload a trade's YES button to mean promotion approval.

## 1. Sources, cache and no-lookahead boundary

- Robinhood: use the existing exact MCP read allowlist and record sanitized source events; never expose orders, cancellation, exercise, transfer or other write tools. Raw account credentials must not enter caches or model prompts.
- Stooq/Yahoo: source-specific daily-price adapters plus authorized local-file import. Request up to 20 years and report actual coverage, inception, gaps and adjustment conventions. Never silently splice providers or invent pre-inception history. Do not bypass access restrictions or purchase a subscription.
- SEC: submissions/index metadata identifies filings; retrieve the primary document and relevant exhibits as full text. Store accession, CIK, form, acceptance timestamp, source URL, document hash and extraction version. Respect identifying-header and rate-limit requirements. Public earnings transcripts may be supplied from an authorized source; a missing transcript is unavailable, not synthesized from a filing.
- FRED: use vintage/as-of observations for historical macro features, not today's revised series. A standard FRED API key and an identifying SEC contact configuration may be needed. Missing configuration disables the affected live fetch with a precise status; fixtures still test parsing and timing. Never request brokerage passwords or verification codes.

Each cache record has provider, instrument/series/document ID, event time, known-available time, retrieval time, vintage where applicable, raw-response hash, parser version, and quality flags. Store immutable raw blobs separately from normalized SQLite indexes; refreshed observations append versions rather than overwrite history. Retrieval today does not mean a filing or macro revision was known years ago.

As-of views admit only information available by the decision clock. Unknown intraday release times use a conservative next-session eligibility rule. Daily-close signals cannot fill at that same close; earliest simulated execution is the next eligible session. Macro revisions and filing amendments become usable only at their own availability times. Recomputed adjusted historical prices are not treated as original point-in-time snapshots.

Handle splits and distributions explicitly, avoiding simultaneous use of dividend-adjusted returns and a second dividend cash credit. Report reconstructed-history and fixed-universe/survivorship limitations. Missing corporate-action information needed for correct accounting, invalid timestamps, future data or benchmark gaps make the affected run ineligible for promotion, even if an exploratory report can still be produced.

Tests: deterministic cache replay and hashes; timezone normalization; amendments/revisions invisible before availability; gaps/inception; split/dividend accounting; malformed-provider responses; provider failures; no unexpected network use in offline tests; future-row perturbation cannot change earlier decisions.

## 2. Deterministic strategies

All strategies are versioned pure Python functions over as-of views. They return target exposures and machine-readable explanations, not broker calls. The approved symbol whitelist remains authoritative; VTI is a candidate and benchmark, not a required allocation.

- ETF rotation: rank positive trailing momentum among eligible ETFs; require the configured trend filter, select the top configured count, rebalance on a declared schedule and retain cash when no asset qualifies. Lookbacks, selection count and rebalance rules belong to the frozen parameter set.
- Mean reversion: a completed one-day drop at least as large as the declared threshold while price remains above its 200-session moving average; deterministic exit by recovery or maximum holding time. Require full warm-up data, one active entry per instrument, no shorting and no same-day lookahead fill.
- Sizing: base target notional × target annualized volatility / annualized 20-session realized volatility, capped by the existing position limit, settled cash and other risk limits. Require 21 valid completed closes. Zero, missing or invalid volatility blocks new exposure, but does not prevent a verified risk-reducing close.

Start with small predeclared parameter grids, not open-ended AI parameter generation. Log every attempted grid and strategy version so selecting a winner cannot erase failed trials.

Initial grids: momentum lookback 63/126/252 sessions, top 1/2/3 assets, 200-session trend filter and monthly rebalance; mean-reversion drop threshold 3%/5%/7%, maximum hold 5/10/20 sessions, exit on recovery to the pre-drop close or the maximum hold, whichever is observed first. Exit observations execute no earlier than the following eligible session. Select parameters by training-window after-cost CAGR, breaking ties by lower turnover then stable parameter order. These declared defaults are frozen before examining test results, not selected because a backtest looks favorable. Backtests enforce the same configured position, cash and order constraints that the resulting strategy will face in shadow mode.

Tests: ranking ties, negative-trend cash allocation, MA warm-up, exact drop threshold, exits, rebalancing, caps, missing/zero volatility, input immutability and deterministic output.

## 3. Walk-forward simulation and metrics

Default research configuration: $500 starting cash, rolling five-year training windows followed by one-year non-overlapping test windows, advancing one year. Report insufficient history explicitly; never shorten windows silently. Fit/select only on each training window; freeze parameters before its test period. Stitch out-of-sample results chronologically without resetting capital, tax lots or settlement at fold boundaries. Reserve the last complete test window from discretionary strategy selection and label it the final holdout; repeated peeking taints its qualification status.

The ledger models next-session execution, configurable bid/ask spread and slippage estimates, FIFO lots, dividends, corporate actions, fees, estimated taxes and date-appropriate settlement rules. Daily bars do not contain actual historical bid/ask spreads: all modeled costs and sensitivity assumptions must be labeled. Sales cannot fund a buy before settlement; no borrowing, negative cash, unsupported shorts or unheld sells. Missing prices mean no fill, not a fabricated mark.

Reuse the existing configurable estimated short/long-term tax assumptions as modeling inputs, not personal tax advice. Report that wash-sale rules, loss offsets and actual tax circumstances are not fully modeled. Use the same accounting assumptions for VTI; present common-horizon liquidation-equivalent after-tax values so an active seller is not compared with an untaxed unrealized benchmark gain. Deduct AI costs only from AI-using strategies, never from VTI/cash. Historical deterministic experiments with no inference have no fictional AI charge.

Output gross and after-cost CAGR; maximum drawdown; annualized Sharpe with a declared, as-of-compatible risk-free assumption; one-way turnover (one-half absolute traded notional divided by portfolio value); profitable closed-trade fraction; and the fraction of test windows beating VTI. Distinguish trade win rate from benchmark win rate. Undefined quantities such as Sharpe on a constant series or win rate with no closed trades remain unavailable.

Tests: hand-calculated balances and metrics, compounding, tax lot holding periods, settlement weekends/holidays/regime boundaries, benchmark costs/dividends, empty periods, no resets across folds, training-only parameter selection, holdout contamination, future-data mutation and deterministic seed/config replay.

## 4. Monte Carlo and plain-English risk report

Run 10,000 paired block-bootstrap paths from validated out-of-sample strategy and VTI daily returns, with 252 trading sessions per path. Resample identical date blocks for strategy and benchmark to preserve their contemporaneous dependence. Default block length is 20 sessions, with declared sensitivity checks at 5 and 60; persist seed, input hashes and configuration. Use already cost-adjusted return streams consistently and do not charge the same costs twice. Disclose that resampling net returns is an empirical approximation, not a new tax-lot simulation or a forecast guarantee.

Separately run 10,000 trade-reshuffling stress paths where the trade ledger permits it. Reorder whole completed trade episodes rather than individual fills; overlapping trades must be grouped or marked unsupported. Re-execute through the capital/settlement ledger; never assume every shuffled trade remains affordable. Report these as sequencing stress tests, not an independently validated source of market probabilities. Do not average incomparable bootstrap and reshuffling probabilities into one promotion number.

Report P(strategy terminal equity exceeds VTI after costs), median and fifth-percentile signed maximum drawdown (negative; fifth percentile is the worse tail), and P(terminal equity below $400 from $500). Also distinguish the probability of ever crossing below $400 during the year. Include Monte Carlo sampling uncertainty and the sensitivity range; 10,000 runs do not remove model or data uncertainty. The qualifying 60% probability is the predeclared primary paired-bootstrap estimate, not whichever sensitivity result looks best.

Tests: 10,000-run count, deterministic seeds, paired-date preservation, block boundaries, identical strategy/benchmark equality, certain-loss/certain-outperformance fixtures, loss thresholds, signed drawdown quantiles, no double costs, no affordable-capital violations during reshuffling and invalid/insufficient samples failing closed.

## 5. Forward-only AI event signals

Maintain a separate append-only forward-signal store. Every JSON signal includes strategy/signal/prompt/model versions, ticker, event ID, source URLs, source hashes and cited text locations, source availability times, generation time, confidence/uncertainty, missing evidence and validity state.

Earnings scoring separates guidance direction, tone change against the previous quarter, and surprises. A surprise needs a cited pre-release expectation; otherwise that field is unavailable. Score only after the new source is available, retain the actual source snapshots, and never create backdated historical AI signals. Tests and demonstrations use explicitly labeled fixtures, not performance evidence.

A deterministic mapping converts the score to a bounded size multiplier (default 0.75–1.25). It can modify an already eligible deterministic proposal's size only. Apply all cash, volatility and position caps after this multiplier; it cannot create an independent buy, waive a veto or add a symbol.

The filing red-flag output is separate: veto status, enumerated concerns, materiality, citations, uncertainty and review state. A valid active veto blocks new buys, never verified risk-reducing sells. An unavailable required assessment is not interpreted as a clean filing. An active veto cannot disappear merely because a cache timer elapsed; clearing it requires a newer sourced assessment or explicit recorded review under the veto policy, not a promotion exception.

Use the existing Agents SDK architecture and shared $0.40 estimated daily inference budget. Event analysis belongs to the daily cycle; intraday maintenance remains code-only. If budget or sources are unavailable, do not invent a signal. Non-AI strategy results and AI-overlay forward results remain distinguishable.

Tests: strict JSON parsing, citation/source identity, future or missing sources, previous-quarter matching, unavailable consensus, injected instructions treated as data, historical-mode rejection, no backdating, bounded sizing and post-tilt caps, veto precedence, valid closing sells, shared budget and honest unavailable outcomes.

## 6. Promotion and prompted exceptions

### Mandatory qualification

For a frozen deterministic strategy version to enter the new research-qualified shadow lane: valid untainted out-of-sample evidence must beat VTI after declared costs, and the primary 10,000-path Monte Carlo P(beat VTI) must be at least 60%. Missing, stale, mismatched or incomplete evidence fails closed. Mock data cannot qualify a strategy. New research strategies cannot bypass this gate through the existing discretionary proposal path; existing legacy paper observations remain explicitly labeled and cannot be counted as qualified research evidence.

Default live-review eligibility additionally requires six calendar months of prospective shadow observation, 30 completed position round trips (partial exits and repeated decisions cannot inflate the count), positive after-cost performance against same-period VTI, and no unresolved safety/data-integrity violations. These are minimum observation criteria, not proof of profitability. Strategy or meaningful parameter changes create a new version and restart its forward qualification evidence.

Actual real-money activation is a separate explicit operator decision and separately authorized implementation step. This scope produces only eligibility/recommendation states; Stage 1 broker write capabilities remain blocked.

### Recommendation card

Expose a distinct “Review promotion readiness” / “Suggest an exception” action in the local inbox. A deterministic eligibility assessment supplies the facts; optional AI explanatory text may summarize them within the shared budget but cannot alter them. A suggested action can be WAIT, CONTINUE SHADOW, or REQUEST LIMITED EXCEPTION. No suggestion is a self-approval.

The card must show strategy/version, standard thresholds and current values, precisely which waiting-period/trade-count rules would be waived, evidence supporting the exception, evidence against it, sample size, uncertainty, cost assumptions, remaining mandatory rules, and a recommended next step. The user receives an editable proposed rationale, not a silently submitted preselected approval. Insufficient evidence must support WAIT, not invented justification for promotion.

### Human override record

Overrideable fields are only `shadow_min_calendar_months` and `shadow_min_completed_trades`. A request identifies the desired limited exception for one strategy version and one evidence snapshot. Approval requires an explicit operator YES and a nonempty substantive reason, which the operator can edit or replace; NO, no response, malformed input or expiry creates no exception. Use the existing configurable 30-minute approval expiry for the request.

Store request ID, strategy/version, original and proposed thresholds, evidence hashes, suggested action and rationale, uncertainty, operator reason, decision timestamp, expiry and consumed/revoked state in an append-only audit log. The exception is single-use for that eligibility review, not a global configuration change or standing broker permission. Changed evidence or strategy version invalidates it. Recheck all mandatory gates and the kill switch transactionally before consuming it. A later safety failure revokes eligibility.

An approved exception produces `READY_FOR_LIVE_REVIEW_WITH_EXCEPTION`, not `LIVE`, and does not place an order. Historical VTI outperformance, the 60% Monte Carlo minimum, actual forward outperformance, no-lookahead, source integrity, active filing vetoes, risk/cash/position limits, kill switch, explicit real-money approval and the Stage 1 write block are not overrideable here.

Tests: suggestion-only no state change; blank/whitespace reasoning rejected; YES/NO/expiry; restart persistence; replay and concurrent resolution; evidence/version mismatch; allowlisted exception fields; attempts to override 60%/cash/veto/broker restrictions; post-approval revalidation; audit completeness; no raw credentials; and no real broker call from any recommendation, approval or exception action.

## Reporting and delivery

Provide a local research command/report with source coverage, cache snapshots, strategy/config versions, walk-forward fold tables, VTI comparison, requested metrics, 10,000-path summaries, cost assumptions, caveats and qualification verdicts. Never label a simulation as a live return or an estimated bootstrap probability as a measured future chance. Store reproducible manifests and experiment metrics locally.

Deliver tests for each of the six pieces, an adversarial no-lookahead suite, historical-mode rejection of AI signals, an exception-card example, and preserved Stage 1 real-order-block regression evidence. Keep live-source smoke tests distinct from offline fixtures and report exact access blockers without making up data. Existing services, accounts and histories are preserved during development. No plan or test result is represented as implemented functionality.

## Reference checks

The design's source-access assumptions were checked against official sources on 2026-09-27:

- SEC public submissions/XBRL API and access to filing documents: https://www.sec.gov/search-filings/edgar-application-programming-interfaces and https://www.sec.gov/about/developer-resources . Full-text document retrieval is distinct from XBRL facts.
- FRED vintage/as-of periods: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html and https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html .
- Stooq historical-data entry point: https://stooq.com/db/h/ . Actual machine access/coverage still needs a source smoke test; page discovery alone is not proof.
- Yahoo historical-data access varies by entitlement and instrument. Authorized import remains a supported fallback; the design does not assume a freely supported download API or permission to bypass controls.

## Review outcome

Self-review: source timing is separate from retrieval timing; AI forward testing is separate from historical qualification; costs are never assigned to passive benchmarks as AI charges; exceptions affect observation minimums only; no automatic live execution is introduced. The written spec must be reviewed before writing the implementation plan, per the brainstorming workflow.
