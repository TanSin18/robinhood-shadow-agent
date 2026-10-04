# Checkpoint 7 — tournament plan (written before any model was fitted)

Written 2026-10-03, committed before the first tournament run. Plan version `checkpoint7-tournament-plan-v1`
(`firm_lab/modeling/tournament.py`, `selection.py`). Everything below was fixed before a single out-of-sample number
existed. A change after results are seen is a new plan version, recorded with its reason.

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.** Nothing here places, sizes or schedules a trade. No model
gets a production or live status. The Firm trading trial is NOT REGISTERED.

## 1. What is being asked

Which features or model families, if any, carry out-of-sample information about the **10-session forward excess
price return against VTI**? Companion targets: the 5- and 20-session excess return, the probability that the
10-session excess return is positive, and three close-based risk targets over the next 10 sessions (largest adverse
close excursion, largest favourable close excursion, realised close-to-close volatility).

Not asked: what to buy, how much, with what instrument, or when to enter or leave.

## 2. Data, and what it cannot support

- Source: a hash-recorded snapshot of the Firm Lab research database. 23 instruments, 378 exchange sessions
  (2025-03-31 to 2026-09-30) of stored, split-adjusted, price-return closes. VTI is the benchmark; 22 instruments are
  samples (6 single stocks, 16 exchange-traded funds).
- **Time rule: `SESSION_TIME_RETROSPECTIVE` (operator decision, 2026-10-03).** Firm Lab captured all of this on
  2026-10-01 to 2026-10-03. Under the strict known-at rule no historical session has a usable feature (0 samples). For
  modeling research, a close counts as known at its own session close, an SEC fact at its SEC acceptance time, a macro
  value at its publication time. Nothing counts as known earlier. Every result is retrospective: not evidence that the
  system held the data then. Closes are split-adjusted as of the capture date.
- Features: the accepted Checkpoint 6 calculators, unchanged (same calculation hash), asked "what was known at the
  close of session T" for every instrument and session, stored in a separate modeling database. The live research
  database and the Feature Explorer are not touched.
- Model inputs: numeric and boolean descriptors whose unit means the same for every instrument and date. Dollar
  price levels and structured descriptions are left out by a fixed rule (`dataset.MODEL_UNITS`).
- Sample: rows with at least 63 sessions of history and a label for every horizon. About 294 sessions × 22
  instruments. **About 15 non-overlapping 20-session windows and 29 non-overlapping 10-session windows in total.** That
  is very little. The realistic outcome of this checkpoint is that most questions come back INCONCLUSIVE.
- Unavailable and not substituted: OHLCV (true range, candles, volume), intraday, CPI, labor, Treasury yields, market
  volatility, historical sector constituents and mappings, consensus estimates.
- Label limits: both legs are price returns (distributions are not added back); the label starts at the close the
  features end at (a research label, not an executable entry).

## 3. Validation design

- No random split. Sessions are the unit; all instruments of a session are on the same side.
- **Final holdout:** the last 20% of labelled sessions. Read once, at the end. Nothing is tuned or chosen on it.
- **Development:** expanding walk-forward, 5 consecutive validation blocks after a first 80 training-only sessions.
- **Purge:** 20 sessions (the longest label) before every validation block, for every target.
- **Embargo:** 5 further sessions; with the purge it separates development from the holdout by 25 sessions.
- **Configuration choice:** inside each training window, on its last quarter, purged the same way. Every tried
  configuration and its inner score is recorded.
- Preprocessing (feature availability filter, clipping, imputation, scaling, target scaling) is fitted on training
  rows only. A descriptor available in fewer than 10% of a training window's rows, or constant in it, is dropped for
  that window. Linear and neural models get the training median and a missing-value flag where a value is
  unavailable; trees see "unavailable" as it is. A model left with no descriptor predicts its training mean.

## 4. Families and search spaces (bounded, listed in `models.GRIDS` and `deep.py`)

