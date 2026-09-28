# Agentic Shadow Cycle Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Stage 1 safety scaffold into a usable, bounded agentic shadow cycle with read-only tool use, multi-candidate decisions, relevant lesson retrieval, configurable benchmarks, and run-now/scheduled operation.

**Architecture:** Python retains deterministic orchestration, storage, risk, approvals, scheduling, and the Stage 1 default-deny policy. The OpenAI Agents SDK runs one tool-enabled Research Agent; the Portfolio Agent and separate Critic receive frozen typed inputs and no tools. A fixture adapter proves the complete workflow offline, while host mode requires externally injected authenticated MCP and model adapters and fails closed when either is absent.

**Tech Stack:** Python 3.12+, OpenAI Agents SDK, Pydantic 2, SQLite, pytest, PyYAML, local Phoenix/OpenTelemetry, local MLflow.

**Spec:** `docs/superpowers/specs/2026-09-27-agentic-shadow-cycle-upgrade-design.md`

## Global Constraints

- Stage 1 remains the default and requires the paper broker.
- No Stage 1 code may invoke Robinhood order, cancellation, exercise, scanner/watchlist mutation, transfer, money-moving, or unknown tools.
- The model never receives a broker write tool or a way to construct `LiveUnlock`.
- Robinhood passwords, verification codes, OAuth tokens, and API keys never enter project configuration, command-line arguments, logs, or SQLite.
- Candidate discovery permission and execution whitelist permission remain independent.
- Host mode never substitutes fixture data after authentication, model, tool, schema, freshness, or budget failure.
- All new storage is append-only; existing history is never rewritten or deleted.
- Every production behavior starts with a failing automated test and completes with the whole suite green.
- Real external order and money-moving tools are never called during implementation or verification.

## Review Focus

- Empty or malformed candidate universes must skip honestly rather than defaulting to VTI; Task 1 and Task 3 test this.
- Tool calls with nested or alternate symbol/account arguments must not bypass universe and account validation; Task 3 tests this.
- Partial or stale research must not be described as complete or reach a paper order; Task 5 tests this.
- Restart and schedule catch-up must not duplicate cycles or paper orders; Task 7 tests this.
- Host adapter failure must not fall back to fixture responses or write a successful-cycle status; Task 6 tests this.

---

### Task 1: Configuration, typed decisions, and append-only cycle storage

**Files:**
- Modify: `config/loader.py`
- Modify: `agents/schemas.py`
- Modify: `data/schema.sql`
- Modify: `data/store.py`
- Modify: `config/settings.yaml`
- Test: `tests/test_agentic_config_and_schemas.py`
- Test: `tests/test_store_and_prompts.py`

**Interfaces:**
- Produces: `ResearchConfig`, `EvaluationConfig`, `ScheduleConfig`, `CandidateDiscoveryResult`, `CandidateResearch`, `CandidateResearchBatch`, `RetrievedLesson`, `PortfolioDecision`, and new append-only SQLite tables.
- Consumes: existing `EvidenceItem`, `TradeProposal`, `AppConfig`, and `SQLiteStore`.

- [ ] **Step 1: Write failing configuration tests**

Create `tests/test_agentic_config_and_schemas.py` with literal configurations proving defaults and validation:

```python
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agents.schemas import PortfolioDecision, TradeProposal
from config.loader import AppConfig


BASE = {
    "stage": 1,
    "broker": "paper",
    "starting_cash_usd": "500",
    "model_name": "gpt-test",
    "daily_api_budget_usd": "25",
    "risk": {"agentic_account_id": "999991234"},
}


def test_agentic_defaults_do_not_default_candidate_universe_to_vti() -> None:
    config = AppConfig.model_validate(BASE)
    assert config.research.candidate_symbols == ()
    assert config.research.max_candidates == 5
    assert config.research.max_tool_calls == 18
    assert config.research.max_cycle_api_cost_usd == Decimal("2.50")
    assert config.evaluation.benchmarks == ("VTI", "CASH")
    assert config.schedule.equity_times_et == ("10:00", "14:30")


@pytest.mark.parametrize(
    ("field", "value"),
    [("max_candidates", 0), ("max_tool_calls", 31), ("max_cycle_seconds", 9)],
)
def test_research_limits_are_bounded(field: str, value: int) -> None:
    raw = {**BASE, "research": {field: value}}
    with pytest.raises(ValidationError):
        AppConfig.model_validate(raw)


def test_portfolio_hold_cash_requires_reason_and_forbids_proposal() -> None:
    with pytest.raises(ValidationError):
        PortfolioDecision(action="HOLD_CASH", decline_reason="", compared_symbols=("AAPL",))
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_agentic_config_and_schemas.py`

Expected: import failures for the new configuration and schema types.

- [ ] **Step 3: Implement frozen configuration models**

Add to `config/loader.py`:

```python
class ResearchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_symbols: tuple[str, ...] = ()
    max_candidates: int = Field(default=5, ge=1, le=10)
    max_tool_calls: int = Field(default=18, ge=1, le=30)
    max_cycle_seconds: int = Field(default=180, ge=10, le=900)
    max_tool_result_bytes: int = Field(default=25_000, ge=1_000, le=100_000)
    max_cycle_api_cost_usd: Decimal = Field(default=Decimal("2.50"), gt=0)

    @field_validator("candidate_symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().upper() for item in value if item.strip()))
        if len(normalized) > 100:
            raise ValueError("candidate universe cannot exceed 100 symbols")
        return normalized


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    benchmarks: tuple[str, ...] = ("VTI", "CASH")

    @field_validator("benchmarks")
    @classmethod
    def validate_benchmarks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip().upper() for item in value if item.strip()))
        if not normalized:
            raise ValueError("at least one benchmark is required")
        return normalized


class ScheduleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    equity_times_et: tuple[str, ...] = ("10:00", "14:30")
    crypto_enabled: bool = False
```

