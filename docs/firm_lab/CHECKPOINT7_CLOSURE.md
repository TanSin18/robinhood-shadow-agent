# Checkpoint 7 — modeling laboratory and validation tournament

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.**

Branch `claude/checkpoint7-modeling`, based on `codex/checkpoint6-features` at `3b34b97`. Written 2026-10-04.
The question was: which features or model architectures have genuine out-of-sample predictive value?

**The answer this data supports: none is established.** No model reached CHALLENGER or ELIGIBLE_FOR_FUTURE_REVIEW.
Of 43 judged candidates, 28 are EXPERIMENTAL and 15 REJECTED. Every network fails the data-sufficiency gate. On the
primary target no model's development interval clears the naive baselines, and the holdout is too short to test
anything on the 10- and 20-session targets. Fibonacci is INCONCLUSIVE. One observation is worth looking at again when
more sessions exist (5-session LightGBM and XGBoost on the holdout); it is recorded below as that and nothing more.

## Checkpoint

| | |
|---|---|
| Research, validation and review | complete |
| Stored result | report `de322bfd1ce6d44cff7a561896a89f52c0092f2db496e029ba84bd3c05f0c79d`, plan `checkpoint7-tournament-plan-v3.1`, code hash `dc7d5b4085357873e61bd9d7307c61c977a20fb9125cc40357a5b1b5032b63c0`; `cli verify` matches |
| Deployment to the Mac (read-only page, laboratory file, capability rows) | see `CHECKPOINT7_DEPLOYMENT.md` |
| Native Mac test run | see `CHECKPOINT7_VALIDATION.md` |
| Checkpoint 8 | not started |

### Four runs, one result

The plan allowed one run and a rerun only for a recorded defect. There were four, each for recorded defects, each on a
clean copy of the same feature history (sha256 `2b788f98…47a9`):

| Run | Plan | Report | Why it exists |
|---|---|---|---|
| 1 | v1 | `ceb4a311…` | the planned run |
| 2 | v2 | `4794d1f4…` | reporting defects found in run 1, and the independent review's findings |
| 3 | v3 | `5a1c9af9…` | the verification review's findings; all 106 prediction sets identical to run 2 |
| 4 | v3.1 | `de322bfd…` | six minor points from the delta review of v3; all 106 prediction sets identical to run 3 |

The holdout was therefore read by every run. Between runs 1 and 2, seven of 106 prediction sets changed: the four
sequence networks and the multi-task transformer (they now get missing-value flags, as plan section 3 always said) and
the stacker and gating combinations (no learned weight for a member that was constant in the inner block). Between
runs 2, 3 and 4 no prediction changed. The rules changed as recorded in plan sections 12 and 13, each change for a
stated defect with a failing regression first.

### Holdout disclosure

**The current holdout is no longer an untouched final test set for future model selection.** The tournament was run
four times and the holdout (2026-06-09 to 2026-09-01) was read after defects were found, each time. Its numbers in
this report describe what happened on those sessions; they must not be presented as an untouched test in any future
scientific claim, and no configuration may be chosen because of them. **Future model research needs a newly
accumulated or separately reserved untouched evaluation period.**

### The primary limitation

Strict point-in-time usable samples: **0**. Retrospective samples: **6,490**. All current feature inputs were captured
on October 1–3, 2026. The historical feature modeling here is therefore retrospective and cannot establish a genuine
historical point-in-time trading edge, whatever a model scored.

Statuses that differ between run 1 and the closing run, and the change that moved them:

| Row | Run 1 | Closing run | Change |
|---|---|---|---|
| 20-session CatBoost | CHALLENGER | EXPERIMENTAL | v2 #1 honest interval (3 batches), #3 every naive baseline |
| Future volatility: ridge, LightGBM | CHALLENGER | REJECTED | v2 #6 judged against persistence, the stronger naive forecast |
| 10-session LightGBM, CatBoost | REJECTED | EXPERIMENTAL | v2 #2: the strongest baseline's mean over all 131 sessions is +0.040, not +0.051 |
| 10-session GRU, both multi-task heads, gating, family rank average | REJECTED | EXPERIMENTAL | v2 #5: a gate-failed network's result is not evidence either way |
| 20-session, 5-session and classification multi-task heads (5 rows) | REJECTED | EXPERIMENTAL | v2 #5 |
| coin_flip (classification baseline) | — | baseline | v2 #7 new naive baseline |

