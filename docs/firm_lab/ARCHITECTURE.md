# Firm Lab — architecture and status

## Checkpoint 6 closed — 2026-10-03

Task12 deployed only the isolated research-feature store and read-only explorer.
222definitions;153,180stored results across23instruments/30sessions, explicitly
retrospective at an October3knowledge cutoff. No strategy, score, model, orders,
fills, schedule or Control A changes. Close-based structure uses
`close_fractal_3x3_v1`; future OHLC-based structure remains a separate version.
OHLCV/volume/intraday and incomplete data stay unavailable. Overall feature
families are PARTIAL_EXISTING, intraday UNAVAILABLE, macro regime/options
strategy/ML ranker NOT_STARTED. See `CHECKPOINT6_CLOSURE.md` for exact evidence,
cloud exception, known installed-Codex failure and accepted limitations.
Only the dashboard service restarted. Checkpoint7 is not started.

The sections below retain earlier plans as history, not current deployment status.

## Checkpoint 5 continuation (2026-10-03)

See `CODEX_CHECKPOINT5_HANDOFF.md` for current, verified progress. The historical
status blocks below describe earlier checkpoints; they are not current acceptance
evidence. Checkpoint 5 closed on 2026-10-03: validated Fed/PCE observations and
the read-only macro UI are deployed to the isolated research DB/dashboard only.
CPI, labor and Treasury yields remain unavailable with documented timing gaps.
See `CHECKPOINT5_CLOSURE.md`. No macro trading model exists.

### Checkpoint 6 — future feature work, not activated

The Technical Structure family will include moving averages, momentum, RSI,
MACD, ATR/volatility, support/resistance, breakout/breakdown structure, candlestick
geometry, volume confirmation, Fibonacci retracements/extensions, distance to the
nearest Fibonacci level, confluence with support/resistance and moving averages,
later VWAP confluence, and reaction/rejection around levels. Fibonacci anchors
must come from deterministic swing-high/swing-low logic—never manual drawing or
LLM visual interpretation.

Sector features planned for Checkpoint 6: relative momentum, breadth, volatility,
constituent participation and leadership change. No sector rotation or technical
strategy is introduced by Checkpoint 5.

### Checkpoint 7 — future validation, not a buy rule

Fibonacci is a testable feature, not a trading rule. Test incremental out-of-sample
value against simpler technical features; if it adds none, retain it only as an
explanation. A 61.8% retracement is not automatically a BUY. No technical engine,
ML model, options strategy or new trading schedule is activated by this roadmap.

Firm Lab is built beside Control A and is completely separate from it. It starts, and at this checkpoint stays,
in `BUILD_OBSERVE`: it may store data, features, research records, capability status, counterfactual
recommendations and benchmark observations, and show them read-only. It may not create a paper order, write a
paper fill, change a paper portfolio, write an Official decision or reach real execution.

## Component status (2026-10-02)