| Family | Members | Configurations |
|---|---|---|
| A naive baselines (mandatory) | zero; historical mean; per-instrument mean; 20-, 63- and 126-session momentum scaled by a one-variable line; registered-style momentum (126-session, only above the 200-session average); base rate (classification); training quantiles (distribution) | none |
| B linear | least squares on 5 descriptors; ridge; elastic net; logistic regression; linear quantile regression | ridge 4, elastic net 3, logistic 3 |
| C boosted trees | XGBoost, LightGBM, CatBoost (regression and classification); LightGBM quantiles | 3 each |
| D shallow neural | feed-forward network, 32-16 hidden units, dropout 0.3, 3 seeds | 1 |
| E sequence | causal temporal convolution, GRU, LSTM over 20 sessions, width 16, 3 seeds | 1 each |
| F transformer | encoder only, 1 layer, 2 heads, width 16, 20 sessions, 3 seeds; single-task and multi-head | 1 |

Also evaluated: multi-task heads against separately trained models; quantiles 10/25/50/75/90 and interval coverage;
seed and bootstrap disagreement as model uncertainty; specialist models per feature family, their equal-weight
average, a train-only linear stacker and a small gating network; a meta-label model against a plain
prediction-size rule; conditional results by factual context where the count allows.

Not built: reinforcement learning, options models, portfolio construction, position sizing, any buy/sell output.

## 5. Feature-family ablation (mandatory)

With ridge and LightGBM as the two reference models, on the primary target: technical baseline (trend, momentum,
volatility); + Fibonacci; + support/resistance and breakout structure; + fundamentals; + earnings/SEC; + sector;
+ macro; full set. Each step is compared with the technical baseline, per session, paired.

**Fibonacci rule (fixed now).** Let Δ be the per-session rank-correlation difference (technical + Fibonacci minus
technical) on development sessions, with a 90% block-bootstrap interval.

- `YES`: the interval's lower bound is above 0 for both reference models **and** Δ is positive on the holdout for both.
- `NO`: the interval's upper bound is below +0.01 for both (the data rule out an improvement of 0.01), **or** Δ is at
  or below 0 for both models on both development and holdout.
- `INCONCLUSIVE`: anything else.

Fibonacci gets no protection. If it adds nothing, that is what is reported.

## 6. Metrics

Regression: MAE, RMSE, R² (against the period mean and against a zero forecast), Pearson, Spearman, directional
accuracy, realised mean by prediction bucket. Classification: ROC-AUC, PR-AUC, log loss, Brier, calibration error,
reliability buckets. Ranking: per-session Spearman rank correlation (IC), top-5 and bottom-5 realised mean,
top-minus-bottom, top-5 hit rate. Distribution: pinball loss, interval coverage and width.

**Primary comparison metric: mean per-session IC on development sessions.** Sharpe is not used: no strategy exists.

## 7. Statistics

- Rows are not independent. Uncertainty is computed on per-session series with a moving-block bootstrap (block =
  label horizon, 2,000 draws, fixed seed) and reported with the number of non-overlapping windows.
- Model against baseline: paired per-session differences, same bootstrap.
- Many models are compared. Holdout tests of "mean IC above zero" are adjusted across all registered models of a
  target with Holm's method at 10%. The count of configurations evaluated is reported.
- One good split proves nothing; fold-by-fold results are shown, and a model must be positive in at least 4 of 5 folds
  to be more than experimental.

## 8. Data-sufficiency gate for neural models (fixed now)

Effective independent observations = (training sessions ÷ horizon) × effective number of independent instruments
(participation ratio of the label correlation matrix). A network needs **at least 10 effective observations per
trainable parameter** for its result to be treated as more than experimental. A model that fails is still run and
reported, labelled `EXPERIMENTAL_INSUFFICIENT_DATA`, and cannot be a challenger. Seed-to-seed spread and
fold-to-fold spread are reported for every network.