Two of these moved in the less negative direction on the primary target (LightGBM and CatBoost, REJECTED to
EXPERIMENTAL). EXPERIMENTAL means "not established".

## Control A

| | |
|---|---|
| Release | N |
| Fingerprint | `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876` (240 files; verified at the start, 2026-10-03 ≈20:00 ET, and again 2026-10-03 22:36 ET) |
| Strategy changed | NO |
| Runner restarted | NO |
| Official Lane B | PAUSED |
| Real execution | DISABLED |
| Codex maintenance | PREPARED_AND_PROVEN_NOT_INSTALLED |

Nothing in this checkpoint touches the registered runtime, its database or its schedule. The end-of-checkpoint
fingerprint check is recorded in `CHECKPOINT7_DEPLOYMENT.md`.

## Dataset

| | |
|---|---|
| Instruments | 22 samples (6 single stocks, 16 funds) and VTI as the benchmark |
| Sessions | 378 stored (2025-03-31 to 2026-09-30); 295 usable (2025-07-01 to 2026-09-01) |
| Usable PIT samples | **0 under the strict known-at rule** (0 stored closes were held at their own session close). 6,490 retrospective samples under the session-time rule the operator chose |
| Targets | excess price return vs VTI over 5, 10 (primary) and 20 sessions; sign of the 10-session excess return; close-based adverse excursion, favourable excursion and realised volatility over the next 10 sessions |
| Horizons | 5, 10, 20 |
| Dataset hash | `1dadc0bb5f733755c8a1cf621dd717f88199709af095acb3606007ae3420fe9c` (features `a4068ea0…`, labels `f0aacfc5…`, rows `7b3a065b…`, snapshots `bc417324…`) |
| Source snapshot | sha256 `a18f0f294108ee00465b894771ebdfefa87af02b588d2703b519279dc7a249a3` (the research database without its stored feature runs) |
| Feature calculation | Checkpoint 6 calculators, unchanged: hash `45b4c2ab719f13dd17cb735118792adc9bc3f8f872466ccba0c2cba3196e3926`; 8,694 snapshots, one per instrument and session, each asked what was known at that session's close |
| Descriptors | 159 encoded as numbers; 140 offered to a model; 113 of those ever available; 63 left out by rule |

Limitations:

- Retrospective. Every input was captured on 2026-10-01 to 2026-10-03. Nothing here is evidence that the system held
  the data then. Closes are split-adjusted as of the capture date.
- Small. 131 development sessions and 59 holdout sessions are predicted: 26, 13 and 6 non-overlapping windows of 5,
  10 and 20 sessions on development; 11, 5 and 2 on the holdout. The cross-section behaves like about 6 independent
  instruments, not 22.
- Labels are price returns on both legs (distributions not added back) and start at the close the features end at: a
  research label, not an executable entry.
- No OHLCV, intraday, CPI, labor, Treasury-yield, market-volatility, consensus or historical sector data. Nothing
  substitutes for them. Fundamental and event descriptors exist for 5 single stocks. The "sector" set holds only
  trailing returns relative to VTI. Macro descriptors are validated from mid-2026 only.

## Validation

| | |
|---|---|
| Split method | `expanding-walk-forward-purged-v1`; sessions are the unit; no random split |
| Walk-forward folds | 5 (27, 26, 26, 26, 26 predicted sessions) after a first 60 training sessions |
| Purge | 20 sessions before every predicted block, for every target |
| Embargo | 5 sessions |
| Final holdout | the last 59 labelled sessions (2026-06-09 to 2026-09-01), 25 sessions after development |
| Tuning | on the last quarter of each training window, purged; 1,248 configuration fits, every one recorded |
| Intervals | Student t on the means of consecutive batches two horizons long; none below three batches |
| Second gate | a challenger must beat its own predictions with instrument identities shuffled (100,000 shuffles) |
| Many comparisons | Holm at 10% over every registered model judged by ranking the label: 16, 51 and 16 tests |

## Baselines

Mean per-session rank correlation, development / holdout. A session a model does not rank counts as 0.

| Baseline | 5-session | 10-session | 20-session |
|---|---|---|---|
| zero, historical mean | 0 / 0 | 0 / 0 | 0 / 0 |
| per-instrument mean | +0.046 / −0.020 | +0.025 / −0.063 | **+0.041 / −0.003** |
| 20-session momentum | −0.003 / −0.090 | −0.083 / −0.075 | +0.040 / −0.126 |
| 63-session momentum | +0.032 / −0.060 | +0.022 / −0.150 | −0.011 / −0.182 |
| 126-session momentum | **+0.048 / −0.100** | **+0.040 / −0.166** | +0.020 / −0.132 |
| registered-style momentum | −0.008 / −0.089 | −0.019 / −0.126 | −0.006 / −0.034 |

