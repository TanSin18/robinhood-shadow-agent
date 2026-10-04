# Checkpoint 7 — validation record

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

## Where the work ran

The operator chose the cloud container (2026-10-03). Python 3.11, 2 cores. An isolated research environment
(`/home/claude/modeling-venv`), pinned in `firm_lab/modeling/requirements-research.txt`: numpy 2.4.4, pandas 3.0.2,
scipy 1.17.1, scikit-learn 1.8.0, xgboost 2.1.4, lightgbm 4.7.0, catboost 1.2.10, torch 2.14.1 (CPU),
exchange_calendars 4.13.2. Nothing was installed on the Mac. The container held a copy of the research database
without account data, without the registered database, and without any credential.

## Provenance of the stored result

| | |
|---|---|
| Source | the live research database at sha256 `8611da11beda1d97012c9ea773a3c86777805ce28a526e4785148365eaa27b14`, copied without its stored feature runs to a snapshot, sha256 `a18f0f294108ee00465b894771ebdfefa87af02b588d2703b519279dc7a249a3` |
| Session-time view and feature history | built once by `timeview.py` and `history.py` at commit `3a18f20`; those two files, `targets.py`, `dataset.py`, `splits.py` and `preprocess.py` have not changed since (`git diff 3a18f20 --` those files is empty). 8,694 snapshots, calculation hash `45b4c2ab…3926`, identical to Checkpoint 6. File sha256 `2b788f984883e41808a1a042d9757ffdfb2db7570c4def21d4cd6a8abb4e47a9` |
| Check against Checkpoint 6 | AAPL 2026-09-15: every feature value equal to the deployed Checkpoint 6 value, digit for digit; only the known-at differs |
| Dataset | hash `1dadc0bb5f733755c8a1cf621dd717f88199709af095acb3606007ae3420fe9c`, the same in all four runs |
| Closing run | report `de322bfd1ce6d44cff7a561896a89f52c0092f2db496e029ba84bd3c05f0c79d`, code hash `dc7d5b4085357873e61bd9d7307c61c977a20fb9125cc40357a5b1b5032b63c0`, 424 s, 106 registry rows, 1,248 configuration fits; modeling database sha256 `f4c24be5f8696c0e97791ec223c63d6c3196839f69a7af7c139763513790800f` |
| `python -m firm_lab.modeling.cli verify` | `matches: true`: the stored report and all 106 registry rows were produced by the code in this tree under plan v3.1 |
| Exported laboratory file | 1,396,736 bytes, sha256 `2d383629a582a0a782a4969533f1c7ae17720471a603961c5275598ee83bc6ce`; the report, 106 registry rows, one dataset manifest, one run record; no feature row, sample or prediction |
| Determinism | runs 2, 3 and 4 produced 106 of 106 identical prediction hashes; a reviewer refitted eleven models in a new process with maximum difference 0.0 |

The modeling databases of all four runs and their logs are kept in the container (`/home/claude/c7data/`). They are
research material, not source: they are not in the repository.

## Tests

Commands, from the repository root, with the research environment's Python:

```sh
python -m pytest -q -p no:cacheprovider tests/test_modeling_core.py tests/test_modeling_tournament.py \
  tests/test_modeling_dataset.py tests/test_modeling_isolation_ui.py tests/test_modeling_review.py tests/test_modeling_report.py
python -m pytest -q -p no:cacheprovider
```

| Run | Result |
|---|---|
| Cloud, Checkpoint 6 baseline (`3b34b97`), before any Checkpoint 7 change | 1068 passed, 1 skipped (92 s). The first cloud run of that branch: Codex could not run one |
| Cloud, focused modeling tests (`7792a2f`) | 79 passed |
| Cloud, full suite (`7792a2f`) | **1147 passed, 1 skipped** (225 s). The skip is `tests/test_installed_isolation.py`, which needs the operator's installed Codex |
| Cloud, full suite from a plain source export with no git metadata (`f6f605c`) | 1143 passed, 1 skipped: the suite does not need a git checkout |
| Cloud, modeling tests with torch, xgboost, lightgbm and catboost made unimportable | 63 passed, 1 module skipped (`test_modeling_report.py`, the end-to-end run): what the Mac's environment will do |
| Native Mac, Python 3.14.6, source export of `7292a4d` | **1129 passed, 3 failed, 1 skipped, 27 warnings** (86 s); see below |

After 2026-10-04 13:10 UTC the full suite shows two failures that have nothing to do with this checkpoint:
`tests/test_dashboard.py::test_decision_room_links_pending_approval_and_marks_failed_boundary` and
`::test_historical_pending_proposal_never_claims_no_proposal` issue an approval card at a fixed time with a
10,000-minute expiry and read the page with the real clock. They fail from that moment on every branch, including the
Checkpoint 6 commit `3b34b97` (checked). Cloud at `35d6656`, 2026-10-04 14:00 UTC: 1145 passed, 2 failed (these two),
1 skipped. They are left as they are and reported.

One earlier test was changed: `tests/test_firm_lab_features.py::test_blocked_capabilities_are_unavailable` pinned the
exact set of capability states; `RESEARCH_ONLY` was added to it.

### What the tests prove

- **Labels and features** (`test_modeling_core.py`, `test_modeling_dataset.py`): the label is the excess price return
  over exactly the stated sessions; a label whose window runs past the stored history does not exist; features are
  built without reading a close or a label; nothing after a session can change that session's features; a snapshot
  that is not a session-close view is refused.
