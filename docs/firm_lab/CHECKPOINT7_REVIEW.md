# Checkpoint 7 — independent review record

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

Two fresh reviewers, who had not seen the work being written, read the modeling laboratory at commit `3abb5dd`
(2026-10-03). One looked for information leaking from the future (labels, features, splits, preprocessing, tuning,
combiners). The other looked at statistics, model selection, the networks, hidden trade rules, isolation, the registry
and the claims in the documents. They worked on a read-only copy, ran their own experiments, and changed nothing.

Every important finding below got a regression test that fails on `3abb5dd` (recorded run: 25 failed, 16 errors) and a
repair (commits `4cad8b2`, `1ac2b17`). The tournament was then rerun under plan v2. A third fresh reviewer then verified
the repairs against the stored v2 report; its findings were repaired in `1e57231` under plan v3 and the tournament was
run again with no prediction changed. A fourth fresh reviewer read only the v3 changes; its six minor points were
repaired in `7792a2f` under plan v3.1 and the closing run (`de322bfd…`) again changed no prediction and no status. No
critical or important finding is deferred.

What "fails on `3abb5dd`" means, exactly. Seven of the regressions fail there on behaviour: the old code runs and gives
the wrong answer (A1 the zero count, A3, B13, B14/B15, A7/B16, B7, B8). The others fail because the old code has no
way to express the rule under test (there was no batch interval, no list of baselines, no gate record to be missing):
that shows the rule is new, not that the test reproduces the defect. For those, the defect itself is on record in the
reviewers' own experiments, quoted below.

## What the leakage reviewer found sound

No leak of future information into features, training, tuning or combiners. Evidence:

- **Labels and features.** Feature values recomputed from closes up to T match the stored ones; labels match closes
  T..T+h. With every close after a date rescaled and every later SEC and macro row deleted, all 69 recomputed
  snapshots at or before that date kept their stored digest; the control one session later changed. All 8,694 stored
  snapshots have their newest input at or before their own close.
- **Time view.** Every close is relabelled to exactly its own exchange close; SEC and macro rows to exactly their
  acceptance or publication time. Sector mappings and corporate actions are dated 2026-10-03 and are never eligible
  historically.
- **Splits.** For every block and target the last training label closes one session before the block begins;
  development labels end before the holdout starts; every inner block is purged.
- **Preprocessing, tuning, early stopping, combiners, baselines.** With all labels after a training window and all
  later feature rows randomised, predictions, chosen configurations and inner scores were bit-identical for all 20
  specifications tried; stacker weights, ensemble outputs, meta-label scores and recalibrated probabilities likewise.
- **Determinism.** Refits in a new process reproduced stored predictions with maximum difference 0.0.

## Findings and what was done