Bold is the strongest on development sessions. Every baseline that ranks is negative on the holdout.

- **Linear** (10-session): least squares on 5 descriptors −0.040 / −0.091 REJECTED; ridge +0.019 / −0.037 REJECTED;
  elastic net +0.082 / −0.026 EXPERIMENTAL (interval −0.027 to +0.191).
- **Classification**: base rate log loss 0.6953 / 0.6915; coin flip 0.6931 / 0.6931. Logistic 0.7143 / 0.7820
  REJECTED. No classifier's log loss is below a coin flip's.

## Boosted trees

| | 5-session | 10-session | 20-session | Classifier (log loss) |
|---|---|---|---|---|
| XGBoost | +0.042 / +0.108 REJECTED | +0.031 / −0.013 REJECTED | +0.063 / −0.025 EXPERIMENTAL | 0.7322 / 0.7763 EXPERIMENTAL |
| LightGBM | +0.065 / +0.123 EXPERIMENTAL | +0.048 / +0.021 EXPERIMENTAL | +0.039 / +0.002 REJECTED | 0.7324 / 0.7803 EXPERIMENTAL |
| CatBoost | +0.037 / +0.036 REJECTED | +0.047 / −0.016 EXPERIMENTAL | +0.113 / +0.131 EXPERIMENTAL | 0.7220 / 0.7634 EXPERIMENTAL |

All three libraries were installed in the isolated cloud research environment (pinned in
`firm_lab/modeling/requirements-research.txt`); nothing was installed on the Mac.

**The one observation to revisit.** On the 5-session holdout LightGBM and XGBoost have mean rank correlation +0.123
and +0.108, five batch means all positive, Holm-adjusted p 0.054 and 0.060 in a family of 16 (below the plan's 10%
level). It is one result, not two (the two series correlate 0.92). On development sessions neither clears the gates:
LightGBM's interval is −0.014 to +0.145 and its identity-shuffle p is 0.053; XGBoost is below the strongest baseline.
The holdout is 11 non-overlapping windows and was read by every run. Status: EXPERIMENTAL and REJECTED.

## Neural

| Model (10-session) | Parameters | Development / holdout | Folds above zero | Status |
|---|---|---|---|---|
| MLP 32-16 | 4,417 | +0.059 / −0.076 | 4 of 5 | EXPERIMENTAL |
| MLP on the sequence descriptors | 2,721 | +0.129 / +0.003 | 4 of 5 | EXPERIMENTAL |
| TCN | 4,465 | +0.078 / −0.010 | 4 of 5 | EXPERIMENTAL |
| GRU | 4,529 | +0.088 / −0.055 | 5 of 5 | EXPERIMENTAL |
| LSTM | 6,033 | +0.006 / −0.065 | 3 of 5 | EXPERIMENTAL |

**Data sufficiency: every network is `EXPERIMENTAL_INSUFFICIENT_DATA`.** The last development fold gives 65
effective independent observations on the 10-session label (112 sessions of gradient steps ÷ 10, times 5.8 effective
instruments) against 2,721 to 6,033 parameters: 0.011 to 0.024 per parameter, where the gate asks for 10. Seed-to-seed
range of the development rank correlation is up to 0.13. The highest development score on the primary target
(+0.129) fell to +0.003 on the holdout.

## Transformers

| | |
|---|---|
| Architecture | encoder only, 1 layer, 2 heads, width 16, learned positions, 20 sessions, final step read; no decoder (the targets are scalars) |
| Parameter count | 3,793 (single task), 3,861 (five heads) |
| Training samples | 65 effective independent observations (10-session), 26.5 (multi-task, judged at the longest horizon) |
| Results | single task +0.053 / +0.004; multi-task head on the 10-session target +0.035 / +0.082, on the 5-session target +0.073 / +0.036 |
| Stability | 4 of 5 folds positive; seed range 0.005 (single task), 0.09 (multi-task) |
| Data sufficiency | `EXPERIMENTAL_INSUFFICIENT_DATA`: 0.017 and 0.007 observations per parameter against 10 required |

## Multi-task

