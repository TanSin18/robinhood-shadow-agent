# Research Layer and Reasoned Promotion Exceptions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** First complete and prove the existing trader's operational fixes, then add reproducible, cost-aware research and forward AI comparisons with tightly scoped, human-approved promotion exceptions.

**Architecture:** Keep Stage 1's default-deny broker boundary and existing Agents SDK Research → Portfolio → Critic cycle. Put immutable source snapshots, deterministic strategies, chronological accounting, walk-forward evaluation and Monte Carlo in a separate research package/database. Forward AI overlays and promotion-review cards consume that evidence; neither can activate real trading.

**Tech Stack:** Existing Python 3.12+, Pydantic 2, SQLite, pytest, OpenAI Agents SDK, Codex read-only MCP bridge, local inbox, local MLflow and Phoenix; add NumPy for seeded simulations and a tested exchange-session calendar dependency only when research begins.

**Spec:** docs/superpowers/specs/2026-09-27-research-layer-design.md, approved with the user's six amendments on 2026-09-27. User-facing design summary: outputs/research-layer-design.md. Read the complete specification with this plan.

**Status:** Plan only. No research feature, new test pass, background-auth success or investment-performance result is claimed by this document.

## Global Constraints

- **Blocking sequence:** Task 1 must be complete and freshly verified before implementing any research code in Tasks 2–14. Prior test reports and interactive authentication are not sufficient.
- **Stage 1 stays paper:** real orders, cancellations, transfers, exercise and other money-moving actions remain default-denied. Exceptions produce readiness states, not LIVE.
- Existing account size is $500 per stocks/ETFs and options paper lane. Research PLAIN/AI accounts are additional independent $500 virtual comparisons, not allocations from a real account.
- The shared daily API budget stays $0.40. Separate Research, Portfolio and Critic model keys remain. Full LLM cycle once per trading day at 10:00 ET; intraday maintenance is code only.
- Preserve whitelist SPY, QQQ, VTI, SOXX, XLE, XLU, GLD, TLT, AAPL, MSFT, NVDA, AMZN, GOOGL, META. Single-stock research additionally requires current mega-cap verification.
- Historical strategy research is stocks/ETFs only. Existing defined-risk options paper behavior must not regress; no options-history claim is implied.
- Trade approvals expire after 30 minutes. Promotion-exception requests expire after seven days / 168 elapsed UTC hours, using a separate setting.
- Standard prospective confirmation is six calendar months AND 30 completed position round trips. Approved exceptions never reduce this below eight weeks / 56 elapsed days AND 15 completed round trips.
- Exceptions cannot waive historical after-cost VTI outperformance, primary Monte Carlo P(beat VTI) ≥ 60%, forward after-cost outperformance, AI net benefit where relevant, data validity or any trading safety rule.
- AI signals and AI ablations are prospective only. Historical AI ablation must say “not available: AI signals are forward-tested only”.
- Both strategies and VTI use verified total-return analytics; execution/accounting uses raw prices and explicit corporate actions, without double dividends.
- Each qualifying strategy requires full 2008, 2020 and 2022 out-of-sample test years. Five-year training for 2008 means 2003–2007 plus older indicator warm-up. Missing history blocks qualification; never invent or proxy it.
- Freeze the universe, parameter grid, selection rule, folds, costs and seeds before testing. Report all registered, attempted, successful, failed and repeated trials, including earlier linked registrations.
- Single-stock reports say “survivorship-biased: selected from today's mega-caps”; report actual coverage per ticker. Mega-cap threshold: $200 billion USD at registration, supported by timestamped evidence.
- Cache locally with source, event/availability/retrieval times, vintage, hash and parser version. No later revision or future observation may affect an earlier decision.
- Never request brokerage passwords or verification codes. Do not bypass source restrictions, purchase data, silently increase inference budgets or expose account credentials in artifacts.
- Preserve the dirty working tree, running services, existing histories and unrelated changes. Implementation uses an isolated workspace and disposable test databases; do not indiscriminately stage the whole repository.
- Every claimed capability needs passing tests. Fixture-based results, actual source smoke tests and performance evidence must be clearly separated.

## Review Focus

1. A terminal can authenticate while the actual background service cannot: prove the installed background environment's full read-only cycle, not merely the transport in an interactive shell (Task 1).
2. Dividend/split restatements can create lookahead or double-count income: compare causal total-return indicators with independently checked raw-price ledger wealth (Tasks 3 and 6).
3. A crash inside training is not an out-of-sample crisis test; newer tickers cannot inherit invented 2008 history: test complete per-strategy crisis coverage and universe admission (Tasks 3 and 7).
4. Shared AI calls, unavailable AI assessments and divergent holdings can make ablations look better than they are: allocate real costs once, preserve missingness and compare independent synchronized accounts (Tasks 9 and 10).
5. Seven-day cards can become stale, be replayed, or pass an eight-week floor with too few actual round trips: transactionally validate evidence, elapsed UTC time, unique completed positions and hard floors on approval and consumption (Tasks 11 and 12).

---

## Delivery order and acceptance gates

| Phase | Tasks | Deliverable | Exit condition |
|---|---|---|---|
| 0 — Operations first | 1 | Authenticated background cycle, inbox, correct costs and independent risk checks | Fresh automated tests AND genuine background read-only cycle evidence |
| 1 — Historical research | 2–8 | Sources/cache, total returns, registered strategies, ledger, walk-forward, Monte Carlo | Offline/adversarial tests pass; real-source coverage explicitly reported |
| 2 — Prospective AI value | 9–10 | Sourced event signals and matched PLAIN/AI comparisons | Forward-only enforcement, cost attribution and budget tests pass |
| 3 — Human review | 11–12 | Qualification registry and seven-day exception inbox | Hard floors, immutable audit and real-write-block tests pass |
| 4 — Integration | 13–14 | Local reports, daily/weekly integration, reproducibility and handover | Full regression suite plus accurately labeled source/performance evidence |

Do not start Phase 1 while Phase 0 is blocked. Report the exact blocker once and preserve mocked tests, but do not substitute mocked background authentication for acceptance. A research provider blocked in Phase 1 may be developed against fixtures, but cannot supply qualifying evidence.

## File map

Existing operational files to verify and fix only as needed:
- agents/codex_bridge.py — authenticated restricted transport and persistent cost accounting.
- agents/daily_cycle.py — one daily Research/Portfolio/Critic cycle and authoritative observations.
- agents/inbox.py, agents/inbox_web.py — persistent trade decisions and local security.
- agents/maintenance.py, scripts/install_shadow_services.py — code-only maintenance and installed background services.
- eval/scoreboard.py, eval/weekly.py — agent-only inference charges and scheduled reports.
- risk/engine.py, risk/models.py — independent position, settled-cash and sizing checks.
- config/loader.py, config/settings.yaml — existing operational values plus separate research/review configuration.
- broker/policy.py — existing default-deny boundary; locate actual policy exports before editing.

