# Temporary Claude takeover — 2026-09-30

Status: READY FOR CLAUDE ACKNOWLEDGEMENT. Operator requested temporary takeover
while Codex credits recover. This file is not evidence Claude has started.
Codex development wakeups are PAUSED; installed trading services are untouched.

## Start here

1. Read AGENTS.md, canonical docs/review/CLAUDE_REVIEW.md and CODEX_STATUS.md.
2. Review this handoff and acknowledge in docs/review/CLAUDE_REVIEW.md with
   actual ET time, working path, branch and commit. Become sole development
   owner only after checking there is no other active implementer.
3. Continue on claude/continuation-2026-09-30, based on the latest handoff commit.
   This branch is pushed to GitHub, not merged into main.
4. Existing clean development worktree:
   /Users/tanmaysinnarkar/.codex/worktrees/robinhood-live-rehearsal
   After confirming clean status, fetch and switch to the continuation branch.
   Do NOT use the installed primary directory as a source checkout.
   If your app lacks access, ask the operator to grant this development folder
   or clone the private repository into an authorized development folder.
5. Repository: https://github.com/TanSin18/robinhood-shadow-agent
   Git main is NOT the latest development or installed composition.

## Authority and safety

The operator delegates development, testing, isolated rehearsals and sanitized
Git synchronization to Claude temporarily. This supersedes reviewer-only
ownership for that work, not the live-runtime safeguards. Work on claude/*
branches. Disposable databases and isolated config/registration copies are
permitted for approved rehearsals. Do not alter the installed config,
preregistration, official DB, proxy identity, credentials, services or scheduler.
No real orders/cancels/money movement. Only the existing eleven read methods.
Order histories stay in health/tripwire code, never model prompts.
Any release still needs a fresh explicit operator go identifying the executor,
completed drill, after-close timing, pinned manifest, rollback, installed full
suite and verification before Thursday October 1 09:30 ET. Otherwise leave the
installed version. Do not treat this handoff as deployment approval.
Operator personally handles login, consent and revocation; never request secrets.

## Paths and exact checkpoint

Primary installed directory (non-Git):
/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent
Official DB: primary/data/agent.db (read-only to rehearsals).
Logs: primary/logs. Shared channel: primary/docs/review.
Development branch before handoff: codex/task2-handoff-replay.
Implementation commit: 45806e69663837087979f497bba6e61fabd7e0aa.
Schedule/status commit: a1abe36b6364c4247d3d054d44d90c46b8c4f5a6.
Read subsequent handoff commit from Git; do not pin to the old code-only commit.
UI worktree: /Users/tanmaysinnarkar/.codex/worktrees/robinhood-ui-sync
UI review branch last inspected tip: claude/ui-truthful-outcome at
614e3aa69e4f66dc9c0e66bb2f66efe8dfceb5d4; fetch and verify before integrating.
Do not merge claude/agent-desk-final-plan.
Local interpreter:
/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python

Active registration is v1.4.2, SHA256:
39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075
v1.5 is a separate inactive draft in docs/superpowers/plans.
Last development suite: 725 passed, 61 warnings, 47.45s at 45806e6.
Exact command, from development worktree:
`/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q --tb=short`
This is historical test evidence, not installed readiness. Rerun after changes.
Last reported installed suite was 665; do not replace that with the branch count.

## What is actually built / what remains

- Shared-cost repair was previously installed. Today's official run was code-only
  and $0, so paid live attribution is still unproven.
- ETF pure planner and draft rules are tested; production_enabled is hard-false.
  NOT a complete issuer. No three-arm fills/cards have been proven.
- Planner uses code-only fixed first-fresh midpoint *1.005, cutoff
  min(15:30 ET, session close minus30), $1 minimum and six-decimal round-down.
  AI approved stock pick takes Lane A slot. Desk policy applies to agent_alone,
  with_approvals and deterministic_no_ai, not VTI/cash/random; never call it AI alpha.
  Approval card author must be "Desk rule (no AI)".
- Remaining ETF work: trusted signal integration; immutable reference in capsule;
  three distinct arm accounts with per-arm cash/holdings/risk/idempotency;
  fresh quote plus registered slippage at operator YES; activation loader/pin.
  PaperInbox currently initializes only two arms and legacy YES uses old quote/time.
  Do NOT route new policy through that unsafe legacy behavior.
- Task2 packet/replay foundations exist; full daily integration and capsule remain.
  Read docs/superpowers/plans/2026-09-29-agent-desk-reconciled.md.
  Integrate blind Critic inputs, paper portfolio context, lane identity, ETF exclusion
  from AI, no account identifiers in new payloads. Capture exact sanitized
  inputs/outputs and content hashes for future deterministic replay. Do not invent
  missing historical inputs or substitute current prices.
- Readiness change remains: accept HOLD_CAPABILITY_GAP only with ALL operational
  checks passed. Operational failure must still fail. Do not rewrite today's
  official record or label missing capability as investment discipline.
- Review UI branch, run Mac tests, then include only reviewed changes in candidate.
- Prepare effective v1.5 package; active registration remains unchanged until
  separate operator activation. No guessed strategy edge/policy values.

## Rehearsals, costs and release — latest authority wins

Canonical review 11:14 and operator confirmation remove the 15:30 freeze and
17:00 review cutoff. Continue building/rehearsing; regular-session fresh data
during market hours, stored snapshot/capsule replays after close.
Targets today: 12:30 code-only; 13:30 paid stock-triggered/shared cost; 14:30
combined pinned candidate + Today/Room screenshots; additional runs when ready.
These are targets, not completed proofs. Codex heartbeat
today-isolated-agent-desk-rehearsals is PAUSED to conserve credits/avoid overlap.
Claude must manage these checkpoints in its active session; no Claude scheduler
has been installed or verified. Do not assume Codex will wake Claude.
No new official runner or duplicate background trading job.

Today-only what-if AI cap: $0.60 TOTAL, <=$0.20 per paid rehearsal, other limits
retained. Include uncertain charged attempts. Never use diagnostic cap waiver.
Current BoundedInference CostLedger is per disposable DB: aggregate enforcement
is NOT done. Build/test shared durable atomic reservation accounting and
reconcile prior rehearsal spend before paid calls. Stay code-only if uncertain.
No paid calls were made during the ETF planner/scheduling/handoff turns.

Use disposable DB, isolated registration/config, run_mode what_if,
parent_official_run_id and approved read-only proxy. Official parent today:
37c7e7947a124a9c821570a55ecb00db.
Preserve API/DB isolation. Simulated issuance artifacts are non-actionable,
never official cards/fills/scoreboard/memory. Verify official business digest
before/after (agents.rehearsal.official_digest); no whole-file hash assumptions
for a WAL database. Prevent overlapping rehearsals.

Each report: branch/commit, inputs/freshness, actual outcomes, costs including
uncertainty, capsule hash, replay result, isolation proof, missing checks.
Never report a planned or mocked step as live end-to-end success.

Drill: docs/review/WEDNESDAY_DRILL_RECEIPT.md. Prepared helper is not proof it is
installed. Respect proxy OS identity; no permission widening, guessed install
paths, or synthetic receipts. Verify current auth validity/expiry read-only.
No release before completed drill and fresh explicit operator go. Hard finish:
before 2026-10-01 09:30 ET. If missed, keep current installed version.

## Git / two-way review discipline

Before each task read canonical CLAUDE_REVIEW.md. After each checkpoint prepend
dated ET progress to CLAUDE_REVIEW.md and update CLAUDE_RETURN.md with:
branch/commit, files changed, test command/count/failures, remaining work,
rehearsal evidence paths/digests, API spend/reservations, approvals and any
installation actions (expected none without separate go).
Preserve CODEX_STATUS authored history. Keep local canonical and branch review
documents synchronized without overwriting newer entries.
Stage explicit source/tests/docs only; inspect staged diff for secrets/account
IDs. Never commit .env, private settings, credentials, runtime DB, logs, raw
broker responses or capsules containing private evidence. Commit coherent
checkpoints, push claude/continuation-2026-09-30, verify remote SHA, report failures.
No force push or implicit merge/deploy. If changes are untested, label WIP, not ready.

## Returning control to Codex

When operator says credits are back, stop starting new work and finish/stop
current test safely. Push final sanitized checkpoint and fill CLAUDE_RETURN.md.
Record any running process and unresolved reservation; working tree clean or
explicitly list uncommitted files. Set owner to HANDOFF_PENDING_CODEX.
Codex must read CLAUDE_RETURN + canonical review/status, fetch branch, inspect
diff, verify commit/tests/runtime/registration and budget ledger before accepting
ownership. Never reset to an old Codex checkout or rerun the official day.
Codex acknowledges in CODEX_STATUS. Only then Claude stops and Codex resumes.
Do not resume today's expired heartbeat on a later date; retire it.