Tested: a feed-forward network and the transformer with five heads (5-, 10-, 20-session return, sign, future
volatility), against separately trained networks. The multi-task feed-forward network is worse than the separate one
on every head (10-session +0.026 against +0.059). The multi-task transformer is mixed. Nothing is established; both
fail the gate.

## Distribution / uncertainty

- **Quantile model.** Training quantiles (naive) have the lowest pinball loss: 0.01154 / 0.01240. LightGBM quantiles
  0.01165 / 0.01322 and linear quantiles 0.01165 / 0.01448 are REJECTED.
- **Interval calibration.** Nominal 80% intervals cover 72% to 79%; nominal 50% intervals 43% to 48%. Too narrow.
- **Model disagreement.** Models disagree on the sign for 55% of development rows and 84% of holdout rows. Dispersion
  goes with the size of the error on development (rank correlation 0.28) and not on the holdout (0.06). Bootstrap
  spread 0.21, quantile width 0.28, seed spread 0.14 against the size of the error. A diagnostic; no rule.
- **Classifier calibration.** The tree classifiers are overconfident (calibration error 0.10 to 0.19); recalibrated
  LightGBM improves to log loss 0.7011 / 0.7089, still worse than a coin flip.

## Specialist models

LightGBM on one feature family each, 10-session target, development / holdout:

| Specialist | Result | Note |
|---|---|---|
| Technical | +0.069 / +0.049 | trend, momentum, volatility, Fibonacci, structure |
| Fundamental | −0.027 / −0.084 | 5 single stocks; ranks 26 of 131 sessions |
| Event | −0.060 / +0.067 | 5 single stocks; ranks 26 of 131 sessions |
| Sector | −0.023 / −0.043 | trailing returns relative to VTI only |
| Macro | 0 / 0 | the same for every instrument on a day: cannot rank |

One unified LightGBM on everything: +0.048 / +0.021.

## Ensemble / MoE

| | Development / holdout | Status |
|---|---|---|
| Simple ensemble (equal weight of specialists) | +0.014 / +0.028 | REJECTED |
| Stacker (non-negative linear, fitted on inner blocks) | +0.011 / +0.049 | REJECTED |
| Gating model (softmax over live specialists, 6 parameters) | +0.020 / +0.038 | EXPERIMENTAL, fails the gate |
| Rank average across model families | +0.044 / −0.027 | EXPERIMENTAL, holds a gate-failed network |

Result: no combination beats the technical specialist alone or the strongest naive baseline. Meta-label research: a
second model's AUC for "is the primary direction right" is 0.58 on development and 0.49 on the holdout.

## Feature ablation

Each family added to the technical baseline (26 descriptors), 10-session target. Change in development rank
correlation with its 90% interval, then the holdout change.

| Set | Ridge | LightGBM |
|---|---|---|
| Technical baseline | −0.066 / −0.057 | +0.044 / +0.047 |
| + Fibonacci | +0.097 (+0.041 to +0.153); holdout +0.061 | −0.023 (−0.067 to +0.020); holdout −0.014 |
| + structure | +0.048 (+0.005 to +0.091); +0.034 | +0.020 (−0.071 to +0.110); −0.008 |
| + fundamentals | +0.007 (−0.002 to +0.016); 0.000 | +0.010 (−0.009 to +0.029); −0.048 |
| + earnings | −0.016 (−0.038 to +0.006); −0.010 | −0.005 (−0.014 to +0.005); +0.013 |
| + sector | −0.013 (−0.034 to +0.008); +0.004 | +0.006 (−0.049 to +0.061); −0.004 |
| + macro | 0.000; 0.000 | 0.000; 0.000 |
| Full (140) | +0.085 (+0.040 to +0.130); +0.020 | +0.004 (−0.078 to +0.086); −0.026 |

**FIBONACCI ADDS INCREMENTAL OOS VALUE = INCONCLUSIVE**

The two reference models disagree. Fibonacci descriptors lift a ridge model that was negative without them (to
+0.031, still below the naive baseline), and do nothing for LightGBM, which was already the better model. The rule
needs both. Fibonacci got no protection.

## Best research models

"Best" is the highest development score among the rows compared: a selection-biased number, shown with its holdout.

