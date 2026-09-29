# Current handoff — September 28, 2026

## Latest portability repair

The seven export test failures are fixed using synthetic temporary settings and
proxy source fixtures, plus `sys.executable` for child processes. No private
settings were copied and no production configuration changed. The affected
52-test group and 46-test focused safety group pass. See
[Phase 0 closure progress](docs/phase0-closure-progress.md) for remaining gaps;
this does not close model/budget alignment or the installed scheduled gate.
Final fresh full suite: **601 passed, 0 failed, 31 warnings**. Independent review
found and corrected a fixture exclusion-coverage weakness before this final run.

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

## Isolated rehearsal branch update — 2026-09-28

LATEST: operator approved a diagnostic-only cap waiver and current models.
Run `01362a8c955e4af8bfaa5ac7555ef611` completed live collection, Research,
Portfolio, Critic and final quote refresh in 60.15 seconds. Estimated
API-equivalent cost $0.0481896. Market closed; risk issuance not exercised;
news disabled. No cards/fills/official-record changes. The run is explicitly
noncompliant diagnostic evidence, not the installed scheduled proof. The
one-invocation CLI flag is rejected for official runs; no permanent policy
change. Fresh suite: 594 passed, same 7 baseline failures, 31 warnings;
focused rehearsal suite: 12 passed. Installed runtime fingerprint unchanged.
Earlier blocked-attempt notes below are historical, not the latest outcome.

`codex/live-readonly-rehearsal` adds an operator-invoked diagnostic, not a service.
Official input is read-only; private what-if storage rejects claims, cards,
fills, scoreboard and lessons writes. See [live rehearsal report](docs/live-rehearsal-report.md).

Live collection and deterministic discovery ran. The rehearsal stopped before AI
at `REHEARSAL_MODEL_CAP_NOT_CERTIFIED`; the existing transport cannot certify the
registered what-if ceiling. It collected 537 quotes / 14 volatility series;
13 quotes were fresh, 524 stale or future-dated; market session was closed.
No model calls, cards or fills; official business records and installed source
fingerprint unchanged. News remains disabled. This is not Phase 0 completion.

Verification: `python -m pytest tests/test_rehearsal.py -q`: 10 passed.
`python -m pytest -q --tb=no`: 592 passed, 7 pre-existing portability failures,
28 warnings. Operator explicitly accepted documenting the baseline failures;
they are listed with causes in the report. No private configuration copied.
No deployment, merge, dashboard restart or preregistration change.
Next: certify the bounded inference transport before another AI rehearsal;
preserve the separate scheduled-proof requirement and Phase 1 boundary.

Follow-up audit: installed Codex protocol schemas expose no explicit output-token
cap, and runtime model aliases differ from the registered dated model IDs.
The recommended next step is an operator-approved, isolated Responses API
transport using the registered models and caps. Separate API credentials are
not present in the current process environment. Do not read/copy Codex auth
as an API credential, bypass budget guards, or modify the frozen deployment.
See the report's follow-up section for evidence and the remaining access choice.

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