```text
Daily data            AVAILABLE      completed-session closes, read from Control A's decision capsules (read-only)
Feature store         BUILDING       one family: close, session count, MA200, above_ma200, momentum_126d
Session dates         BUILT          exchange_session_date stored beside the raw provider timestamp
Baseline check        BUILT          control_a_baseline_counterfactual, DEVELOPMENT_ONLY
Capability registry   BUILT
VTI ruler             DEFINED        price return; dividends not included yet
70/30 ruler           DEFINED — 70% VTI + 30% 3-month U.S. Treasury-bill total return, rebalanced monthly on the
                      first NYSE trading session; methodology APPROVED_AND_FROZEN 2026-10-02; computed from stored
                      auction records as a ruler only (VTI leg is price return)
Provider interfaces   BUILT — nine interfaces in firm_lab; without a collector behind them they return UNAVAILABLE
Research collectors   BUILT — firm_lab_collectors: SEC EDGAR, Massive, Sharadar, ThetaData; hand-started samples only;
                      cannot trade; each stays NOT CONFIGURED until the operator supplies access
Raw provider storage  BUILT — seven raw tables with provenance; provider_runs; provider_connections
Provenance standard   BUILT
Data-quality checks   BUILT — flag and reject, never repair
Data Readiness view   BUILT — read-only, on /firm-lab
T-bill total return   BUILT — 13-week bill accrual index from official auction records; frozen methodology; stops on a gap
Corporate actions     ADAPTER BUILT — Sharadar; needs operator access; nothing stored
Fundamentals          ADAPTER BUILT — Sharadar; needs operator access; nothing stored
Analyst revisions     BLOCKED — NO PROVIDER SELECTED
Earnings calls        PLANNED — NO SOURCE CONNECTED
News / catalysts      PLANNED
SEC filings           ADAPTER BUILT — SEC EDGAR; runs once the operator declares a User-Agent
Sector model          PLANNED
ML ranker             PLANNED — STRATEGY COMPONENT (belongs to a registered recipe)
Intraday              ADAPTER BUILT — Massive raw bars, trades, quotes; needs operator access. VWAP, opening range,
                      RVOL, flow and order book are not computed
Options analytics     DATA ONLY — ThetaData adapter and storage; needs operator access; no recommendation
Portfolio optimizer   PLANNED
Scheduler             NOT BUILT — ingestion is a manual research-only command
Experiment registry   EMPTY — no active Firm Lab experiment
Firm trading trial    NOT REGISTERED — takes the next unused experiment ID when it is registered
Fill engine           DOES NOT EXIST
Real execution        DISABLED
```

Nothing listed as PLANNED or BLOCKED has code that produces values.

## Isolation rules

1. **Separate database.** `robinhood-diagnostics/firm_lab/firm_lab.db`. The store refuses a path that is the
   Official database or in its directory. It has no order, fill, position, cash, account or portfolio table.
2. **Official is read-only from Firm Lab.** Three independent barriers: SQLite `mode=ro`, `PRAGMA query_only`,
   and an authorizer that allows only reads. Official tables are never reused as Firm Lab storage.
3. **One execution boundary.** `firm_lab.boundary.ExecutionBoundary` is the only place an order or fill attempt
   may go. In `BUILD_OBSERVE` it records the attempt and raises. In any other mode it also raises, because no fill
   engine exists. A real order raises in every mode. The boundary holds no broker, ledger or Official handle.
4. **The mode cannot be changed by the package.** `set_meta('mode', …)` and `request_trial_mode()` raise. Starting
   a trial is a separate operator decision and separate code that does not exist yet.
5. **Fail closed.** A missing, unreadable or unexpected mode, timestamp convention or database is never read as
   permission or as a healthy state.

## Architecture rule: there is exactly one trading-capable service

`com.openai.robinhood-daily` remains the only process that can reach `PaperBroker`, Inbox execution, risk issuance,
order creation or a broker. Future Firm Lab scheduling may use only one of two designs:

- **Design 1 — existing service.** Research functions are called from the existing 60-second service and stay
  isolated from execution while Firm Lab is `BUILD_OBSERVE`.
- **Design 2 — research-only worker.** A separate process is allowed only if it is structurally unable to import
  or call trading or execution modules.

The `firm_lab` package is written to satisfy Design 2: it uses the Python standard library only and imports
nothing from `agents`, `broker`, `risk`, `data`, `research`, `eval`, `scripts` or `config`. A test parses every
file in the package and fails on any such import, on any network or subprocess module, and on any name that
looks like an order or fill writer. No launchd job exists for it. The dashboard reads it through
`firm_lab.view` (opened `mode=ro`) and nothing else.

## Data path at this checkpoint

```text
Control A decision capsule (Official DB, read-only)
        │  inputs.session_closes  {symbol: {label: close}}
        ▼
session date = label + 1 day (must be a weekday, else stop)
        ▼
feature_observations  (append-only; revision number; known_at; raw/reconstructed timestamp basis)
        ▼
baseline features: completed_session_count, ma200, above_ma200, momentum_126d
        ▼
control_a_baseline_counterfactual  →  counterfactual_decisions (label DEVELOPMENT_ONLY)
        ▼
compared with Control A's own recorded ranking for the same run (plumbing check)
```

`ingest_provider_daily_bars` accepts raw provider bars (timestamp stored exactly as received) for the day a
direct, research-only read path is approved. It is not connected to anything today.

