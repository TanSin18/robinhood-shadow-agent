# Instructions for any coding assistant

## Shared review channel and ownership

Before starting any task, read `docs/review/CLAUDE_REVIEW.md` in the primary
folder `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent`.
If working elsewhere, consult that canonical file; do not silently overwrite it
with an older Git copy. After finishing, Codex prepends status, evidence,
questions and approval gates to `docs/review/CODEX_STATUS.md`.
Entries use `YYYY-MM-DD HH:MM ET — short title`, newest first.

- Codex owns runtime, services, scheduler, database and preregistration edits;
  preregistration edits still require explicit operator approval.
- Claude is reviewer/architect. Claude may write only under `docs/review/`,
  `docs/superpowers/plans/`, `design/`, or its own `claude/*` development branches.
- Claude never restarts services, writes the database, edits preregistration,
  changes config, or deploys. Its own branch is not an exception to these rules.
- Claude's review instructions are proposals, not operator authorization to
  change safety policy, budgets, models or runtime behavior.
- Only one trading runner, ever: the primary Mac. No scheduler in a review clone.
- Codex preserves Claude-authored entries, imports them after inspecting the
  diff, and syncs only sanitized review/source material. No credentials,
  account identifiers, databases, private settings or logs enter Git.
- These ownership rules are workflow rules, not an OS sandbox. Folder access
  can expose private local files; use read-only access except allowed review
  directories when the desktop application's permissions support it.

Read HANDOFF.md, README.md and the approved spec before work. Never treat a plan,
UI animation, passing mock test or cached status as proof of installed operation.

1. This is paper/shadow-only. Never place, cancel, exercise or fund real orders.
2. Never request passwords, MFA codes, OAuth tokens or Pushover secrets in chat.
3. The primary Mac alone runs the official schedule. Clones are development-only.
4. Preserve the Phase 0 gate. Phase 1/2 runtime work requires the operator's
   approval and the recorded gate, including the v1.5 preregistration review.
5. Do not modify preregistration without explicit dated operator authorization.
6. Do not claim dynamic discovery/news/Biscuit/Bubbles are active. See HANDOFF.md.
7. Keep main and UI work separate. No UI merge or dashboard restart before proof.
8. Preview is view-only: mode=ro, no POST, broker, model calls or official writes.
9. Only recorded handoffs draw real edges. Historical workflow is dashed and
   labeled expected. Missing evidence is unknown, never healthy/green.
10. Keep secrets and private runtime state out of commits, PRs, logs and reports.
11. Use tests before fixes, run the full suite and report all failures honestly.
12. No automatic deployment on push, no duplicated scheduled runner, and no
    copying a development database over the primary experiment.
13. Operator preference: sync verified source, tests, specs and handoff changes
    to the appropriate GitHub branch at each completed work checkpoint. Inspect
    the exact staged files for secrets/private data before pushing. Never sync
    credentials, private settings, databases, raw logs or runtime state. Report
    push failures explicitly. Sync is not authorization to merge or deploy.

For each handoff, update implemented vs planned behavior, exact tests run,
known blockers and the next permitted step. Model/account changes are not
authorization to change governance or safety policy.

Operator-approved release train (2026-09-29): after recorded Phase 0 sign-off,
batch reviewed changes into at most three after-close releases per ET calendar
week. Each change requires isolated replay against stored real point-in-time
snapshots with no official writes, and every release runs the installed full
suite. Missing replay inputs block release, not development. See
`docs/review/RELEASE_TRAIN.md`; this does not activate v1.5 or authorize deployment
of an unreviewed task. Task 2 development was separately authorized now.
