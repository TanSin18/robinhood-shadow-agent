# Firm Lab — future model lifecycle (design only)

Checkpoint 7, written 2026-10-03. **A design. Nothing in this document is switched on.** No production model exists,
no model is retrained on a schedule, nothing is promoted, and no output of a model reaches a trading path.

**MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE.** The Firm trading trial is NOT REGISTERED.

## 1. The intended loop, when it is eventually built

```
new data arrives
  → data checks (provenance, known-at, schema, gaps)
  → features update (versioned calculators, append-only)
  → challenger models retrain (fixed recipe, fixed seeds)
  → walk-forward validation (purged, with a holdout)
  → calibration, stability and drift checks
  → comparison with the current champion
  → eligible challenger
  → controlled promotion (a person decides)
```

**Automatic retraining is not automatic deployment.** A retrained model is a challenger. It becomes anything else only
through a recorded decision by the operator.

## 2. Stages

| Stage | What it does | What stops it |
|---|---|---|
| Automated data check | Confirms every new source row has provenance, a known-at time, the right units and no gap | Any failed check: nothing downstream runs |
| Feature generation | Runs the versioned calculators for the new session; appends, never rewrites | A calculation-hash change without a new feature version |
| Retraining trigger | Decides whether a challenger is fitted (see 3) | No trigger: nothing is fitted |
| Challenger training | Fits the registered recipe on the purged training window with recorded seeds | Dataset hash or code hash not recorded |
| Automated validation | The same purged walk-forward and holdout rules as Checkpoint 7 | Any leakage check failing |
| Calibration test | Reliability, Brier and log loss on a window not used to fit or calibrate | Calibration error above its limit |
| Drift test | See 4 | Drift beyond its limit |
| Champion comparison | Paired, per session, with overlap respected and the number of comparisons counted | Not better with the interval above zero |
| Promotion gate | A written record: what, why, evidence, who approved | No approval: stays a challenger |
| Rollback | The previous champion and its artifacts are kept; switching back is one recorded step | — |

## 3. Retraining triggers (candidates; none is active)

- **Scheduled**: at a fixed interval.
- **Enough new samples**: a stated number of new non-overlapping label windows since the last fit.
- **Model drift**: a drift measure crosses its limit.
- **Prediction-performance deterioration**: realised rank correlation or calibration falls outside its expected band
  for a stated number of windows.

A trigger starts a challenger fit. It never changes what is in use.

## 4. Drift monitoring (design; no live reaction)

| What is watched | How | What it may cause |
|---|---|---|
| Input feature drift | Distribution of each descriptor against its training distribution (population stability, quantile shifts) | A flag; a retraining trigger |
| Missingness drift | Share of unavailable values per descriptor and family against training | A flag; a data check |
| Prediction drift | Distribution of predictions against the training-period predictions | A flag |
| Calibration drift | Reliability of probabilities on newly closed label windows | A flag; a retraining trigger |
| Realised performance drift | Per-session rank correlation and loss on closed windows, against the validation band | A flag; a retraining trigger |
| Regime unfamiliarity | Distance of the current descriptor vector from the training set; share of inputs outside the training range | A flag; wider reported uncertainty |

None of these changes a position, a size or an order. They produce records and, at most, a challenger fit.

## 5. Self-improvement principle

The system may, under a future fixed and recorded policy, **retrain**: refit the same recipe on more data.

It may **not** silently rewrite:

- objectives or targets,
- risk limits,
- target definitions,
- portfolio constraints,
- execution safety,
- strategy registration.

Any material change of method (a new target, a new feature version, a new architecture, a new validation rule) creates
a **new version and a new challenger**, evaluated from the start. Nothing is changed in place.

## 6. Registry (built in Checkpoint 7, research only)

`firm_lab/modeling/registry.py`, in the separate modeling database, append-only. Every model: identity, family,
architecture, target, horizons, feature set and versions, training and validation windows, split definition,
hyperparameters (chosen and tried), seeds, library versions, code hash, dataset hash, metrics, artifact hashes and a
status. Statuses: `EXPERIMENTAL`, `CHALLENGER`, `REJECTED`, `ELIGIBLE_FOR_FUTURE_REVIEW`. There is no `PRODUCTION` and
no `LIVE`, and a test refuses them.

## 7. Capital readiness (future layer; nothing active)

A later layer, after models, a simulator and a registered trial exist, would assess whether the system has earned more
capital. It would look at:

- evidence maturity (how many closed, untouched windows support the system),
- opportunity breadth (how many qualified candidates there are),
- model confidence and uncertainty,
- portfolio concentration and capital utilisation,
- the number of qualified opportunities rejected only because capital was not available,
- drawdown state,
- calibration health.

It could then state one of: *no additional capital needed*, *capital constrained*, *potential scaling opportunity*,
*do not add capital now*.

**It must never move money.** Automatic external funding enabled: **NO**. No capital recommendation of any kind is
produced in Checkpoint 7.

## 8. Diagnostics kept now for later frequency analysis

So that a later strategy is not accidentally filtered down to nothing, the laboratory records, per session: how many
candidates were evaluated, the distribution of predictions, how many exceeded each *research* threshold, the breadth
of the ranking, and the distribution of model disagreement. No threshold is chosen and none is tuned toward a wanted
number of trades.

## 9. Deferred research tracks

- **Reinforcement learning**: not used for stock selection. A possible later track for sequential decisions
  (position management, allocation, execution, options management), only after reliable forecast models and a
  simulator exist.
- **Options models** (shares versus options): Checkpoint 8 or later. `options_strategy = NOT_STARTED`.
- **Portfolio construction** (sizing, optimiser, sector limits from model output): Checkpoint 8 or later.
- **Mixture-of-experts as a live system**: prototyped offline only; not built.

## 10. What must stay true while any of this is designed

Control A is frozen and separate. Firm Lab stays `BUILD_OBSERVE`, with no order, fill, position, account or cash
table. No model output is a buy, sell, entry or exit instruction.
