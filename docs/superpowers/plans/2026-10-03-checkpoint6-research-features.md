# Checkpoint 6 Research Feature Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn validated research observations into reproducible, auditable, point-in-time descriptors without trading or modeling.

**Architecture:** Isolated immutable feature package, additive append-only research tables, manual generator and read-only explorer. Pure family calculators consume one typed, cutoff-filtered snapshot; no execution handles or network access. Preserve existing baseline and benchmark code.

**Tech Stack:** Python3.12+, Decimal, SQLite, pytest, existing pinned exchange-calendars4.13.2, existing server-rendered dashboard/SVG/CSS; no new paid services or ML dependencies.

**Spec:** `docs/superpowers/specs/2026-10-03-checkpoint6-research-features-design.md`, implements the operator's 51-section Checkpoint6 request. Architecture approved2026-10-03; this detailed plan awaits review. No implementation authorized by this document alone.

## Global Constraints

- Control A unchanged; fingerprint `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
- BUILD_OBSERVE; Firm Lab fills0; trial NOT REGISTERED; October stop not superseded.
- Official Lane B PAUSED; real execution DISABLED; no trading-runner restart.
- Codex maintenance PREPARED_AND_PROVEN_NOT_INSTALLED, independent of this work.
- No strategy scores, predictions, fitting, execution imports, broker/network calls or official DB writes.
- No invented OHLC, volume, publication time, historical mappings or zero imputation.
- Every result versioned; legacy baseline and frozen Treasury methodology unchanged.
- Read-only UI: RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL.
- Git checkpoints sanitized and pushed; push is not deployment. Stop after Checkpoint6.

## Review Focus

- Backdated close history looks historical but was learned later: Task2 tests strict cutoff and retrospective labeling.
- A missing holiday/early-close session changes windows/confirmation: Task2 tests XNYS rather than weekdays.
- Conflicting revisions or input order changes anchors: Tasks1/4 test deterministic rejection and immutable prior results.
- A zero-range candle or negative fundamental base becomes a plausible fake number: Tasks5/7 test explicit undefined ratios and signed-base convention.
- A symlink/hardlink or dashboard GET reaches a writable official DB: Tasks1/9/10 test identity checks and read-only connection enforcement.

## Execution map and common commands

Worktree: `/Users/tanmaysinnarkar/.codex/worktrees/robinhood-live-rehearsal`.
Branch: `codex/checkpoint6-features`, base `85f6597`.
Use primary `.venv` interpreter only as a development tool, not a runner:

```sh
/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest tests/test_research_feature_contract.py -q
```

Each task follows RED → minimal implementation → GREEN → inspect diff → commit.
Run the named test file using the command above with its filename substituted.
Do not commit failing product tests. Record unchanged known environment failures
separately. Commit only the task's explicit source/test/doc paths, not `git add .`.
All paths below are relative to this isolated worktree, never installed paths.

The file map and formulas in the design are normative. Create the package
`firm_lab/research_features/__init__.py` empty: importing it must not migrate,
collect, generate or connect anything. Helpers below define public contracts;
implementation may use private helpers without altering formulas or interfaces.

### Task 1 — Contracts and isolated append-only storage

**Files:** create package `__init__.py`, `types.py`, `registry.py`, `store.py`;
test `tests/test_research_feature_contract.py`.
**Interfaces:** design's SourceRef/Request/FeatureResult; `FeatureStore(path,
official_db)` context manager, `append(result)->bool`, `read(request)->tuple`,
`start_run(request)->str`, `finish_run(run_id,receipt)->None`. Receipt is an
immutable final append, not an update. Registry `definitions()->tuple[dict,...]`
includes every design family and formula version. Definition content is hashed.

- [ ] Write failing tests for null versus zero, unsupported types/NaN, source refs,
  hash determinism, official paths/symlink/hardlink/signature and SQL immutability.

```python
def test_official_alias_rejected(tmp_path):
    import os, sqlite3, pytest
    from firm_lab.research_features.store import FeatureStore
    official = tmp_path / 'agent.db'
    sqlite3.connect(official).close()
    alias = tmp_path / 'alias.db'
    os.link(official, alias)
    with pytest.raises(ValueError, match='OFFICIAL'):
        FeatureStore(alias, official_db=official)
