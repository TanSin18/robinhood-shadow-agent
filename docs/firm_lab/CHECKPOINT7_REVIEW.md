# Checkpoint 7 — independent review record

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

Two fresh reviewers, who had not seen the work being written, read the modeling laboratory at commit `3abb5dd`
(2026-10-03). One looked for information leaking from the future (labels, features, splits, preprocessing, tuning,
combiners). The other looked at statistics, model selection, the networks, hidden trade rules, isolation, the registry
and the claims in the documents. They worked on a read-only copy, ran their own experiments, and changed nothing.

Every important finding below got a regression test that fails on `3abb5dd` (recorded run: 25 failed, 16 errors) and a
repair (commits `4cad8b2`, `1ac2b17`). The tournament was then rerun once under plan v2. No critical finding is deferred.

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
| B9 | Registry status contradicted the report for 28 risk and quantile rows. | Important | Registry rows take the status and role the report gives (v2 #9). | `test_the_registry_says_about_a_risk_or_quantile_model_exactly_what_the_report_says` |
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
  assumption. A regression test holds its error rate to 5% to 7.5% at nominal 5% under a worst-case overlapping
  series. It is honest about width, not powerful.