Add these members on `AppConfig`:

```python
research: ResearchConfig = Field(default_factory=ResearchConfig)
evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
```

Add an `AppConfig` model validator requiring `research.max_cycle_api_cost_usd <= daily_api_budget_usd`. Add a `ScheduleConfig.equity_times_et` validator that parses every value with `datetime.strptime(value, "%H:%M").time()`, rejects duplicates, and requires every time to be between `time(9, 30)` and `time(16, 0)` inclusive.

- [ ] **Step 4: Implement multi-candidate schemas**

Add to `agents/schemas.py`:

```python
class CandidateDiscoveryResult(StrictModel):
    symbols: tuple[str, ...]
    rejected: dict[str, str] = {}
    as_of: datetime


class CandidateResearch(StrictModel):
    symbol: str
    evidence: tuple[EvidenceItem, ...]
    data_quality: Decimal = Field(ge=0, le=1)
    missing_evidence: tuple[str, ...] = ()
    tool_calls_used: int = Field(ge=0)


class CandidateResearchBatch(StrictModel):
    candidates: tuple[CandidateResearch, ...]
    as_of: datetime
    universe: tuple[str, ...]
    budget_exhausted: bool = False


class RetrievedLesson(StrictModel):
    lesson_id: int
    relevance_reason: str
    thesis: str
    outcome: str
    reasoning_or_luck: str


class PortfolioDecision(StrictModel):
    action: Literal["PROPOSE", "HOLD_CASH"]
    proposal: TradeProposal | None = None
    decline_reason: str | None = None
    compared_symbols: tuple[str, ...]

    @model_validator(mode="after")
    def valid_action_payload(self) -> "PortfolioDecision":
        if self.action == "PROPOSE" and (self.proposal is None or self.decline_reason is not None):
            raise ValueError("PROPOSE requires only a proposal")
        if self.action == "HOLD_CASH" and (self.proposal is not None or not self.decline_reason):
            raise ValueError("HOLD_CASH requires only a decline reason")
        if self.proposal and self.proposal.ticker not in self.compared_symbols:
            raise ValueError("proposal ticker was not compared")
        return self
```

Use tuple default factories instead of mutable class values where Pydantic requires them. Add timezone-aware validators to discovery/batch timestamps.

- [ ] **Step 5: Write failing append-only storage tests**

Extend `tests/test_store_and_prompts.py`:

```python
def test_agentic_cycle_tables_are_append_only(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    for table in (
        "shadow_cycles",
        "tool_calls",
        "candidate_sets",
        "portfolio_decisions",
        "benchmark_values",
    ):
        row_id = store.append_json(table, {"cycle_id": "cycle-1", "status": "recorded"})
        assert row_id == 1
        assert store.read_json(table) == [{"cycle_id": "cycle-1", "status": "recorded"}]


def test_store_can_return_stable_ids_for_lesson_retrieval(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "agent.db")
    lesson_id = store.append_json(
        "lessons",
        {"thesis": "AAPL quality", "outcome": "worked", "reasoning_or_luck": "reasoning"},
    )
    assert store.read_json_with_ids("lessons") == [
        (
            lesson_id,
            {"thesis": "AAPL quality", "outcome": "worked", "reasoning_or_luck": "reasoning"},
        )
    ]
    rows = store.read_json_rows("lessons")
    assert rows[0][0] == lesson_id
    assert datetime.fromisoformat(rows[0][1]).tzinfo is not None
    assert rows[0][2]["thesis"] == "AAPL quality"
```

- [ ] **Step 6: Run the storage test and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_store_and_prompts.py::test_agentic_cycle_tables_are_append_only`

Expected: `ValueError` because the new tables are not registered.

- [ ] **Step 7: Add the append-only tables**

Add the five table names to `REQUIRED_TABLES` and add schema entries using the established `(id, created_at, payload_json)` pattern:

```sql
CREATE TABLE IF NOT EXISTS shadow_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
```

Repeat the same shape for `tool_calls`, `candidate_sets`, `portfolio_decisions`, and `benchmark_values`.

Add the read-only ID/timestamp-preserving API used by deterministic lesson retrieval and persisted daily budgets:

```python
def read_json_rows(self, table: str) -> list[tuple[int, str, dict[str, Any]]]:
    if table not in REQUIRED_TABLES:
        raise ValueError(f"unknown table: {table}")
    with self._connect() as connection:
        rows = connection.execute(
            f"SELECT id, created_at, payload_json FROM {table} ORDER BY id"
        ).fetchall()
    return [
        (int(row["id"]), row["created_at"], json.loads(row["payload_json"]))
        for row in rows
    ]

def read_json_with_ids(self, table: str) -> list[tuple[int, dict[str, Any]]]:
    return [(row_id, payload) for row_id, _created_at, payload in self.read_json_rows(table)]
