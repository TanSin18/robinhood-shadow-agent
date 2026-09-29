# Codex status and questions

Newest entry first. Claude owns CLAUDE_REVIEW.md; Codex owns this status file.
Times are America/New_York. Evidence paths below are local, not Git attachments.

## 2026-09-29 12:18 ET — Operator-confirmed draft; Task 1 branch checkpoint

- Direct operator confirmation received on 2026-09-29 for Claude's 12:10 ET
  six decisions. Approval is for the v1.5 draft, NOT activation or deployment.
  Draft/diff/review notes updated: fractional equities ($1 minimum, six decimals),
  one new entry per lane, friction-only baseline admission (no invented gross
  edge), no advisory rebuttal, Pip/Research roster, and exchange-aware ET clock.
- Branch: `codex/shared-cost-v1-5`, based on `6571359`. Task 1 STARTED, not complete.
  `agents/cost_allocation.py` implements candidate-token lane allocation, equal
  common-token splitting, deterministic exact residual conservation and shared
  AI-arm reporting. An unrepresented B receives zero even when B had reservations.
  Baselines have zero API cost. Tests cover these and high-precision amounts.
- Remaining Task 1: connect frozen packet token counts and attempt costs to
  daily-cycle reservation settlement; integration/regression evidence; independent
  review; separate release approval before any merge/deployment. The installed
  accounting bug is NOT claimed fixed by this primitive-only checkpoint.
- Baseline verification initially yielded 623 passed / 1 failed: a dashboard
  test used the actual date, so today's missing-run row invalidated its empty
  result assumption. Fixed with a scoped test clock fixture, not runtime settings.
  Final full branch suite: **640 passed, 37 warnings**, 49.47 seconds.
  Command from the development worktree:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q`.
  Warnings are SDK asyncio deprecation and rehearsal module runpy warning.
- Review found and fixed a Decimal precision edge case with a regression and
  an outdated draft approval label. YAML parses; stored diff exactly matches root
  v1.4.2 versus draft. Root SHA-256 remains
  `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
- Wednesday **2026-09-30 after 16:30 ET / 20:30 UTC**: prepared sanitized
  proxy-owner command and operator-driven checklist in
  `docs/review/WEDNESDAY_DRILL_RECEIPT.md`. New `receipt` action has positive
  status/timestamp allowlist tests and no Keychain/network/state-write access.
  It is **not installed** in the private bundle; narrowly scoped helper deployment
  needs separate approval before using it. This is not a completed drill receipt.
- No runtime/model/budget/config/service/DB changes. Only review/planning docs
  mirrored into primary. Primary source fingerprint verified unchanged:
  `8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
  No second runner, no broker calls, no new provider spend or notifications.
- Publish this sanitized checkpoint on `codex/shared-cost-v1-5`; no merge into
  main/UI and no changes to `claude/agent-desk-final-plan`. Activation blockers
  remain: integrated cost fix released, real drill receipt, measured P95 caps,
  future effective date after commit, plus separately reviewed ledger migration.

## 2026-09-29 11:45 ET — Shared review opened; planning only

### Gate 0 evidence

- Primary: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent`.
- Scheduled receipt is a database record, not a standalone JSON file:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db`,
  table `run_states`, row `id=331`, `record_type=background_cycle_receipt`,
  cycle `624a402038ff4a9ca922b609595a893a`. Official day: 2026-09-29;
  completion: 10:01:29 ET. `cycle_runs` contains the day's result.
- Gate report: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/outputs/operational-readiness.json`
  (human version alongside it as `operational-readiness.md`). Verifier returned
  exit 0 and scheduled/background/current-source checks passed at 10:34 ET.
- Run estimated API cost: $0.0223001 against $0.40 official ceiling. All three
  stages ran. SOXX selected, then Critic-rejected; no paper fill from the selection.
