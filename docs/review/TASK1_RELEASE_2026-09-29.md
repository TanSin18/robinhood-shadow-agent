# Task 1 conditional release and rollback

Operator approval: 2026-09-29, this conversation. Window: September 29 only,
after 16:30 America/New_York and before midnight; otherwise skip and report.
This is NOT authorization for the Wednesday proxy drill deployment or Task 2.

## Compatibility confirmed before release

Candidate runtime source is commit `6e2c220eabef4e1d2153d06967c5b098c66dfac8`,
on `codex/shared-cost-v1-5`. The branch name does not activate v1.5.
`task1-release-manifest.json` pins the exact 13-file overlay and previous/new
hashes. Install ONLY those paths, not a branch-wide copy.

- Root preregistration remains byte-exact v1.4.2, SHA-256
  `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
- `agents.preregistration` still enforces version, hash and Phase 0-only scope.
  `bounded_inference.policy()` reads root registration, not the v1.5 draft.
- Existing registered input-token-share allocation and exact residual rule are
  implemented. The operator's separately approved auxiliary-only candidate-count
  fallback is the sole allocation amendment. It does not change mandatory counts,
  model assignments, token envelopes, stage reservations or any budget ceiling.
- No edits to config, prompts, models, risk, selection/entry/exit rules, baseline
  gates, fractional policy, seats, news, discovery, pulse or arm execution.
  Additional arm names in the accounting report are zero-cost labels only;
  no baseline trading is activated. Historical rows are not backfilled.
- New `ai_cost_settlements` is an additive accounting audit table created only
  during settlement, not a new portfolio/lot ledger or migration of old results.
- `broker_proxy/revocation.py`, proxy tests/helper and private proxy bundle are
  explicitly excluded. Existing proxy identity, credentials and services unchanged.
- Focused compatibility tests: 46 passed, 27 warnings on September 29 before
  release; command: primary `.venv/bin/python -m pytest
  tests/test_preregistration_phase0.py tests/test_attempt_allocation.py
  tests/test_accounting_resilience.py tests/test_phase0_budget.py
  tests/test_scheduled_inference.py -q`, from development worktree.

## Release procedure — execute only inside the approved window

1. Read canonical CLAUDE_REVIEW/CODEX_STATUS for intervening instructions. Check
   actual ET date/time; outside September 29 after 16:30, do not deploy. Confirm
   no active official run/claim or unexpected safety incident. Do not clear stops.
2. Confirm primary is `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent`.
   Verify its complete source fingerprint equals manifest `before_source_fingerprint`;
   verify every candidate file at pinned commit equals its `after_sha256`.
   Any drift stops release for review; do not overwrite unknown changes.
3. Capture service state and current dashboard PID for evidence without secrets.
   Only targets allowed to unload/reload are `gui/501/com.openai.robinhood-daily`
   and `gui/501/com.openai.robinhood-maintenance`. Their plists are respectively
   `/Users/tanmaysinnarkar/Library/LaunchAgents/com.openai.robinhood-daily.plist`
   and `.../com.openai.robinhood-maintenance.plist`.
   Never restart `com.openai.robinhood-inbox`, proxy, or another runner.
4. Stop only daily/maintenance with `launchctl bootout` for these exact targets.
   Confirm they are stopped; abort if a run remains active. Keep dashboard up.
5. Create a mode-0700 unique rollback directory outside primary using `mktemp -d`
   under `/Users/tanmaysinnarkar/LocalProjects/task1-rollback.XXXXXX`. Copy only
   previously existing manifest files, preserving relative paths; record which
   files were absent. Save the manifest and service-state evidence privately.
   Verify all backup hashes before altering primary. Never copy DB, tokens,
   private config, broker credentials or the whole project into a release bundle.
6. Apply only manifest-listed source/test updates, verifying each after hash.
   Use apply_patch for source edits. Keep config/root registration/proxy byte-exact.
   Verify complete source fingerprint equals manifest expected-after value.
7. From primary run `.venv/bin/python -m scripts.verify_operations --run-tests
   --output-dir outputs/task1-release-2026-09-29
   --test-report outputs/task1-release-2026-09-29/tests.xml
   --test-manifest outputs/task1-release-2026-09-29/test-run.json`.
   It runs the INSTALLED full suite and read-only operational verifier. Keep
   reports local; publish only sanitized counts, hashes, gate names and blockers.
   Do not use stale branch-suite results as installed evidence.
8. Require full suite exit zero, all collected cases passing, stable installed
   fingerprint before/after tests, exact active v1.4.2 hash, no unauthorized changes.
   The operational verifier may return 2 for missing new-source scheduled proof
   and missing revocation-drill evidence. Report these explicitly as NOT PROVEN;
   do not weaken the verifier or fabricate a receipt. Unexpected failures trigger
   rollback, not a claim of readiness. If uncertain about a blocker, stop/review.
9. On success, `launchctl bootstrap gui/501` the two exact original plist paths.
   RunAtLoad triggers an after-hours schedule check, not a forced official cycle.
   Confirm jobs loaded and no second runner. Do not force market data/model calls.
   Confirm dashboard PID unchanged. Recheck source/config/proxy file hashes.
10. Prepend installed tests, verifier result, before/after fingerprints, backup
    path, service evidence, blockers and Wednesday criteria to CODEX_STATUS.
    Sync sanitized review/source documents; do not push private evidence or DB.

## Written rollback — any unexpected release/test failure

Keep or stop only daily/maintenance. Restore each previously existing manifest
file from its verified backup using apply_patch; move newly introduced files to
a `withdrawn/` folder in the private rollback directory (recoverable, no broad
delete). Do not restore a database, erase audit rows, clear safety markers,
reset reservations or change broker state. An additive settlement audit table,
if present later, is retained; old runtime ignores it.

Verify every original hash and full previous fingerprint
`8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
Then reload only the original daily/maintenance plists if the rollback is proven
and no incident requires the services to remain stopped. If restoration cannot
be proven, leave these jobs stopped and report urgently. Never compensate with
an extra official trading run. Record cause and backup location in CODEX_STATUS.

## Operator-facing behavior and remaining proof

Auxiliary allocation failure: warning/page queued once, cycle may continue.
Settlement failure or unexpected inference programming failure: safety latch;
**paper activity paused for your review** until operator review/rearm. This is
deliberately more conservative than retaining reservations alone. Queued pages
are not proof of phone delivery. Never auto-clear these incidents.

No dashboard restart is authorized. Runtime history projection is included,
but an already-running dashboard may retain its loaded module. The new Health
wording must not be claimed visible tonight; a separately approved UI release
can say “paused for your review.” Existing pause/incident indicators remain.

Wednesday 10:00 ET is the first scheduled live check of this accounting release:
`accounting_status: SETTLED`, unrepresented B cost zero, unique total equals
trusted provider-estimate sum, and no incident. Report no-AI/code-only outcomes
honestly; they do not prove live shared-AI allocation. Wednesday after 16:30
revocation drill is separate, with `--drill-not-before 2026-09-30T16:30:00-04:00`.
No proxy helper installation is included in this release.