```

- [ ] **Step 8: Update tracked configuration defaults and run Task 1 tests**

Add explicit `research`, `evaluation`, and `schedule` sections to `config/settings.yaml`. Keep `candidate_symbols: []`, Stage 1, paper broker, and unset tracked account/cash values.

Run: `.venv/bin/python -m pytest -q tests/test_agentic_config_and_schemas.py tests/test_config_and_schemas.py tests/test_store_and_prompts.py`

Expected: all tests pass.

- [ ] **Step 9: Commit Task 1**

```sh
git add config/loader.py config/settings.yaml agents/schemas.py data/schema.sql data/store.py tests/test_agentic_config_and_schemas.py tests/test_store_and_prompts.py
git commit -m "feat: add agentic cycle configuration and schemas"
```

---

### Task 2: Generic passive benchmarks and scoreboard

**Files:**
- Modify: `eval/scoreboard.py`
- Modify: `eval/evaluator.py`
- Modify: `eval/reports.py`
- Modify: `scripts/generate_samples.py`
- Modify: `tests/test_evaluator_and_reports.py`

**Interfaces:**
- Produces: `BenchmarkInput`, `Scoreboard.benchmarks`, and a scoreboard without VTI-specific fields.
- Consumes: configured benchmark symbols and existing agent-track P&L/cost values.

- [ ] **Step 1: Replace VTI-specific test expectations with generic benchmarks**

Update `tests/test_evaluator_and_reports.py` to construct:

```python
BenchmarkInput(name="VTI", gross_pnl=Decimal("200")),
BenchmarkInput(name="CASH", gross_pnl=Decimal("0")),
BenchmarkInput(name="QQQ", gross_pnl=Decimal("250")),
```

Assert the scoreboard has three benchmark lines in that order, `VTI` is not a special attribute, passive benchmarks are not charged AI API cost, and the two agent tracks retain API cost.

- [ ] **Step 2: Run the scoreboard test and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_evaluator_and_reports.py`

Expected: import or constructor failure for `BenchmarkInput`.

- [ ] **Step 3: Implement the generic scoreboard**

Replace `vti_gross_pnl` with:

```python
@dataclass(frozen=True)
class BenchmarkInput:
    name: str
    gross_pnl: Decimal
    non_api_costs: Decimal = Decimal("0")


@dataclass(frozen=True)
class ScoreboardInputs:
    starting_cash: Decimal
    agent_alone_gross_pnl: Decimal
    approved_gross_pnl: Decimal
    agent_alone_non_api_costs: Decimal
    approved_non_api_costs: Decimal
    api_cost: Decimal
    benchmarks: tuple[BenchmarkInput, ...]


@dataclass(frozen=True)
class Scoreboard:
    agent_alone: ScoreboardLine
    with_approvals: ScoreboardLine
    benchmarks: tuple[ScoreboardLine, ...]

    @property
    def lines(self) -> tuple[ScoreboardLine, ...]:
        return (self.agent_alone, self.with_approvals, *self.benchmarks)
```

Use zero API cost when building passive benchmark lines. Reject duplicate or blank benchmark names.

- [ ] **Step 4: Update sample/report callers**

Pass `benchmarks=(BenchmarkInput("VTI", Decimal("200")), BenchmarkInput("CASH", Decimal("0")))` from sample generation. Make report rendering iterate over `scoreboard.lines`; do not branch on VTI.

- [ ] **Step 5: Run Task 2 tests**

Run: `.venv/bin/python -m pytest -q tests/test_evaluator_and_reports.py`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 2**

```sh
git add eval/scoreboard.py eval/evaluator.py eval/reports.py scripts/generate_samples.py tests/test_evaluator_and_reports.py
git commit -m "feat: make passive benchmarks configurable"
```

---

### Task 3: Bounded read-only research gateway

**Files:**
- Create: `agents/research_tools.py`
- Modify: `broker/policy.py`
- Test: `tests/test_research_tools.py`
- Test: `tests/test_stage1_robinhood_policy.py`

**Interfaces:**
- Produces: `ResearchToolBudget`, `ResearchToolCall`, `ResearchToolGateway.call(tool_name, arguments)`, and `ResearchToolError`.
- Consumes: `RobinhoodBroker`, `SQLiteStore`, configured account/universe, cycle ID, clock, call/result/deadline limits.

- [ ] **Step 1: Write failing gateway tests**

Create `tests/test_research_tools.py` using a recording invoker. Cover:

```python
def test_gateway_allows_read_for_universe_symbol_and_records_ledger(tmp_path: Path) -> None:
    result = gateway.call("get_equity_quotes", {"symbols": ["AAPL"]})
    assert result["data"]["quotes"][0]["symbol"] == "AAPL"
    assert invoker.calls == [("get_equity_quotes", {"symbols": ["AAPL"]})]
    assert store.read_json("tool_calls")[0]["outcome"] == "ok"


@pytest.mark.parametrize(
    "tool_name",
    ["place_equity_order", "cancel_equity_order", "exercise_option", "move_money_new_tool"],
)
def test_gateway_blocks_writes_before_invoker(tool_name: str) -> None:
    with pytest.raises(BrokerError):
        gateway.call(tool_name, {"symbol": "AAPL"})
    assert invoker.calls == []
```

Also add literal tests for `symbol`, `symbols`, `underlying_symbol`, nested filters containing tickers, wrong `account_number`, a 19th call under an 18-call budget, expired deadline, an oversized result list that is truncated at a complete item boundary, and one oversized scalar item that fails closed.

- [ ] **Step 2: Run gateway tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_research_tools.py`

Expected: import failure for `agents.research_tools`.

- [ ] **Step 3: Implement budgets and validated invocation**

Create:

```python
@dataclass
class ResearchToolBudget:
    max_calls: int
    deadline: datetime
    max_result_bytes: int
    calls_used: int = 0