```

- [ ] Run test file; confirm failure is absent new contract, not environment error.
- [ ] Implement additive tables from design. Before writable connection, resolve
  paths/inode, validate Firm Lab metadata and reject official schema. Use explicit
  column lists, parameterized SQL, transaction and uniqueness on content hash.
  Add SQL triggers rejecting UPDATE/DELETE; duplicate append returnsFalse.
- [ ] Add round-trip and duplicate tests with two revisions; read earlier cutoff
  returns earlier result. Run all storage/isolation tests; inspect and commit
  `feat: add isolated research feature contracts and append-only store`.

### Task 2 — PIT adapters and session resolution

**Files:** create `inputs.py`, `calendar.py`; test `tests/test_research_feature_inputs.py`.
**Interfaces:** `resolve_request(instrument,as_of=None,session=None,known_by=None)->Request`;
`load_snapshot(connection,request)->dict` with keys `closes`, `ohlcv`, `facts`,
`filings`, `earnings`, `macro`, `mappings`, `source_refs`, `missing_reasons`.
`connection` must be opened read-only by caller. Each record retains source ID,
unit, basis, source-known-at, effective/acceptance time. Never accept official DB.

- [ ] Write tests for late-captured older closes, exact cutoff equality, revisions,
  2026-07-03 holiday, 2026-11-27 early close, missing sessions and timezone errors.

```python
def test_early_close_resolution():
    from firm_lab.research_features.calendar import resolve_request
    r = resolve_request('VTI', as_of='2026-11-27')
    assert r.knowledge_cutoff == '2026-11-27T18:00:00+00:00'
```

- [ ] Confirm RED. Implement XNYS lookup without modifying legacy sessions.py;
  each adapter applies source eligibility BEFORE latest-revision selection.
  Exclude benchmark-only inputs via existing `firm_lab.usage` contract.
- [ ] Add tests where a revised PCE/SEC record is physically present but cutoff
  predates it, input rows reversed, mismatched basis, known split and absent bar.
  Assert no backfill/forward-fill; then GREEN and commit
  `feat: enforce research feature knowledge cutoffs and session windows`.

### Task 3 — Close-based technical calculators

**Files:** create `technical.py`; test `tests/test_research_feature_technical.py`.
**Interfaces:** functions `sma(values,n)`, `simple_return(values,n)`,
`rsi_wilder(values,n=14)`, `ema(values,n)`, `realized_vol(values,n)` return
Decimal|None; `technical_features(snapshot,request)->tuple[FeatureResult,...]`.
EMA helper returns latest scalar; internal series helper preserves seed refs.

- [ ] Add hand-calculated tests, including constant, increasing/decreasing,
  short history, full SMA windows and Decimal precision.

```python
def test_sma_return_and_flat_rsi():
    from decimal import Decimal as D
    from firm_lab.research_features.technical import sma, simple_return, rsi_wilder
    assert sma([D(1), D(2), D(3)], 3) == D(2)
    assert simple_return([D(10), D(11)], 1) == D('.1')
    assert rsi_wilder([D(10)] * 15) == D(50)
```

- [ ] Verify RED; implement design equations exactly, explicit warmup dependencies,
  MACD smoothing seed, five-session SMA slope, 252-feature-value percentiles.
- [ ] Verify flat-series MACD/histogram/volatility0, ramp EMA hand expectations,
  percentile ties50, nreturn requiresn+1, no missing-session compression.
  GREEN and commit `feat: calculate versioned close-based technical descriptors`.

### Task 4 — Confirmed structure and Fibonacci

**Files:** create `structure.py`, `fibonacci.py`;
tests `tests/test_research_feature_structure.py`, `tests/test_research_feature_fibonacci.py`.
**Interfaces:** `confirmed_pivots(closes)->tuple[dict,...]`,
`completed_legs(pivots)->tuple[dict,...]`, `directed_levels(start,end)->dict`,
`structure_features(snapshot,request)` and `fibonacci_features(snapshot,request)`
return tuples of FeatureResult. All pivot/leg dictionaries carry immutable IDs,
session and confirmation times, endpoint value/type, input refs.

- [ ] Write tests for strict3×3 ties, unconfirmed high, same-type replacement,
  up/down legs, reversed inputs, revisions and short-history unavailable.

```python
def test_directed_levels():
    from decimal import Decimal as D
    from firm_lab.research_features.fibonacci import directed_levels
    up = directed_levels(D(100), D(120))
    assert up['retracement_0.618'] == D('107.640')
    assert up['extension_1.618'] == D('132.360')
    down = directed_levels(D(120), D(100))
    assert down['retracement_0.618'] == D('112.360')