| # | Finding | Severity | Repair | Regression |
|---|---|---|---|---|
| B1 | The "90% intervals" and the p-values fed to Holm were not what they were labelled: the moving-block bootstrap (block = one horizon) is anti-conservative at this sample size, and its tail share could be exactly 0. | Critical | Student t interval on batch means two horizons long; no interval or p-value below three batches (plan v2 #1). | `test_a_no_information_series_is_called_positive_about_as_often_as_the_interval_says`, `test_no_interval_and_no_p_value_is_given_below_three_batches` |
| A1, B4 | The strongest baseline was scored on fewer sessions than the candidates (104 of 131). | Important | A session a model does not rank counts as 0 for it; every mean, fold result and paired difference covers every session (v2 #2). | `test_a_session_a_model_does_not_rank_counts_as_zero_for_that_model_everywhere`, `test_a_candidate_is_compared_with_a_baseline_over_every_session…` |
| B2 | The one CHALLENGER (CatBoost, 20-session) was fragile: it passed against one of two near-tied baselines and not the other, and was shown without selection-bias caveats. | Important | A challenger must beat every naive baseline (v2 #3); best-score rows carry "highest of N", the holdout number and the gate label. | `test_a_challenger_must_beat_every_naive_baseline…`, `test_the_report_counts_the_windows_that_are_predicted…` |
| B3 | The Holm family was the candidates of one table, not every registered model of the target as the plan says. | Important | Family = every registered model that ranks the label: 16, 55 and 16 tests (v2 #4). | `test_the_holm_family_of_a_label_is_every_registered_model_that_ranks_it` |
| B5 | The gating network escaped the sufficiency gate (registered with 0 parameters), and a missing gate record counted as a pass. | Important | The gate covers the gating network and combinations holding a failed network; a missing record raises (v2 #5). | `test_every_result_fitted_as_a_network_is_gated…`, `test_a_model_that_fails_the_gate_is_experimental…` |
| B6 | Gate-failing networks were REJECTED where the plan says EXPERIMENTAL. | Important | The gate is applied first (v2 #5). | same |
| B7 | The page raised on a partial or older report and took the Firm Lab page down. | Important | The section degrades to a notice; the projection refuses an incomplete report. | `test_a_partial_or_malformed_stored_report_never_takes_the_page_down` |
| B8 | After a rerun the page would count both runs' models together. | Important | Registry rows carry their run; rows of another run, or of none, are not counted. The rerun was also made on a clean copy of the feature history. | `test_registry_rows_of_another_run_or_of_no_run_are_not_counted…` |
| B9 | Registry status contradicted the report for risk and quantile rows (25 registry rows were registered as unjudged diagnostics; 14 of them had a different status in the report). | Important | Registry rows take the status and role the report gives (v2 #9). | `test_the_registry_says_about_a_risk_or_quantile_model_exactly_what_the_report_says` |
| B10 | Window counts flattered the evidence ("about 29 independent 10-session windows"). | Important | The report and page count predicted sessions: 13 development and 5 holdout windows of 10 sessions; batches are shown beside every interval. | `test_the_report_counts_the_windows_that_are_predicted…`, page test |
| B11 | "Best" rows favoured gate-failed networks without saying so; the classification bar (base rate) was weaker than a coin flip. | Important | Gate label and holdout beside every best score; a coin-flip baseline; classifiers must beat both (v2 #7). | same, `test_a_forecast_that_is_constant_within_each_fold_has_no_ranking_skill_by_auc` |
| A2 | A status rule changed after results were seen with no new plan version. | Important | Plan v2, section 12: every change with its reason and direction; `cli verify` checks a stored report against the tree. | `test_no_calculator_reads…and_the_documents_say_what_the_code_does`, `test_the_stored_report_can_be_checked_against_the_code…` |
| A3 | Stacker and gate learned weights from inner refits that were constant. | Minor | No learned weight for a member constant in the inner block (v2 #11). | `test_the_stacker_gives_no_learned_weight_to_a_member_that_was_constant…` |
| A4, B12 | The gate counted the whole training window, not the sessions gradient steps used. | Minor | It counts the latter (112 of 165 in the last fold). | `test_every_result_fitted_as_a_network_is_gated…` |
| A5 | The gate's breadth read holdout labels. | Minor | Development sessions only, per label. | `test_nothing_measured_before_the_fits_reads_a_holdout_label` |
| A6 | Sequence networks got no missing-value flag (plan section 3). | Minor | They get it (v2 #10). | `test_a_sequence_network_gets_the_same_missing_value_flags…` |
| A7 | The same model identity with different content was silently ignored. | Minor | It raises; a run's rows are named by the run. | `test_the_registry_refuses_a_different_record_under_the_same_identity…` |
| A8 | Earnings-event rows carry two fields linked from a later filing. No calculator reads them. | Minor, latent | A test holds every calculator to not reading them. The time view is unchanged (rebuilding it would not change a feature). | `test_no_calculator_reads_a_field_that_was_linked_from_a_later_filing…` |
| B13 | PR-AUC and the top/bottom spread depended on row order under ties; pooled AUC gave a constant forecast 0.47. | Minor | Order-free; AUC by block (v2 #12). | `test_tied_predictions_give_the_same_answer_in_any_row_order` |
| B14, B15 | Edge cases of the Fibonacci and loss rules (one reference model, a tie, an unscored holdout). | Minor | Handled (v2 #8). | `test_the_rules_do_not_answer_yes_or_reject_on_missing_or_tied_evidence` |
| B16 | Registry gaps: a forbidden status inside `status_by_target`; INSERT OR REPLACE could overwrite an append-only row; empty hyperparameters for combinations. | Minor | Refused; trigger added; weights and gate notes recorded. | registry test above |
| B17 | Claims untrue of the code: "159 descriptors used" (140 offered to a model, 113 ever available); "sector" set is trailing returns relative to VTI; a hard-coded zero; two docstrings; an unchecked export folder; "15" twenty-session windows. | Minor | Each corrected; the strict point-in-time count is now measured from the time view (0 closes). | report and review tests |
| B18 | Diagnostics closest to a rule: threshold counts called "candidates"; examples shown without the rule that picked them; a "champions" key; a column that could read as a go signal. | Minor | Renamed and labelled; the page states how examples were picked. | page test |

## Known and accepted, with reasons

- **The holdout was read twice.** Once by the first run and once by the rerun. It is disclosed in the plan, the
  report, the page and the closure report.
- **Inner tuning sees fewer descriptors than the final fit in late blocks.** The train-only availability filter keeps
  69 descriptors in the inner window of the last blocks and 85 to 92 in the outer one, because fundamentals and event
  descriptors exist only late. A configuration is therefore chosen on a slightly different model than the one refitted.
  This is not leakage; it is a consequence of fitting everything on training rows only. It affects every tuned family
  alike.
- **A combiner trains on the inner predictions of members whose configuration was chosen on the same inner labels.**
  Mildly optimistic for the combiner, the same for all members. The combinations are diagnostics and are all REJECTED
  or EXPERIMENTAL.
- **The batch interval assumes batch means are roughly normal and independent.** With 3 to 6 batches that is a strong
  assumption. Under a Gaussian moving-sum series it rejects about 6% at nominal 5% (a regression test holds it under
  7.5%). That is not the worst case: see V1 below. It is honest about width, not powerful.

## Verification review (commit `93e2046`, stored v2 report `4794d1f4…`)

A third fresh reviewer recomputed the stored result independently and attacked the repairs.

**Confirmed.** All 66 table rows recomputed with the reviewer's own rank correlation, interval, Holm and status code:
0 mismatches (means, fold results, interval bounds, ranked-session counts, batch counts, Holm values, statuses). Risk,
quantile and classification rows: 0 mismatches. No CHALLENGER or ELIGIBLE_FOR_FUTURE_REVIEW anywhere, and both remain
reachable: a synthetic strong 5-session model reaches ELIGIBLE_FOR_FUTURE_REVIEW through the same code. All 13 gate
records follow the plan's formula. All 106 registry rows carry the report's run, plan and code hash and agree with the
report. With every label from the first holdout-adjacent session on replaced, breadth, stacker weights, gate notes,
sufficiency records and all 84 model-blocks checked were bit-identical. The page rendered the real report in full;
659 injected markup strings were all escaped; no action wording; one status style.

| # | Finding | Severity | Repair (plan v3) | Regression |
|---|---|---|---|---|
| V1 | The batch interval is still anti-conservative for rankings that persist across sessions: on real labels a no-information ranking with fixed instrument identities had its interval above zero 8.5% to 11.5% of the time on the 5-session label (development), about 7% on the 10-session label. "Worst case" was the wrong description. No stored status depended on it. | Important | A challenger must also beat its own predictions with instrument identities shuffled, an exact test for that case (v3 #13); the description is corrected. | `test_a_ranking_that_persists_by_chance_is_caught_by_the_identity_shuffle_where_the_interval_alone_is_not`, `test_the_identity_shuffle_is_the_mean_rank_correlation_of_the_shuffled_predictions`, `test_a_challenger_must_also_beat_its_own_predictions_with_identities_shuffled` |
| V2 | The page could still raise: an integer too large to convert (a hand-edited or corrupt stored report) gave OverflowError. | Important | Caught in the number formatter, the section guard and the projection. | `test_an_inherited_gate_row_says_so_and_a_huge_number_cannot_take_the_page_down`, fuzz value added |
| V3 | The zero rule was not applied to the top-minus-bottom spread, the inner tuning score, or a fold with nothing predicted. | Minor | Applied (v3 #14). The strongest baseline's 10-session spread is +1.13% over all 131 sessions, not +1.42% over 104. | `test_the_zero_rule_also_covers_the_spread_the_tuning_score_and_a_fold_with_nothing_predicted` |
| V4 | The record "25 failed, 16 errors" did not say which regressions failed on behaviour and which on a renamed interface. | Minor | Stated at the top of this record. | — |
| V5 | The exported file had no protection against INSERT OR REPLACE; `verify` wrote triggers into the file it checked. | Minor | Exports are protected; `verify` reads only (v3 #16). | `test_an_exported_file_is_append_only_and_checking_a_file_never_changes_it` |
| V6 | The 5-session LightGBM and XGBoost rows showed "Holm-adjusted p 0.054 / 0.060" without the level or whether it was met. | Minor | The reason names the level, met or not met, the batch count, and that it does not by itself make a challenger. | end-to-end family test |
| V7 | Three statements in the documents were wrong or not yet true (a closure report that did not exist yet; "28 rows"; "5% to 6%"). | Minor | Corrected; `CHECKPOINT7_CLOSURE.md` lists every moved status. | document test |
| V8 | The Holm family counted two identical models twice and its description claimed more than the code did. | Minor | Identical results count once (v3 #15): 16, 51 and 16 tests. | end-to-end family test |
| V9 | A combination's inherited gate row was shown with its member's parameter count. | Minor | Shown as inherited. | page test above |

**On the 5-session LightGBM and XGBoost holdout result.** Holdout mean rank correlation +0.123 and +0.108; five batch
means all positive; Holm-adjusted p 0.054 and 0.060 in a family of 16, below the plan's 10% level. The reviewer's
fixed-identity permutation test agrees in size (0.28% and 0.53% unadjusted). It is one result, not two: the two series
correlate 0.92. On development sessions neither clears the gates (LightGBM's interval includes zero and its
identity-shuffle p is 0.053; XGBoost is below the strongest baseline), so the statuses are EXPERIMENTAL and REJECTED.
The holdout is 11 non-overlapping windows and has been read by every run. It is recorded as the one observation worth
looking at again when more sessions exist, and as nothing more.


## Delta review of plan v3 (commit `f6f605c`, stored v3 report `5a1c9af9…`)

A fourth fresh reviewer read only the v3 changes. **No critical or important finding.**

**Confirmed.** The identity-shuffle shortcut is exact: re-ranking the permuted predictions from scratch for every draw
differed by at most 7.5e-17, ties and zero sessions included. All 43 stored p-values reproduced bit for bit. The
direction of the permutation is valid and the p-value formula is right. Against real development labels with random
fixed rankings, the pair of gates rejects 5.3%, 4.0% and 1.8% for the 5-, 10- and 20-session labels at nominal 5%
(the interval alone: 12.1%, 7.1%, 4.2%). The gate fails closed and cannot promote. Between the v2 and v3 reports no
mean, fold result or status moved in any of the 66 table rows; what moved was the spread of the seven rows that do not
rank every session, the 10-session family size (55 to 51), reason strings, and new fields. All 212 stored prediction
sets are identical. The four merged Holm rows have bit-identical predictions. `verify` leaves the file byte-identical;
an exported file refuses every write to a stored identity. 43,320 hostile single-leaf mutations of the real report:
no exception escaped the page.

| # | Finding (all minor) | Repair (plan v3.1) | Regression |
|---|---|---|---|
| D1 | A part in which a model predicted nothing made report assembly raise (not reachable with this data). | A part of zeros, with no error or loss; a classifier without a loss has not passed the loss gate. | `test_a_part_with_nothing_predicted_is_a_part_of_zeros_not_a_crash` |
| D2 | The identity gate was decided inside its own Monte Carlo error: with 2,000 shuffles four rows changed sides across 20 seeds. | 100,000 shuffles. | `test_the_identity_gate_does_not_turn_on_the_luck_of_the_shuffles` |
| D3 | The gate accepted values that are not p-values (a negative number, a boolean). | Only a real number above 0 and at most 1. | `test_the_identity_gate_accepts_only_a_p_value_and_a_partly_predicted_session_gets_none` |
| D4 | The Holm level printed and the level used were two constants. | One. | `test_the_holm_level_shown_is_the_level_used_and_a_dataset_row_cannot_be_quietly_replaced` |
| D5 | A different dataset row under a stored identity was silently ignored. | It is an error; the same row again is ignored. | same |
| D6 | A partly predicted session was zeroed by the shuffle test and scored on its finite pairs by the mean. | Such a model gets no p-value. | D3's test |

What the reviewer says the identity shuffle does **not** protect against, recorded here as a limit of the method: it is
conditional on the one realised history and draws its power from 22 instruments, not from time; it treats instruments
as exchangeable; it is not adjusted for the 43 candidates tried; it does not cover choices made across the runs.

The v3.1 repairs were not themselves read by a further reviewer. They are six small changes, each held by a regression
that failed on `f6f605c` (`delta_regressions_on_f6f605c.txt`: 4 failed), and the closing run was compared with the v3
run row by row: 106 of 106 prediction hashes identical, no status changed, no number moved other than the
identity-shuffle p-values (now on 100,000 shuffles; no row changed sides of the 0.05 level).