class ResearchToolGateway:
    def __init__(
        self,
        broker: RobinhoodBroker,
        store: SQLiteStore,
        *,
        cycle_id: str,
        account_id: str,
        universe: frozenset[str],
        holdings: frozenset[str],
        allowed_tools: frozenset[str],
        budget: ResearchToolBudget,
        now: Callable[[], datetime],
    ) -> None:
        self.broker = broker
        self.store = store
        self.cycle_id = cycle_id
        self.account_id = account_id
        self.permitted_symbols = universe | holdings
        self.allowed_tools = allowed_tools
        self.budget = budget
        self.now = now

    def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        normalized = normalize_robinhood_tool_name(tool_name)
        if normalized not in self.allowed_tools:
            self._record(normalized, arguments, "blocked_capability", 0)
            raise BrokerError(f"research capability blocked: {normalized}")
        self._validate_arguments(arguments)
        if self.now() > self.budget.deadline:
            self._record(normalized, arguments, "deadline_exhausted", 0)
            raise ResearchToolError("research deadline exhausted")
        if self.budget.calls_used >= self.budget.max_calls:
            self._record(normalized, arguments, "call_budget_exhausted", 0)
            raise ResearchToolError("research tool-call budget exhausted")
        self.budget.calls_used += 1
        result = self.broker.call_tool(normalized, arguments)
        if not isinstance(result, dict):
            self._record(normalized, arguments, "invalid_result", 0)
            raise ResearchToolError("research tool result must be an object")
        bounded, truncated = bound_complete_items(result, self.budget.max_result_bytes)
        encoded = json.dumps(bounded, sort_keys=True, default=str).encode()
        outcome = "ok_truncated" if truncated else "ok"
        self._record(normalized, arguments, outcome, len(encoded))
        return bounded

    def _validate_arguments(self, value: Any, key: str = "") -> None:
        symbol_keys = {"symbol", "symbols", "ticker", "tickers", "underlying_symbol"}
        account_keys = {"account_number", "rhs_account_number"}
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                self._validate_arguments(child_value, child_key)
            return
        if isinstance(value, list):
            for child in value:
                self._validate_arguments(child, key)
            return
        if key in symbol_keys and isinstance(value, str):
            if value.strip().upper() not in self.permitted_symbols:
                raise ResearchToolError(f"symbol outside research universe: {value}")
        if key in account_keys and value != self.account_id:
            raise ResearchToolError("research tool account does not match Agentic account")

    def _record(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        outcome: str,
        result_bytes: int,
    ) -> None:
        argument_keys = tuple(sorted(arguments))
        self.store.append_json(
            "tool_calls",
            {
                "cycle_id": self.cycle_id,
                "tool_name": tool_name,
                "argument_keys": argument_keys,
                "outcome": outcome,
                "result_bytes": result_bytes,
            },
        )
```

Implement `bound_complete_items(result, limit)` by deep-copying the result, removing the optional top-level `guide` field first, then binary-searching a prefix of the first list found under `data.results`, `data.positions`, `data.chains`, `data.filings`, `data.instruments`, or `data.indicators`. Preserve every retained item unchanged and add `{"_truncated": true}` at the top level. If no complete item can fit, raise `ResearchToolError("research tool result exceeded byte limit")`.

Normalize tool names first. Call the broker policy before any argument or budget result can reach the invoker. Recursively inspect keys named `symbol`, `symbols`, `ticker`, `tickers`, and `underlying_symbol`; require values to be in `universe | holdings`. Require every account-shaped argument to equal `account_id`. Serialize with deterministic JSON and reject results larger than `max_result_bytes`. Append a redacted ledger record for both successes and failures.

- [ ] **Step 4: Add the narrower research capability set**

Define `RESEARCH_TOOL_ALLOWLIST` in `agents/research_tools.py` as the exact subset listed by the design. Assert it is a subset of `READ_ONLY_TOOL_ALLOWLIST` at import time. Do not add writes to `broker/policy.py`; only expose any missing read-only tool already verified in the MCP inventory.

- [ ] **Step 5: Run Task 3 tests plus the original real-write block tests**

Run: `.venv/bin/python -m pytest -q tests/test_research_tools.py tests/test_stage1_robinhood_policy.py`

Expected: all tests pass and recording invokers remain empty for every write/unknown case.

- [ ] **Step 6: Commit Task 3**

```sh
git add agents/research_tools.py broker/policy.py tests/test_research_tools.py tests/test_stage1_robinhood_policy.py
git commit -m "feat: add bounded read-only research gateway"
```

---

### Task 4: Tool-enabled Research Agent and versioned prompts

**Files:**
- Modify: `agents/definitions.py`
- Modify: `agents/workflow.py`
- Create: `prompts/research_v2.md`
- Create: `prompts/portfolio_v2.md`
- Create: `prompts/critic_v2.md`
- Modify: `prompts/registry.py`
- Test: `tests/test_agentic_agent_definitions.py`
- Modify: `tests/test_agents_and_approval.py`

**Interfaces:**
- Produces: `build_research_function_tools(gateway)`, tool-enabled `build_agents`, and bounded `OpenAIAgentsSDKRunner(max_turns: int)`.
- Consumes: `ResearchToolGateway`, the new schemas, and existing local tracing.

- [ ] **Step 1: Write failing agent-definition tests**

Create `tests/test_agentic_agent_definitions.py`:

```python
def test_only_research_agent_receives_tools(registry: PromptRegistry, gateway: ResearchToolGateway) -> None:
    tools = build_research_function_tools(gateway)
    bundle = build_agents(registry, model_name="gpt-test", research_tools=tools, prompt_version="v2")
    assert {tool.name for tool in bundle.research.tools} == {
        "discover_candidates",
        "research_equity",
        "research_sec_filings",
        "research_earnings",
        "research_options",
        "research_crypto",
        "get_portfolio_context",
    }
    assert bundle.portfolio.tools == []
    assert bundle.critic.tools == []
