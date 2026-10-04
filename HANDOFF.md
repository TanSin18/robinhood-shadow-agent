# Current handoff — September 28, 2026

## Operator-approved dashboard-only exception

Deployment completed on September 28 at approximately 22:01 ET. Agent Desk is
now the main page on 8765; operational controls/approvals/history are linked at
`/legacy#controls`, `/legacy#decisions`, `/legacy#history`. Browser navigation
from new home to legacy controls and back was verified; no live POST submitted.
Full suite: **620 passed, 27 warnings**, including three front-door integration
tests (paper approval/fill, pause, redirects, origin/CSRF and read-only pages).
Runtime source fingerprint remained unchanged. Only the inbox launch service
was restarted. Launchd bootstrap initially raced teardown; retry after confirming
the old service was absent succeeded. Phase 0 scheduled proof remains missing.
The versioned local release contains `inbox-before.plist` for rollback. The
release is separate from the UI worktree; future Git pushes do not deploy it.

The operator explicitly approved Agent Desk as the main screen before the
scheduled Phase 0 proof, provided existing operational approval/control pages
remain clearly linked. `agents.desk.frontdoor` composes the read-only Agent Desk
at `/` with the unchanged operational handler at `/legacy`. POSTs retain the
existing origin/CSRF checks and paper-only behavior; redirects return to legacy
approvals/controls. This is not approval to enable direct Agent Desk mutations,
claim Phase 0 completion, change broker/cycle/risk code, or start Phase 1.

`scripts/serve_agent_desk.py` loads operational modules from the frozen runtime
and only the new desk package from this separate UI release. The deployment
must restart only the inbox service and retain a rollback copy of its launch
configuration. Existing preview entrypoint remains view-only.

## Latest UI synchronization

Pre-gate repair checkpoint: the full suite now passes **617 tests**, with 27
SDK deprecation warnings. Reproduced all 36 failures before changes. Seven were
the known export portability failures; reused synthetic fixtures and the active
interpreter fixes from runtime commit 584b197 (tests only). The other 29 came
from prematurely replacing the operational inbox renderer with the incomplete
Agent Desk renderer. Restored `agents/inbox_web.py` to the unchanged main
implementation. Agent Desk remains served by its separate read-only preview
entrypoint; no Agent Desk screens, avatars or assets were removed.

This is NOT proof of an operational Agent Desk replacement: approvals/controls,
history/filter/security parity still need an explicit post-gate integration.
Installed readiness assessment remains false: no fresh authenticated scheduled
cycle for the installed code/configuration. No merge, deployment or restart.
The older 36-failure result below is retained as historical evidence.

Latest lane diagrams and preview polish are preserved on `ui/agent-desk`.
Fresh suite: 581 passed, 36 failed; preview tests 6 passed, polish tests 3 passed.
See [UI synchronization status](docs/ui-sync-status.md) for every failing test.
Do not merge or deploy this checkpoint as an acceptance-approved dashboard.
Rehearsal source and its latest live results are on the separate
`codex/live-readonly-rehearsal` branch. Main remains unchanged.

## Actual status

Phase 0 safety/read-only integration is implemented; its installed scheduled
full-cycle proof is still missing. The target was September 29 at 10:00 AM ET.
Verify current records on the primary Mac; do not infer that this future run
succeeded from this document.

Last primary-code test result: **589 passed**, 27 SDK deprecation warnings.
This is historical evidence for the primary checkout, not automatic proof for
this export or a new machine. Private freeze/test receipts were deliberately
not copied because they contain machine-specific metadata.

## Latest runtime repairs

- Live quotes lacked permanent instrument IDs. Resolve absent equity IDs from
  the approved option-chain read's matching, unambiguous underlying identity.
  Cited content hashes retained; URL identifiers parsed, never fetched.
- Underlying symbols may be blank in the actual provider response. Conflicting
  underlying identities still fail closed; never map an option to an equity ID.
- Historical reads split into individual tickers after live 10-symbol requests
  failed. Keep the full 550-day window.
- Refresh equities after slower history/options collection and again before
  issuance. The 60-second freshness limit was not relaxed.
- Added malformed-record and identity-conflict regression tests.

The last live diagnostic retrieved 14 resolved equity quotes, 14 volatility
series, 377 completed daily bars per ticker and 534 retained option quotes.
Some invalid option records were excluded and some after-hours prices were stale.
It did not invoke models, create cards/fills or mutate official results.

## Firm Lab Checkpoint 7 (October 4, 2026) — modeling research, no trading change

Branch `claude/checkpoint7-modeling` (on `codex/checkpoint6-features`). A modeling laboratory and validation
tournament, research only: `docs/firm_lab/CHECKPOINT7_CLOSURE.md`. Result: no feature family or model architecture is
established on this data; no model has more than a research status; Fibonacci is INCONCLUSIVE. Control A is unchanged
and was not restarted. The Firm trading trial is NOT REGISTERED and the October research stop is not superseded.
Deployed read-only to the dashboard and closed on October 4 (native suite 1129 passed, 3 failed for reasons outside
the checkpoint). The Checkpoint 7 holdout is no longer an untouched test set for future model selection. Current
state and what is left for the operator: `docs/review/CLAUDE_STATUS.md`. Checkpoint 8 is not started.

## Important unfinished items

- The approved design retires the 14-symbol primary universe, but runtime still
  uses that whitelist and a hardcoded 14-symbol bound. Broader S&P 500-plus-ETF
  discovery is an implementation gap. Do not call these agent-discovered picks.
- News collection is disabled. Biscuit and Bubbles are not implemented agents.
- Agent Desk Ask and Tune are disabled/read-only, not connected capabilities.
- Research/Portfolio/Critic are conditional on the AI-needed gate; ETF-only
  discovery can result in a code-only day.
- Full Phase 1 accountability, baselines, broader discovery, calibrated forecasts
  and Phase 2 research are not complete merely because modules/plans exist.

## Primary machine boundaries

The primary runtime is in the operator's Documents/Codex directory. Its broker
proxy uses a separate macOS identity and private deployment under
`/Users/Shared/RobinhoodShadow`, never the agent's token access. The approved
preregistration remains byte-exact and pins eleven read methods.

Dashboard 8765 is the existing operational UI. Preview 8766 is a separate UI
checkout and manual process. Neither was restarted by the market-data repair.

iCloud offloading recurred during export: some main source/config/Git metadata
became dataless. Download requests were issued. Recheck all required files before
claiming scheduled readiness. Plan a separately approved primary-runtime move
out of synchronized Documents after the gate; this export does not perform it.

## Next permitted steps

1. Confirm current local-file residency, authorization and installed service state.
2. Obtain the matching installed scheduled-cycle receipt and run the operational gate.
3. If it passes, review dashboard-only integration before any primary UI swap.
4. Prepare/review preregistration v1.5 and a concrete implementation checklist for
   broader discovery and the remaining agent features before enabling them.

## Provenance

Fresh source export; old Git history is intentionally not transferred because
it has not been audited for historical credentials/runtime data. The primary
dirty checkout and UI worktree are not modified or merged by publication.
Only source, templates, specs, tests and UI reference assets are carried over.

Export-only hygiene: the template dashboard URL is loopback rather than a
personal network hostname; package discovery includes proxy/research modules;
the pytest warning filter does not require optional SQLAlchemy at startup.
These changes are not applied to the frozen primary checkout.

Export verification: Python syntax parsing passed. A full-suite attempt using
the primary virtual environment stalled while iCloud files were unavailable
and was stopped; it is not a passing export test result. Re-run tests in a
fresh local environment before deployment. No live service was restarted.