## 9. Research status rules (fixed now)

Statuses: `EXPERIMENTAL`, `CHALLENGER`, `REJECTED`, `ELIGIBLE_FOR_FUTURE_REVIEW`. There is no production or live status.

For a ranking/regression or classification model, against the strongest naive baseline of the same target (the
baseline with the highest development mean IC):

- `REJECTED`: development mean IC is at or below 0, or at or below the strongest baseline's.
- `CHALLENGER`: development mean IC above the baseline's; the paired difference interval's lower bound above 0;
  positive IC in at least 4 of 5 folds; holdout mean IC above 0 and at least the baseline's; and, for a network, the
  sufficiency gate passed. A classifier must also have a development log loss below the base rate's.
- `ELIGIBLE_FOR_FUTURE_REVIEW`: a challenger whose holdout mean IC is above zero after Holm adjustment at 10%, and
  whose paired holdout difference against the baseline has a lower bound above 0.
- `EXPERIMENTAL`: everything else, including every model that fails the sufficiency gate.

For quantile and risk models (no rank test is defined): `REJECTED` if worse than the naive baseline on development;
`CHALLENGER` if better in at least 4 of 5 folds and on the holdout; otherwise `EXPERIMENTAL`.

Naive baselines are registered as `EXPERIMENTAL` with the role `BASELINE`.

## 10. What a result may and may not say

May say: predicted excess return, probability, uncertainty, rank, model disagreement. May not say: buy, sell, enter,
exit, strong buy, conviction trade. The economic-relevance note compares a top-minus-bottom spread with a stated,
plausible cost range; it is not a profit figure and no cost model is fitted.

## 11. Reruns

The tournament is run once. If a defect in the code is found afterwards, it gets a failing test first, then the fix,
then a full rerun, and the reason is recorded in the closure report. A rerun to get a better-looking number is not a
defect fix and is not done.

## 12. Plan v2 — changes after the first run and the independent review

Plan version `checkpoint7-tournament-plan-v2`, 2026-10-03/04. Sections 1 to 11 above are the plan as it stood before
any model was fitted and are left as written. The tournament ran once under v1 (report `ceb4a311…`). Two things then
happened: reporting defects were found in that report, and two fresh reviewers examined the code
(`CHECKPOINT7_REVIEW.md`). Each change below has a regression test that failed on the reviewed code. None was made to
move a result. Where a change can only make a status less favourable it says "stricter"; where it can move a status
either way it says so.

