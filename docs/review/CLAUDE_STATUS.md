# Claude status and questions

## 2026-10-04 19:40 ET — Checkpoint 8 built, reviewed and installed read-only; NOT CLOSED; operator purchase decision required; STOP

`CHECKPOINT 8 = NOT CLOSED`. `OPERATOR PURCHASE DECISION REQUIRED`: Sharadar "Prices — Full History", Personal Use
License, $39 per month or $299 per year. Nothing was purchased, no account was created, no key exists.

Branch `claude/checkpoint8-data-foundation`, from `claude/checkpoint7-modeling` `3978d1b`. No merge to main. No
Checkpoint 9. Codex maintenance stays PREPARED_AND_PROVEN_NOT_INSTALLED.

**DATA READINESS ONLY — NO TRADING MODEL IS ACTIVE.**

- Honest result: no licensed historical bars are stored. Strict point-in-time samples 0 (tier A 0, tier B 0); the
  6,490 retrospective samples of Checkpoint 7 are a separate dataset and are not counted. Every model family is
  INSUFFICIENT. 0 of 25 sufficiency bars are met.
- Built: the sufficiency specification (committed alone, first), the provider decision, a separate append-only
  historical research database with validation, a versioned historical universe, OHLCV feature versions, labels on
  the exact close, dataset contract v2, two sealed holdouts (the Checkpoint 7 holdout is burned and is not reused), a
  readiness report and page, six capability rows.
- FRED and ALFRED removed from the collector and the macro store: their terms prohibit storing the data and training
  models on it without written consent.
- Nine independent reviewers in eight rounds. Every critical and important finding has a regression and a repair; the
  ninth found none in the package. Record: `docs/firm_lab/CHECKPOINT8_REVIEW.md`.
- Installed on the Mac at 19:37 ET: five overlay files, the readiness file, six capability rows. Control A verified
  before and after: fingerprint `901f7606…c876`, 240 files, no stop file, fills 3. `com.openai.robinhood-daily` was not
  touched. Record: `docs/firm_lab/CHECKPOINT8_STATUS.md`.

### For the operator to run

```sh
launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox
sleep 5; cd ~/LocalProjects/robinhood-diagnostics/checkpoint8-data-foundation-20261004 && curl -s http://127.0.0.1:8765/firm-lab -o page.html; grep -c "DATA READINESS ONLY" page.html | tee page-check.txt
cd ~/LocalProjects/robinhood-diagnostics/checkpoint8-data-foundation-20261004/src && PY=~/LocalProjects/robinhood-shadow-agent/.venv/bin/python && $PY --version 2>&1 | tee ../native-tests.txt && $PY -m pytest -q -p no:cacheprovider 2>&1 | tee -a ../native-tests.txt
```

Expected: the page check prints 1. The native suite fails only the three tests that failed at Checkpoint 7 (the two
wall-clock tests of the registered dashboard and the installed-Codex `configWarning` test).

### Questions for the operator

1. Buy one month of Sharadar "Prices — Full History"? If yes: download SEP, SFP, TICKERS, ACTIONS and SP500 into a
   private folder outside any repository. Send no login, key or payment detail.
2. Delete any `fred_*.csv`, `fredapi_*.json` or `alfred_*.csv` capture files.
3. Forward capture of each day's bars before the next open: wanted, and by what means?
4. SEC history: may the bulk path carry its own evidence label? Run the free validation sample now?
5. Remove `robinhood-diagnostics/checkpoint8-data-foundation-20261004/_to_delete/` (nothing licensed in it).

## 2026-10-04 11:40 ET — Checkpoint 7 deployed, natively verified and CLOSED; STOP

CHECKPOINT 7 = CLOSED. The read-only laboratory is live on `/firm-lab`: one laboratory file, six overlay files, eight
capability rows (four RESEARCH_ONLY, four NOT_STARTED). Native suite on Python 3.14.6 at `7292a4d`: 1129 passed,
3 failed, 1 skipped; the failures are the known Codex `configWarning` test and two wall-clock tests of the registered
dashboard, none caused by this checkpoint. Control A final recheck: Release N, fingerprint `901f7606…c876`, 240 files,
no stop file, runner not restarted. No Checkpoint 8. Records: `docs/firm_lab/CHECKPOINT7_CLOSURE.md`,
`CHECKPOINT7_DEPLOYMENT.md`, `CHECKPOINT7_VALIDATION.md`.