```

- [ ] Confirm RED; implement immutable emitted legs, frozen prior levels,
  bounded0.5% clusters and three-leg limit; audit every emitted Fibonacci result.
- [ ] Test no pivot at i+2, visibility at i+3 only if all inputs known, no old
  anchor mutation after new extreme, no pre-confirmation touches. Test cluster
  bridge rejection, nearest ties, support equality and five-session retest expiry.
  GREEN and commit `feat: add auditable confirmed close structure and Fibonacci`.

### Task 5 — OHLCV library and honest live unavailability

**Files:** create `ohlcv.py`; test `tests/test_research_feature_ohlcv.py`.
**Interfaces:** `geometry(o,h,l,c,prior_close=None,prior_high=None,prior_low=None)->dict`;
`true_range(h,l,prior_close)->Decimal`, `ohlcv_features(snapshot,request)->tuple`.

- [ ] Write exact geometry/TR/ATR/volume and zero denominator tests.

```python
def test_geometry():
    from decimal import Decimal as D
    from firm_lab.research_features.ohlcv import geometry, true_range
    g = geometry(D(10), D(14), D(9), D(12))
    assert (g['body'], g['upper_wick'], g['lower_wick']) == (D(2), D(2), D(1))
    assert g['clv'] == D('.2')
    assert true_range(D(14), D(9), D(8)) == D(6)
```

- [ ] Confirm RED; implement range checks, ATR seed/recursion, prior-window volume
  means and design's four interactions. No OHLC adapter may construct fake fields.
- [ ] Add invalidOHLC, negative/zero volume, zero-range ratio null, prior-volume0,
  missingATR while Fibonacci price-distance valid, and close-only snapshot tests.
  GREEN and commit `feat: add input-gated OHLCV research calculations`.

### Task 6 — Effective-dated sector descriptors

**Files:** create `sector.py`, `docs/firm_lab/sector_mapping.md`;
test `tests/test_research_feature_sector.py`.
**Interfaces:** `mapping_at(rows,instrument,cutoff,session)->dict|None`;
`sector_features(snapshot,request)->tuple`. Mapping fields: instrument, internal
sector, ETF, effective_from/to, known_at, source URLs/hash, version, proxy label.

- [ ] Add failing future-mapping and missing-reference tests.

```python
def test_mapping_never_backdates():
    from firm_lab.research_features.sector import mapping_at
    row = dict(instrument='AAPL', known_at='2026-10-03T20:00:00+00:00',
               effective_from='2026-10-03', effective_to=None,
               sector='technology', etf='XLK', version='internal-v1')
    assert mapping_at([row], 'AAPL', '2026-09-30T20:00:00+00:00', '2026-09-30') is None
```

- [ ] Verify RED; verify official issuer/ETF sources before recording mapping,
  store capture timing, implement aligned returns/volatility and fixed-set rank.
- [ ] Test absentETF history, ETF incorrectly mapped as stock, changing rank
  universe, tiedrank, missing constituent snapshot and subset breadth labels.
  GREEN and commit `feat: add provenance-bound sector research descriptors`.

### Task 7 — SEC fundamentals and factual events

**Files:** create `fundamental.py`, `events.py`;
tests `tests/test_research_feature_fundamental.py`, `tests/test_research_feature_events.py`.
**Interfaces:** `signed_growth(current,prior)->Decimal|None`;
`fundamental_features(snapshot,request)->tuple`, `event_features(snapshot,request)->tuple`.

- [ ] Add failing tests with CONFIRMED and NOT_FOUND facts, acceptance later than
  cutoff, 3M versus9M incompatibility, same fiscal quarter across years and debt null.

```python
def test_growth_convention():
    from decimal import Decimal as D
    from firm_lab.research_features.fundamental import signed_growth
    assert signed_growth(D(-5), D(-10)) == D('.5')
    assert signed_growth(D(1), D(0)) is None
