# Checkpoint 5 closeout — 2026-10-03

Status: **CHECKPOINT 5 = CLOSED**, 2026-10-03 17:20 ET.
Accepted source: `975066521ad324dca3f06a9151ecc73e1c6d26a7`.
No Checkpoint 6 work. No maintenance installation.

## Final source investigation

At 17:10–17:17 ET, a final ordinary request to each official archived CPI
and employment release returned HTTP 403. The returned BLS page explicitly
describes automated-access policy enforcement. The exact server-side cause
cannot be determined from that response; no evasion or user-agent spoofing was
attempted.

The documented [BLS public API](https://www.bls.gov/developers/api_signature_v2.htm)
is accessible: four ordinary single-series GET requests returned HTTP 200 and
REQUEST_SUCCEEDED for CUUR0000SA0, CUUR0000SA0L1E, LNS14000000 and
CES0000000001 (2026 window: 8, 8, 9 and 9 records respectively).
Responses contain year, period, periodName, latest, value and footnotes, but no
exact publication timestamp or authoritative historical vintage identity.
The payroll response is a **level**, not the release parser's monthly change;
no silent substitution or derived change was ingested. Zero API rows accepted.
Capture time establishes availability now, not original release timing.
Without the required exact publication evidence the existing contract rejects
these rows. CPI and labor remain UNAVAILABLE, despite working API transport.
There is no need to substitute FRED or an unofficial mirror for this limitation.

[Treasury's official daily-rates methodology](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve)
identifies CMT yields and describes approximate 15:30 market quotation inputs,
not an exact publication timestamp. The official FAQ and XML documentation
do not establish per-observation historical publication instants. Local capture
proves only that the downloaded revision was available at capture; it cannot
identify when each historical value first became public. No date or customary
posting time is substituted for publication. Treasury yields stay UNAVAILABLE
for historical predictive research; all 570 previously rejected candidates
stay out of macro observations. The frozen 13-week bill benchmark is unchanged.

Provider conclusion retained: RECOMMENDED_PROVIDER = NONE. Required licensed
non-display/local retention rights remain unconfirmed; no purchase or activation.
Tick trades + quotes sufficient: YES. Level 2 required: NO.

## Deployment scope and rollback

The operator explicitly accepts unavailable datasets and absence of a cloud
executor as non-blocking when native, isolation and post-deployment checks pass.
This supersedes the previous report's stricter unfinished deployment gate.

Only the following dashboard-overlay files are to be installed:

- `agents/desk/firm_lab_page.py`
- `firm_lab/view.py`
- `firm_lab/macro_view.py`

The accepted MacroStore/manual ingest runs from the isolated development tree,
targeting only `robinhood-diagnostics/firm_lab/firm_lab.db`. No collector or
write-capable macro store is installed into the dashboard or trading runtime.
Replay the existing hash-checked captures; accepted facts append, failed sources
produce receipts and unavailable metadata, not observation rows. Do not copy a
development DB over the live research DB.

Before changes: SQLite backup of live research DB and full copy of dashboard
overlay under local `robinhood-diagnostics/firm_lab/checkpoint5-close-backup/`.
Rollback: restore the two existing UI/view files from that backup and move the
new macro_view.py aside, then restart **only** com.openai.robinhood-inbox.
Research data are isolated and may remain while the old UI ignores them. If DB
rollback is needed, first verify no later research writes, then use SQLite's
backup API from the saved pre-deployment DB into the research DB. Never restore
anything into `data/agent.db`, and never restart the daily runner.

## Closeout ledger

- Accepted source unchanged; no parser or policy rebuild.
- Focused native tests: 69 passed.
- Firm Lab native tests: 250 passed.
- Full native suite: 968 passed, 1 failed, 27 warnings, 51.81 seconds.
- Known independent failure: `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server` — installed Codex emits `configWarning`, rejected by the unchanged guard. Not a passing test and not hidden.
- Cloud suite: NOT RUN — executor unavailable.
- Deployment and post-deployment evidence: PASS, below.

Ruling: retain unavailable BLS/Treasury under the accepted exact-publication
contract; cost is incomplete economic coverage, not invented historical timing.
Ruling: deploy only read-only projection files to the UI overlay; migration is
one deliberate manual research operation, not a background ingestion service.
The cost is that future updates require another deliberate ingest.

## Final deployment evidence

Live research DB migrated in place through the accepted manual ingest command,
replaying the existing hash-verified capture directory. Zero new network calls
for deployment. It returned exit 2 **because rejected families remain rejected**;
the receipt and resulting database, not exit code alone, establish outcomes.
6 Fed + 12 PCE observations and 18 linked event records stored. No CPI, labor or
Treasury candidate was inserted. Four new tables: macro_observations,
macro_events, macro_release_evidence, macro_ingest_receipts.

Rehearsal on a backup and post-deployment comparison both show that the only
changed pre-existing tables are data_capabilities and capability-audit events.
Every old economic row, benchmark row, feature row, experiment record and meta
row is unchanged. No existing capability status regressed. CPI/labor metadata
was explicitly refined after replay: API works, archived pages denied, exact
publication/vintage evidence missing. This is metadata, not a data promotion.

SQLite integrity_check = ok for backup and deployed DB. BUILD_OBSERVE; zero
experiments; no order/fill/position/account tables. No macro imports in installed
daily_cycle, broker or risk code. Firm Lab boundary/import tests passed. All
macro input remains isolated from the registered run and portfolio sizing.

Exactly three files installed into the separate Agent Desk release overlay:

| File | Before SHA-256 | Installed SHA-256 |
|---|---|---|
| agents/desk/firm_lab_page.py | c9156b11d28e6edd0a60bac1780971eb7f1498f12697fda07ba7578a8f69dacd | d54cb64425e973045549ef9b74a8d33bd1c588b2bd59752539fe98d242f71e57 |
| firm_lab/view.py | 69058f3cf9e5138026d69ae87581433008fd00b468f1df145c473de5d984bfac | b1f4e11fb9669b01441ea4f6395f03915c22c11ead8fd00d1b23219ca0dac1de |
| firm_lab/macro_view.py | absent | 3ccead9267bcbd66605bfabfefbbb21062f2b5713d7a2c99844e5cc262cbd7da |

Installed bytes equal accepted branch bytes. The full backup establishes that
no other existing overlay source changed. Only com.openai.robinhood-inbox was
restarted. HTTP 200 at `/firm-lab`; four latest values, six unavailable cards,
18 event/version disclosures. Browser interaction opened Fed provenance and
July PCE revision 1: publication, capture/known-at, source hash and earlier
0.2 versus later 0.1 are visible. The permanent factual-only warning is present;
macro_regime remains NOT_STARTED and trading state NO TRADES. A GET left the
research DB hash unchanged. No POST, broker call or model call was made.

Control A: release N; pre/post source fingerprint exactly
`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
Runner definition unchanged, loaded on its existing 60-second timer, last exit
0, idle between ticks. No runner restart requested or performed. No stop file.
Installed options_buys_paused(root=primary) = true. No strategy/config/broker
change. Codex maintenance remains PREPARED_AND_PROVEN_NOT_INSTALLED.

## Final datasets and capability classification

| Family | Observations | Linked event/version rows | Final state |
|---|---:|---:|---|
| Fed | 6 | 6 (three decisions) | AVAILABLE |
| PCE | 12 | 12 (three release documents) | AVAILABLE — monthly percentage changes only |
| CPI | 0 | 0 | UNAVAILABLE — precise timing absent from reachable API |
| Labor | 0 | 0 | UNAVAILABLE — precise timing absent from reachable API |
| Treasury yields | 0 | 0 | UNAVAILABLE — exact historical publication not established |

Latest validated Fed range: 3.75–4.00%, September 16, 2026, explicit +25 bps.
Latest PCE: August 2026 headline 0.3%, core 0.2%, month-over-month, seasonally
adjusted. Four local revisions, two changed values; July headline/core each
change from 0.2 to 0.1 only after the later capture's known_at. Read-only deployed
checks confirm no row is visible before October capture. Local revision 0 does
not imply original economic vintage. Consensus UNAVAILABLE; future events 0.

| Capability | Live state |
|---|---|
| fed_policy_data | AVAILABLE |
| treasury_yields | UNAVAILABLE |
| cpi | UNAVAILABLE |
| pce | AVAILABLE |
| labor_data | UNAVAILABLE |
| macro_event_calendar | PARTIAL_EXISTING |
| market_volatility | UNAVAILABLE |
| macro_regime | NOT_STARTED |
| intraday (intraday_bars) | UNAVAILABLE |
| trades (tick_trades_quotes) | UNAVAILABLE |
| order_flow (trade_flow) | UNAVAILABLE |
| order_book | UNAVAILABLE |
| technical_engine | NOT_STARTED |
| sector_engine | NOT_STARTED |
| options_strategy | NOT_STARTED |
| ml_ranker | NOT_STARTED |

## Verification commands and review

Working tree: `/Users/tanmaysinnarkar/.codex/worktrees/robinhood-live-rehearsal`.
Interpreter: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python`.

```sh
python -m pytest -q tests/test_macro_parsers.py tests/test_macro_ingest.py tests/test_macro_view.py tests/test_firm_lab_macro.py
python -m pytest -q tests/test_firm_lab*.py tests/test_macro*.py --tb=short
python -m pytest -q --tb=short
```

69 / 250 / 968 passed plus the one known full-suite failure respectively.
The first group covers source parsers, point-in-time, event links and UI.
Cloud suite: NOT RUN — executor unavailable. No unrelated maintenance fix or
guard weakening. No application source changed during this closeout: installed
projection bytes are from the freshly tested accepted commit.

Fresh read-only deployment review found no critical compatibility issue.
All requested closeout checks were performed: capability-state comparison,
more precise deployed BLS explanations, live invariants, backups, hashes, and
browser disclosures. These were verification/metadata tasks, not deferred code
defects. Reviewer did not independently rerun tests/network/live checks; those
are the executor's recorded evidence above. No deferred minor code findings.

The Checkpoint 6 technical roadmap is preserved, including deterministic swing
anchors and Fibonacci as candidate features only. Nothing in it was started.

Firm Lab fills: 0

Firm trading trial: NOT REGISTERED

October research stop superseded: NO

Control A: UNCHANGED

Official Lane B: PAUSED

Real execution: DISABLED

CHECKPOINT 5 = CLOSED
