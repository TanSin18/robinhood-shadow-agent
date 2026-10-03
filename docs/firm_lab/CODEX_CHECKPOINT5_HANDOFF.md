# Checkpoint 5 — Codex continuation

## 2026-10-03 16:04 ET — Storage foundation; checkpoint NOT complete

Owner: Codex. Development branch: `codex/checkpoint5-macro`.
Base: `claude/firm-lab-foundation` at `3fdf450e3f51ff221d1d5beb9e399de2f6ea5ce7`.
No merge, deployment, service restart, registration or trading change.

### Where Claude stopped

Checkpoint 4 is closed. Claude's last commit captures raw official macro samples;
it does not parse them into validated macro facts. The installed Firm Lab database
has no macro observation/event tables. Older root HANDOFF.md and primary review
notes describe September work and are not the current Firm Lab milestone.

### Fresh preflight

- Control A release N source fingerprint:
  `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
- Daily service loaded, last exit 0, 60-second schedule, normal off-session skips.
  Not running between ticks is not a stopped service. No restart performed.
- No `STOP_TRADING` file. Installed `options_buys_paused()` returns true.
- Firm Lab read-only inspection: BUILD_OBSERVE; experiment registry empty; no
  order/fill/position/account tables. No official database writes by this work.
- Existing capabilities remain SEC filings and earnings AVAILABLE; fundamentals
  PARTIAL_EXISTING; VTI, Treasury and composite total-return rulers AVAILABLE.
- Macro regime, sector, ML and options strategy remain NOT_STARTED. No capability
  is promoted merely because the new schema or synthetic tests exist.
- October research stop remains in force. Real execution remains disabled.

### Implemented on the branch only

`firm_lab/macro.py` is an opt-in, standard-library-only research domain:

- Separate macro observations and event tables in an isolated Firm Lab database.
- Required content hash verified against source bytes; authoritative source/host
  and series/unit checks; secret-bearing provenance URLs refused.
- Exact offset-aware publication/source/ingestion timestamps. Ambiguous dates,
  impossible values, future timestamps and future realized periods are rejected.
- `known_at = max(publication, source, ingestion)`. This is **local availability**,
  not a claim that we collected historical releases at their original release time.
- Serialized revision checks and append-only insertion APIs. Repeated captures
  preserve the first stored ingestion/known time. Conflicting or skipped local
  revisions are rejected rather than overwritten or guessed.
- Version numbers describe the local append chain. Version 0 does **not** prove
  an observation is the original economic release. Source parsers must establish
  initial/revised vintage identity from authoritative publication evidence.
- Historical reads select the latest version known by the supplied instant.
- Calendar records distinguish scheduled and actual publication. Future scheduled
  events can be stored, but cannot carry released values. Consensus must remain
  UNAVAILABLE. No derived signals, classification, LLM, network or execution path.

This is storage/validation infrastructure, **not a validated live macro feed**.
No data or schemas were installed into the live research database this turn.

### Tests and review

Interpreter: the primary project's existing `.venv/bin/python`.
Working directory: the isolated `robinhood-live-rehearsal` worktree.

Commands:

```sh
python -m pytest -q tests/test_firm_lab_macro.py
python -m pytest -q --tb=short
```

- Baseline before changes: **899 passed, 1 failed**, 27 warnings, 54.25 seconds.
- Macro tests: **40 passed**. Synthetic fixtures only, no credentials or real accounts.
- Full suite before the final review fix: **938 passed, 1 failed**, 27 warnings.
- Final full suite: **939 passed, 1 failed**, 27 warnings, 51.94 seconds. The only
  failure is the same pre-existing installed-isolation failure below; not an
  all-green result and not installed-operation proof.
- Existing failure: `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`;
  installed Codex reports `configWarning`, rejected by the unchanged isolation guard.
- Independent read-only review found a future-period actual-event gap. Added a
  failing regression, fixed the validator, and verified all 40 focused tests pass.
  No deferred minor findings. Review did not assess unimplemented collectors/UI.

### Keep Codex maintenance separate

Status: **PREPARED_AND_PROVEN_NOT_INSTALLED**.
`claude/codex-path-fix` at `ca4aacf` contains executable discovery and the
`features.view_image` compatibility correction. Its existing isolated native
evidence reports 29 focused / 873 full tests passing. Those are historical
maintenance-tree results, not this branch's results. The next separately approved
Control A maintenance release must include it; do not cherry-pick it into macro
work or relax the isolation guard to silence the baseline failure.

### Next permitted work — complete Checkpoint 5, then STOP

1. Source-specific parsers and validated fixtures for Fed/FOMC, Treasury, BLS and
   BEA/FRED. Preserve original series identities, seasonal adjustment/base units,
   released and revised values, and publication evidence. A date-only vintage or
   BLS latest-value JSON is not sufficient evidence for an exact release time.
   Do not invent timing, economic vintages or consensus. GDP is optional and gated.
2. FOMC range/change/meeting parsing; CPI/PCE/payroll/unemployment event association;
   event/observation cross-checks. No macro score. Verify source licensing and
   current official documentation before parser assumptions become policy.
3. Manual research-only ingest from validated captures, with rejection receipts;
   inspect real rows before capability promotion. Keep market volatility UNAVAILABLE.
4. Focused official-doc comparison: Massive vs Alpaca SIP; Databento only if a
   concrete depth hypothesis warrants it. Verify price/licensing/storage terms.
   Recommendation must be evidence-backed or NO_PROVIDER_SELECTED. No purchases,
   credentials, subscriptions or live intraday activation.
5. Read-only macro readiness/events UI, permanent factual-only label, honest
   provenance/revision/known-at display. No raw payload dump or inferred sentiment.
6. Full tests, current-state recheck, sanitized GitHub sync and explicit final
   Checkpoint 5 report. Research/UI deployment is permitted by the specification,
   but only after validation; never restart the daily runner.

### Rulings made in this slice

- The pre-existing installed-isolation failure stays visible and separate because
  the operator explicitly forbids installing the prepared maintenance patch in
  Checkpoint 5. Cost: this branch cannot claim a fully green native suite until
  that independent maintenance issue is resolved.
- Reject date-only publication evidence in this initial storage contract. Cost:
  some captures remain unusable until a cited publication-time source is joined.
  This intentionally prevents backdating; no source gets an AVAILABLE claim yet.

### Return criteria for Claude or another Codex session

Read this entry and the operator's full Checkpoint 5 spec first. Continue on this
branch; inspect Git status before edits. Do not repeat raw capture unnecessarily,
do not overwrite the live research DB, and do not activate a strategy. Preserve
the frozen Treasury methodology and the separate maintenance release boundary.