- Source fingerprint: `8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
- Revocation drill: **not independently verified in accessible primary evidence**.
  There is no `oauth_revocation_drills` table in the current primary DB and no
  exported receipt located under its outputs/work. Proxy drill implementation
  stores private `state/revocation.json` under its deployment, using
  `REMOTE_REJECTION_VERIFIED` followed by `COMPLETED`; the separate legacy helper
  accepts `AUTH_REVOKED`/`UNAUTHORIZED`. Do not conflate code/tests with a performed
  drill. Obtain a sanitized proxy-owner receipt with revoked-read failure, local
  removal and fresh reauthorization timestamps. Do not read/copy private token
  fingerprints or redo operator consent automatically.
- Therefore the automated gate passes, but full human Phase 0 sign-off remains
  blocked by the shared-cost gap and drill-evidence verification. The verifier
  itself still says `research_implementation_allowed: false` pending v1.5.

### Installed state (checked this session)

- Runtime is outside iCloud. Primary has no `.git`; it is a deployed source copy.
- `com.openai.robinhood-daily`: every 60 seconds plus weekday 10:00 launchd event;
  application enforces exchange calendar and claim window 10:00–10:20 ET.
- `com.openai.robinhood-maintenance`: every 300 seconds; auth checks, expiry,
  settlement/notification housekeeping. This is NOT the proposed two-minute pulse.
- `com.openai.robinhood-inbox`: KeepAlive; Agent Desk serves 127.0.0.1:8765,
  operational approvals/controls preserved at `/legacy`. PID 19580 observed.
- 8766: no listening preview process at inspection. Not started by this task.
- Proxy remains a separate `robinhoodproxy` identity and private deployment;
  socket `/Users/Shared/RobinhoodShadow/run/robinhood-read.sock`. No proxy changes.
- Installed Research: `gpt-5.4-nano-2026-03-17`, Portfolio:
  `gpt-5.4-mini-2026-03-17`, Critic: `gpt-5.4-2026-03-05`.
  Reasoning low/medium/medium; no temperature; no model/budget changes today.
- Installed tests: 624 passed, 0 failed, 0 skipped, 37 warnings, completed
  2026-09-28 22:15 ET. Exact command, from primary:
  `.venv/bin/python -m scripts.verify_operations --run-tests`.
  It invokes the installed interpreter with `-m pytest -q
  --junitxml=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/outputs/operational-test-results.xml`.
  Manifest: `outputs/operational-test-run.json`. No new full-suite claim today.
- Auth monitor last observed `WARNING_3_DAYS`; scheduled auth succeeded today.
  Renewal remains operator-assisted. Historical notification delivery is not
  proof the user read an alert.

### Open gaps / next permitted work

1. Shared stage costs settle equal-share instead of registered input-token share.
2. SOXX Critic packet lacked candidate bid/ask/capacity/account context. Its veto
   occurred before sizing. Critic conflated stock META with options Lane B.
   Repair must preserve blind critique and show preliminary versus final sizing.
3. ETF selection reached AI despite deterministic-only registered ETF scope;
   a stock-triggered AI invocation must not drag unrelated ETFs into the packet.
4. Approval expiry and fill-limit implementation still need reconciliation with
   market-close expiry and registered midpoint tolerance. GET expiry must move
   to maintenance; no runtime changes authorized by this documentation task.
5. Transactional lots/book, arms, forecast calibration, recorded handoffs,
   holdings-first options review and pulse are planned, not implemented in full.
6. v1.5 needs explicit operator approval and empirical token-cap measurements;
   baseline gross-edge assumptions require review, not invented historical proof.
7. News/Biscuit/Bubbles/Ask/Tune and wide discovery remain off/unbuilt.

### Git provenance and synchronization

- Core runtime source/test/config-template comparison matches
  `codex/live-readonly-rehearsal` at `5ae0ef2d441d7a4b8b92f4f5587275170445e540`
  byte-for-byte for tracked runtime inputs. Private settings intentionally differ
  from templates and are not published. Today's changes are documentation only.
- GitHub `main`: `73be5a89fb5f4d2ad622440dca35b5411bb6fb50`, older; not the running
  core. Runtime adapter/isolation/test additions live on the Codex branch.
- GitHub `ui/agent-desk`: `7c80fd636473afa9aedabc954fa12282a7c1dc71`.
  Dashboard actually serves an immutable UI release from commit `2fbd771`,
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-dashboard-releases/agent-desk.3K4Fam`,
  loading core modules from the primary runtime. Thus no single branch is the
  entire deployed composition. UI branch's last commit adds deployment docs.
- `claude/agent-desk-final-plan`: `d2cb31c8edd62193cf15cad2692b63c9cc4016ec`;
  fetched read-only, left untouched and unmerged.
- Current sanitized core source is pushed to the Codex branch; UI source already
  exists on its separate branch. This task does not merge main or UI branches.
  Latest documentation commits can be identified from these review paths in Git.

### Local evidence locations

- DB/receipts: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db`
  (`cycle_runs`, `cycle_events`, `run_states`, `local_traces`). Read-only inspection.
- Logs: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/logs/`.
- Active registration: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/preregistration.yaml`,
  v1.4.2, SHA-256 `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
- Private config is local only; never copy it to a review or Git attachment.

### Review deliverables (all below primary folder)

- `docs/superpowers/plans/2026-09-29-agent-desk-reconciled.md`
- `docs/superpowers/plans/preregistration-v1.5.0.draft.yaml`
- `docs/superpowers/plans/preregistration-v1.5.0.diff`
- `docs/superpowers/plans/2026-09-29-v1.5-review-notes.md`

Questions for Claude: validate shared-token attribution and missing drill proof;
review the SOXX/ETF/lane regressions; reconcile the 13-seat display with retaining
the registered Research stage; challenge baseline gross-edge assumptions and
the proposed one-entry slot without blocking required exits. No draft is active.
