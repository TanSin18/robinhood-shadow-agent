# Checkpoint 6 validation — isolated branch, not deployed

Status: **NATIVE VALIDATION FINISHED; STOPPED BEFORE DEPLOYMENT; CHECKPOINT 6 NOT CLOSED**.
Operator decision, 2026-10-03: stop before deployment. No cloud-test exception.
Source branch: `codex/checkpoint6-features`. Initial review head: `810be5c`.
Repaired source: `34531dfbfe9567ee65a749af416c73a5eb42f104` (pushed and verified).
The accepted Checkpoint 5 implementation is preserved.

## Scope and evidence boundaries

Tasks 1–10 implement an isolated feature library, append-only derived storage,
manual dry-run-default generation and a stored-result explorer. This is not a
strategy, ranker, macro regime model or trading trial. Close structure names and
`close_fractal_3x3_v1` are explicit; later OHLC structure must have its own version.

Task 11 validates only a copy of the research database. No official account
database is copied into research or written. No live research migration, live
feature generation, dashboard installation or service restart has occurred.
Task 12 remains withheld by the operator; Checkpoint 7 has not begun.

## Native tests

Interpreter: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python`.
Commands run from the development worktree:

```sh
python -m pytest tests/test_research_feature_*.py -q
python -m pytest --collect-only -q tests/test_firm_lab*.py tests/test_macro*.py tests/test_research_feature_*.py
python -m pytest tests/test_firm_lab*.py tests/test_macro*.py tests/test_research_feature_*.py -q
python -m pytest -q
```

- Before review:86focused,336FirmLab,1,054native passes plus one known failure.
- After review repairs: **98 focused passed** (1.64seconds).
- Firm Lab: **348 passed** (6.51seconds).
- Full native: **1,066 passed, 1 failed, 27 warnings** (54.15seconds).
- Known failure: `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`.
  Installed Codex emits `configWarning`, rejected by the existing isolation
  guard. The baseline already failed this test; it has not been weakened.
- Cloud: NOT RUN; no cloud executor. Native evidence is not cloud evidence.
- Codex maintenance: `PREPARED_AND_PROVEN_NOT_INSTALLED`, separate from this work.

## Controlled sample

Initial sample: VTI, SPY, AAPL, MSFT, NVDA, AMZN, GOOGL, SOXX; latest 30 stored
exchange sessions each. Each request is first a dry run, then an explicit write
to the isolated copy. Cutoff: 2026-10-03T22:00:00Z. All results are retrospective,
not proof that the system knew these facts on their economic observation dates.
Only after independent-review repairs and full native verification did the
repaired initial sample run, followed by the remaining15 existing instruments.

Local receipts: `checkpoint6-validation-20261003/` under the diagnostics folder.
Databases, raw receipts and logs are not committed. The first pre-repair sample
finished:52,320rows,29,504available/22,816unavailable, zero duplicates,331.97seconds.
Those are not final-code counts. Repaired initial8x30sample: **53,280rows,
31,693available/21,587unavailable**, zero duplicates,142.29seconds. It used three
isolated research-worker databases, no concurrent writes to one DB and no
trading runner. The remaining15instruments finished in259.86seconds.

Final combined repaired sample: **23instruments ×30sessions =690snapshots**,
August19–September30,2026. **153,180 inserted results:85,204available and
67,976unavailable**, zero duplicate inserts. There are222definition versions
and9,270distinct source-row/content versions. Source known-at range:
2026-10-01T14:02:11.471152+00:00 through2026-10-03T20:12:15.912346+00:00.
These later knowledge times are why this is retrospective, not a historical
availability claim. API/model calls during feature generation:0.

| Family | Available | Unavailable |
|---|---:|---:|
| breakout_structure | 14,906 | 1,654 |
| candlestick_geometry | 0 | 8,280 |
| earnings_events | 640 | 7,640 |
| fibonacci | 26,220 | 4,830 |
| fundamentals | 2,250 | 8,790 |
| intraday_future | 0 | 8,970 |
| macro_context | 4,163 | 6,877 |
| momentum | 10,350 | 0 |
| sector | 4,140 | 11,730 |
| support_resistance | 8,735 | 235 |
| trend | 11,730 | 0 |
| volatility | 2,070 | 2,070 |
| volume | 0 | 6,900 |

Missing-reason counts: INSUFFICIENT_HISTORY188;
INSUFFICIENT_VALIDATED_HISTORY4,117; MISSING_OR_INCOMPATIBLE_CONFIRMED_FACTS8,790;
NO_AUTHORITATIVE_EVENT_FIELD7,640; NO_CONFIRMED_LEVEL47;
NO_ELIGIBLE_MAPPING_OR_REFERENCE_HISTORY10,350; NO_POINT_IN_TIME_CONSTITUENTS1,380;
NO_PRIOR_BREAKOUT1,654; NO_VALIDATED_ATR4,830; NO_VALIDATED_INPUT2,760;
NO_VALIDATED_INTRADAY_DATA8,970; NO_VALIDATED_OHLCV17,250.

Repaired calculation hash:
`45b4c2ab719f13dd17cb735118792adc9bc3f8f872466ccba0c2cba3196e3926`.

A strict historical dry run on repaired code for VTI at2026-09-30market close
returned **0 available /222 unavailable**, correctly excluding later captures.
An identical repaired VTI write rerun inserted0rows and recognized222duplicates.
All26pre-existing tables in each of the six repaired sample databases compare
equal to the source research tables (156comparisons, zero changes). No
orders/fills/official-account tables were added. Source database hash unchanged.

## Isolated UI verification

Temporary preview on 8786 used the isolated research database and a read-only
official dashboard snapshot. It is not a deployed dashboard. Desktop and
390-pixel phone layout checked: factual warning, retrospective label, GET-only
filters, expandable provenance and close-level/anchor audit table. The mobile
feature section measured 326px wide / 324px scroll width; no horizontal overflow.
The SVG becomes an exact-value disclosure table on narrow screens.

## Control A recheck — 2026-10-03 19:23 ET

Release: N. Exact installed source fingerprint:

`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`

Daily service loaded, idle between ticks, last exit 0, interval 60 seconds.
No STOP_TRADING file. Options-buy pause true. No trading strategy, model, budget,
configuration or broker change; no runner restart.

Live research database SHA-256 remains the pre-validation value:
`b06cca62dcd3775c30cc08197408c1f2db99b1a9cef01d9aa0ee0aae8cf44164`.

## Review gate

Fresh whole-branch review found seven Important issues, reproduced and repaired
in one owner RED→GREEN pass. See [full disposition](CHECKPOINT6_REVIEW.md).
Two lower-priority limitations remain explicit: complete FOMC coverage is not
established by an adapter; some unavailable diagnostics group multiple causes.
Neither becomes an available capability. Native fixes are tested; cloud and
deployment remain separate gates. No merge or deployment is implied.

## Feature infrastructure

Registry:222 descriptive definitions. Store: five additive append-only tables,
content-addressed shared input sets and exact completed-run result manifests.
PIT: source knowledge/acceptance/publication checks precede revision selection;
XNYS completion/contiguity enforced in adapters and public engine. Feature
version and whole-package calculation hash retained, including source row refs.
Rows stored: isolated validation only; live derived-feature rows remain0.

## Technical features

Moving averages, momentum, RSI, MACD, close support/resistance and breakouts:
implemented and fixture-tested, eligible stored closes used in isolated samples.
ATR, candle geometry and volume: pure calculators tested; no validated live
OHLCV adapter/input, so real-sample outputs stay unavailable. No candles are
reconstructed from closes. Zero volume/range are not silently imputed.

## Fibonacci

Algorithm:`close_fractal_3x3_v1`, strict three neighbors on each side; available
only after the third subsequent session and all source knowledge. Ties are not
pivots. Retracements23.6/38.2/50/61.8/78.6%; extensions127.2/161.8%. Last-three
completed-leg clusters use0.5% bounded grouping. Anchors, confirmation and
current close are auditable. Separate nearest extension and equality/touch
records are descriptive, never entry signals. ATR distances remain unavailable
without separately validated aligned OHLCV. Capability: partial input coverage,
not deployed. Final sample row counts are reported in the family table.

## Sector

Six current internal classifications have dated official issuer/fund citations;
not historical GICS. Relative price returns require aligned same-basis history.
Leadership uses the fixed dated XLK/XLY/XLC subset and includes every dependency.
Breadth/above-SMA50 calculators require a complete dated constituent record;
there is no live constituent snapshot. Current mappings are not backdated into
September. Historical sample sector comparisons therefore remain partial.

## Fundamentals

Confirmed SEC growth, margins, cash-flow, debt-related ratios and diluted-share
changes are implemented. Same-end duration selection and comparative prior-year
facts have regression coverage. Missing debt/facts remain null. No valuation or
fundamental score. Detailed duration/source audit is retained; grouped missing
reasons still lack every operand-level diagnostic. Capability: partial.

## Earnings / SEC

Filing ages, forms and trailing counts use accepted, known accessions. Earnings
session distance/timing need authoritative event fields. No filing acceptance is
substituted for earnings publication. Transcript analysis is not implemented.
Capability: partial filing evidence; missing earnings fields remain unavailable.

## Macro

Fed target bounds/midpoint and PCE descriptors use validated factual observations.
Prior change needs a legitimately linked prior value. Last-three meetings are
unavailable without source-certified coverage; a sparse sample is not enough.
CPI, labor, Treasury yields and market volatility remain unavailable. No macro
regime classifier or score; capability partial, model remains NOT_STARTED.

## Intraday

VWAP, RVOL, opening range and trade-flow entries are registry-only, unavailable.
No provider activation, feed connection, credentials, account or purchase.

## UI

Feature explorer deployed: **NO**. An isolated temporary preview was tested.
Fibonacci audit visible in preview: YES; current close/anchors/exact-value table.
Research-only warning: YES. Same-date retrospective mode explicitly labelled.
Family AVAILABLE/PARTIAL_EXISTING/UNAVAILABLE describes stored-snapshot coverage,
not live deployment. Preview processes/tabs are stopped after inspection.
Trade recommendation present: NO.

## Capabilities — isolated implementation, NOT installed promotion

| Capability | Branch state / coverage |
|---|---|
| technical_engine | Implemented; PARTIAL_EXISTING without live OHLCV/volume |
| fibonacci_features | Implemented close-only; PARTIAL_EXISTING without ATR |
| sector_engine | Implemented; PARTIAL_EXISTING, no historical mapping/constituents |
| fundamental_features | Implemented; PARTIAL_EXISTING confirmed SEC coverage |
| earnings_features | PARTIAL_EXISTING filing metadata; event fields incomplete |
| macro_features | PARTIAL_EXISTING factual Fed/PCE; no complete meeting-coverage adapter |
| intraday_features | UNAVAILABLE registry only |
| macro_regime | NOT_STARTED |
| options_strategy | NOT_STARTED |
| ml_ranker | NOT_STARTED |

## Experiment state

No temporary8786preview or research-validation workers remain running.
Development worktree and gitignored validation ledger are preserved for handoff;
cloud gate remains incomplete, so the plan is not marked fully complete.

Firm Lab fills: 0

Firm trading trial: NOT REGISTERED

October research stop superseded: NO

Control A: UNCHANGED

Official Lane B: PAUSED

Real execution: DISABLED
