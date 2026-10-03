# Checkpoint 5 — continuation report

**Historical pre-deployment report. Superseded by [Checkpoint 5 closure](CHECKPOINT5_CLOSURE.md),
2026-10-03 17:20 ET: research-only deployment verified; CHECKPOINT 5 = CLOSED.**
The earlier results below are retained as an audit trail, not current status.

2026-10-03, 17:05 ET. Accepted base `5d4b4fe`, branch
`codex/checkpoint5-macro`. **Partial real-data validation; not a completed
deployment gate.** No Checkpoint 6 work has started.

## Control A

Release: N.

Fingerprint: `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.

Strategy changed: NO. Runner restarted: NO. Daily launchd job remains loaded,
last exit 0; no stop file at the checked primary paths. Official Lane B's
installed policy returns paused. No broker calls, official database writes,
paid model calls, configuration or preregistration changes.

Codex maintenance: `PREPARED_AND_PROVEN_NOT_INSTALLED`. Its known isolation
failure is reported below, not suppressed or fixed in this checkpoint.

## Macro infrastructure

Storage: accepted append-only foundation retained, with distinct NSA CPI and
monthly-percent-change PCE series added. No economic concepts relabeled as
index levels. Manual capture/ingest and cached replay added. Observation/event
pairs are committed atomically; a reproduced partial-write defect was fixed.

Revision handling: four PCE local republication revisions, of which two change
values and two repeat the previous value under a newer release. Original local
rows remain. Local version 0 does not certify an original economic release.

Point-in-time handling: exact publisher release/embargo headers; timezone/clock,
period, host, unit, hash and event/observation checks. No inferred publication
times. Known-at is no earlier than local raw capture. Both July PCE series show
0.2 before the later local capture and 0.1 after; no September as-of read can
see data captured in October. Real captured-data assertions passed.

Live research DB migration: **NO**. All new rows are isolated in
`/Users/tanmaysinnarkar/LocalProjects/robinhood-diagnostics/firm_lab/checkpoint5-final-validation.db`.
The existing live `firm_lab.db` was inspected read-only and remains unchanged.

Raw public captures and hashes:
`/Users/tanmaysinnarkar/LocalProjects/robinhood-diagnostics/firm_lab/checkpoint5-capture-1/manifest.json`.
No raw captures, database, private config or runtime logs enter GitHub.

## Real-data accounting

Eleven actual network requests were made once. The final code was validated by
hash-checked replay of those captured bytes into a new isolated database, with
**zero additional network requests**. The table separates network requests from
final replay outcomes. A failed HTTP document is one rejection, not an invented
count of missing economic observations.

| Family | Network requests | Parsed candidates | Accepted/stored observations | Rejected | Duplicates on fresh replay | Local revisions |
|---|---:|---:|---:|---:|---:|---:|
| Federal Reserve | 3 | 6 | 6 | 0 | 0 | 0 |
| Treasury | 1 | 570 | 0 | 570 | 0 | 0 |
| CPI | 2 | 0 | 0 | 2 documents | 0 | 0 |
| PCE | 3 | 12 | 12 | 0 | 0 | 4 |
| Labor | 2 | 0 | 0 | 2 documents | 0 | 0 |

Replaying an already populated validation database separately demonstrated
6 Fed and 12 PCE duplicates, with no new observations/events.

### Federal Reserve

Requests: 3. Events: 3 decisions, represented by 6 linked series-event records.
Observations: 6. Rejected: 0.
Latest target range: **3.75–4.00 percent**, September 16, 2026; publisher states
a 25-basis-point increase. June 17 and July 29 state unchanged 3.50–3.75 ranges.
Capability: `AVAILABLE` in isolated validation only.
Source example: [September statement](https://www.federalreserve.gov/newsevents/pressreleases/monetary20260916a.htm).
Change is taken from explicit decision wording, not inferred market direction.

### Treasury yields

Requests: 1. 2Y observations stored: 0. 10Y: 0. 3M: 0.
The official 2026 CMT CSV contains 190 dates × 3 decoded series; all 570
candidates are rejected, not backfilled. No auction yield or total-return
index substitution. Rejection:
`EXACT_PUBLICATION_UNAVAILABLE: Treasury daily CMT date is not publication time`.
Capability: `UNAVAILABLE`. The frozen Treasury-bill total-return methodology and
its stored ruler are untouched.

### CPI

Observations: 0. Revisions: 0. Rejected: 2 release documents, both `HTTP_403`.
Capability: `UNAVAILABLE`. Narrow parser fixtures cover headline/core NSA
indexes (`CUUR0000SA0`, `CUUR0000SA0L1E`, 1982–84=100), including caption and
column-date checks. **These are synthetic tests, not real BLS parser proof.**
No SA index is synthesized from the NSA series.

### PCE

Observations: 12 (six headline, six core, including prior-month republications).
Revisions: 4 local versions, two changed values. Rejected: 0.
Capability: `AVAILABLE` in isolated validation **for monthly percent changes**;
price-index levels and GDP are not provided by this parser.
Three official releases cover June/July/August plus the preceding month shown
in each release. August headline/core: 0.3% / 0.2% month-over-month.
The selected table establishes monthly units; its link to
[BEA statistical conventions](https://www.bea.gov/news/pio-release-additional-information)
records the supported seasonal basis. No unrelated paragraph can establish the
table's measure. The [August release](https://www.bea.gov/news/2026/personal-income-and-outlays-august-2026)
also explains its annual-update revision context.

### Labor

Unemployment observations: 0. Payroll observations: 0. Revisions: 0.
Rejected: 2 documents, `HTTP_403`. Capability: `UNAVAILABLE`.
Synthetic parser fixtures cover LNS14000000 unemployment and the publisher's
monthly change in CES0000000001, converted explicitly from persons to thousands.
No payroll level is claimed. **Real source validation remains missing.**

### Macro events

FOMC: 6 series records for 3 decisions. PCE: 12 series/vintage records from
3 releases. CPI: 0. Employment: 0. Scheduled future events: 0.
Capability: `PARTIAL_EXISTING`, isolated validation only. Calendar completeness
is not claimed; no missing scheduled time is guessed. Consensus: `UNAVAILABLE`.

## Market-data provider comparison

Full official-source comparison, license constraints and capability matrix:
[market-data decision](CHECKPOINT5_MARKET_DATA_DECISION.md).

Massive: advertised Stocks Advanced $199/month; longer history and tick/NBBO
coverage, but required non-display/storage rights not established.
Alpaca SIP: advertised Algo Trader Plus $99/month; history since 2016, so no
2008 coverage; retention/redistribution entitlement still requires confirmation.
Databento: relevant only to a later depth-specific hypothesis; not selected.

`RECOMMENDED_PROVIDER = NONE`

Verified prices are advertised tiers, not quotes including any additional
licenses. Technically the feeds can unlock intraday bars, VWAP, opening range,
RVOL and quote-based signed-volume proxies. None is activated. Later operator
action: obtain written non-display/local storage/retention terms, then approve
a specific entitlement and purchase. No account or subscription was created.

## Order-flow decision

`TICK_TRADES_QUOTES_SUFFICIENT_FOR_FIRST_FIRM_TRIAL = YES`

`LEVEL_2_REQUIRED_FOR_FIRST_FIRM_TRIAL = NO`

The envisioned first research inputs do not require queue position or depth
imbalance. Signing is an uncertain trade/quote-derived proxy, not observed
aggressor intent. Depth adds book-level information only for a later explicit
hypothesis. No trading trial is registered by this decision.

## Macro UI

Deployed: **NO**. Built on branch and tested with an isolated static preview;
that temporary process/tab were stopped. Existing 8765/8766 services untouched.
Rows displayed in preview: 4 latest factual values, 6 explicitly unavailable
cards, 18 expandable event-series/vintage records. Provenance disclosure was
opened and checked in the browser. Permanent factual-only warning: YES.
Trading interpretation: **NO**. Model state: `macro_regime = NOT_STARTED`.
UI uses existing Firm Lab styling; this is not a dashboard redesign.

## Capabilities

The current live research database retains its prior state. Macro availability
below applies only to the explicitly named isolated validation database.

| Capability | Live research state | Checkpoint 5 validation state |
|---|---|---|
| daily_closes | AVAILABLE | not imported into validation DB |
| sec_filings | AVAILABLE | not imported |
| fundamentals | PARTIAL_EXISTING | not imported |
| earnings_events | AVAILABLE | not imported |
| vti_total_return | AVAILABLE | unchanged |
| treasury_total_return | AVAILABLE | unchanged |
| total_return_ruler | AVAILABLE | unchanged |
| fed_policy_data | UNAVAILABLE / not installed | AVAILABLE |
| treasury_yields | UNAVAILABLE / not installed | UNAVAILABLE |
| cpi | UNAVAILABLE / not installed | UNAVAILABLE |
| pce | UNAVAILABLE / not installed | AVAILABLE, monthly changes only |
| labor_data | UNAVAILABLE / not installed | UNAVAILABLE |
| macro_event_calendar | UNAVAILABLE / not installed | PARTIAL_EXISTING |
| market_volatility | UNAVAILABLE / not installed | UNAVAILABLE |
| macro_regime | NOT_STARTED | NOT_STARTED |
| intraday | UNAVAILABLE (`intraday_bars`) | unchanged |
| trades | UNAVAILABLE (`tick_trades_quotes`) | unchanged |
| order_flow | UNAVAILABLE (`trade_flow`) | unchanged |
| order_book | UNAVAILABLE | unchanged |
| sector_engine | NOT_STARTED | unchanged |
| technical_engine | NOT_STARTED / not installed | NOT_STARTED |
| options_strategy | NOT_STARTED | unchanged |
| ml_ranker | NOT_STARTED | unchanged |

## Tests

Working directory: `/Users/tanmaysinnarkar/.codex/worktrees/robinhood-live-rehearsal`.
Interpreter for every command below:
`/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python`.

- Focused: `-m pytest -q tests/test_macro_parsers.py tests/test_macro_ingest.py tests/test_macro_view.py tests/test_firm_lab_macro.py`
  — **69 passed**.
- Firm Lab: `-m pytest -q tests/test_firm_lab*.py tests/test_macro*.py --tb=short`
  — **250 passed**.
- Full native development suite: `-m pytest -q --tb=short`
  — **968 passed, 1 failed**, 27 warnings, 53.70 seconds.
- Cloud: **NOT RUN**. This session has a Mac executor; the repository has no
  cloud CI workflow. Native evidence is not relabeled as cloud evidence.
- Native installed-release suite: **NOT RUN**, because no release was deployed.
- Known failure: `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`,
  unchanged guard rejects installed Codex `configWarning`.

Independent review found five issues; all reproduced with failing tests and
fixed: selected-table PCE units; CPI date-column identity; unrelated-family
capability promotion; malformed clock normalization; malformed Treasury numeric
receipt handling. The latter two were regraded as important because the user
requires exact timestamps and rejection receipts. No review fix weakens the
installed Codex isolation test. No deferred reviewer minor findings.

## Remaining gate evidence and rulings

- Ruling: preserve unavailable BLS/Treasury instead of substituting date-only
  API data. Cost: incomplete coverage until authoritative release evidence is
  reachable; no amount of mock tests can replace it.
- Ruling: no live migration/UI deployment in this turn while source validation
  and the requested cloud test are incomplete. Cost: new macro UI is branch-only.
- Ruling: provider NONE pending explicit licensed-use/retention confirmation.
  Cost: intraday activation remains deferred; no paid feed is purchased blindly.
- Review did not independently re-browse vendor terms; the implementer verified
  linked official sources. No commercial rights or eligibility are assumed.

To close Checkpoint 5: validate actual BLS release bytes with explicit timing and
identity; establish admissible Treasury publication evidence or explicitly
accept its unavailable scope; obtain a cloud test result; then migrate only
validated facts and the read-only UI with a dashboard-only restart if needed.
Do not restart daily, install maintenance or start Checkpoint 6 as a shortcut.

## Technical roadmap

Fibonacci explicitly retained: YES. Deterministic Fibonacci anchors: YES.
Candlestick geometry retained: YES. Support/resistance retained: YES.
Breakouts retained: YES. Volume confirmation retained: YES. Sector features
retained: YES. Macro feature work deferred to Checkpoint 6/7: YES.
Moving averages, momentum, RSI, MACD, ATR, Fibonacci retracements/extensions and
distance/confluence, later VWAP/RVOL/opening range remain future work in
`ARCHITECTURE.md`. No `61.8% => BUY` rule or other strategy is implemented.

## Experiment state

`Firm Lab fills: 0`

`Firm trading trial: NOT REGISTERED`

`October research stop superseded: NO`

`Control A: UNCHANGED`

`Official Lane B: PAUSED`

`Real execution: DISABLED`
