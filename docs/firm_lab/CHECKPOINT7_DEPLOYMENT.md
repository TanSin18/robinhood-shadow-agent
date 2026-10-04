# Checkpoint 7 — deployment note

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

## State at the time of writing (2026-10-04)

**NOT DEPLOYED.** The research, validation and review were done in the cloud container. The Mac was reachable until
2026-10-03 22:37 ET and not on 2026-10-04 when the work was ready (the link was tried at 08:40, 09:10, 09:55, 10:00 and
10:05 ET and each time the device was not connected), so nothing of Checkpoint 7 has been written to the Mac: no
overlay file, no laboratory file, no capability row. The Firm Lab page on the Mac is as Checkpoint 6 left it.

The operator's order of 2026-10-04 09:51 ET accepts the scientific result and fixes the deployment scope: the
laboratory file, the six read-only dashboard files and the eight capability rows below, and nothing else. The source
to deploy is commit `35d6656`. A bundle with exactly these files and their sha256 sums is staged in the session.

Last checks made on the Mac (2026-10-03 22:36 ET, read-only):

| | |
|---|---|
| Control A fingerprint | `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`, 240 files, match |
| Stop file | none |
| `daily.log` | being written by the one registered service |
| Live research database | sha256 `8611da11beda1d97012c9ea773a3c86777805ce28a526e4785148365eaa27b14`, unchanged since the snapshot was taken |
| Dashboard overlay | the four files this checkpoint changes equal the Checkpoint 6 source exactly |

The end-of-checkpoint Control A check required by the handoff has to be repeated when the Mac is reachable.

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
   | `agents/static/botfolio-theme.css` | `0b8b15490400bd79d59a3ea877ee8955f2e6292f80eb442c732bdd6a405137c9` | replaces `3aaa9193…` |
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
   curl -s http://127.0.0.1:8765/firm-lab | grep -c "MODEL RESEARCH ONLY" | tee ~/LocalProjects/robinhood-diagnostics/checkpoint7-modeling-20261003/page-check.txt
   cd ~/LocalProjects/robinhood-diagnostics/checkpoint7-modeling-20261003/src && ~/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q -p no:cacheprovider 2>&1 | tee ../native-tests.txt
   ```

   `src/` is a plain export of commit `35d6656` placed there at deployment; the suite does not need a git checkout.
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
