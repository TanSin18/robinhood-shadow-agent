# Checkpoint 6 Task 12 deployment — 2026-10-03

Operator authorizes research-only deployment of accepted source `34531df` from
`codex/checkpoint6-features` at `4861b1d`, with the following explicit exception:

Cloud suite: NOT RUN — executor unavailable

Checkpoint 6 cloud-test exception: APPROVED BY OPERATOR

No Checkpoint 7. No trading, scheduler, broker, model, budget or strategy change.
Only the dashboard/inbox service may restart. Control A remains Release N,
fingerprint `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.

## Preflight and precise scope

Live Firm Lab DB is `robinhood-diagnostics/firm_lab/firm_lab.db`; SHA-256 before
deployment `b06cca62dcd3775c30cc08197408c1f2db99b1a9cef01d9aa0ee0aae8cf44164`.
SQLite integrity passes, mode BUILD_OBSERVE, registry empty, 26 research tables.
No feature tables yet. All five existing overlay files match pre-Checkpoint-6
source exactly. Primary runtime has no Firm Lab package.

Use the reviewed manual CLI from the development tree for in-place additive
migration/generation. No database replacement, network calls or scheduled task.
23 existing instruments × latest 30 stored sessions; explicit retrospective
cutoff `2026-10-03T22:00:00Z`. Expected calculation hash:
`45b4c2ab719f13dd17cb735118792adc9bc3f8f872466ccba0c2cba3196e3926`.

Install only these read-only projection files into the separate dashboard overlay:

- agents/desk/feature_explorer.py
- agents/desk/firm_lab_page.py
- agents/desk/frontdoor.py
- agents/desk/preview.py
- agents/static/agent-desk.css
- firm_lab/view.py
- firm_lab/research_features/__init__.py
- firm_lab/research_features/types.py
- firm_lab/research_features/stored_payload.py
- firm_lab/research_features/view.py

Write-capable generation machinery remains a deliberate development-tree command,
not dashboard code. Existing overlay files beyond this list are untouched.

## Deployment discrepancy resolved before installation

The accepted nearest-level metric covers both projections: VTI on September 3
selects extension 1.272. It is not the separately requested nearest retracement.
A UI-only correction sorts already-recorded retracement distances, requires all
five recorded pairs, and never recomputes a feature on GET. Missing, null or
invalid operands return unavailable. No change to 222 definitions or calculation
hash. Two regression tests reproduced failures before passing.

Fresh independent delta review found one Important paired-null omission, fixed
fail-closed with RED→GREEN evidence. No core review repeated. Reviewer checked
only UI/test delta; live data, deployment and full-suite verification remain
executor responsibilities. Signed distances and malformed values were independently
probed; no new generator imports or writes. Test coverage beyond these cases is
a minor deferred item, not permission to relax missingness.

## Backup and rollback — before mutation

Timestamped SQLite backup, content hashes for all 26 old tables, original daily
plist hash, and full dashboard copy are retained under local diagnostics:
`checkpoint6-deployment-20261003/`. Record file SHA-256 in `preflight.json`.
The SQLite backup must match every old-table hash before generation starts.

Rollback UI: copy the five pre-existing UI/projection files from
`dashboard-before/`; move the newly installed explorer and research_features
projection directory into the diagnostics folder. Restart only
`com.openai.robinhood-inbox`. Do not touch daily/maintenance/proxy services.
Keep derived research tables if ignored by the old UI. Restore the research DB
only after confirming no later writes, using SQLite backup from the verified
pre-deployment backup into the research DB. Never restore into `data/agent.db`.

Post-deploy verification must pass before closure. Accepted unavailable FOMC
aggregate coverage and grouped nontechnical missing reasons remain unchanged.