```

- [ ] Confirm RED; implement exact comparable-period matching, ratios and explicit
  missing reasons. Compute no synthetic quarter from YTD OCF. Events use accepted
  factual timestamps and XNYS; unknown release time is not default before-open.
- [ ] Test SEC amendment known later, duplicate accession, unsupported consensus,
  future scheduled event only if already known, unknown timing, weighted-average
  shares not outstanding shares. GREEN and commit
  `feat: derive validated SEC and earnings research descriptors`.

### Task 8 — Macro context and future intraday registry

**Files:** create `macro.py`; extend new `registry.py`;
test `tests/test_research_feature_macro.py`.
**Interfaces:** `target_midpoint(lower,upper)->Decimal`;
`macro_features(snapshot,request)->tuple`. Intraday definitions are registry-only.

- [ ] Add tests for midpoint, three distinct meeting counts, PCE revision cutoff
  and absence of CPI/labor/yield proxies.

```python
def test_midpoint():
    from decimal import Decimal as D
    from firm_lab.research_features.macro import target_midpoint
    assert target_midpoint(D('3.75'), D('4.00')) == D('3.875')
```

- [ ] Verify RED; compute only design's factual descriptors. Preserve MoM percent
  unit; revisions don't increment meeting count. Insufficient three meetings null.
- [ ] Assert every intraday result absent/unavailable, no macro classifier or
  trading hook, PCE level/YoY unsupported. GREEN and commit
  `feat: expose factual macro context and unavailable intraday definitions`.

### Task 9 — Pure engine, manual generator and feature catalog

**Files:** create `engine.py`, `cli.py`, `docs/firm_lab/feature_catalog.md`;
tests `tests/test_research_feature_engine.py`, `tests/test_research_feature_cli.py`.
**Interfaces:** `compute(snapshot,request)->tuple[FeatureResult,...]` calls family
calculators, sorts byfamily/name/version; `main(argv)->int` CLI. Dry-run default;
`--write` explicit. Receipt counts byfamily/instrument/session and reason.

- [ ] Write failing engine order/hash, CLI dry-run byte-unchanged and schema tests.

```python
def test_cli_requires_temporal_mode():
    import pytest
    from firm_lab.research_features.cli import main
    with pytest.raises(SystemExit) as e:
        main(['--database', '/not-opened.db', '--instrument', 'VTI'])
    assert e.value.code == 2
```

- [ ] Verify RED; wire only new pure functions and read-only adapters. Provide
  explicit date/cutoff parser, reject contradictory flags. No default DB path.
  Dry-run prints receipt; write requires valid Firm Lab boundary before transaction.
- [ ] Add import-graph guards for execution/broker/model/network, monkeypatch
  socket creation to fail during generation, officialDB digest unchanged, no
  prohibited tables, duplicate rerun stable, availability derived from validated
  rows. Catalog must enumerate every registry field/formula and limitation;
  test name/version parity. GREEN and commit
  `feat: add manual isolated feature generation and complete catalog`.

### Task 10 — Read-only feature explorer

**Files:** create `view.py`, `agents/desk/feature_explorer.py`;
modify `agents/desk/firm_lab_page.py`; test `tests/test_research_feature_ui.py`.
**Interfaces:** `feature_view(readonly_connection,request)->dict` returns stored
rows/coverage/anchor graph only; `render_features(view)->str` escaped HTML/SVG.

- [ ] Write failing render/provenance/cutoff/read-only tests.

```python
def test_warning_and_missing_data_visible():
    from agents.desk.feature_explorer import render_features
    html = render_features({'rows': [], 'coverage': {}, 'anchors': [],
                            'missing_reason': 'NO_VALIDATED_OHLC'})
    assert 'RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL' in html
    assert 'NO_VALIDATED_OHLC' in html