New focused files:
- agents/readiness.py; scripts/verify_operations.py — operational acceptance proof.
- research/models.py, research/cache.py, research/asof.py — contracts, immutable cache, temporal filtering.
- research/providers/{history,robinhood,sec,fred}.py — provider boundaries; no credential storage.
- research/returns.py, research/universe.py — causal total returns and actual coverage/eligibility.
- research/registration.py, research/strategies.py — immutable grids and pure signals.
- research/calendar.py, research/ledger.py — session/settlement rules and cash/tax/corporate-action accounting.
- research/walkforward.py, research/metrics.py — train/test separation, continuous OOS ledger and metrics.
- research/monte_carlo.py — paired bootstrap and separate sequencing stress.
- research/events.py, research/event_store.py — prospective sourced JSON and veto/tilt rules.
- research/ablation.py — synchronized plain/AI paper experiments and cost allocation.
- research/qualification.py, research/promotion.py — non-waivable gates and audited exception lifecycle.
- research/reports.py, research/service.py; scripts/research.py — reports and explicitly gated integration.
- prompts/earnings_signal_v1.md, prompts/filing_veto_v1.md, prompts/promotion_explanation_v1.md — versioned source-grounded prompts.
- tests/test_operational_readiness.py and tests/research/test_*.py — isolated fixtures and safety tests.
- tests/research/factories.py — deterministic synthetic fixture builders, explicitly non-qualifying.
- docs/research-operations.md — commands, limitations and recovery instructions.

Use SQLite at a configurable separate research database path and content-addressed raw blobs in a research cache directory; tests always use temporary paths. Add tests/research/__init__.py and tests/research/conftest.py for fixture discovery; no fixture may read the real account database. Persist Pydantic schema versions. Add research* to packaging only in Task 2. Verify Python compatibility, pin resolved research dependencies and record versions in manifests. Reuse local MLflow/Phoenix exporters without making either service availability a trading-safety dependency.

## Shared interface contract

Define these Pydantic models in Task 2, with extra fields forbidden and UTC-aware timestamps. Financial ledger fields use Decimal; metric/return arrays use finite floats. Collections must be copied/frozen at boundaries.

| Type | Required fields |
|---|---|
| SourceRecord | id, provider, key, event_at, available_at, retrieved_at, vintage, payload_sha256, parser_version, quality_flags, fixture |
| MarketBar | ticker, session, available_at, raw_open, raw_close, volume, source_id |
| CorporateAction | ticker, effective_session, available_at, kind: split/dividend, value, source_id |
| Coverage | ticker, first_session, last_session, observations, gaps, elapsed_years, usable_years, verified_adjustments, required_years_complete |
| TotalReturnPoint | ticker, session, available_at, index_value, source_ids |
| ResearchConfig | initial_cash=500, train_years=5, test_years=1, required_test_years=(2008,2020,2022), primary_block=20, sensitivity_blocks=(5,60), runs=10000, horizon=252, seed, spread_bps, slippage_bps, fee_usd, risk_free_rule |
| Registration | id, created_at, parent_id, strategy_version, universe, universe_evidence_ids, parameters, selection_rule, folds, holdout_year, config, input_hashes, registration_hash |
| Target | ticker, fraction, reason, earliest_execution_session |
| Fill | id, position_id, ticker, side, quantity, price, fee, session, settlement_session |
| LedgerState | settled_cash, unsettled_cash, positions, tax_lots, taxes_accrued, equity, closed_position_ids |
| DailyResult | session, gross_equity, net_equity, benchmark_gross_equity, benchmark_net_equity, traded_notional, completed_trade_pnls |
| Metrics | gross_cagr, net_cagr, max_drawdown, sharpe, one_way_turnover, trade_win_rate, windows_beating_vti; unavailable fields are None |
| RunResult | id, registration_id, daily, fills, metrics, coverage, fold_records, trial_counts, final_state, input_hashes, valid, fixture, invalid_reasons |
| MCResult | runs, seed, horizon, primary_block, p_beat_vti, p_beat_interval, median_max_drawdown, p05_max_drawdown, p_terminal_loss_gt_100, p_ever_loss_gt_100, sensitivities, reshuffle_status, input_hashes |
| EventSignal | id, kind, ticker, event_id, strategy_version, generated_at, source_ids, citations, source_available_at, prompt_version, model_version, assessment, uncertainty, missing_evidence, validity |
| ForwardResult | strategy_version, started_at, as_of, plain_equity, ai_equity_before_api, attributable_api_cost, fully_loaded_api_cost, benchmark_equity, closed_round_trips, signal_count, decision_divergences, missing_inputs, paired_sample_identifiable, evidence_hash |
| Qualification | strategy_version, historical_pass, forward_pass, ai_net_pass, hard_floor_pass, standard_sample_pass, reasons, state, evidence_hash |
| ExceptionRequest | id, strategy_version, evidence_hash, created_at, expires_at, proposed_fields, suggested_action, suggested_reason, warnings, decision, operator_reason, decided_at, consumed_at, revoked_at |

String fields with finite valid states must be enums/Literals. Quantities/prices must be finite and nonnegative, with positivity where required. IDs/hashes must be validated, not free-form evidence assertions. Downstream code reads these types; it does not create alternative untyped performance dictionaries.

---

## Task 1: Finish and prove the earlier operational fixes

**Files:** Modify existing operational files from the map only where current tests or the real background check fail. Create agents/readiness.py, scripts/verify_operations.py, tests/test_operational_readiness.py. Extend tests/test_codex_bridge.py, test_daily_cycle.py, test_inbox_web.py, test_hardening.py, test_service_schedule.py, test_stage1_robinhood_policy.py and test_review_regressions.py.

**Interfaces**
- Consumes existing cycle, risk, inbox, scoreboard and service APIs as implemented locally; inspect their exact signatures before changing them.
- Produces OperationalProof model in agents/readiness.py with booleans background_auth, daily_cycle, inbox, agent_only_api_costs, closing_checked, cash_checked, real_writes_blocked, plus source/config hashes, test-run ID, cycle ID, timestamps and sanitized background-environment evidence.
- Produces operations_ready(proof: OperationalProof) -> bool and require_operations_ready(proof: OperationalProof) -> None; false/invalid/stale/hash-mismatched proof raises ValueError in the latter.

- [ ] Inspect current dirty diff and run the existing targeted tests before making repairs. Treat prior handover reports as leads, not fresh evidence.
- [ ] Add this red test and fixtures for each independently failing prerequisite:

~~~python
def test_interactive_success_does_not_prove_background_auth():
    from types import SimpleNamespace
    from agents.readiness import operations_ready
    proof = SimpleNamespace(
        background_auth=False, daily_cycle=True, inbox=True,
        agent_only_api_costs=True, closing_checked=True, cash_checked=True,
        real_writes_blocked=True, evidence_valid=True,
    )
    assert operations_ready(proof) is False