Left for the operator to decide, outside this checkpoint: the two wall-clock tests in `tests/test_dashboard.py`
(fixed issue time, 10,000-minute expiry, real clock) now fail on every branch; and the Codex maintenance fix remains
PREPARED_AND_PROVEN_NOT_INSTALLED.

The holdout of Checkpoint 7 is no longer an untouched final test set for future model selection. Future model research
needs a newly accumulated or separately reserved untouched evaluation period, and strict point-in-time inputs.

## 2026-10-04 (earlier) — Checkpoint 7 research, validation and review complete; deployment to the Mac outstanding

Owner: Claude; branch `claude/checkpoint7-modeling`, based on `codex/checkpoint6-features` `3b34b97`. No merge to
main. No Checkpoint 8. Codex maintenance stays PREPARED_AND_PROVEN_NOT_INSTALLED.

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

- Operator decisions of 2026-10-03: session-time retrospective time rule; the accepted Checkpoint 6 calculators over
  all 378 stored sessions in a separate modeling database; the work in the cloud container, nothing installed on the Mac.
- Built `firm_lab/modeling/` (targets, dataset contract, purged walk-forward splits, metrics, model families A to F,
  tournament, status rules, registry, report, CLI), a read-only projection and page section, capability rows for
  research states, the tournament plan and the lifecycle design.
- Ran the tournament four times, each rerun for recorded defects: plan v1, v2 (reporting defects and the independent
  review), v3 (verification review), v3.1 (delta review). No prediction changed across the last three. Closing report
  `de322bfd…`, code hash `dc7d5b40…`; `cli verify` matches.
- Independent review by fresh reviewers in four rounds: `docs/firm_lab/CHECKPOINT7_REVIEW.md`. One critical and
  thirteen important findings, all repaired with a regression first. No leak of future information was found.
- Result: 43 judged candidates, 28 EXPERIMENTAL, 15 REJECTED, none CHALLENGER or ELIGIBLE_FOR_FUTURE_REVIEW. Every
  network is EXPERIMENTAL_INSUFFICIENT_DATA. FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE.
- Cloud suite: 1147 passed, 1 skipped. This is also the first cloud run of the Checkpoint 6 branch (1068 passed,
  1 skipped at `3b34b97`).
- Control A: Release N, fingerprint `901f7606…c876`, verified at the start and at 2026-10-03 22:36 ET; strategy not
  changed; runner not restarted.

### 2026-10-04 09:51 ET — operator accepts the scientific result; deployment order

The operator accepted the Checkpoint 7 conclusion (43 judged, 28 EXPERIMENTAL, 15 REJECTED, none established;
Fibonacci INCONCLUSIVE; networks insufficient data), ordered that the tournament not be rerun, that the holdout be
disclosed as no longer untouched, and that only the research laboratory be deployed. Done since: the page now opens
with what stands (no validated trading model; strict point-in-time samples 0; retrospective count; holdout
disclosure) and labels the highest scores as not recommended models; the closure report and the lifecycle design carry
the holdout disclosure. Commit `35d6656`, pushed. The stored report is unchanged and still verifies. The Mac was still
not connected at 10:05 ET.

A pre-existing wall-clock defect in two registered-dashboard tests surfaced today (see `CHECKPOINT7_VALIDATION.md`).

### Outstanding, and why

The Mac was not reachable when the work was ready (2026-10-04). Not done, and not claimed:

1. Deployment of the read-only laboratory (one file beside the research database, six overlay files, eight capability
   rows). Prepared and described in `docs/firm_lab/CHECKPOINT7_DEPLOYMENT.md`.
2. The dashboard restart (`com.openai.robinhood-inbox` only) and a look at `/firm-lab#fl-modeling`. Operator.
3. The native Mac test run. Operator.
4. The end-of-checkpoint Control A check on the Mac.

Until these are done the checkpoint is not closed. (All four were done later the same day; see the entry above.)

### Questions for the operator

None that block. One thing to know: the 5-session LightGBM and XGBoost holdout result (closure report, "The one
observation to revisit") is the only place where anything looked like a signal, and it does not meet the rules. It
should not be acted on.