| Question | Highest development score | Development / holdout | Status |
|---|---|---|---|
| 5d | transformer multi-task head (of 16) | +0.073 / +0.036 | EXPERIMENTAL, insufficient data |
| 10d | MLP on the sequence descriptors (of 25) | +0.129 / +0.003 | EXPERIMENTAL, insufficient data |
| 20d | CatBoost (of 16) | +0.113 / +0.131 | EXPERIMENTAL |
| Classification | coin flip, a naive baseline (of 9) | log loss 0.6931 / 0.6931 | baseline |
| Risk / downside | training mean, a naive baseline (of 3) | RMSE 0.0318 / 0.0332 | baseline |
| Best baseline | 126-session momentum | +0.040 / −0.166 | baseline |
| Best advanced candidate | MLP on the sequence descriptors (of 15) | +0.129 / +0.003 | EXPERIMENTAL, insufficient data |

Size of the ranking spread (top 5 minus bottom 5, realised 10-session excess return): the strongest baseline +1.13%
on development and −2.97% on the holdout; no model's development interval is above the stated cost range (0.10% to
0.40%). Not a profit figure.

## Explainability

- **Methods.** Standardised coefficients (ridge); split gain and TreeSHAP contributions computed by the library, and
  permutation of one feature family within sessions (LightGBM), on one fold; contributions by family for six holdout
  rows, with the feature snapshot and calculation hash behind each.
- **Limitations.** The fold used had a negative validation rank correlation (−0.14), so the importances describe a
  model that did not work there. Reliance is not cause; correlated descriptors share credit arbitrarily; one fold is
  unstable. No explanation is written by a language model and attention weights are not presented as explanations.

## MLOps design

`docs/firm_lab/model_lifecycle_design.md`. Design only; nothing is scheduled or activated.

| | |
|---|---|
| Registry | built: append-only, every row named by its run, dataset hash, split, configuration, seeds, library versions and code hash; statuses EXPERIMENTAL, CHALLENGER, REJECTED, ELIGIBLE_FOR_FUTURE_REVIEW only; no weights stored |
| Retraining design | documented; automatic retraining is not automatic deployment |
| Drift design | documented |
| Promotion gate | documented; human review; no automatic promotion exists |
| Rollback design | documented |

## Capital readiness

Future architecture documented. **Automatic external funding enabled: NO.**

## UI

A read-only "Modeling Laboratory" section on the Firm Lab page (`/firm-lab#fl-modeling`), rendered from a stored
report only; the page loads no model code.

| | |
|---|---|
| Model lab | summary, limits, best scores with holdout and gate label, leaderboards per target, registry counts |
| Calibration | classifier reliability and interval coverage |
| Ablations | per family with intervals and the Fibonacci statement |
| Explainability | family reliance and six traced examples, labelled research only |
| Research-only warning | permanent: MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE; one neutral style for every status; no form, button or action wording |

Whether it is live on the Mac is in `CHECKPOINT7_DEPLOYMENT.md`.

## Tests

`CHECKPOINT7_VALIDATION.md` has the commands and outputs.

| | |
|---|---|
| Focused | 79 passed (six modeling test files) |
| Firm Lab | included in the full suite |
| Native | see `CHECKPOINT7_VALIDATION.md` |
| Cloud | **1147 passed, 1 skipped** (commit `7792a2f`); the Codex Checkpoint 6 baseline in the same environment was 1068 passed, 1 skipped |
| Without the research libraries | 63 passed, 1 module skipped (what the Mac's environment will run) |
| Known failures | none in the cloud. One Checkpoint 5 test was changed: it pinned the exact set of capability states, and `RESEARCH_ONLY` was added |

Independent review: three rounds by fresh reviewers plus a delta review (`CHECKPOINT7_REVIEW.md`). One critical and
thirteen important findings, all repaired with a regression first; none deferred.

## Capabilities

Research-specific states. Nothing is live or in production; `capabilities.require` refuses `RESEARCH_ONLY`.

| Capability | State |
|---|---|
| research_modeling | RESEARCH_ONLY |
| ml_ranker | RESEARCH_ONLY |
| deep_learning | RESEARCH_ONLY (every network `EXPERIMENTAL_INSUFFICIENT_DATA`) |
| transformer_models | RESEARCH_ONLY (`EXPERIMENTAL_INSUFFICIENT_DATA`) |
| macro_regime | NOT_STARTED |
| portfolio_optimizer | NOT_STARTED |
| options_strategy | NOT_STARTED |
| rl_policy | NOT_STARTED |

Whether these rows are written to the live research database is in `CHECKPOINT7_DEPLOYMENT.md`.

## Experiment state

Firm Lab fills: 0

Firm trading trial: NOT REGISTERED

October research stop superseded: NO

Control A: UNCHANGED

Official Lane B: PAUSED

Real execution: DISABLED