```

- [ ] Verify RED; use existing page navigation and self-hosted assets; selected
  instrument/session/cutoff GET parameters validated. Group families with native
  disclosures, neutral styling and accessible stored-level SVG/table. Include
  retrospective warning, no-results state and received knowledge times.
- [ ] Test source-text HTML injection, inaccessible/emptyDB, stale capability
  metadata, keyboard disclosures, mobile layout, no runtime writes on GET/POST,
  no generator import and absent critical provenance never shown AVAILABLE.
  GREEN and commit `feat: add read-only auditable research feature explorer`.

### Task 11 — Controlled generation and independent review

**Files:** create `docs/firm_lab/CHECKPOINT6_VALIDATION.md`; add regression tests
to corresponding task files. Local receipts/data stay outside Git.

- [ ] Reverify Control A fingerprint/service/no stop/LaneB and BUILD_OBSERVE;
  make an SQLite backup of researchDB for isolated validation, not officialDB.
- [ ] Run newCLI dry-run for approved sample, latest30sessions with full eligible
  history; then write only to isolated copy. Explicit retrospective mode required
  for older sessions captured later. Record unique results, unavailable reasons,
  input counts, knowledge ranges, duplicates and all formula versions.
- [ ] Independently review allnine risk categories in original section49. Reviewer
  reads actual code/results, not just report. Reproduce every defect with failing
  regression, fix and rerun. Do not expand sample before review passes.
- [ ] Run all focused `tests/test_research_feature_*.py`, allFirmLab tests
  (`pytest --collect-only` first to include macro/collector modules), full
  `python -m pytest -q`, then cloud suite in an available cloud checkout.
  Record command, interpreter, SHA, exact counts and named failures. Known
  configWarning isolation failure stays separate; no guard weakening.
- [ ] If review passes, expand to existing23instruments in isolated copy and
  report per-family coverage. No new provider or unregistered instruments.
  Commit sanitized validation report and regression fixes; push and verify SHA.

### Task 12 — Research-only deployment, audit and stop

**Files:** create `docs/firm_lab/CHECKPOINT6_CLOSURE.md`, update
`docs/review/CODEX_STATUS.md` and `docs/firm_lab/ARCHITECTURE.md`.

- [ ] Before deploy, confirm detailed plan approval, no unresolved critical review,
  parser/input/calculation validation passes and cloud evidence or explicit
  operator exception. Prepare hash manifest and backup of researchDB/UI overlay.
- [ ] Migrate only isolated live FirmLabDB with additive new tables and deliberate
  manual generator; never copy validationDB over liveDB. Compare all old table
  content before/after; only approved capability audit entries may change.
- [ ] Install reviewed UI files in dashboardoverlay; runtime trading checkout
  untouched. Restart only com.openai.robinhood-inbox if necessary. Verify HTTP,
  screenshots/disclosures, SQLite readonly behavior and no source-ref leakage.
- [ ] Rollback if validation fails: restore changed UI files from backup and
  restart only inbox. Derived research tables may remain ignored; DB restoration
  only after proving no subsequent writes, from verified research backup.
  Never restore anything into officialDB or restart daily.
- [ ] Recheck exact ReleaseN fingerprint, unchanged daily service definition,
  no stopfile, LaneBpause, mode, trial count0, no orders/fills, unchanged frozen
  Treasury methodology. Capture sanitized evidence, not private config/logs.
- [ ] Fill every section51 report heading with actual counts/limitations; never
  mark hypothetical capabilities AVAILABLE. Document cloud/native separately.
  Print required invariant lines and CLOSED only if all gates pass; STOP.
- [ ] Update canonical local CODEX_STATUS and branch copy, inspect staged data,
  commit `docs: close verified Checkpoint 6 research feature layer`, push and
  verify remote SHA. No Checkpoint7 work.

## Spec coverage / self-review

| Original sections | Owning tasks |
|---|---|
| 1–3,31–35 | 1–2,9,12 |
| 4–8 | 3,5 |
| 9–14 | 4 |
| 15–19 | 5 (optional named candles deliberately excluded) |
| 20 | 8 |
| 21–22 | 6 |
| 23–26 | 7 |
| 27–30 | 4–5,8–9; no composite scores |
| 36–38 | 10 |
| 39–42 | 9,11–12 |
| 43–46 | 1–10 tests,11 independent review |
| 47–51 | 11–12 |

Self-review: interfaces match design; all five Review Focus cases assigned;
optional features excluded explicitly, not promised; fixture completeness never
implies live availability. New formulas are detailed proposals awaiting review.

## Handoff state

Operator approved native task-by-task implementation on 2026-10-03. Tasks1–10
are implemented on `codex/checkpoint6-features`; Task11 native isolated validation
and fresh independent review/repair pass are finished. Cloud testing is NOT RUN.
This supersedes the planning-only
handoff above; historical planning entries in CODEX_STATUS remain historical.

Operator decision on 2026-10-03: **STOP BEFORE DEPLOYMENT**. There is no cloud
executor and no cloud-test exception. Task12 is withheld, not completed.
No live schema migration, UI installation or service restart is authorized by
this implementation checkpoint. No Checkpoint7 work. Finish and record the
native validation/review evidence, synchronize the sanitized branch, and hand off
the exact unresolved gates without claiming Checkpoint6 closed.