- **Splits and tuning** (`test_modeling_core.py`, `test_modeling_tournament.py`): chronological, purged, embargoed;
  no model is fitted on a row it predicts or on a label that overlaps the block; wrecking every label outside a
  training window changes no chosen configuration and no prediction.
- **Statistics and statuses** (`test_modeling_core.py`, `test_modeling_review.py`): hand-checked metrics; a
  no-information series is called positive about as often as the interval says; no interval below three batches; a
  ranking that persists by chance is caught by the identity shuffle; every status rule, including that there is no
  production or live status.
- **End to end** (`test_modeling_report.py`): a whole laboratory run on a small synthetic dataset, its registry, its
  export and the page that reads it; recalibration and stacking learn only from inner blocks; a network refits to the
  same numbers.
- **Isolation and the page** (`test_modeling_isolation_ui.py`, `test_modeling_review.py`): the modeling package cannot
  import a broker, the network or the trading side; nothing on the trading side imports it and nothing schedules it;
  the page shows no action wording, one neutral status style, and survives any malformed stored report.

### Regressions recorded failing before each repair

| Recorded on | File in the container | Result |
|---|---|---|
| `3abb5dd` (before the independent review's repairs) | `review_regressions_on_3abb5dd.txt` | 25 failed, 16 errors, 20 passed |
| `93e2046` (before the verification review's repairs) | `verification_regressions_on_93e2046.txt` | 8 failed, 33 passed |
| `f6f605c` (before the delta review's repairs) | `delta_regressions_on_f6f605c.txt` | 4 failed |

`CHECKPOINT7_REVIEW.md` says which of the first set failed on behaviour and which because the old code could not
express the rule.

## Native Mac run (2026-10-04 11:34 ET, run by the operator)

| | |
|---|---|
| Interpreter | Python 3.14.6, the primary `.venv` (`~/LocalProjects/robinhood-shadow-agent/.venv/bin/python`) |
| Commit | `7292a4d` (`claude/checkpoint7-modeling`), a plain source export at `robinhood-diagnostics/checkpoint7-modeling-20261003/src/`; its code is what is installed in the overlay, except one later stylesheet property |
| Command | `python -m pytest -q -p no:cacheprovider`, from that folder |
| Result | **1129 passed, 3 failed, 1 skipped, 27 warnings in 86.04 s** |
| Skipped | `tests/test_modeling_report.py` (16 end-to-end tests): the native environment has no xgboost, lightgbm, catboost or torch, as intended. Cloud runs them |
| Warnings | 27, all one `DeprecationWarning` from the installed `agents` library (`asyncio.get_event_loop_policy`), as in Checkpoint 6 |
| Output | `robinhood-diagnostics/checkpoint7-modeling-20261003/native-tests.txt` |

The three failures, none caused by this checkpoint:

1. `tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server` — the installed
   Codex emits `configWarning` and the unchanged guard rejects it. The same known failure as in Checkpoint 6. The guard
   is not weakened and nothing is whitelisted. An independent maintenance issue; Codex maintenance stays
   PREPARED_AND_PROVEN_NOT_INSTALLED.
2. `tests/test_dashboard.py::test_decision_room_links_pending_approval_and_marks_failed_boundary`
3. `tests/test_dashboard.py::test_historical_pending_proposal_never_claims_no_proposal`

   Tests 2 and 3 issue an approval card at a fixed time (2026-09-27 14:30 UTC) with a 10,000-minute expiry and read
   the registered dashboard with the real clock. The card expired at 2026-10-04 13:10 UTC, so both fail from then on
   every branch; they fail on the Checkpoint 6 commit `3b34b97` in the cloud too. A wall-clock defect in two tests of
   the registered dashboard. Not changed here: it belongs to a separate, operator-approved repair.

Against the Checkpoint 6 native baseline (1068 passed, 1 failed): 61 more tests pass (the modeling tests that need no
research library), and the two additional failures are the wall-clock tests.

## Live page check (2026-10-04 11:34 ET)

The operator restarted `com.openai.robinhood-inbox` and saved `http://127.0.0.1:8765/firm-lab` to
`checkpoint7-modeling-20261003/page.html` (9.2 MB; the count of "MODEL RESEARCH ONLY" is 1). Checked on the saved page:

- the section `#fl-modeling` is present; it is the full section, not the "could not be shown" or "no run stored" notice;
- "No validated trading model exists" with 43 judged, 28 EXPERIMENTAL, 15 REJECTED; strict point-in-time samples 0;
  all 6,490 samples retrospective; FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE; 13 of 13 network results
  insufficient data; the holdout disclosure in the operator's words;
- model tables with statuses and baselines, the walk-forward design and the holdout block, feature ablation,
  calibration, model disagreement, explainability with its limits, data-sufficiency labels, plan v3.1 and the code hash;
- no BUY, SELL, ENTER, EXIT, OVERWEIGHT or UNDERWEIGHT; no "we recommend", "conviction", "target price" or "position
  size"; one neutral status style; no form, button or script in the section; "Trial 18" nowhere on the page;
- the Firm Lab header still says fills 0 and trial NOT REGISTERED; four capability rows show RESEARCH_ONLY;
- rendered with the deployed stylesheets at 1280 and 390 pixels: 18 tables, 15 folded sections, no horizontal page
  scroll and no element past the right edge outside a table scroller. One long status token overflowed its box at 390
  pixels; a one-property stylesheet fix (`overflow-wrap`) was installed and rechecked. A stylesheet is served from
  disk, so no restart was needed;
- **no database mutation from read-only access**: the research database (`f58b1d02…`) and the laboratory file
  (`2d383629…`) have the same sha256 after the request as before it.
