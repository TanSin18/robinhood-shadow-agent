# Checkpoint 7 — deployment note

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

## State (2026-10-04 11:31 ET)

**DEPLOYED AND VERIFIED.** Installed on the Mac at 11:30 ET (15:30 UTC) under the operator's order of 09:51 ET. The
operator restarted the dashboard and ran the page check and the native suite at 11:34 ET; the final Control A recheck
was at 11:40 ET. Operator-step evidence is at the end of this note.

| Step | Evidence |
|---|---|
| Control A before | fingerprint `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`, 240 files, match; no stop file; `daily.log` being written (15:28 UTC) |
| Bundle on the Mac | `robinhood-diagnostics/checkpoint7-modeling-20261003/bundle/`; every file checked against its sha256 |
| Overlay before | the four existing files equal the Checkpoint 6 source (`b092f1ea…`, `54449760…`, `3aaa9193…`, `cf317b14…`); backed up to `overlay-backup/` with their sums |
| Six overlay files | installed; each equals the sha256 in the table below. `firm_lab/modeling/` and `firm_lab/modeling_capability.py` are not in the overlay |
| Laboratory file | `robinhood-diagnostics/firm_lab/firm_lab_modeling_lab.db`, sha256 `2d383629a582a0a782a4969533f1c7ae17720471a603961c5275598ee83bc6ce` |
| Research database backup | `research-db-backup/firm_lab.db.before-checkpoint7`, sha256 `8611da11beda1d97012c9ea773a3c86777805ce28a526e4785148365eaa27b14` (unchanged since the modeling snapshot was taken) |
| Capability rows | written on a copy by `firm_lab.modeling_capability.record` from the stored report `de322bfd…`, then put in place. Table-by-table comparison of all 31 tables and the schema: only `data_capabilities` (40 → 44 rows) and `events` (52 → 57) differ. The 52 earlier events are preserved as a prefix; the 5 appended are capability-status events. New rows: `research_modeling`, `deep_learning`, `transformer_models`, `rl_policy`. Changed rows: `ml_ranker` (NOT_STARTED → RESEARCH_ONLY) and the detail text of `macro_regime`, `portfolio_optimizer`, `options_strategy` (still NOT_STARTED) |
| Research database after | sha256 `f58b1d02910c5e3608a25335392f331c5d5bbfd968f29d07c83a444c4d903015`; integrity check ok; BUILD_OBSERVE; experiment registry empty; no order, fill, position, account or cash table |
| Live capability states | research_modeling, ml_ranker, deep_learning, transformer_models = RESEARCH_ONLY; macro_regime, portfolio_optimizer, options_strategy, rl_policy = NOT_STARTED |
| Page from the installed overlay | rendered on the Mac from the overlay's own code against the live files (no server): the laboratory section is present with 106 registry rows, the permanent warning once, "No validated trading model exists", strict point-in-time samples 0, the retrospective count, Fibonacci INCONCLUSIVE, networks insufficient data, the holdout disclosure, ablation, calibration, disagreement and explainability; no action wording; not the degraded notice |
| Read-only | the research database and the laboratory file have the same sha256 after the page was rendered |
| Control A after | fingerprint `901f7606…c876`, 240 files, match; no stop file; `daily.log` being written (15:30 UTC). Nothing in the registered runtime was written; `com.openai.robinhood-daily` was not restarted |
| Source for the native run | `checkpoint7-modeling-20261003/src/`, a plain export of commit `7292a4d` (its overlay files are identical to `35d6656`) |

The operator ran the three commands once at 11:27 ET, before the install: the dashboard restarted, the page check
wrote 0, and the test command had no `src/` folder. Harmless. They were run again at 11:34 ET, after the install.

## What deployment consists of

Everything is read-only dashboard material or research metadata. Nothing is a trading model, a strategy score, an
optimizer, a promotion or a fill. Only `com.openai.robinhood-inbox` (the dashboard) restarts, and the operator does
that. `com.openai.robinhood-daily` is not touched.

1. **Laboratory file** → `~/LocalProjects/robinhood-diagnostics/firm_lab/firm_lab_modeling_lab.db`
   (1,396,736 bytes, sha256 `2d383629a582a0a782a4969533f1c7ae17720471a603961c5275598ee83bc6ce`). A new file beside the
   research database. It holds the report and the registry rows; no feature row, sample or prediction.
2. **Six overlay files** → `~/LocalProjects/robinhood-dashboard-releases/agent-desk.3K4Fam/`, after backing up the
   four that exist to `~/LocalProjects/robinhood-diagnostics/checkpoint7-modeling-20261003/overlay-backup/`:

   | File | sha256 | |
   |---|---|---|
   | `agents/desk/firm_lab_page.py` | `1912d247ee4aaa1c9b70d51160bdd1e7e7f11f93e086b50361a3fbe28bbe81a3` | replaces `b092f1ea…` |
   | `agents/desk/modeling_lab.py` | `1907872e727990fe434eaebc3236e420a9512ddb3e24fe5e6328d12a3f6eadc8` | new |
   | `agents/static/botfolio-theme.css` | `17146bd3fee72b6ea369c721e770e26779a1b0592e81322e65905d3d2cdc6e67` | replaces `3aaa9193…`. First installed as `0b8b1549…`; one property (`overflow-wrap` on the opening list) was added after the phone-width check |
   | `firm_lab/view.py` | `1518b31a3e220f925b64096b4d017eaf2fd562a22e469283f5a6728463baa0a5` | replaces `54449760…` |
   | `firm_lab/modeling_view.py` | `edd7e0e50e69a101e75abc49273ab16439946ed3086e7c1fab3ce1b8ace07699` | new, standard library only |
   | `firm_lab/capabilities.py` | `6f29885976204a5f6fbc82c737671dab1821139014663f3a22e6f3aed1c93f9d` | replaces `cf317b14…`; adds the `RESEARCH_ONLY` state |

   The `firm_lab/modeling/` package is **not** installed in the overlay. The page reads a stored report and loads no
   model code; a test holds that.
