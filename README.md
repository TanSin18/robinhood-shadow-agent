# Robinhood Shadow Agent

Private, paper-only investment-research project. **Real orders are blocked.**

Current deployment and shared reviewer channel: [CODEX_STATUS](docs/review/CODEX_STATUS.md).
Read [CLAUDE_REVIEW](docs/review/CLAUDE_REVIEW.md) before every task. Deployment
uses the Codex runtime branch plus a separate immutable UI release; main alone
is an older snapshot. Historical branch/deployment notes below are superseded
by the dated review status. Draft v1.5 is not active.

Start with [HANDOFF.md](HANDOFF.md), [AGENTS.md](AGENTS.md), and the approved
[organization spec](docs/superpowers/specs/2026-09-28-intelligent-agentic-investment-organization-design.md).
The spec describes intended capabilities; it is not a claim they are implemented.

## Continue from another account or device

1. Give your other Codex/Claude account access to this private GitHub repository.
2. Clone it outside iCloud/OneDrive/Dropbox-synced folders and open the clone as a project.
3. Ask the assistant to read `AGENTS.md` and `HANDOFF.md` before changing anything.
4. Create a local Python environment and install the project. Never copy brokerage credentials into chat or Git.
5. Work on a branch, run tests, and submit a pull request. Do not deploy automatically.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
```

Python 3.12+ is declared; the primary Mac was tested with Python 3.14. A clean
dependency install on another platform is not yet certified. Some legacy tests
or optional observability imports may require additional dependencies; report
these rather than claiming the clone is operational.

## Branches

- `main`: sanitized snapshot of the repaired Phase 0 runtime, specifications and tests.
- `ui/agent-desk`: Agent Desk UI overlay on this runtime, for read-only preview work.
  Not deployed or merged into the primary Mac. Original UI checkout had 13
  collection errors due to stale runtime dependencies; this export's test result
  must be checked independently.

On the UI branch, a local preview is started manually with:

```sh
.venv/bin/python -m agents.desk.preview --database /absolute/path/to/your/local/agent.db --port 8766
```

The database is not in Git. Preview opens it read-only, denies POST requests,
does not call a broker or model, and displays local recorded evidence only.

## One primary runner

The existing Mac remains the only scheduled runner. Other devices are development
and review machines by default. Do not install services, authorize a broker,
copy live databases, or start an official cycle on another device. An explicit
operator-controlled migration is required to change the runner.

GitHub stores source, not a shared running account. It does not transfer OAuth,
Keychain access, Apple user separation, Pushover credentials, private network
access, live positions or experiment state. Each AI service has its own sign-in
and access permissions.

## Safety and privacy

- Stage 1 remains paper-only and default-deny for real writes.
- Approved proxy has exactly eleven read methods. Order histories are health-only.
- Real Agentic data and paper balances are separate.
- `config/settings.yaml` and `config/broker-proxy.yaml` are templates, not credentials.
- Local settings, `.env`, tokens, Keychains, databases/WAL files, runtime logs,
  traces, old Git history, report bundles and installation receipts are excluded.
- The primary checkout and services are not relocated by this export.

The original [README](docs/LEGACY_README.md) and historical plans are retained
for context. Use the current handoff when historical documents conflict.