~~~

This test isolates the conjunction with a structural test double. Separately construct actual OperationalProof instances with hashed temporary artifacts to test computed validation. Synthetic receipts may test validation but are forbidden in the real readiness artifact.

- [ ] Run .venv/bin/python -m pytest tests/test_operational_readiness.py -q. Expect missing-module/contract failure before implementation.
- [ ] Implement the conjunction and evidence checks, not a manually editable “ready” flag:

~~~python
REQUIRED = (
    "background_auth", "daily_cycle", "inbox", "agent_only_api_costs",
    "closing_checked", "cash_checked", "real_writes_blocked",
)
def operations_ready(proof: OperationalProof) -> bool:
    return all(getattr(proof, name) for name in REQUIRED) and proof.evidence_valid
~~~

Make evidence_valid a computed property that checks test results, artifact hashes, current source/config hashes, authenticated non-fixture background receipt and expiry before integration. Never trust a submitted evidence_valid boolean. Keep configurable validity short enough to detect a changed environment; explicitly reverify after transport, model, schedule, risk or inbox changes.

- [ ] Pin each prior fix with tests: closing sell quantity ≤ actual held quantity; false closing flags cannot bypass cash/sizing; buys above settled cash rejected before broker invocation; costs deducted only from Agent alone/Agent + approvals; budget 0.40; separate model keys; full whitelist; two $500 lanes; volatility sizing/caps; proposal-derived GOOD IF; once-per-day 10:00 ET scheduling with DST/holidays; restart-safe YES/NO and 30-minute expiry; intraday no model calls; scheduled weekly report.
- [ ] Verify rejected real order, cancel and transfer attempts never reach transport. Include an attempted real order in the end-to-end safety regression.
- [ ] Run the full existing suite. Repair only demonstrated failures; preserve unrelated edits.
- [ ] Prove the actual installed background environment can run Research → Portfolio → Critic using authenticated read-only MCP and real source payloads. Reuse the existing restricted Codex bridge, not Python OAuth. Capture worker environment identifiers without secrets, cycle/trace IDs, tool names, observed data timestamps and cost. Prefer the next scheduled eligible cycle; if the daily allowance is already used or budget is insufficient, wait rather than bypass limits. A closed-market HOLD may prove connectivity but must be labeled, and cannot prove market-open data freshness or fills.
- [ ] Create outputs/operational-readiness.json and outputs/operational-readiness.md only after the actual checks. If background auth fails, state the exact non-secret error once; stop research implementation until fixed. Do not claim an interactive test proves this gate.
- [ ] Re-run .venv/bin/python -m pytest -q. Record fresh results and inspect diff. Commit only this task's intended changes with message “fix: verify operational prerequisites before research”; do not include unrelated pre-existing files.

**Acceptance:** All five user-listed prerequisites plus Stage 1 blocking are tested and the real background cycle is evidenced. No research file implementation before this gate.

## Task 2: Typed research contracts and immutable as-of cache

**Files:** Create research/__init__.py, research/models.py, research/cache.py, research/asof.py, tests/research/factories.py, tests/research/test_cache.py. Modify pyproject.toml and research configuration in config/loader.py/settings.yaml.

**Interfaces**
- Consumes validated Task 1 proof.
- Produces the shared models above.
- Cache(root: Path, db: Path); put(record: SourceRecord, payload: bytes) -> str; get(source_id: str) -> bytes; available(key: str, at: datetime) -> tuple[SourceRecord, ...].
- asof(records: Sequence[SourceRecord], at: datetime) -> tuple[SourceRecord, ...].
- Test factory source_record(*, available_at: datetime, payload: bytes=b"{}") -> SourceRecord creates deterministic fixture=True records with valid hashes.

- [ ] Add the test below plus immutable duplicate/hash-conflict, timezone, restart, unknown-source and offline-network-denial tests:

~~~python
def test_future_revision_is_not_visible():
    from datetime import datetime, timezone
    from research.asof import asof
    from tests.research.factories import source_record
    old = source_record(available_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
    revised = source_record(available_at=datetime(2020, 2, 1, tzinfo=timezone.utc))
    assert asof([old, revised], datetime(2020, 1, 15, tzinfo=timezone.utc)) == (old,)
~~~

- [ ] Run .venv/bin/python -m pytest tests/research/test_cache.py -q; expect import/contract failure.
- [ ] Implement content-addressed append-only blobs, transactional indexes and the explicit eligibility filter:

~~~python
def asof(records, at):
    if at.tzinfo is None:
        raise ValueError("Decision time must be timezone-aware")
    return tuple(r for r in records if r.available_at <= at)
~~~

Reject a mismatched hash or changed payload under an existing immutable ID. Reject naive timestamps instead of guessing a timezone. Availability is distinct from retrieval time. Schema defaults must not mark fixtures as real.
- [ ] Add finite-value/Decimal/schema tests for every contract; allow None only for genuinely unavailable metrics. Run cache and existing config tests.
- [ ] Inspect and commit only this task's files: “feat: add immutable research data contracts and cache”.

## Task 3: Historical prices, total returns, universe and coverage

**Files:** Create research/providers/__init__.py, research/providers/history.py, research/returns.py, research/universe.py, tests/research/test_history.py, tests/research/test_total_returns.py, tests/research/test_universe.py.

**Interfaces**
- Consumes Cache, SourceRecord, MarketBar, CorporateAction, Coverage.
- parse_history(provider: str, payload: bytes, metadata: Mapping[str, str]) -> tuple[MarketBar, ...].
- total_return_step(previous_raw: Decimal, current_raw: Decimal, split_ratio: Decimal, dividend_per_new_share: Decimal) -> Decimal.
- build_total_returns(bars: Sequence[MarketBar], actions: Sequence[CorporateAction], at: datetime) -> tuple[TotalReturnPoint, ...].
- coverage(bars: Sequence[MarketBar], required_years: tuple[int, ...]) -> Coverage.
- register_universe(symbols: Sequence[str], market_caps: Mapping[str, Decimal], evidence_ids: Mapping[str, str], registered_at: datetime) -> tuple[str, ...].

- [ ] Add hand-calculated dividend/split tests:

~~~python
from decimal import Decimal as D

def test_dividend_offsets_ex_dividend_price_drop():
    from research.returns import total_return_step
    assert total_return_step(D("100"), D("98"), D("1"), D("2")) == D("1")

def test_two_for_one_split_is_not_a_loss():
    from research.returns import total_return_step
    assert total_return_step(D("100"), D("50"), D("2"), D("0")) == D("1")
~~~

- [ ] Add tests for newer tickers without 2008 history, current mega-cap filtering, exact first/last dates and observations, gaps, invalid provider data, unknown adjustments and future-action perturbations.
- [ ] Run .venv/bin/python -m pytest tests/research/test_history.py tests/research/test_total_returns.py tests/research/test_universe.py -q; expect failure.
- [ ] Implement this return convention, validated against split/dividend fixture wealth:

~~~python
def total_return_step(previous_raw, current_raw, split_ratio, dividend_per_new_share):
    if previous_raw <= 0 or split_ratio <= 0 or current_raw <= 0:
        raise ValueError("Invalid corporate-action return inputs")
    return split_ratio * (current_raw + dividend_per_new_share) / previous_raw
~~~

Document action ordering for coincident events. Build indicators only from actions available by the decision time. Never fill orders at total-return-index values. Normalize provider semantics explicitly; ambiguous Stooq adjustments or missing corporate-action metadata produce ineligible evidence.
- [ ] Implement Yahoo/Stooq adapters behind injected transport plus authorized file import. Do not bypass login/paywalls or silently splice providers. Keep URLs and terms/access status in source provenance.
- [ ] Freeze the selected stock subset at registration using sourced market caps; unknown eligibility excludes that stock. Attach the required survivorship label to the dataset, not just one report template. ETF selection limitations are also recorded.
- [ ] Run all Task 3 tests plus cache tests. Commit “feat: add verified total-return history and universe coverage”.

## Task 4: Read-only live data, full-text filings and macro vintages

**Files:** Create research/providers/robinhood.py, research/providers/sec.py, research/providers/fred.py, tests/research/test_providers.py.

**Interfaces**
- Consumes Cache and existing restricted Codex transport; do not create another brokerage login store.
- normalize_robinhood_read(tool_name: str, payload: bytes, retrieved_at: datetime) -> SourceRecord.
- parse_sec_document(payload: bytes, accession: str, cik: str, accepted_at: datetime, url: str) -> tuple[SourceRecord, str].
- parse_fred_vintage(payload: bytes, series_id: str, retrieved_at: datetime) -> tuple[SourceRecord, ...].
- Each network adapter accepts an injected callable fetch(url: str, headers: Mapping[str, str]) -> bytes; default implementation enforces timeouts, bounded retries and provider rate limits.

- [ ] Add tests including the actual policy boundary:

~~~python
def test_robinhood_write_payload_cannot_enter_research():
    import pytest
    from datetime import datetime, timezone
    from research.providers.robinhood import normalize_robinhood_read
    with pytest.raises(ValueError, match="read"):
        normalize_robinhood_read("place_order", b"{}", datetime.now(timezone.utc))
~~~

Also test filing acceptance vs filing date, amended filings, primary document plus exhibit text, missing transcript, FRED revised values hidden before vintage availability, missing API key/contact, malformed HTML/JSON and sanitized logs.
- [ ] Run .venv/bin/python -m pytest tests/research/test_providers.py -q; expect failure.
- [ ] Implement strict read-name validation before normalization and sanitized caching. SEC stores full document text and hashes, not merely XBRL facts. FRED keeps each vintage separately. For date-only availability use a conservative next-session rule, not midnight on the release date.
- [ ] Inject sources into the cache without automatic inference; reuse a daily collected Robinhood snapshot. A model-assisted MCP fetch must consume the same daily budget and not create a second full cycle.
- [ ] Run fixtures offline, then separately attempt permitted read-only provider smoke checks. Report inaccessible providers exactly; fixtures cannot qualify a strategy.
- [ ] Commit “feat: add provenance-aware read-only research sources”.

## Task 5: Pre-registration and deterministic strategy library

**Files:** Create research/registration.py, research/strategies.py, tests/research/test_registration.py, tests/research/test_strategies.py. Reuse risk/engine.py sizing validation; extract a pure shared sizing helper only if necessary.

**Interfaces**
- Consumes as-of total-return data and immutable ResearchConfig.
- parameter_grid() -> dict[str, tuple[dict[str, int | float], ...]].
- freeze_registration(registration: Registration, cache: Cache) -> str.
- momentum_targets(points: Mapping[str, Sequence[TotalReturnPoint]], parameters: Mapping[str, int | float], decision_at: datetime) -> tuple[Target, ...].
- mean_reversion_targets(points: Mapping[str, Sequence[TotalReturnPoint]], state: LedgerState, parameters: Mapping[str, int | float], decision_at: datetime) -> tuple[Target, ...].
- scaled_notional(base: Decimal, target_vol: Decimal, realized_vol: Decimal, position_cap: Decimal, settled_cash: Decimal) -> Decimal.

- [ ] Add grid and sizing tests:

~~~python
def test_declared_grid_is_not_selected_after_results():
    from research.registration import parameter_grid
    grid = parameter_grid()
    assert len(grid["momentum"]) == 9
    assert len(grid["mean_reversion"]) == 9

def test_volatility_scaling_respects_position_cap():
    from decimal import Decimal as D
    from research.strategies import scaled_notional
    assert scaled_notional(D(50), D(".20"), D(".04"), D(125), D(500)) == D(125)
~~~

- [ ] Add ties, negative-momentum cash, 200-day warm-up, exact drop thresholds, monthly rebalance, recovery/hold-limit exits, no repeated entry, no same-close execution, zero/nonfinite volatility and verified closing-without-volatility tests.
- [ ] Run .venv/bin/python -m pytest tests/research/test_registration.py tests/research/test_strategies.py -q; expect failure.
- [ ] Implement the declared Cartesian grids:

~~~python
from itertools import product

def parameter_grid():
    return {
        "momentum": tuple(
            {"lookback": lookback, "top_n": top_n, "trend_ma": 200}
            for lookback, top_n in product((63, 126, 252), (1, 2, 3))
        ),
        "mean_reversion": tuple(
            {"drop": drop, "max_hold": hold, "trend_ma": 200}
            for drop, hold in product((.03, .05, .07), (5, 10, 20))
        ),
    }
~~~

Annualize sample standard deviation of 20 simple daily total returns by sqrt(252), requiring 21 closes. Apply base × target_vol / realized_vol and then every position/cash/risk cap. Rank ties by ticker. Recovery target is the pre-drop close adjusted consistently for intervening corporate actions.
- [ ] Hash the manifest before any fit/test. Record all strategy/ticker/grid/fold attempts and status, including retries. Eighteen parameter combinations are not the total trial count when multiple universes or tickers are tested; report both.
- [ ] Test modified manifests produce linked registrations, reused holdouts stay tainted and failed attempts remain visible. Run Task 5 tests and existing risk tests. Commit “feat: preregister deterministic research strategies”.

## Task 6: Chronological ledger, costs, settlement and taxes

**Files:** Create research/calendar.py, research/ledger.py, tests/research/test_ledger.py, tests/research/test_settlement.py.

**Interfaces**
- Consumes raw MarketBar, CorporateAction, Target, ResearchConfig and existing deterministic risk rules.
- settlement_lag(trade_session: date) -> int; settlement_session(trade_session: date) -> date.
- Ledger(initial_cash: Decimal, config: ResearchConfig); apply_action(action: CorporateAction) -> None; advance(session: date) -> None; execute(target: Target, bar: MarketBar) -> Fill | None; snapshot() -> LedgerState.
- liquidation_equivalent(state: LedgerState, prices: Mapping[str, Decimal], as_of: date) -> Decimal.

- [ ] Pin historical settlement regimes:

~~~python
from datetime import date

def test_settlement_regimes_are_historical_not_today_only():
    from research.calendar import settlement_lag
    assert settlement_lag(date(2008, 9, 15)) == 3
    assert settlement_lag(date(2020, 3, 16)) == 2
    assert settlement_lag(date(2024, 5, 28)) == 1
~~~

- [ ] Add hand-calculated buys/sales/spread/fees, unsettled proceeds rejected, unheld sells blocked before execution, FIFO tax lots, long-term threshold, splits/dividends, no dividend duplication, holiday/weekend settlement and missing-quote-no-fill tests.
- [ ] Run .venv/bin/python -m pytest tests/research/test_ledger.py tests/research/test_settlement.py -q; expect failure.
- [ ] Pre-register initial estimated execution costs of 10 basis points full spread, 5 basis points slippage per fill and $0 fixed commission, with doubled spread/slippage sensitivity. These are modeling assumptions, not measured historical quotes; changes create a linked registration. Use a declared zero risk-free rate for the primary Sharpe estimate and label it; a FRED-derived alternative needs valid vintage data.
- [ ] Implement session-based settlement:

~~~python
def settlement_lag(trade_session):
    from datetime import date
    if trade_session >= date(2024, 5, 28):
        return 1
    if trade_session >= date(2017, 9, 5):
        return 2
    return 3
~~~

Use a verified exchange calendar and separately correct settlement-business-day treatment where it differs; test exceptional closures and settlement holidays. Do not approximate with elapsed calendar days.
- [ ] Implement next-eligible-open fills: buy at raw_open × (1 + half_spread + slippage), sell at raw_open × (1 − half_spread − slippage), plus fees. Apply cash/holding/position/order checks before fills. Record estimated spreads, not observed quotes.
- [ ] Accrue estimated taxes under the configured 35% short-term / 15% long-term assumptions and explicitly report unmodeled loss offsets/wash sales. Model dividends consistently and conservatively; disclose treatment. Use identical accounting assumptions and a common liquidation-equivalent valuation for VTI.
- [ ] Verify wealth reconciliation after every ledger event and after corporate actions; no resets at year boundaries. Run Task 6 and existing paper-broker/risk tests. Commit “feat: add auditable historical cash and tax ledger”.

## Task 7: Walk-forward, crisis coverage, trial audit and metrics

**Files:** Create research/walkforward.py, research/metrics.py, tests/research/test_walkforward.py, tests/research/test_metrics.py.

**Interfaces**
- Consumes Registration, cached data, pure strategies and Ledger.
- walk_forward(registration: Registration, cache: Cache) -> RunResult.
- required_test_years_present(complete_oos_years: set[int]) -> bool.
- calculate_metrics(daily: Sequence[DailyResult], windows: Sequence[tuple[date, date]]) -> Metrics.
- Test factory crisis_registration(cache: Cache, *, missing_year: int | None=None) -> Registration constructs fully synthetic reproducible multi-year prices and known ledger expectations, always fixture=True.

- [ ] Add explicit OOS regime test:

~~~python
def test_training_crash_does_not_count_as_oos_coverage():
    from research.walkforward import required_test_years_present
    assert required_test_years_present({2008, 2020, 2022})
    assert not required_test_years_present({2009, 2020, 2022})
~~~

- [ ] Add full-year session coverage, VTI-gap, warm-up, newer-ticker admission, training-only selection, no boundary capital reset, future-data mutation, untouched-final-holdout and retry/trial-count tests.
- [ ] Run .venv/bin/python -m pytest tests/research/test_walkforward.py tests/research/test_metrics.py -q; expect failure.
- [ ] Implement rolling five-year fit / next one-year test, advancing one year, with after-cost training CAGR selection and tie-breaks lower turnover then stable parameter order. Freeze selected parameters before entering each test; keep one continuous OOS ledger. Monthly rebalances and position exits must not reset at folds.
- [ ] Enforce full calendar-year coverage, not a year-label shortcut:

~~~python
def required_test_years_present(complete_oos_years):
    return {2008, 2020, 2022}.issubset(complete_oos_years)
~~~

Construct complete_oos_years only after every required trading session, VTI mark, training window and warm-up has been validated. Predeclared pooled strategies may admit newly eligible instruments; standalone newer stocks cannot claim missing years.
- [ ] Implement CAGR using elapsed years, signed drawdown equity/running_peak − 1, annualized Sharpe using the declared risk-free rule, summed 0.5 × absolute traded notional / contemporaneous equity, profitable completed-trade fraction, and fraction of test windows beating VTI. Undefined/no-trade/zero-variance metrics return None with reason.
- [ ] Add small hand-computed metric fixtures, append-only MLflow trial records and frozen final-holdout access logs. Validate qualifying runs reject fixture data, tainted holdouts and incomplete coverage. Run Task 7 tests. Commit “feat: evaluate registered strategies out of sample”.

## Task 8: 10,000-path Monte Carlo and understandable risk statements

**Files:** Create research/monte_carlo.py, tests/research/test_monte_carlo.py.

**Interfaces**
- Consumes validated aligned daily net return streams from RunResult.
- paired_bootstrap(strategy_returns: Sequence[float], benchmark_returns: Sequence[float], *, runs: int=10000, horizon: int=252, block: int=20, seed: int) -> MCResult.
- reshuffle_trades(run: RunResult, *, runs: int=10000, seed: int) -> Mapping[str, object].
- risk_summary(result: MCResult) -> str.

- [ ] Add exact-count/equality test:

~~~python
def test_identical_returns_never_strictly_beat_each_other():
    from research.monte_carlo import paired_bootstrap
    result = paired_bootstrap([.001] * 756, [.001] * 756, seed=7)
    assert result.runs == 10000
    assert result.p_beat_vti == 0
    assert result.p_terminal_loss_gt_100 == 0
~~~

- [ ] Add seed replay, identical paired date indexes, bounds, insufficient samples, certain loss, strict >$100 terminal loss, ever-crossed loss, signed fifth-percentile drawdown and no double-cost tests.
- [ ] Run .venv/bin/python -m pytest tests/research/test_monte_carlo.py -q; expect failure.
- [ ] Implement seeded moving-block resampling using the same selected date indexes for both streams. Use non-wrapping contiguous source blocks, truncate concatenated blocks to 252 sessions, and fail if the declared history requirements are unmet. Compound already-net returns from $500.
- [ ] Compute strict terminal_strategy > terminal_VTI, terminal_strategy < 400 and any_path_equity < 400 separately. Report binomial Monte Carlo sampling intervals, not a confidence claim about the market model. Fifth percentile of negative maximum drawdowns is the worse tail.
- [ ] Run 5/20/60-session sensitivity using predeclared seeds; only primary 20-session P drives qualification. Separately reshuffle complete trade episodes through the ledger 10,000 times, preserving duration/internal fills and grouping overlapping episodes. Mark unsupported ledgers explicitly; do not fabricate a probability or average it with bootstrap.
- [ ] Verify shuffled paths cannot borrow unsettled cash and rejected trades are reported. Plain-English output must say “In these simulations…” and “not a forecast guarantee.” Run Task 8 tests. Commit “feat: add paired Monte Carlo and sequencing stress reports”.

## Task 9: Prospective sourced earnings and red-flag signals

**Files:** Create research/events.py, research/event_store.py, prompts/earnings_signal_v1.md, prompts/filing_veto_v1.md, tests/research/test_events.py. Modify daily cycle source-to-agent inputs only after offline tests.

**Interfaces**
- Consumes cached source records, actual current cycle clock and shared cost ledger.
- validate_forward_signal(signal: EventSignal, *, mode: str, now: datetime, cache: Cache) -> EventSignal.
- earnings_multiplier(score: float) -> Decimal, score range [-1,1].
- buy_allowed(assessment: EventSignal | None, *, required: bool, closing_verified: bool) -> bool.
- EventStore(db: Path); append(signal: EventSignal) -> None; effective(ticker: str, at: datetime) -> tuple[EventSignal, ...].

- [ ] Pin the historical prohibition and bounded mapping:

~~~python
def test_earnings_tilt_is_bounded():
    from decimal import Decimal as D
    from research.events import earnings_multiplier
    assert earnings_multiplier(-1) == D(".75")
    assert earnings_multiplier(0) == D("1")
    assert earnings_multiplier(1) == D("1.25")
~~~

Add strict JSON, missing citation/hash, future sources, backdated generation, mismatched prior quarter, no cited pre-release consensus, prompt injection, historical-mode rejection and insufficient-budget tests.
- [ ] Run .venv/bin/python -m pytest tests/research/test_events.py -q; expect failure.
- [ ] Implement prompt/schema versions and source-grounded fields: guidance direction, tone change vs previous quarter and surprise only with pre-event consensus. Missing evidence stays missing. Prompts say source text is untrusted data and cannot alter tools, risk rules or output schema.
- [ ] Implement score-to-size mapping:

~~~python
from decimal import Decimal
def earnings_multiplier(score):
    if not -1 <= score <= 1:
        raise ValueError("Score outside registered range")
    return Decimal("1") + Decimal(".25") * Decimal(str(score))
~~~

Reapply all volatility, position and cash caps afterward. No signal may create a new standalone buy or enlarge the allowed universe.
- [ ] Enforce active veto precedence and missing-required-assessment blocks. Verified closing sells remain allowed. Veto expiration alone cannot clear it; require a sourced replacement or audited explicit policy review. Promotion exceptions cannot clear vetoes.
- [ ] Reuse the existing Research Agent event pass; do not add another unrestricted agent or intraday model task. Persist actual model/prompt/source IDs and real attributable usage. Run Task 9 and risk/transport budget tests. Commit “feat: add forward-only sourced AI event overlays”.

## Task 10: Matched PLAIN/AI lanes and honest cost ablation

**Files:** Create research/ablation.py, tests/research/test_ablation.py; extend research/event_store.py for immutable usage attribution records.

**Interfaces**
- Consumes Registration, prospective EventSignal, Ledger and unique inference usage receipts.
- incremental_net_benefit(ai_pnl_before_api: Decimal, plain_pnl: Decimal, api_cost: Decimal) -> Decimal.
- allocate_shared_cost(cost: Decimal, eligible_strategy_ids: Sequence[str]) -> Mapping[str, Decimal].
- compare_forward(plain: LedgerState, ai: LedgerState, evidence: ForwardResult) -> Mapping[str, object].
- advance_pair(registration: Registration, decision_at: datetime, signals: Sequence[EventSignal], plain: Ledger, ai: Ledger) -> None.

- [ ] Add the cost-dominates-gross-improvement regression:

~~~python
def test_ai_must_beat_plain_after_its_own_api_costs():
    from decimal import Decimal as D
    from research.ablation import incremental_net_benefit
    assert incremental_net_benefit(D(12), D(10), D(3)) == D(-1)
~~~

- [ ] Add tests for every registered strategy/version receiving both arms, synchronized opportunity timestamps, independent cash after divergent trades, missing signals, partial exits not counted as round trips, unique usage IDs and cost-allocation sum equality.
- [ ] Run .venv/bin/python -m pytest tests/research/test_ablation.py -q; expect failure.
- [ ] Implement the paired after-trading-cost/tax comparison:

~~~python
def incremental_net_benefit(ai_pnl_before_api, plain_pnl, api_cost):
    return ai_pnl_before_api - api_cost - plain_pnl
~~~

Charge each actual shared inference once in aggregate, equally across predeclared eligible strategies with deterministic remainder allocation. Report per-strategy allocated cost, standalone full-call cost sensitivity and fully loaded operational-cost sensitivity. Plain/VTI/cash incur zero inference charges.
- [ ] Keep the plain arm research-only: an AI-vetoed hypothetical counterfactual may be recorded for ablation, but can never emit a production executable proposal. Test this boundary with a broker spy that fails on any call.
- [ ] Report gross and net incremental P&L, matched dates, signals, completed positions, missing observations, divergence and uncertainty. Use “insufficient forward evidence” if samples are unavailable/unidentifiable; otherwise clearly qualify “AI adds value” / “AI does not add value” as observed-window results, not statistical proof.
- [ ] Never fabricate historical AI comparisons. AI-underperformance prevents that overlay's promotion, not a independently qualified plain strategy. Run Task 10 and scoreboard tests. Commit “feat: compare every strategy with and without AI after costs”.

## Task 11: Qualification and narrowly scoped exception state machine

**Files:** Create research/qualification.py, research/promotion.py, tests/research/test_qualification.py, tests/research/test_promotion.py. Inspect eval/learning.py and ensure its legacy promotion helper cannot bypass this registry.

**Interfaces**
- Consumes RunResult, MCResult, ForwardResult and actual audit/source records.
- evaluate_qualification(run: RunResult, mc: MCResult, forward: ForwardResult | None, now: datetime, *, ai_overlay: bool) -> Qualification.
- absolute_sample_floor(elapsed: timedelta, completed_round_trips: int) -> bool.
- PromotionStore(db: Path); suggest(qualification: Qualification, now: datetime) -> ExceptionRequest; decide(request_id: str, decision: str, operator_reason: str, now: datetime) -> ExceptionRequest; consume(request_id: str, current: Qualification, now: datetime) -> Qualification.
- Config adds promotion_exception_expiry_hours=168, shadow_min_calendar_months=6, shadow_min_completed_trades=30. Hard floors 56 elapsed days and 15 round trips are code-enforced non-waivable constants; do not add a configuration knob below them.

- [ ] Add the floor boundary test:

~~~python
from datetime import timedelta

def test_both_absolute_floors_are_required():
    from research.qualification import absolute_sample_floor
    assert not absolute_sample_floor(timedelta(days=55, hours=23), 15)
    assert not absolute_sample_floor(timedelta(days=56), 14)
    assert absolute_sample_floor(timedelta(days=56), 15)
~~~

- [ ] Add mandatory gate tests: 59.99% fails, 60% passes only with all other evidence; OOS ties fail; mock/tainted/incomplete data fail; positive forward VTI comparison required; AI overlay must additionally beat matched plain net; version changes restart observation.
- [ ] Run .venv/bin/python -m pytest tests/research/test_qualification.py tests/research/test_promotion.py -q; expect failure.
- [ ] Implement explicit states INELIGIBLE, QUALIFIED_FOR_SHADOW, CONTINUE_SHADOW, READY_FOR_LIVE_REVIEW, READY_FOR_LIVE_REVIEW_WITH_EXCEPTION and REVOKED. Do not add LIVE or brokerage permissions here.

~~~python
from datetime import timedelta
def absolute_sample_floor(elapsed, completed_round_trips):
    return elapsed >= timedelta(days=56) and completed_round_trips >= 15
~~~

Calculate elapsed time from the actual version-specific prospective start. Count unique fully closed position episodes; partial closes, order count and repeated decisions do not increase it. Calendar-month standards use calendar arithmetic, not 180 days.
- [ ] Permit exceptions only for standard observation months/trade count down to the absolute floor. Require explicit YES and substantive editable operator reason. Validate allowed fields, evidence hashes and current safety gates in a SQLite transaction on decision and consumption; single-use consumption is atomic. Relevant evidence/version changes invalidate the request/approval.
- [ ] Add NO, whitespace reason, expired-at-exact-boundary, replay/concurrency, restart, revoked safety state, hash mismatch and attempts to override MC/cash/veto/write-block tests. Every exception path must make zero broker calls.
- [ ] Run Task 11 tests plus Stage 1 regression tests. Commit “feat: gate strategy promotion with non-waivable evidence floors”.

## Task 12: Seven-day promotion cards in the approval inbox

**Files:** Modify agents/inbox_web.py, agents/maintenance.py and config/loader.py/settings.yaml; create prompts/promotion_explanation_v1.md, tests/research/test_promotion_inbox.py. Keep trade-card handlers and tables separate.

**Interfaces**
- Consumes PromotionStore and Qualification.
- promotion_card_view(request: ExceptionRequest, qualification: Qualification) -> Mapping[str, object] in research/promotion.py.
- New local routes GET /research/promotions, POST /research/promotions/suggest, POST /research/promotions/{id}/decision; use existing Host/Origin/CSRF protections and explicit YES/NO plus operator_reason.
- A suggestion writes at most a pending request, never approval; approving a promotion card cannot resolve a trade card.

- [ ] Add seven-day UTC expiry and exact warning assertions:

~~~python
def test_promotion_and_trade_expiry_are_independent():
    from config.loader import AppConfig
    assert AppConfig.model_fields["approval_expiry_minutes"].default == 30
    assert AppConfig.model_fields["promotion_exception_expiry_hours"].default == 168
~~~

Add HTTP tests for no default YES submission, editable reason, NO persistence, expiry across DST, below-floor disabled button AND server-side rejection, stale evidence, HTML escaping, CSRF and restart recovery.
- [ ] Run .venv/bin/python -m pytest tests/research/test_promotion_inbox.py -q; expect failure.
- [ ] Render current/standard/hard-floor sample values, supporting and opposing evidence, AI-vs-plain net result, uncertainty, caveats and suggested WAIT/CONTINUE SHADOW/REQUEST LIMITED EXCEPTION. Include these exact messages:

> This sample is too small to establish reliable performance; an exception does not make the evidence stronger.

> Not eligible for an exception: at least 8 weeks and 15 completed trades are required.

Show the first whenever either standard minimum is unmet, including approved floor-level exceptions. Show the second below either floor and disable approval. Even above standard minima, unidentifiable samples remain “insufficient forward evidence”.
- [ ] Optional AI narration may summarize immutable facts within the existing daily budget; deterministic text works without an AI call. Never preselect or autosubmit approval. Give each card a local trace/evidence link and show “readiness review only; no real trade”.
- [ ] Maintain independent expiry cleanup paths. UI actions create audit records only; they cannot call a broker. Run new HTTP tests and existing inbox tests. Commit “feat: add reasoned seven-day promotion review cards”.

## Task 13: Research commands, local reports and gated schedule integration

**Files:** Create research/reports.py, research/service.py, scripts/research.py, tests/research/test_reporting.py, tests/research/test_integration.py, docs/research-operations.md. Modify agents/daily_cycle.py, agents/maintenance.py and eval/weekly.py only at narrow integration points.

**Interfaces**
- Consumes OperationalProof, registration/cache/run/MC/forward evidence and qualification registry.
- build_report(run: RunResult, mc: MCResult | None, forward: ForwardResult | None) -> str.
- research_daily_step(proof: OperationalProof, decision_at: datetime, *, enabled: bool) -> None.
- CLI subcommands: sources, register, backtest, monte-carlo, report, readiness. They operate on explicit IDs and never infer “latest best” from trial performance.

- [ ] Add report tests for actual ticker coverage, mandatory survivor label, 2008/2020/2022 fold tables, all variants and failures, cost attribution, unavailable historical AI comparison, both probability definitions and clear mock/real provenance.
- [ ] Add an integration test that rejects a failed operations proof before any research work:

~~~python
def test_research_cannot_run_without_operational_gate():
    import pytest
    from types import SimpleNamespace
    from datetime import datetime, timezone
    from research.service import research_daily_step
    invalid = SimpleNamespace(
        background_auth=False, daily_cycle=False, inbox=False,
        agent_only_api_costs=False, closing_checked=False, cash_checked=False,
        real_writes_blocked=False, evidence_valid=False,
    )
    with pytest.raises(ValueError):
        research_daily_step(invalid, datetime.now(timezone.utc), enabled=True)
~~~

- [ ] Run .venv/bin/python -m pytest tests/research/test_reporting.py tests/research/test_integration.py -q; expect failure.
- [ ] Implement a disabled-by-default research configuration. Enabling source/analysis integration does not qualify strategies: the selector reads only qualified registry versions, and labels existing discretionary paper observations separately. New research proposals cannot route around the registry through the legacy path.
- [ ] Integrate one prospective signal pass into the existing 10:00 ET cycle, with no extra full LLM cycle. Keep intraday updates/expiry/settlement code-only. Extend existing weekly scheduling to include research/AI ablation summaries without changing the user's schedule or adding unrequested independent services.
- [ ] Persist experiment/seed/input hashes locally in MLflow and source/decision trace links in Phoenix when available; SQLite remains authoritative if exporters are offline. Trace and report sanitization tests must reject credentials/account identifiers.
- [ ] Document exact commands, provider requirements, blockers, restore/replay behavior, local-only URLs, cost assumptions and no-live-activation boundary. Run daily-cycle, schedule, report and new integration tests. Commit “feat: integrate gated research and forward-value reports”.

## Task 14: Adversarial verification, real-source evidence and handover

**Files:** Create tests/research/test_end_to_end.py and tests/research/test_no_lookahead.py; generate outputs/research-verification.md, outputs/research-test-results.xml, outputs/research-sample-report.md, outputs/sample-promotion-exception-card.md and outputs/research-scoreboard.md during implementation.

**Interfaces**
- Consumes the complete tested research workflow. No new production interface.
- Produces reproducible evidence manifest with code/config/data/registration hashes, test commands and results, coverage, trial counts, costs and exact remaining blockers.

- [ ] Add end-to-end fixture scenarios: qualified plain strategy; OOS failure; MC 59% failure; future-source contamination; missing 2008; insufficient warm-up; missing total-return metadata; AI gross improvement erased by costs; active buy veto; missing required assessment; 55-day/15-trade rejection; 56-day/14-trade rejection; valid floor-level exception still warning; stale/replayed exception; real order attempt blocked.
- [ ] Run .venv/bin/python -m pytest tests/research/test_end_to_end.py tests/research/test_no_lookahead.py -q, observe any failures before fixes and repair only their owning modules.
- [ ] Adversarially append future prices, dividends, filing amendments and macro revisions; every earlier selected parameter, signal and fill must remain byte-identical. Verify an AI forward store cannot be populated by historical replay.
- [ ] Run the full offline suite:

~~~bash
.venv/bin/python -m pytest -q --junitxml=outputs/research-test-results.xml
~~~

- [ ] Run permitted read-only source smoke checks separately. Execute registered real-data deterministic research only if actual coverage/provenance allows it. Perform the primary 10,000-run analysis plus sensitivities and a separately labeled 10,000-run trade reshuffle where supported. Never substitute synthetic passes for unavailable real performance evidence.
- [ ] Re-run Stage 1 real-order blocking after integration, using a transport spy that proves no call escapes. Confirm exceptions do not change allowed tools, stage, broker or runtime permissions.
- [ ] Produce a mocked $500 promotion card labeled MOCK, showing seven-day expiry, editable reason, hard floors, explicit small-sample warning and a working local trace/evidence link. Report a sample scoreboard with inference costs only on AI-using rows and an explicit AI-vs-plain net-benefit column.
- [ ] In the handover, distinguish implemented-and-tested, live-source-verified, awaiting forward observation, and blocked. State that eight weeks and 15 completed trades require genuine time/trades and cannot be manufactured by a test. State whether any strategy actually qualified; “none” is valid.
- [ ] Perform a final code review and preserve all unrelated changes. Commit only intended implementation/report changes with “test: verify research safety and reproducible handover”. Do not enable real trading or infer permission to move money.

## Acceptance matrix

| Requirement | Owning tasks | Evidence required |
|---|---|---|
| Earlier fixes before research | 1, 13 | Fresh operational tests + actual background-cycle receipt; integration refuses invalid proof |
| Read-only Robinhood / prices / SEC full text / FRED | 2–4 | Offline parsers, cache/as-of tests and separately labeled source smoke status |
| Total-return strategies and VTI | 3, 6, 7 | Split/dividend wealth reconciliation, raw-fill separation and benchmark accounting |
| Current mega-caps / bias / actual history | 3, 7, 13 | Frozen universe evidence, repeated bias label, per-ticker coverage |
| Deterministic strategies and sizing | 5, 6 | Fixed grid, known outputs and shared independent risk constraints |
| Registration / variant counts / crisis OOS | 5, 7 | Immutable before-fit manifest, complete trial history, full 2008/2020/2022 test sessions |
| Walk-forward and requested metrics | 6–7 | Training-only selection, continuous ledger, hand-calculated metrics |
| 10,000 simulations and risk language | 8 | Seeded counts, paired paths, separate stress results and probabilities |
| Forward-only AI and veto precedence | 9 | Source validation, historical rejection, safe closes and post-tilt caps |
| Every strategy with/without AI after costs | 10 | Paired prospective accounts, unique actual usage allocation and net increment |
| Seven-day exception cards | 11–12 | 168-hour boundary/DST tests independent of 30-minute trade expiry |
| Eight weeks AND 15 trades even on exception | 11–12 | Boundary, partial-close and server-side rejection tests; visible warning |
| Mandatory gates never overridden | 11, 14 | Attempts to waive data/MC/cash/veto/broker policy rejected |
| Local reporting, tracking and no claims without tests | 13–14 | Fresh test report, source status, trace links and labeled evidence |

## Source and modeling checks for implementation

- Historical settlement changed to T+2 on September 5, 2017: [SEC 2017 implementation notice](https://www.sec.gov/newsroom/press-releases/2017-163). T+1 started May 28, 2024: [SEC T+1 FAQ](https://www.sec.gov/exams/educationhelpguidesfaqs/t1-faq). Verify calendar exceptions rather than applying current settlement to all historical trades.
- SEC submissions APIs do not replace actual full-text filing retrieval: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) and [developer access requirements](https://www.sec.gov/about/developer-resources).
- Historical macro availability requires real-time/vintage periods: [FRED real-time periods](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).
- Provider access and adjustment conventions must be checked at implementation time. This plan does not assert Yahoo/Stooq downloads are currently available or that a provider's generic Close column is verified total return.

## Plan self-review and execution handoff

- Coverage reviewed against all six user amendments and all six research components: mapped above.
- Dependencies reviewed: no research implementation until the operational gate; forward signals never enter historical performance; research activation cannot bypass qualification.
- Type/signature review: shared models are defined once; downstream task APIs reference those contracts; test-only helper fixtures are explicitly defined in their owning tasks.
- Safety review: no automatic live activation; seven-day request expiry is not a standing authorization; immutable absolute floors and current-evidence revalidation apply.
- Deliverable limitations reviewed: planning is not implementation, mocked evidence is not real performance, and minimum counts do not establish statistical significance.

Recommended execution approach: **native implementation in this session**, task by task, with an independent final review if authorized. These tasks share ledger, temporal-data and qualification contracts, so one implementer avoids repeated context/setup costs; the operational gate and each task's tests remain mandatory. A subagent-driven implementation is an alternative with separate task/reviewer contexts and higher review cost.

Pause here for the user's plan review and execution-method choice. Do not begin Task 1 merely because this document has been written.
