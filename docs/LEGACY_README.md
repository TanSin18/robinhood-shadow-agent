# Robinhood AI Shadow Agent

This local project implements Sections 1–8 of the v4 Stage 1 shadow-mode trading-agent specification. It is research and evaluation software, not a promise of returns.

## Safety state

- `config/settings.yaml` defaults to Stage 1 and the paper broker.
- Robinhood MCP access uses an exact read-only allowlist. Every write and every unknown future tool is denied before invocation.
- A future live write requires a separate Stage 2 configuration, a manually created unlock, and a matching per-order approval ID. No auto-approve route exists.
- The deterministic Python risk engine is upstream of every broker submission.
- No password or verification code belongs in this project. The application never asks for either.

## Local setup

Python 3.12 or later is required. Create an isolated environment and install the project with development and local-observability dependencies:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,observability]'
```

Copy `config/settings.yaml` to the ignored `config/settings.local.yaml` and set two non-secret values before starting a shadow run:

1. `starting_cash_usd`: the paper account's starting cash.
2. `risk.agentic_account_id`: the dedicated Agentic account identifier.

The code-only market reader connects to Robinhood's official Trading MCP at `https://agent.robinhood.com/mcp/trading` through a dedicated authenticated Codex app-server child. Python never copies OAuth tokens. Exactly eight read tools are accepted after checking the same session's effective inventory and pinned input schemas. Model sessions are separate: they receive snapshots, have zero MCP tools, and cannot call the reader. App-server remote access is disabled for each ephemeral child. News is currently disabled; the research output must disclose that limitation.

## Daily operation and current readiness

Keep the safety pause until the repaired runtime is explicitly activated. Passing tests and a read-only connectivity check do **not** prove a scheduled three-agent run. Check `outputs/operational-readiness.md` for the evidence gates and the local dashboard at http://127.0.0.1:8765/ for actual state.

- One scheduled attempt begins at 10:00 AM Eastern on exchange trading days. A delayed wake may start before 10:20 AM, never at or after 10:20. Calendar triggers use the Mac's local timezone; the periodic code-only Eastern-time guard is authoritative.
- Research uses the configured cheap model; Portfolio and Critic use their separate stronger-model settings. The daily ledger limits estimated API-equivalent usage to $0.40 in reservations. Unknown interrupted-call usage remains reserved. Estimates are not an invoice or absolute provider-spending guarantee.
- Python fetches fresh quotes after the three model stages. No fourth AI call is used for refresh. Stale data or insufficient budget saves the reasoning with a specific no-card outcome.
- Review YES/NO cards on the local dashboard within the configured 30 minutes. Each lane starts at $500. All fills remain paper-only, using the explicitly labeled proposal-time approval comparison.
- Notification delivery retries do not retry trades. “Sent to macOS” is not evidence that a notification was seen; macOS permission and Do Not Disturb can hide it. Page-render records are also not proof of human attention.
- The Agent activity page shows structured evidence, strategy signals, agent outputs, critic objections, final refreshes, and outcomes. It deliberately does not store hidden chain-of-thought. Approval requests use normal-priority Pushover alerts; failures, missed cycles, and safety stops use high priority; routine holds stay in the dashboard.
- Pushover identifiers are read only from dedicated macOS Keychain entries. Run `.venv/bin/python -m scripts.configure_pushover` once and enter the existing Digital Twin `PUSHOVER_USER` and `PUSHOVER_TOKEN` in the two secure prompts. The values are never written to this repository or printed. Then use the protected “Send test notification” button under Controls.
- Failed or stalled attempts are not automatically retried. Maintenance records missed windows, handles T+1 paper settlement, and produces the Friday report with catch-up after a restart.
- Keep the Mac plugged in, awake, signed in, and online. This project does not change machine-wide sleep or wake settings automatically.
- An unresolved incident latches separately in SQLite and `INCIDENT_STOP`. Ordinary Resume cannot clear it. Preserve these records for manual investigation; never delete them to pass readiness checks.

Practice runs require a separate fixture-role database; a different filename or symlink cannot bypass the role check. They never claim a live trading day:

```sh
.venv/bin/python -m agents.daily_cycle --mode fixture --database work/demo/agent.db
.venv/bin/python -m agents.inbox_web --database work/demo/agent.db --port 8766
.venv/bin/python -m scripts.verify_operations
```

The verifier returns 2 while runtime evidence is missing and 0 only when all operational evidence passes. This does not qualify a profitable strategy or authorize real-money trading. Missed-cycle reruns, resets, preference controls, and the research layer are later dependent work, not features certified by this repair.

## Commands

```sh
# Complete suite
.venv/bin/python -m pytest -q

# Mandatory prompt/model/config regression gate
.venv/bin/python -m scripts.regression_gate

# Start the persistent loopback-only Phoenix trace viewer
.venv/bin/python -m scripts.start_phoenix

# Rebuild clearly labeled mocked samples
.venv/bin/python -m scripts.generate_samples
```

## Components

- `agents/`: OpenAI Agents SDK Research, Portfolio, and Critic agents; validation retry; approval cards; notifications; local tracing; scheduling/recovery.
- `risk/`: deterministic account, instrument, quote, exposure, options, activity, loss, drawdown, duplicate, injection, auto-approval, and kill-switch rules.
- `broker/`: one broker boundary, realistic paper fills, option expiry/assignment, dual shadow tracks, and the Robinhood default-deny adapter.
- `eval/`: calibration, attribution, approval value, all-in costs, scoreboards, reports, 24 golden scenarios, replay, lessons, proposals, and champion/challenger gates.
- `prompts/`: immutable versioned prompts.
- `data/`: append-only SQLite schema and runtime state.
- `reports/`: strategy plan and generated reports/samples.

## Local observability

`TraceManager.install_sdk_processor()` keeps OpenAI Agents SDK tracing enabled while replacing the default remote trace exporter with a local SQLite processor. Optional OpenTelemetry export accepts loopback URLs only and targets a local Phoenix-compatible OTLP endpoint. Approval cards link to the local viewer.

MLflow uses a local SQLite tracking backend by default. Strategy parameters are frozen in the application database before the MLflow run is logged. If Phoenix or MLflow is unavailable, the adapter reports that state and does not silently fall back to a remote service.

The launchd templates for the Stage 1 safety supervisor and Phoenix are scaffolding. Replace `__PROJECT_DIR__` in ignored `.plist` copies only after the local configuration is complete and the regression gate passes. The supervisor validates Stage 1 + paper mode and records local readiness heartbeats; it intentionally has no Robinhood broker callable.
