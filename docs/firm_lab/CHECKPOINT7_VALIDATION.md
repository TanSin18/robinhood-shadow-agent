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
| Native Mac | see below |

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

## Native Mac run

**NOT RUN at the time of writing.** The Mac was not reachable from this session on 2026-10-04 (the link dropped
before deployment). The native environment has numpy, pandas, scipy, scikit-learn and exchange_calendars and none of
xgboost, lightgbm, catboost or torch, so the expected native result is the full suite with the end-to-end modeling
module skipped, plus the one known Checkpoint 6 failure
(`tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`, the installed
Codex `configWarning`; Codex maintenance stays PREPARED_AND_PROVEN_NOT_INSTALLED). That is an expectation, not
evidence. `CHECKPOINT7_DEPLOYMENT.md` has the command.
