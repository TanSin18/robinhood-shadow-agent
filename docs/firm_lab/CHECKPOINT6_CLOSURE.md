# Checkpoint 6 — research feature deployment

## Checkpoint

Status: **CHECKPOINT 6 = CLOSED**. Task12 only, 2026-10-03, 19:50 ET.
Accepted calculation source: `34531dfbfe9567ee65a749af416c73a5eb42f104`.
Reviewed read-only UI correction: `d15d8044d3ac509a1578569ed727593ad0fe6e38`;
one-property mobile table fix is included with this closure commit.
Branch: `codex/checkpoint6-features`. No Checkpoint7 work.

Cloud suite: NOT RUN — executor unavailable

Checkpoint 6 cloud-test exception: APPROVED BY OPERATOR

## Control A

Release: N.
Fingerprint: `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
Strategy changed: NO. Runner restarted: NO.
Installed configuration: Stage1, paper broker. Official LaneB paused; no stop file.
Final post-deployment verification: PASS at19:50ET. Daily service remains loaded,
idle between scheduled invocations, last exit0. Its plist SHA-256 is unchanged:
`b4ccc9aa1696c38ad4e77295bdb234a03244d5aaf13a47599ef6f9531e61d318`.
Codex maintenance: `PREPARED_AND_PROVEN_NOT_INSTALLED`.

## Deployment

Research DB: isolated `robinhood-diagnostics/firm_lab/firm_lab.db`.
Additive migration/manual generation complete; five new tables, no replacement
database. All26old tables were unchanged by generation. Subsequent deliberate
capability metadata updates changed only data_capabilities and appended capability
audit events; all24other table-content hashes and every old event are preserved.
Feature explorer: ten read-only projection/UI files installed in the separate
`agent-desk.3K4Fam` overlay. Generator remains manual in development worktree;
not installed into the dashboard or trading runtime. No scheduled generation.
Dashboard restart and live UI checks: PASS. Only `com.openai.robinhood-inbox`
restarted once (PID39591→58179). Trading runner restarted: NO.

Pre-deployment database SHA-256:
`b06cca62dcd3775c30cc08197408c1f2db99b1a9cef01d9aa0ee0aae8cf44164`.
Verified timestamped SQLite backup SHA-256:
`a25d2755ef6029c928116309f80092fc514f1332ea967ed3a3c9aca76c011c49`.
Backup timestamp: 2026-10-03T23:32:44Z. SQLite backup changes file layout; all
26 old table-content hashes match. Full UI backup, file manifest, generation
receipts and verification results stay local in
`robinhood-diagnostics/checkpoint6-deployment-20261003/`.
Written rollback: [deployment runbook](CHECKPOINT6_DEPLOYMENT.md).

## Feature infrastructure

Definitions:222. Calculation hash:
`45b4c2ab719f13dd17cb735118792adc9bc3f8f872466ccba0c2cba3196e3926`.
Live results:153,180; available:85,204; unavailable:67,976; initial duplicates:0.
All result content hashes/provenance hydrate and validate.9,270distinct source/
content versions.690distinct snapshots,691exact completed manifests including
the idempotence probe; no unfinished run. Every manifest owns exactly222results.
Identical VTI rerun:0insertions,222duplicates. Strict September30historical dry
run:0available,222unavailable. Historical UI cutoff:0eligible stored rows.
Generation took695.87seconds,0network/model/APIcalls. Live DB final SHA-256:
`8611da11beda1d97012c9ea773a3c86777805ce28a526e4785148365eaa27b14`.
Scope:23existing instruments ×30sessions, 2026-08-19 through2026-09-30.
Knowledge cutoff:2026-10-03T22:00:00Z.
Mode:`RETROSPECTIVE_NOT_HISTORICAL_AVAILABILITY`.
Later local capture does not establish September historical knowledge.
Source values, unavailable nulls and old research/benchmark rows are not rewritten.

| Family | Available | Unavailable |
|---|---:|---:|
| Trend | 11,730 | 0 |
| Momentum | 10,350 | 0 |
| Volatility | 2,070 | 2,070 |
| Support/resistance | 8,735 | 235 |
| Close breakouts | 14,906 | 1,654 |
| Close-based Fibonacci | 26,220 | 4,830 |
| Candlestick geometry | 0 | 8,280 |
| Volume | 0 | 6,900 |
| Sector | 4,140 | 11,730 |
| Fundamentals | 2,250 | 8,790 |
| Earnings/SEC | 640 | 7,640 |
| Macro context | 4,163 | 6,877 |
| Intraday registry | 0 | 8,970 |

Known-at range:2026-10-01T14:02:11.471152+00:00 through
2026-10-03T20:12:15.912346+00:00. None is backdated into September knowledge.

## Technical

Trend: close-based SMA20/50/100/200, distances, slopes and ordering.
Momentum: returns5/10/20/63/126/252 and20-session acceleration.
RSI:14-session Wilder. MACD:12/26EMA,9EMA smoothing and histogram.
Realized volatility:20/63-session sample log-return SD ×sqrt252.
Close support/resistance and break/retest use confirmed pivots/prior levels.
ATR: implemented/tested, live unavailable without validated OHLCV.
Candles: geometry implemented/tested, live unavailable; no named-candle signal.
Volume: implemented/tested, live unavailable. No synthetic OHLCV or volume.

## Fibonacci

Implementation: explicitly **close-based Fibonacci**, not market-high/low.
Pivot algorithm:`close_fractal_3x3_v1`; strict3left/3right, ties not pivots.
Confirmation delay:3completed sessions plus source known-at restrictions.
Retracements:.236/.382/.5/.618/.786. Extensions:1.272/1.618.
Confluence: bounded0.5% clusters from latest3confirmed close legs; participants
retained, descriptive overlap/density only. No composite strategy score.
UI nearest retracement sorts all five recorded distance operands; missing pairs
make it unavailable. Separate recorded nearest extension is preserved.
OHLC-based version: not implemented; must be a separate feature/version family.
Capability:PARTIAL_EXISTING; ATR-distance outputs unavailable.

## Sector

Mapping: six current internal issuer classifications, explicitly not historical
GICS. Effective October3; cannot be used as September constituent history.
Relative descriptors: VTI-relative returns; mapped ETF comparisons require a
valid mapping at the described session and knowledge cutoff.
Breadth: unavailable without complete point-in-time constituents.
Limitations: no historical mappings, no full sector universe; fixed XLK/XLY/XLC
leadership comparison is labeled a subset and subject to temporal eligibility.
Capability:PARTIAL_EXISTING.

## Fundamentals

Implemented: compatible confirmed SEC facts, margins, growth and ratios.
Coverage: available operands only; see measured family counts after generation.
Limitations: same economic end/duration/concept/unit/entity required; no YTD-to-
quarter synthesis, no missing-debt imputation, some grouped missing reasons.
Capability:PARTIAL_EXISTING.

## Earnings / SEC

Implemented: factual event/filing ages and metadata with acceptance/known-at.
Coverage: only stored authoritative event fields.
Limitations: no transcript interpretation, surprise estimate or AI event signal.
Capability:PARTIAL_EXISTING.

## Macro

Fed: factual target/rate-change/age descriptors where validated.
PCE: validated headline/core monthly-change descriptors, not invented YoY/index.
FOMC aggregate limitation: authoritative complete three-meeting coverage is not
established. Affected features stay unavailable; no inferred completeness.
CPI:unavailable. Labor:unavailable. Treasury yields:unavailable.
Capability:PARTIAL_EXISTING. Macro regime:NOT_STARTED; no classifier/sizing link.

## Intraday

VWAP:unavailable. RVOL:unavailable. Opening range:unavailable. Trade flow:unavailable.
Capability:UNAVAILABLE. Definitions only; no feed/account/purchase activation.

## UI

Explorer:read-only instrument/session/cutoff selection of exact finished manifests.
Fibonacci audit: close anchors/prices/dates/confirmation/direction/current close,
stored levels, nearest retracement/extension and confluence participants.
Retrospective disclosure: permanent when later-cutoff description selected.
Research-only warning:`RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL`.
Trade recommendations present:NO. Source refs, versions, missing reasons and
calculation audit remain expandable. No full dashboard redesign/history removal.
Desktop1440×1000and narrow390×844 verified in the actual deployed browser.
Warnings visible; native expandable audit shows dates/prices/confirmation/source
version; unavailable OHLCV explicitly named. No BUY/SELL wording in explorer.
Expanded mobile table had11px overflow; one-property fixed table layout repaired
it, observed RED→GREEN:panel324px/scroll335px→panel324px/scroll324px. On mobile
the accessible exact-value table replaces the SVG. No second service restart.
Both filtered live GETs return200. Research DB SHA-256 unchanged after HTTP and
browser access. Installed projection imports no calculator/generator module;
only stored-result readers were deployed. Unit tests also forbid generation on GET.
Rendered VTI page is9,173,660bytes because provenance is fully included behind
disclosures; no performance optimization/redesign was attempted in this checkpoint.

## Review

Accepted whole-branch review:7Important findings repaired in source34531df.
See [review record](CHECKPOINT6_REVIEW.md); not repeated during deployment.
Task12 UI discrepancy: overall-nearest could be an extension, not the separately
required retracement. Narrow display-only correction; no feature recalculation.
Fresh delta reviewer identified paired-null omission; fixed fail-closed, regression
reproduced then passed. No additional core changes.
Deferred limitations: complete FOMC coverage and grouped nontechnical missing
reasons, explicitly operator-accepted. Additional UI boundary-test permutations
are a minor coverage limitation; representative invalid/signed inputs were probed.

## Tests

Commands use the primary `.venv/bin/python`, from the isolated development branch:

```sh
python -m pytest tests/test_research_feature_*.py -q
python -m pytest tests/test_firm_lab*.py tests/test_macro*.py tests/test_research_feature_*.py -q
python -m pytest -q
```

After overlay file installation:100focused passed;350FirmLab passed;
full native:1068passed,1failed,27warnings,53.15seconds. After the final CSS fix,
the full native suite was rerun:1068passed,1failed,27warnings,54.16seconds.
Known failure:
`tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`.
Installed Codex emits `configWarning`; unchanged guard rejects it. No whitelist,
weakening or maintenance installation. Full suite is not wholly green.
Native is development-suite evidence, not cloud or an official trading cycle.
Deployed read-only smoke tests:PASS, two filtered HTTP200pages; zero DB mutations;
strict historical page has no eligible results. Desktop/mobile disclosures pass.

Cloud suite: NOT RUN — executor unavailable

Checkpoint 6 cloud-test exception: APPROVED BY OPERATOR

## Capabilities

Live metadata verified, matching measured coverage:

| Capability | State |
|---|---|
| technical_engine | PARTIAL_EXISTING |
| fibonacci_features | PARTIAL_EXISTING |
| sector_engine | PARTIAL_EXISTING |
| fundamental_features | PARTIAL_EXISTING |
| earnings_features | PARTIAL_EXISTING |
| macro_features | PARTIAL_EXISTING |
| intraday_features | UNAVAILABLE |
| macro_regime | NOT_STARTED |
| options_strategy | NOT_STARTED |
| ml_ranker | NOT_STARTED |

## Experiment state

BUILD_OBSERVE; registry empty; exactly31approved research tables. No order,
fill, position, account or cash table. No new strategy, experiment, model, order
path, schedule, provider activation or trading-runtime change.

Firm Lab fills: 0

Firm trading trial: NOT REGISTERED

October research stop superseded: NO

Control A: UNCHANGED

Official Lane B: PAUSED

Real execution: DISABLED

CHECKPOINT 6 = CLOSED

Stop here. Checkpoint7 is not started.
