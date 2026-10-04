# Checkpoint 8 — data-sufficiency specification

Written 2026-10-04, **before any Checkpoint 8 data was collected**, and committed on its own so the order is provable.
Specification version: `checkpoint8-sufficiency-v1`. The numbers below are also constants in
`firm_lab/history/sufficiency.py`; a test fails if the two disagree.

This document says how much historically truthful data a future Checkpoint 9 tournament needs before its results can
be believed. It does not say the data exists. Every bar is either met by stored, validated data or it is not met.
A large row count meets none of them.

## 1. What counts as a sample

Three evidence tiers. A training row takes the **lowest** tier among its inputs, its universe membership and its label.

| Tier | Name | Meaning |
|---|---|---|
| A | `HELD_AT_THE_TIME` | Firm Lab stored the value before the decision time. Only data captured going forward can reach this tier. |
| B | `PUBLISHER_DATED_HISTORICAL` | An authoritative source dates the availability, and the stored value is the value as first published or cannot be changed by a later revision. Rules per source are in `historical_market_data_policy.md` and `CHECKPOINT8_SOURCES_PIT.md`. |
| C | `RETROSPECTIVE` | Anything else: a restated value, a present-day classification applied to the past, a value with no datable availability. |

**Strict point-in-time sample** (the Checkpoint 8 "strict historical known-at rule"): a row whose every input, whose
universe membership and whose label are tier A or tier B, and whose decision time is not earlier than the latest
input availability. Tier C rows are retrospective rows and are never counted as strict.

Checkpoint 7 reported 0 strict samples under tier A alone. That number is not revised: under tier A alone it is
still 0 until forward capture accumulates. Checkpoint 8 reports the two counts separately and never adds them.

## 2. The quantities that are measured

For a label at horizon `h` sessions over `S` sessions:

* **Non-overlapping windows** `W = S / h`. Labels at adjacent sessions share most of their window; only `W` of them
  are independent in time.
* **Effective independent instruments** `N_eff`. The participation ratio of the correlation matrix of the label
  across instruments, with the sampling noise removed: `N_eff = N / (1 + (N - 1) * max(0, m - 1/(W - 1)))`, where
  `m` is the mean squared off-diagonal correlation measured on non-overlapping windows. (Without the correction a
  short sample makes unrelated instruments look related. Measure name `breadth_v2`; Checkpoint 7's measure is kept
  as it was.)
* **Effective independent observations** `E = W * N_eff`.
* **Smallest detectable rank correlation** `MDE = 2.49 / sqrt(E)`. The mean per-session rank correlation of a model
  with no skill has standard error about `1 / sqrt(E)`; 2.49 is the sum of the normal quantiles for a one-sided 5%
  test with 80% power. A period with a larger `MDE` cannot tell a realistic useful model from noise.

`N_eff` is measured on training and development sessions only. It is never measured on a holdout.

For scale: Checkpoint 7's holdout had `E` of about 34 at the 10-session horizon, so `MDE` was about 0.43. No real
equity signal is that large.

## 3. The reference effect size

`REFERENCE_IC = 0.03`. Published cross-sectional equity signals at 5 to 20 sessions typically show mean rank
correlations between 0.02 and 0.05. A design that cannot see 0.03 cannot confirm a realistic model, so 0.03 is the
largest effect the evaluation must be able to detect. It is fixed here, before data, and is not to be raised later
to make a period pass.

`E` needed for `MDE <= 0.03`: `(2.49 / 0.03)^2 = 6,889`.

## 4. Market history

| Bar | Target | Minimum | Why |
|---|---|---|---|
| H1 Years of daily history | From January 1998 (about 28.7 years) | From January 2005 (about 21.7 years) | See the derivation below. |
| H2 Unique sessions | About 7,230 | About 5,470 | Follows from H1. |
| H3 Instruments per reconstitution | 1,000 | 500 | Breadth. `N_eff` grows much more slowly than the count, so fewer than 500 leaves the 20-session horizon untestable. |
| H4 Distinct securities over the history, delisted included | Counted, not targeted | At least 2 × H3 | A universe that never loses a member is a survivor list. |
| H5 Sectors | All 11 groups, at least 20 names each at every reconstitution | Reported only | Requires a historical classification. If none is obtainable the bar is `NOT MEASURABLE` and sector balance is not claimed. |
| H6 Regimes inside training plus development | 2 bear markets, 4 corrections, rising and falling policy rates, 3 separate high-volatility episodes | The same | A model fitted in one regime has not been tested. Definitions in §9. |