| # | Change | Why | Effect |
|---|---|---|---|
| 1 | **Intervals and p-values.** The percentile moving-block bootstrap (block = one horizon) is replaced by a Student t interval on the means of consecutive batches two horizons long. Fewer than three batches: no interval, no p-value; the p-value then counts as 1 in a Holm family. | The reviewer showed the bootstrap is anti-conservative here: a no-information ranking had a "90% interval" above zero 9% to 14% of the time on development sessions, a holdout tail share of exactly 0 up to 14% of the time, and Holm cannot repair a p of 0. Under a worst-case overlapping series the batch interval rejects 5% to 6% at nominal 5%. | Stricter. The holdout (59 sessions) has 5, 2 and 1 batches for the 5-, 10- and 20-session labels: no test exists for the 10- and 20-session targets, so no model can be ELIGIBLE_FOR_FUTURE_REVIEW on them with this data. Development has 13, 6 and 3 batches. |
| 2 | **A session a model does not rank counts as rank correlation 0 for that model.** Means, fold results, paired differences and intervals run over every predicted session for every model. | The strongest baseline of the 5- and 10-session tables (126-session momentum) ranked 104 of 131 development sessions (its descriptor does not exist in the first fold), and its mean over 104 sessions was compared with candidates' means over 131. v1 already said a baseline that ranks nothing counts as 0; this applies the same rule session by session. | Either way. A partly ranking baseline's mean falls (momentum_126, 10-session: +0.051 to +0.040), so some candidates that were REJECTED for being below it are now tested against the lower number; a candidate is never tested against less than zero. |
| 3 | **A challenger must have a paired development interval above zero against every naive baseline of its target**, not only the one with the highest mean. | The "strongest" baseline is chosen with noise: on the 20-session table two baselines were 0.0004 apart, and the one CHALLENGER of the first run passed against one and not the other. | Stricter. |
| 4 | **The Holm family of a label is every registered model that ranks it**: baselines, candidates, ablation and specialist runs, multi-task heads, and classifiers with the 10-session models. | Section 7 says "all registered models of a target". The v1 code used only the candidates of one table (9, 18, 9 and 7 tests; the families are now 16, 55 and 16). | Stricter. The code is brought to the plan. |
| 5 | **A model that fails the data-sufficiency gate is EXPERIMENTAL whatever it scored.** The gating network and any combination that contains a failing network are gated too. A result fitted as a network with no gate record is an error, never a pass. The gate counts the sessions gradient steps were taken on (early stopping holds some back), and the breadth of the cross-section is measured on development sessions only, per label. | Sections 8 and 9 say every model that fails the gate is EXPERIMENTAL; the v1 code returned REJECTED first for eight rows. The 15-parameter gating network was registered with 0 parameters and escaped the gate. The breadth was computed over all sessions, holdout included. | A gate-failed network that scored below its baseline moves from REJECTED to EXPERIMENTAL: its result is not evidence for or against the architecture. The gate itself is stricter. No network passes it. |
| 6 | **A risk model is compared with the strongest naive baseline of its target** (lowest development loss): for future volatility that is persistence, not the training mean. | Found in the first report: two volatility models were CHALLENGER against the training mean while a naive persistence line beat both. | Stricter. |
| 7 | **A classifier's log loss must be below both the base rate's and a coin flip's.** | On a nearly balanced target the training share (0.6953) was a weaker bar than a constant one half (0.6931). | Stricter. |
| 8 | A quantile or risk model level with its baseline is EXPERIMENTAL, not REJECTED; an unscored holdout cannot make a CHALLENGER. | Section 9 says REJECTED "if worse". | Edge cases only. |
| 9 | A multi-head network has one research status per head; the status of the primary target's head names the model in the registry. Registry rows of risk and quantile models carry the status the report gives them, and naive baselines are registered as baselines. | The first run took a multi-head network's status from whichever table came first, and registered every risk and quantile model as an unjudged diagnostic. | Bookkeeping. |
| 10 | Sequence and transformer networks get the training median and a missing-value flag. | Section 3 says so; the v1 code gave them the median without the flag. | The code is brought to the plan. |
| 11 | The stacker and the gate give no learned weight to a member whose inner-block predictions were constant. | In late blocks a specialist's descriptors exist in the outer training window and not in the inner one; 76% of the holdout stacker weight was learned from constants. | Diagnostic combinations only. |
| 12 | PR-AUC and the top/bottom spread treat tied predictions the same in any row order; ROC-AUC and PR-AUC are averaged over blocks, not pooled. | Row-order dependence; pooled over folds a constant forecast scored 0.47 instead of 0.5. | Reporting. |

Corrections to the text above. Section 2 says "about 15 non-overlapping 20-session windows": there are 14 in the 295
usable sessions, and that count is not the one that matters. What is predicted is 131 development sessions (26, 13 and
6 non-overlapping windows of 5, 10 and 20 sessions) and 59 holdout sessions (11, 5 and 2). Non-overlapping is not the
same as independent. The report and the page now show these numbers.

**The holdout has been read twice**: by the first run under v1 and by the rerun under v2. Section 3 says "read once". The
rerun is the defect-fix rerun section 11 provides for; it is disclosed in the report, on the page and in the closure
report, with every status that moved and the change that moved it. No further rerun follows unless a new defect is
found, recorded and tested first.
