# Phase 0 proof and isolated Agent Desk UI scheduling

Operator-approved scheduling decision, 2026-09-28. This addendum overrides the
earlier UI sequence, not the safety gate or preregistration requirements.

## Main checkout: Phase 0 first

- [ ] Apply the operator-approved eleven-method amendment with exact names and
  pinned input schemas. Raw order history is tripwire/health-only, never agent
  evidence, model context, or detailed dashboard content.
- [ ] Verify Agentic-only account binding, bounded incremental history coverage,
  pagination, and a page plus persistent kill switch for unexpected equity,
  option, and crypto orders. Incomplete monitoring fails closed.
- [ ] Finish the dedicated-user private proxy installation; the operator alone
  completes Robinhood authorization, MFA, and consent.
- [ ] Prove an allowed real read, remote revocation rejection, and a fresh allowed
  read after operator reauthorization. Neither mocked results nor deletion of
  local credentials proves remote revocation.
- [ ] Run all current-code tests and install the verified services. Capture the
  source/config/preregistration/dependency hashes and installed service definitions
  in the Phase 0 evidence. Do not include secrets, balances or account identifiers.
- [ ] Freeze runtime AND dashboard code on this checkout after installation.
  No code edits, dependency updates, service substitutions, UI merge, or dashboard
  restart during the scheduled-proof window. Any necessary repair invalidates the
  freeze and requires a new verification/install/freeze receipt.
- [ ] Verify the 2026-09-29 10:00 America/New_York scheduled cycle against that
  exact installed snapshot. If installation or authorization is incomplete, report
  the missed proof; do not manufacture a receipt or backdate a manual run.

Phase 0 remains unpassed until all required real evidence exists. Tests alone are
not installation evidence. No pause marker is removed merely to meet a deadline.

## Parallel UI branch: ui/agent-desk

Worktree is separate from the main checkout, outside iCloud when possible.
Authoritative visual requirements: `outputs/agent-desk-ui-handoff/UI_BUILD_SPEC.md`.
The untracked handoff bundle must be supplied explicitly; a fresh worktree does
not silently inherit it or other uncommitted runtime dependencies.

- [ ] U2: theme, local fonts, local avatars, seven routes, phone layout, and CSP
  with `img-src 'self'` and `font-src 'self'` (no CDN, data, or remote exceptions).
- [ ] U3: Today and Decision room. Use the existing six-stage
  `project_decision_room` projection as the documented fallback. Missing handoffs,
  run-mode or candidate records are shown as unrecorded, never invented.
- [ ] No Talk box. No changes to cycle, broker, proxy, risk, schema or persistence
  code. Only dashboard presentation, assets and dashboard tests belong here.
- [ ] Run all dashboard tests, report exact results and dependency provenance,
  and capture isolated before/after previews without touching the live service.
- [ ] Keep the branch unmerged and the running dashboard unchanged until the
  Phase 0 scheduled-cycle proof has passed.
- [ ] After proof passes, review the branch diff for dashboard-only scope, merge
  that scope, restart only the dashboard service, verify its health, and show
  the operator a before/after. No trading-service restart is authorized by this step.

## Milestone placement

| Milestone | Placement | Boundary |
|---|---|---|
| U2–U3 | Parallel isolated UI track now | Existing projection only; no deployment before Phase 0 proof |
| U1 | First Phase 1 item under separately approved v1.5.0 | Handoffs, run mode, candidate records |
| U4–U5 | Phase 1–2 | Start only within the approved phase scope |
| U6–U7 | Phase 2 | Not authorized for this implementation window |

## Evidence and failure handling

### September 28 local-files and deployment amendment

- Check the complete project, including hidden `.venv` and configuration files,
  for macOS `SF_DATALESS` flags; report counts, never assume Keep Downloaded has
  completed. Recheck immediately before installation and freeze.
- The installed daily launcher must run its standard-library-only metadata
  preflight from a non-iCloud shared path using the app's non-iCloud Homebrew Python before starting the
  project's Python. Any inaccessible, missing, or cloud-only required path gives
  `HOLD_OPERATIONAL`; no inference or brokerage call is permitted.
- Deploy an explicit-source proxy bundle plus self-contained Python under
  `/Users/Shared/RobinhoodShadow/private/current`, owned by `robinhoodproxy`,
  inaccessible to the operator account. Socket access remains through the shared
  group only. No execution adapters, agent modules, database or credentials are
  bundled. Verify source/dependency hashes and absence of external symlinks.
- Keep the first private copy recoverably as `previous-initial`; it failed its
  integrity audit because first imports changed three encoding bytecode caches.
  Revised bundles exclude bytecode and launch with `-B`. Never count the failed
  audit as successful installation evidence.
- September 29 at 10:00 ET remains conditional on complete authorization,
  real revoke/reauthorize proof, full verification, installation and freeze. If
  these are unfinished, label that proof MISSING and target September 30 at
  10:00 ET, subject to the same gates. Do not backdate or substitute a manual run.

### After Phase 0 proof: move main out of iCloud

1. Preserve the proof and freeze receipt before changing paths. Pause scheduled
   work; retain a recoverable copy of source, local configuration and SQLite
   using a consistent database backup, including pending approvals and audit
   history. Do not put secrets in Git or in the migration report.
2. Move to a user-approved non-iCloud location, proposed
   `/Users/Shared/RobinhoodShadow/operator-project` with operator-only access.
   The proxy remains private and separate. Preserve tracked, untracked and dirty
   source; do not use a clean clone that drops required local files.
3. Rebuild the application environment from captured dependency versions. Update
   launchd paths, dashboard paths, log locations and preflight roots. Do not copy
   an environment with absolute links back to Documents.
4. Verify hashes, database roles, histories, pending approvals, 11-method policy,
   private identity denial, notifications, and full tests. Start only the intended
   services and record a new installation receipt. The old proof remains valid
   only for the old installation; require a new scheduled proof for the new one.
5. Keep the original folder as a rollback copy until the new installation is
   proven. No deletion or migration is authorized before the current Phase 0
   proof by this plan.

An iCloud placeholder or stalled read is not an empty source file. Hydrate or use
a separately installed test environment; never overwrite unknown local changes.
The UI branch must report missing baseline dependencies rather than importing
unreviewed runtime changes into its commit. Authorization remains operator-driven;
OS access checks and native permission prompts never justify exposing a token to
the main user or to an agent. Keep the scheduled-proof gate closed on any mismatch.

### Installation findings, September 28

The system-Python launchd preflight was denied Documents access by macOS, despite
the files being local. Use the application's existing non-iCloud Homebrew Python
for the stdlib-only guard; do not broaden macOS permissions or remove the guard.
Verify this change under launchd before freezing. The installed proxy, direct
socket read, separate-user denial, bounded-cash check, all three history reads,
and revoke/reauthorize drill have independent evidence. These are not a full
scheduled-cycle proof. Keep the dashboard and UI branch untouched.