**Where the years come from.**

* Longest feature lookback: 252 sessions. The first year of any instrument is burn-in and yields no sample.
* Walk-forward: at least 5 development folds, each validated on at least 252 sessions (a full year, and at least
  12 non-overlapping 20-session windows per fold). 5 years.
* First training window: long enough that `E` is at least ten times the reference parameter count of boosted trees
  at the 5-session horizon (§8). With `N_eff` near 50 that is about 9.5 years (2,400 sessions), which also covers
  ten times the smallest tree configuration at the 20-session horizon (6.3 years). Adding rows does not shorten it.
  The reference tree configuration at the 20-session horizon would need about 38 years with `N_eff` near 50, more
  than exists; that case is expected to come out `BORDERLINE`, and the specification says so in advance.
* Reserved historical holdout: long enough for `MDE <= 0.03`. With `N_eff` near 50 that is 2.7 years at 5 sessions
  and 10.9 years at 20 sessions. About 4 years is reserved (`CHECKPOINT8_HOLDOUT_DESIGN.md`), which makes the
  5-session horizon testable and states plainly that the 20-session horizon may not be.
* The Checkpoint 7 window (2025-03-31 onward) is burned and cannot serve as a holdout: 1.5 years set aside.
* Regime bar H6 needs two bear markets before the holdout. A start in 2005 gives 2007–2009 and 2020.

Burn-in 1 + first training 9.5 + folds 5 + holdout 4.2 + burned 1.5 = 21.2 years: the minimum. The target adds the
1998–2004 period, which holds the 2000–2002 bear market, so that training covers three and a network's own
training window (§8) can hold two long ones.

## 5. Point-in-time examples

| Bar | Target | Minimum |
|---|---|---|
| P1 Strict samples, total | Reported, with tier A and tier B shown apart | More than 0 in tier B |
| P2 `E` on the training period, 5 / 10 / 20 sessions | At least 10 × the family's reference parameters (§8) | At least 10 × the family's smallest configuration |
| P3 `MDE` on development (all folds together), per horizon | At most 0.03 | At most 0.05 |
| P4 `MDE` on the reserved historical holdout, per horizon | At most 0.03 | At most 0.05 |
| P5 Per instrument | At least 252 sessions before the first sample; median member contributes at least 500 sample sessions | The same |
| P6 Per year | Every calendar year of the period has at least 95% of the target universe size with complete, valid bars | 90% |
| P7 Per regime | Each regime class in §9 holds at least 12 non-overlapping 20-session windows inside training plus development | Reported if not met |

A horizon is **testable** when P3 and P4 are at most 0.03, **weakly testable** between 0.03 and 0.05, and
**not testable** above 0.05. Checkpoint 8 reports this for 5, 10 and 20 sessions and does not choose among them.

## 6. Event and fundamentals coverage

| Bar | Target | Minimum |
|---|---|---|
| E1 Earnings events | At least 80% of universe member-quarters from 2010 have an 8-K Item 2.02 event with an SEC acceptance timestamp | 60% |
| E2 SEC periodic filings | At least 90% of universe member fiscal periods from 2011 have a 10-K or 10-Q with acceptance time | 75% |
| E3 Macro releases | Every scheduled CPI, Employment Situation, PCE and FOMC release in the period has a first-published value and an official release time: at least 98% | 95% |
| F1 Fundamental facts, tier B | For filings counted in E2, the eight required normalized fields resolve under the unchanged rules for at least 70% of filings | Reported |
| F2 Restatement history | Every filing that reported a (company, field, period) is kept in acceptance order; at least one real restatement is shown to be invisible before its restating filing | The same |

