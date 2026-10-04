# Claude status and questions

## 2026-10-04 — Checkpoint 7 research, validation and review complete; deployment to the Mac outstanding; STOP

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

Until these are done the checkpoint is not closed.

### Questions for the operator

None that block. One thing to know: the 5-session LightGBM and XGBoost holdout result (closure report, "The one
observation to revisit") is the only place where anything looked like a signal, and it does not meet the rules. It
should not be acted on.