```

Add a test proving `OpenAIAgentsSDKRunner(max_turns=7)` passes `max_turns=7` to its injected runner function.

- [ ] **Step 2: Run the tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_agentic_agent_definitions.py`

Expected: missing builder/signature failures.

- [ ] **Step 3: Build seven typed function tools**

In `agents/research_tools.py`, define `build_research_function_tools(gateway)` using `agents.tool.function_tool`. Each tool accepts narrow typed arguments and delegates only to the gateway. For example:

```python
@function_tool
def research_equity(
    symbol: str,
    start_time: str,
    end_time: str,
    evidence: list[Literal["quote", "history", "rsi", "fundamentals", "financials", "ratings"]],
) -> str:
    """Collect selected point-in-time equity evidence for one candidate."""
    results = {}
    mapping = {
        "quote": "get_equity_quotes",
        "fundamentals": "get_equity_fundamentals",
        "financials": "get_financials",
        "ratings": "get_equity_analyst_ratings",
    }
    for item in evidence:
        if item == "history":
            results[item] = gateway.call(
                "get_equity_historicals",
                {
                    "symbols": [symbol],
                    "start_time": start_time,
                    "end_time": end_time,
                    "interval": "day",
                    "bounds": "regular",
                    "adjustment_type": "split",
                },
            )
        elif item == "rsi":
            results[item] = gateway.call(
                "get_equity_technical_indicators",
                {
                    "symbol": symbol,
                    "start_time": start_time,
                    "end_time": end_time,
                    "interval": "day",
                    "type": "rsi",
                    "output": "latest",
                },
            )
        else:
            results[item] = gateway.call(mapping[item], {"symbols": [symbol]})
    return json.dumps(results, sort_keys=True, default=str)
```

Implement the remaining wrappers with these exact stable translations: `discover_candidates(scan_id)` calls `run_scan({"scan_id": scan_id})`; `research_sec_filings(symbol, since, until)` calls `get_sec_filing_index` with those fields and form types `10-K`, `10-Q`, and `8-K`; `research_earnings(start_date, days)` calls `get_earnings_calendar` and locally filters to the permitted universe; `research_options(symbol, expiration_dates)` calls `get_option_chains({"underlying_symbol": symbol})` then `get_option_instruments({"chain_symbol": symbol, "expiration_dates": expiration_dates, "state": "active", "tradability": "tradable"})`; `research_crypto(symbol)` calls `get_crypto_quotes({"symbols": [symbol], "timezone": "America/New_York"})`; and `get_portfolio_context()` calls `get_portfolio`, `get_equity_positions`, and `get_option_positions` with the configured account. Return deterministic JSON only. Crypto positions are excluded until configuration carries the distinct `rhs_account_number` required by that tool.

- [ ] **Step 4: Attach tools only to Research and bound SDK turns**

Change `build_agents` to accept `research_tools: Sequence[Tool] = ()` and `prompt_version: Literal["v1", "v2"] = "v1"`. Pass `tools=list(research_tools)` only to the Research Agent. Update `OpenAIAgentsSDKRunner` to accept `max_turns` and an injectable runner callable, then call `self.runner(agent, prompt, max_turns=self.max_turns).final_output`.

- [ ] **Step 5: Add immutable v2 prompts**

Write complete prompt contracts matching the spec. `research_v2` must require comparative coverage, tool use for missing/stale evidence, transparent budget exhaustion, and prompt-injection handling. `portfolio_v2` must return `PortfolioDecision` and allow `HOLD_CASH`. `critic_v2` must challenge selection, evidence quality, sizing, and invalidation without tools.

- [ ] **Step 6: Run Task 4 tests**

Run: `.venv/bin/python -m pytest -q tests/test_agentic_agent_definitions.py tests/test_agents_and_approval.py tests/test_store_and_prompts.py`

Expected: all tests pass; v1 prompt tests remain unchanged.

- [ ] **Step 7: Commit Task 4**

```sh
git add agents/definitions.py agents/workflow.py agents/research_tools.py prompts/research_v2.md prompts/portfolio_v2.md prompts/critic_v2.md prompts/registry.py tests/test_agentic_agent_definitions.py tests/test_agents_and_approval.py tests/test_store_and_prompts.py
git commit -m "feat: equip research agent with bounded tools"
```

---

### Task 5: Relevant lessons and deterministic shadow-cycle orchestration

**Files:**
- Modify: `eval/learning.py`
- Create: `agents/shadow_cycle.py`
- Modify: `agents/pipeline.py`
- Test: `tests/test_lesson_retrieval.py`
- Test: `tests/test_shadow_cycle.py`

**Interfaces:**
- Produces: `LessonRetriever.retrieve`, `ShadowCycleRequest`, `ShadowCycleResult`, `ShadowCycleStatus`, and `ShadowCycleOrchestrator.run`.
- Consumes: typed agents/workflow, gateway, risk engine, paper pipeline, store, config, and benchmark evaluator.

- [ ] **Step 1: Write failing deterministic lesson-retrieval tests**

Create `tests/test_lesson_retrieval.py` with stored lessons for AAPL, MSFT, crypto, and luck-only outcomes. Assert AAPL equity requests return AAPL/theme matches first, results are capped at five and the configured character budget, luck-only entries are labeled negative examples, and retrieval performs no writes.