XBRL data exists from 2009 for the largest filers and from 2011 for all. Before that there is no tier B
fundamentals source at no cost; the price-only feature set is the only one that spans the full history.

## 7. OHLCV coverage

| Bar | Target | Minimum |
|---|---|---|
| O1 Instruments | Every security the provider lists for the period, delisted included, stored raw | The same |
| O2 Sessions | Every exchange session between a security's first and last bar | The same |
| O3 Completeness for universe members | At least 99.5% of expected (member, session) bars present and valid | 99.0% |
| O4 Rejected rows | At most 0.1% of rows, each with a stated reason | At most 0.5% |
| O5 Conflicts | 0 unresolved (two different bars for one security and session from one source version) | 0 |
| O6 Independent cross-check | Closes already held from another source agree within 0.01% after the stated adjustment, on every overlapping (instrument, session) | At least 99.5% agree; every disagreement listed |
| O7 Print precision (added by amendment 1) | At most 1% of member rows have an adjusted close printed more coarsely than 0.05% of its value | At most 5%. Above that, no feature that reads a high, low or open is used for any row |

## 8. Model families

`P_ref` is the parameter count of a reference configuration; `P_min` is the smallest configuration worth running.
Checkpoint 9 counts the real parameters of whatever it fits; these are the planning values.

| Family | `P_ref` | `P_min` | Reference configuration |
|---|---:|---:|---|
| Linear (ridge / elastic net) | 60 | 20 | One coefficient per feature |
| XGBoost | 2,400 | 400 | 300 trees × 8 leaves; smallest 100 trees × 4 leaves |
| LightGBM | 2,400 | 400 | The same |
| CatBoost | 4,800 | 400 | 300 symmetric trees of depth 4; smallest 100 trees of depth 2 |
| MLP | 6,000 | 1,000 | 60 → 64 → 32 → 1; smallest 60 → 16 → 1 |
| TCN | 20,000 | 5,000 | Three dilated blocks, 32 channels |
| LSTM / GRU | 9,000 | 4,000 | One layer, 32 hidden units; smallest 16 |
| Transformer encoder | 20,000 | 3,500 | Two layers, width 32; smallest one layer, width 16 |
| Multi-task network | 6,100 | 1,100 | The MLP trunk with three heads; `E` is taken at the longest horizon, never summed across heads |

Leaf values are counted for trees. Shrinkage makes their effective count smaller, so the tree bar is conservative.

**Verdict per family, per horizon** (`E_train` is `E` on the first training window plus development):

* `SUFFICIENT`: `E_train >= 10 * P_ref`, and the horizon is testable (§5), and H6 is met.
* `BORDERLINE`: `E_train >= 10 * P_min`, and the horizon is at least weakly testable.
* `INSUFFICIENT`: otherwise.

**Extra bar for networks** (MLP, TCN, LSTM/GRU, transformer, multi-task). All of:

1. `E_train >= 10 * P_min` at the horizon being modelled.
2. Training alone contains at least two bear markets and at least 8 calendar years.
3. The reserved holdout is testable at that horizon.
4. Sequence models only: at least 63 consecutive sessions per sample for at least 95% of samples.

Failing any one makes the family `INSUFFICIENT` regardless of row count. Stability across random seeds is part of
the evidence but can only be measured by fitting, which Checkpoint 8 does not do; it is a Checkpoint 9 gate.

The family verdict reported is the verdict at the 5-session horizon and at the 20-session horizon, both shown.

## 9. Regime definitions (descriptive only)

Computed from the broad-market proxy's daily closes and from official policy-rate decisions. No score, no model.

| Class | Definition |
|---|---|
| Bear market | Peak-to-trough decline of at least 20% in the proxy; the period from peak to trough |
| Correction | Decline of at least 10% and less than 20% |
| Bull | Any session not inside a bear market or correction |
| High volatility | 20-session realized volatility in the top fifth of its own history up to that session (expanding window, so no later data is used) |
| Low volatility | Bottom fifth, the same way |
| Rising-rate | From the first increase of the federal funds target to the last increase of that sequence |
| Falling-rate | From the first cut to the last cut of that sequence |
| Inflationary | 12-month change in first-published CPI above 4%; reported only if E3 is met for CPI |