3. **Eight capability rows** in the live research database, written by `firm_lab.modeling_capability.record` from the
   stored report: `research_modeling`, `ml_ranker`, `deep_learning`, `transformer_models` = `RESEARCH_ONLY`;
   `macro_regime`, `portfolio_optimizer`, `options_strategy`, `rl_policy` = `NOT_STARTED`. Procedure as in earlier
   checkpoints: back up the database, change a copy, confirm that only `data_capabilities` and appended capability
   events differ, then put the copy in place. BUILD_OBSERVE, an empty experiment registry and every other table must
   be unchanged.
4. **Operator**: restart the dashboard, look at the page, run the native suite:

   ```sh
   launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox
   sleep 5; cd ~/LocalProjects/robinhood-diagnostics/checkpoint7-modeling-20261003 && curl -s http://127.0.0.1:8765/firm-lab -o page.html; grep -c "MODEL RESEARCH ONLY" page.html | tee page-check.txt
   cd ~/LocalProjects/robinhood-diagnostics/checkpoint7-modeling-20261003/src && PY=~/LocalProjects/robinhood-shadow-agent/.venv/bin/python && $PY --version 2>&1 | tee ../native-tests.txt && $PY -m pytest -q -p no:cacheprovider 2>&1 | tee -a ../native-tests.txt
   ```

   `src/` is a plain export of commit `7292a4d` placed there at deployment; the suite does not need a git checkout.
   Record the interpreter (`python --version`), the commit, the command, and passes, failures and warnings.

   Expected native failures, each independent of Checkpoint 7 and none to be worked around:

   - `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`: the
     installed Codex `configWarning`. The guard is not weakened; Codex maintenance stays PREPARED_AND_PROVEN_NOT_INSTALLED.
   - `tests/test_dashboard.py::test_decision_room_links_pending_approval_and_marks_failed_boundary` and
     `::test_historical_pending_proposal_never_claims_no_proposal`: these two issue an approval card at a fixed time
     (2026-09-27 14:30 UTC) with a 10,000-minute expiry and read the page with the real clock, so they pass until
     2026-10-04 13:10 UTC and fail from then on, on any branch (they fail on the Checkpoint 6 commit `3b34b97` too).
     A test defect in the registered dashboard's tests, found on 2026-10-04; not changed here.
5. **Re-verify Control A**: fingerprint, no stop file, the registered service not restarted.

## Rollback

Remove `firm_lab_modeling_lab.db`: the section then says no laboratory run is stored. To go further, copy the four
backed-up overlay files back, remove the two new ones, restore the research database from its backup, and restart the
dashboard. Nothing else is affected. Control A is not involved at any step.

## What must not be deployed, now or by this note

A trading model, a strategy score into the runner, a portfolio optimizer, an automatic promotion, paper fills from
these models, a scheduler entry for the modeling package, or the Codex maintenance fix (PREPARED_AND_PROVEN_NOT_INSTALLED).

## Operator steps and final checks (2026-10-04)

| Step | Evidence |
|---|---|
| Dashboard restart | `launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox`, by the operator, 11:34 ET. No other service |
| Live page | `page-check.txt` = 1; `page.html` saved and checked (`CHECKPOINT7_VALIDATION.md`) |
| Native suite | `native-tests.txt`: Python 3.14.6, 1129 passed, 3 failed, 1 skipped, 27 warnings; the three failures are independent of this checkpoint |
| Overlay as installed | `overlay-installed.SHA256SUMS` in the checkpoint folder; equals the table above |
| Research database | sha256 `f58b1d02…3015` after the page was served: unchanged by reading. BUILD_OBSERVE, experiment registry empty, 31 tables, none that could hold an order, fill, position, account or cash |
| Capability states in use | AVAILABLE, BUILD_ONLY, NOT_STARTED, PARTIAL_EXISTING, RESEARCH_ONLY, UNAVAILABLE. No ACTIVE, PRODUCTION, LIVE or CHAMPION |
| Control A final recheck, 11:40 ET | Release N; fingerprint `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`, 240 files, match; no STOP_TRADING file; `daily.log` written at 15:39 UTC by the registered service, which was not restarted; 3 fills in the registered database as before; Lane B paper accounts empty |
| Codex maintenance | PREPARED_AND_PROVEN_NOT_INSTALLED |

A short record of the installation, with the rollback steps, is on the Mac at
`robinhood-diagnostics/checkpoint7-modeling-20261003/DEPLOYED.txt`.