- [ ] **Step 2: Run lesson tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_lesson_retrieval.py`

Expected: import failure for `LessonRetriever`.

- [ ] **Step 3: Implement deterministic lesson retrieval**

Add:

```python
class LessonRetriever:
    def __init__(self, store: SQLiteStore, *, limit: int = 5, max_characters: int = 4_000) -> None:
        self.store = store
        self.limit = limit
        self.max_characters = max_characters

    def retrieve(
        self,
        *,
        symbols: tuple[str, ...],
        asset_classes: tuple[str, ...],
        horizon_days: int,
        themes: tuple[str, ...],
    ) -> tuple[RetrievedLesson, ...]:
        query = {item.casefold() for item in (*symbols, *asset_classes, *themes)}
        ranked = []
        for lesson_id, payload in self.store.read_json_with_ids("lessons"):
            text = " ".join(str(value) for value in payload.values()).casefold()
            score = sum(4 for symbol in symbols if symbol.casefold() in text)
            score += sum(2 for item in (*asset_classes, *themes) if item.casefold() in text)
            if not query or score:
                ranked.append((score, lesson_id, payload))
        ranked.sort(key=lambda item: (-item[0], -item[1]))
        selected = []
        characters = 0
        for score, lesson_id, payload in ranked:
            relevance = "exact symbol or theme overlap" if score else "recent general lesson"
            lesson = RetrievedLesson(lesson_id=lesson_id, relevance_reason=relevance, **payload)
            size = len(lesson.model_dump_json())
            if len(selected) == self.limit or characters + size > self.max_characters:
                break
            selected.append(lesson)
            characters += size
        return tuple(selected)
```

Score exact symbol matches above asset/theme overlap, then recency. Break ties by SQLite insertion order. Return immutable typed copies; never update lesson rows.

- [ ] **Step 4: Write failing complete-cycle and hold-cash tests**

Create `tests/test_shadow_cycle.py`. Use real config, store, risk engine, paper brokers, gateway, and deterministic fake runners/adapters. Assert:

- a two-candidate fixture cycle researches both, retrieves a lesson, produces one proposal, runs the critic, creates an approval card, records two paper-track fills, benchmark values, tool ledger, and `COMPLETED` cycle status;
- a `HOLD_CASH` decision persists a portfolio decision but produces zero critic calls, risk submissions, cards, orders, or fills;
- a proposal for an unresearched symbol fails before the risk engine;
- future-dated evidence and stale quotes fail closed;
- budget-exhausted partial research is marked incomplete and cannot be represented as full coverage.
- a daily API budget with insufficient remaining allowance returns a terminal skip before the model runner is called.
- API costs recorded earlier on the same UTC date still count after constructing a new orchestrator, while prior-date costs do not.

- [ ] **Step 5: Run cycle tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_shadow_cycle.py`

Expected: import failure for `agents.shadow_cycle`.

- [ ] **Step 6: Implement the orchestrator state machine**

Create enums and types:

```python
class ShadowCycleStatus(StrEnum):
    STARTED = "STARTED"
    SKIPPED_NO_UNIVERSE = "SKIPPED_NO_UNIVERSE"
    SKIPPED_AUTH = "SKIPPED_AUTH"
    SKIPPED_NO_MODEL = "SKIPPED_NO_MODEL"
    FAILED_RESEARCH_VALIDATION = "FAILED_RESEARCH_VALIDATION"
    HOLD_CASH = "HOLD_CASH"
    RISK_BLOCKED = "RISK_BLOCKED"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class ShadowCycleRequest:
    cycle_id: str
    as_of: datetime
    human_decision: Literal["YES", "NO"] | None
    mode: Literal["fixture", "host"]


@dataclass(frozen=True)
class ShadowCycleResult:
    cycle_id: str
    status: ShadowCycleStatus
    decision: PortfolioDecision | None
    pipeline: PipelineResult | None
    trace_id: str
```

Implement the exact ten-step sequence in the design. Reconstruct `DailyBudget.spent_usd` from `store.read_json_rows("api_costs")` rows whose `created_at` date equals the cycle's UTC date. Call `DailyBudget.can_spend(config.research.max_cycle_api_cost_usd)` before invoking the model, and record actual model costs after each agent step. Persist a `STARTED` row before external work and one terminal row on every return path. Never catch `BrokerError` and continue toward a proposal.

- [ ] **Step 7: Run Task 5 tests**

Run: `.venv/bin/python -m pytest -q tests/test_lesson_retrieval.py tests/test_shadow_cycle.py tests/test_stage1_pipeline.py`

Expected: all tests pass.

- [ ] **Step 8: Commit Task 5**

```sh
git add eval/learning.py agents/shadow_cycle.py agents/pipeline.py tests/test_lesson_retrieval.py tests/test_shadow_cycle.py
git commit -m "feat: orchestrate multi-candidate shadow cycles"
```

---

### Task 6: Fixture adapters and usable run-now command

**Files:**
- Create: `agents/adapters.py`
- Create: `scripts/shadow_cycle.py`
- Create: `tests/fixtures/agentic_cycle_mcp.json`
- Create: `tests/fixtures/agentic_cycle_models.json`
- Test: `tests/test_shadow_cycle_cli.py`
- Modify: `README.md`

**Interfaces:**
- Produces: `FixtureMCPInvoker`, `FixtureModelRunner`, `HostAdapters`, `build_fixture_cycle`, and CLI `python -m scripts.shadow_cycle`.
- Consumes: `ShadowCycleOrchestrator`, local config, and SQLite.

- [ ] **Step 1: Write failing CLI integration tests**