## 10. What this specification does not allow

* Lowering a bar after the data is seen.
* Counting tier C rows as strict.
* Measuring `N_eff`, `MDE` inputs or any model metric on a reserved holdout.
* Reporting a family as sufficient because the row count is large.
* Choosing the horizon to model from these numbers. That belongs to the Checkpoint 9 plan.

## Amendments

**Amendment 1, 2026-10-04, after the independent review and still before any data was collected.** No bar was
lowered. One bar was added:

* O7, print precision. A vendor reprints adjusted prices after every split at a fixed number of decimals. For a
  stock that later split many times, the reprinted early prices are small numbers rounded coarsely, and that
  coarseness depends on the future. Close-based features are therefore computed from the unadjusted close and the
  confirmed split ratios, which are not affected. Features that read a high, low or open still depend on the
  adjusted prints; O7 bounds how much of the dataset may be affected before those feature families are withheld
  from every row. Withholding them row by row would itself mark the rows of future splitters, so above the minimum
  they are withheld from all rows.

**Amendment 2, 2026-10-04, after the second independent review and still before any data was collected.** No bar was
lowered and none was added. Four measurement rules that the text left open are fixed, each in the stricter direction:

* **When breadth can be measured.** A pair of instruments is compared only over at least 24 non-overlapping windows
  it shares. `N_eff` is reported only when at least half of all pairs can be compared and the typical compared pair
  shares at least 60 windows. Otherwise breadth is `NOT MEASURABLE` and is not assumed: with few shared windows the
  chance correlation is too large a part of what is measured to subtract reliably, and a measured minority of pairs
  does not speak for the rest.
* **`E` is summed window by window.** Each non-overlapping window contributes `N / (1 + (N - 1) * m)` for the `N`
  instruments it holds. A period whose membership grows is not credited with its later breadth for its earlier
  windows. For a constant `N` this is `W * N_eff`, as in §2.
* **A separate high-volatility episode** (H6) is at least 20 sessions in the class; runs separated by fewer than 5
  sessions are one episode. A decline is measured only on closes inside the period being described.
* **H4** also requires that delisted securities with bars are among the distinct securities. Twice the member count
  made up only of survivors does not meet it.

The verdict code was also brought into line with §5 and §8 as written: a horizon is as testable as the weaker of
development (P3) and the reserved holdout (P4), and a multi-task network is judged at its longest horizon.

**Amendment 3, 2026-10-04, after the fourth independent review and still before any data was collected.** No bar was
lowered and none was added. Three rules are tightened and two statements of this document are corrected:

* **O7, how the features are withheld.** Amendment 1 withheld the high, low and open families from every row only
  above 5% coarse rows, and row by row below that. Row by row is itself a mark of the stocks that split later. The
  families are now used for every row of a dataset or for none, and for none as soon as one row would read a
  coarsely printed bar. The bar's numbers (1% and 5% of member rows) stay as the reported measure.
* **A restated bar is tier C (§1).** A bar whose value the vendor changed after it was first stored is a restated
  value. A row that reads one, in a feature or in its longest label, is not a strict sample. The code had kept such
  rows in tier B.
* **Tier A needs the machine's own clock.** A capture time someone supplied orders the stored versions and proves
  nothing about when a bar was held.
* **Correction to §4.** "Longest feature lookback: 252 sessions" means the 252-session return, which reads 253 bars.
  Pivot and Fibonacci features read back to the start of the pivot or leg they stand on, which can be earlier. The
  tier of a row follows the oldest bar it reads.
* **Correction to §8.** "Training alone" (two bear markets, eight calendar years) is measured on development without
  the sessions the five walk-forward folds need for validation (5 x 252), not on all of development.

The readiness report lists all 25 bars of this specification. A bar whose measurement is not built yet (P7) is shown
as not met, with that reason. H1 is measured as the first month-end at which the universe holds the minimum number of
members, so that one early bar of one security cannot meet it.