Point in time: every row has `known_at`; an evaluation uses only rows known at or before its own timestamp, and a
changed value is a new revision, never an overwrite. Today's bar is not a close until 16:00 New York.

## Greeks and option data

`option_chain_observations` stores raw provider facts only, with `provider_implied_volatility`, `provider_delta`,
`provider_gamma`, `provider_theta`, `provider_vega`. A value the provider did not supply stays empty. A future
pricing model would write separate `model_estimated_*` fields; the two are never mixed. Nothing reads this table.

## Benchmarks

Ruler 1: 100% VTI (the 100% equity benchmark). Ruler 2, defined by the operator on 2026-10-01: 70% VTI + 30%
3-month U.S. Treasury-bill total return, a fixed allocation with no tactical reallocation. Since 2026-10-02 its
bill leg is an accrual index built from official 13-week auction records under the frozen methodology
(`implementation_status` `AUCTION_ACCRUAL_INDEX_V1`); the VTI leg is price return. No other asset stands in for the
bill, and the result is a ruler only. It is rebalanced monthly, on the first NYSE trading session of each calendar month, with fixed weights, no tactical
changes and no retroactive asset substitution. A ruler's definition can be replaced only while it has no
observations, and the change is recorded; once observations exist it is locked. The Firm
cannot trade a ruler, change it, or choose it after seeing performance. No outperformance figure is computed or
shown in `BUILD_OBSERVE`.

## Future cadence (documentation only; no job exists)

The intended day, once the research-only boundary has been proven and the operator approves scheduling:

| Time (ET) | Job | Kind | May trade? |
|---|---|---|---|
| 06:30 | overnight data collection (closes, filings, calendar) | data | no |
| 08:30 | pre-market research refresh (features, catalysts) | research | no |
| 09:00 | candidate ranking | research | no |
| 09:25 | pre-open checks | research | no |
| 12:00 | midday data refresh | data | no |
| 14:30 | afternoon research refresh | research | no |

Three layers, kept apart:

- **Data collection** can run repeatedly and cannot trade.
- **Research** can compute features and rankings and cannot trade unless a registered trial recipe explicitly
  says its output is consumed.
- **Execution** can be invoked only by the registered strategy, from the one trading-capable service.

## What comes next (not started; each needs an operator decision)

Which external datasets to introduce deliberately (see `data_sources.md` and `provider_matrix.md`), the Treasury-bill
series of the 70/30
ruler, how the October research stop is treated, the trial number and the exact recipe that becomes the Firm's
registered trial.

## Data-source capability layer (Checkpoint 2, 2026-10-01)

- `firm_lab/providers.py`: nine interface definitions (fundamentals, estimates, earnings, filings, news, intraday
  market data, options market data, risk-free benchmark, corporate actions). None is connected. A call returns a
  `ProviderResult` whose status is `UNAVAILABLE`, `REJECTED` or `OK`; records can be read only from an `OK` result.
- `firm_lab/schemas.py`: the minimum fields per domain, and the Greeks naming rule (`provider_*` versus
  `model_estimated_*`).
- `firm_lab/provenance.py`: the provenance every response must carry.
- `firm_lab/quality.py`: validation that flags and rejects; records are never modified.
- `firm_lab/capabilities.py`: statuses `AVAILABLE`, `UNAVAILABLE`, `NOT_STARTED`, `BUILD_ONLY`, `PARTIAL_EXISTING`,
  `BLOCKED`. `AVAILABLE` can be written only with evidence: a named source, stored records and a passed validation.
  `daily_closes` and `daily_baseline_features` are re-confirmed from the stored data at every seed and ingest.
- None of these modules is imported by the baseline, the feature calculations, the execution boundary or the
  Official reader, and a test keeps it that way. They contain no network code.

## Research data stack (Checkpoint 3, 2026-10-02)

See `research_data_stack.md`. In short: `firm_lab_collectors` is the only package that opens a network connection,
it cannot import trading code, and it is started by hand. Raw answers are validated and either stored whole with
provenance or refused whole. A capability becomes `AVAILABLE` only from stored, validated rows. The Treasury-bill
leg of the 70/30 ruler has a written draft methodology (`treasury_bill_total_return_methodology.md`) and no
computation.