Create `tests/test_shadow_cycle_cli.py` that invokes `main([...])` directly with temporary config/database/output paths. Assert fixture mode exits 0, prints `DATA MODE: FIXTURE`, writes a terminal cycle and report, and never instantiates `RobinhoodBroker` with an external invoker. Assert host mode without adapters exits non-zero, prints exactly one missing-adapter message, writes `SKIPPED_AUTH` or `SKIPPED_NO_MODEL`, and does not read fixture files.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_shadow_cycle_cli.py`

Expected: import failure for `scripts.shadow_cycle`.

- [ ] **Step 3: Add complete immutable fixture data**

Create JSON fixtures with two symbols, complete quote/fundamental/technical/filing/earnings responses, one prompt-injection string flagged as data, a portfolio response, a research batch, portfolio decision, and critic response. Use clearly fictional timestamps/prices and `fixture://` provenance. Include all fields documented by the corresponding MCP schemas, not partial mocks.

- [ ] **Step 4: Implement fixture and host adapter boundaries**

`FixtureMCPInvoker` must reject any tool/argument pair absent from the fixture rather than returning a generic success. `FixtureModelRunner` must consume responses in a declared agent order and reject unexpected calls. `HostAdapters` contains optional `mcp_invoker` and `model_runner`; its validation returns a typed skip reason rather than loading fixtures.

- [ ] **Step 5: Implement the run-now CLI**

Support only:

```text
--mode fixture|host
--config PATH
--database PATH
--output PATH
--human-decision YES|NO
```

Do not define token, password, verification-code, API-key, or OAuth arguments. Print data mode, cycle ID, terminal status, proposal/hold reason, risk status, paper fills, costs, benchmarks, and local trace URL. Exit non-zero for host adapter absence and safety failures.

- [ ] **Step 6: Document exact use and boundaries**

Add README commands for fixture mode and explain that host mode is an embedding API, not a promise that a standalone shell inherits Codex OAuth. State that fixture results are installation proof, not market research.

- [ ] **Step 7: Run Task 6 tests and a real fixture command**

Run: `.venv/bin/python -m pytest -q tests/test_shadow_cycle_cli.py`

Run: `.venv/bin/python -m scripts.shadow_cycle --mode fixture --config config/settings.local.yaml --database data/fixture-cycle.db --output outputs/latest-fixture-cycle.md --human-decision NO`

Expected: tests pass; command exits 0; output begins with `DATA MODE: FIXTURE`; no Robinhood network write occurs.

- [ ] **Step 8: Commit Task 6**

```sh
git add agents/adapters.py scripts/shadow_cycle.py tests/fixtures/agentic_cycle_mcp.json tests/fixtures/agentic_cycle_models.json tests/test_shadow_cycle_cli.py README.md
git commit -m "feat: add runnable fixture shadow cycle"
```

---

### Task 7: Idempotent scheduled cycles

**Files:**
- Modify: `agents/operator.py`
- Modify: `config/com.openai.robinhood-shadow.plist.example`
- Test: `tests/test_observability_and_operation.py`

**Interfaces:**
- Produces: `ScheduledCycle`, `CycleScheduler.due`, `CycleScheduler.reserve`, and operator integration that invokes a provided cycle callable.
- Consumes: `MarketSchedule`, local configuration, SQLite `run_states`/`shadow_cycles`, and the shadow-cycle entry point.

- [ ] **Step 1: Write failing scheduler tests**

Add tests proving:

- 10:00 and 14:30 ET equity cycles become due once on valid NYSE days;
- weekends and regular holidays produce no equity cycle;
- restart at 10:07 catches up the 10:00 cycle once;
- restart after the later slot does not replay both missed cycles;
- an existing `(strategy_version, scheduled_at)` reservation suppresses duplicates;
- crypto outside equity hours runs only when `crypto_enabled=true`;
- absent host adapters record a skip and do not invoke fixture mode.

- [ ] **Step 2: Run scheduler tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_observability_and_operation.py`

Expected: import failure for `CycleScheduler` or failing due-cycle assertions.

- [ ] **Step 3: Implement reservation-first scheduling**

Add:

```python
@dataclass(frozen=True)
class ScheduledCycle:
    scheduled_at: datetime
    asset_class: Literal["stock", "crypto"]
    idempotency_key: str


class CycleScheduler:
    def __init__(self, store: SQLiteStore, market_schedule: MarketSchedule | None = None) -> None:
        self.store = store
        self.market_schedule = market_schedule or MarketSchedule()
        self.eastern = ZoneInfo("America/New_York")

    def due(self, moment: datetime, config: AppConfig, strategy_version: str) -> ScheduledCycle | None:
        local = moment.astimezone(self.eastern)
        if not self.market_schedule.should_run(local, asset_class="stock", stage=config.stage):
            return None
        candidates = []
        for value in config.schedule.equity_times_et:
            hour, minute = (int(part) for part in value.split(":"))
            scheduled = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if scheduled <= local <= scheduled + timedelta(minutes=30):
                candidates.append(scheduled)
        if not candidates:
            return None
        scheduled = max(candidates)
        key = f"{strategy_version}:{scheduled.isoformat()}:stock"
        if any(row.get("idempotency_key") == key for row in self.store.read_json("run_states")):
            return None
        return ScheduledCycle(scheduled, "stock", key)

    def reserve(self, cycle: ScheduledCycle) -> bool:
        if any(
            row.get("idempotency_key") == cycle.idempotency_key
            for row in self.store.read_json("run_states")
        ):
            return False
        self.store.append_json(
            "run_states",
            {
                "status": "cycle_reserved",
                "scheduled_at": cycle.scheduled_at.isoformat(),
                "asset_class": cycle.asset_class,
                "idempotency_key": cycle.idempotency_key,
            },
        )
        return True
