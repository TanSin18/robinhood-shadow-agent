# Firm Lab — architecture and status

Firm Lab is built beside Control A and is completely separate from it. It starts, and at this checkpoint stays,
in `BUILD_OBSERVE`: it may store data, features, research records, capability status, counterfactual
recommendations and benchmark observations, and show them read-only. It may not create a paper order, write a
paper fill, change a paper portfolio, write an Official decision or reach real execution.

## Component status (2026-10-01)

```text
Daily data            AVAILABLE      completed-session closes, read from Control A's decision capsules (read-only)
Feature store         BUILDING       one family: close, session count, MA200, above_ma200, momentum_126d
Session dates         BUILT          exchange_session_date stored beside the raw provider timestamp
Baseline check        BUILT          control_a_baseline_counterfactual, DEVELOPMENT_ONLY
Capability registry   BUILT
VTI ruler             DEFINED        price return; dividends not included yet
70/30 ruler           DEFINED — 70% VTI + 30% 3-month U.S. Treasury-bill total return; DATA_SOURCE_PENDING
Fundamentals          BLOCKED — NO PROVIDER
Analyst revisions     BLOCKED — NO PROVIDER
Earnings calls        PLANNED — NO SOURCE CONNECTED
News / catalysts      PLANNED
SEC filings           PLANNED
Sector model          PLANNED
ML ranker             PLANNED — STRATEGY COMPONENT (belongs to a registered recipe)
Intraday              BLOCKED — NO PROVIDER (bars, VWAP, opening range, RVOL, flow, order book)
Options analytics     DATA ONLY — storage schema; nothing is ingested; no recommendation
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
3-month U.S. Treasury-bill total return, a fixed allocation with no tactical reallocation. No clean Treasury-bill
total-return series is connected, so its `implementation_status` is `DATA_SOURCE_PENDING`: nothing is computed and
no other asset stands in for it. Its rebalancing convention has not been specified yet. The Firm
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

Which external datasets to introduce deliberately (fundamentals, revisions, intraday), the Treasury-bill series and
rebalancing convention of the 70/30
ruler, how the October research stop is treated, the trial number and the exact recipe that becomes the Firm's
registered trial.