```

Reserve before calling the cycle runner. Persist the key in `run_states`. Catch up only the most recent eligible slot within 30 minutes. Keep heartbeat writes separate from cycle terminal states.

- [ ] **Step 4: Wire the operator without granting credentials**

Add optional `--run-cycles` and dependency-injected `cycle_callable`. Default local launchd behavior keeps cycles disabled until configuration and host adapters are available. Never add credentials to the plist. Update the template arguments only for safe configuration/database paths and interval.

- [ ] **Step 5: Run Task 7 tests**

Run: `.venv/bin/python -m pytest -q tests/test_observability_and_operation.py tests/test_shadow_cycle.py`

Expected: all tests pass.

- [ ] **Step 6: Commit Task 7**

```sh
git add agents/operator.py config/com.openai.robinhood-shadow.plist.example tests/test_observability_and_operation.py
git commit -m "feat: schedule idempotent shadow cycles"
```

---

### Task 8: Golden scenarios, reports, samples, and final activation gates

**Files:**
- Modify: `tests/fixtures/golden_scenarios.yaml`
- Modify: `eval/golden.py`
- Modify: `eval/reports.py`
- Modify: `scripts/regression_gate.py`
- Modify: `scripts/generate_samples.py`
- Modify: `reports/strategy_plan.md`
- Modify: `outputs/first-deliverable.md`
- Modify: `outputs/sample_approval_card.md`
- Modify: `outputs/sample_scoreboard.md`
- Test: `tests/test_golden_scenarios.py`
- Test: `tests/test_regression_gate.py`
- Test: `tests/test_evaluator_and_reports.py`

**Interfaces:**
- Produces: expanded golden gate, agentic weekly reporting, updated samples, and final evidence package.
- Consumes: completed cycle/tool/decision/benchmark records.

- [ ] **Step 1: Write failing golden/report tests**

Add named golden cases for empty universe, out-of-universe scanner result, conflicting evidence, incomplete candidate coverage, tool-budget exhaustion, prompt injection in tool output, cross-candidate selection, explicit hold cash, proposal for unresearched symbol, missing host adapters, and varied AAPL/MSFT/QQQ/BTC/option cases. Assert the weekly report includes completed/held/risk-blocked/failed counts, tool usage, budget exhaustion, missing evidence, symbol/asset breakdowns, and generic benchmark rows.

- [ ] **Step 2: Run the affected tests and verify RED**

Run: `.venv/bin/python -m pytest -q tests/test_golden_scenarios.py tests/test_regression_gate.py tests/test_evaluator_and_reports.py`

Expected: new scenario handlers/report fields are missing.

- [ ] **Step 3: Expand the golden runner and mandatory regression gate**

Teach `eval/golden.py` to construct the new discovery, tool-budget, research-batch, decision, and host-adapter contexts. Keep literal expected outcomes in YAML. Update `scripts/regression_gate.py` so the mandatory gate includes the original risk suite, original 24 cases, and every new agentic case.

- [ ] **Step 4: Extend weekly reporting and sample generation**

Render the new operational metrics from append-only records. Generate sample approval/scoreboard output using a non-VTI proposal while retaining VTI and cash as labeled passive benchmarks. State `DATA MODE: FIXTURE` and API costs prominently.

- [ ] **Step 5: Update the strategy plan and first deliverable**

Document that candidate selection is multi-symbol, VTI is only a benchmark, Research has bounded tools, HOLD CASH is first-class, and host authentication remains injected. Update Sections 1–8 status only for functionality proven by tests; do not claim live autonomous MCP research.

- [ ] **Step 6: Run complete verification**

Run each command separately and require exit code 0:

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m scripts.regression_gate
.venv/bin/python -m ruff check .
.venv/bin/python -m compileall -q agents broker config data eval prompts risk scripts tests
git diff --check
plutil -lint config/com.openai.robinhood-shadow.plist.example config/com.openai.robinhood-phoenix.plist.example
.venv/bin/python -m scripts.shadow_cycle --mode fixture --config config/settings.local.yaml --database data/fixture-cycle.db --output outputs/latest-fixture-cycle.md --human-decision NO
```

Additionally search tracked files for the real account identifiers observed during activation and require no matches. Verify the Stage 1 write-block test names real order/cancel/exercise tools and proves the invoker call log is empty.

- [ ] **Step 7: Restart and verify only safe local services**

Restart the shadow supervisor after tests pass. Verify its latest heartbeat reports Stage 1, paper, and live execution blocked. Verify Phoenix listens only on `127.0.0.1:6006`. Do not enable scheduled host cycles unless an authenticated host adapter actually exists and three manual host cycles have passed.

- [ ] **Step 8: Request final code review and fix Critical/Important findings**

Use `superpowers:requesting-code-review` with the base commit and final head. Apply every valid Critical/Important finding with a new red-green test, then repeat Step 6.

- [ ] **Step 9: Commit Task 8**

```sh
git add tests/fixtures/golden_scenarios.yaml eval/golden.py eval/reports.py scripts/regression_gate.py scripts/generate_samples.py reports/strategy_plan.md outputs/first-deliverable.md outputs/sample_approval_card.md outputs/sample_scoreboard.md tests/test_golden_scenarios.py tests/test_regression_gate.py tests/test_evaluator_and_reports.py
git commit -m "feat: complete agentic shadow cycle evaluation"
```
