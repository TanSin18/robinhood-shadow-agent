# Checkpoint 8 — fresh holdout design

Reserved 2026-10-04, before any Checkpoint 8 market data existed. Split version `c9-chronology-v1`. The dates are
constants in `firm_lab/history/splits.py`; the reservation record is stored in the historical database when it is
created; a test fails if this document and the code disagree.

No model metric of any kind was computed in Checkpoint 8, on any segment.

## The Checkpoint 7 holdout is burned

Checkpoint 7 read its final holdout in each of four tournament runs. That holdout, and the whole Checkpoint 7 data
window with it, is not reused as a pristine test set:

`old Checkpoint 7 holdout reused as pristine: NO`

## The chronology

| Segment | Sessions | Use |
|---|---|---|
| Burn-in | before 1999-01-04 | The first 252 bars of any instrument yield no sample |
| `DEVELOPMENT` | 1999-01-04 to 2020-11-23 | Training and expanding, purged walk-forward validation: at least 5 folds, each validated on at least 252 sessions |
| `PURGE` | 2020-11-24 to 2020-12-31 (26 sessions) | No samples. A label of session T ends at the open of T+21; then a 5-session embargo |
| `HISTORICAL_HOLDOUT` | 2021-01-04 to 2025-03-28 | **Sealed.** Read once, by a registered Checkpoint 9 plan, after every model and every choice is frozen |
| `BURNED_CHECKPOINT7` | 2025-03-31 to 2026-10-02 | Never a test set |
| `FORWARD_HOLDOUT` | 2026-10-05 onward | **Sealed.** Data that did not exist when this was written |

A holdout sample whose longest label would end after 2025-03-28 is dropped, so the historical holdout does not
reach into the burned window. Its last sample session is 2025-02-27.

## Why these dates

Chosen from the calendar and from the sufficiency specification, without looking at any return, feature or model:

* The holdout must end before 2025-03-31, the first Checkpoint 7 session.
* It must be long enough to detect a rank correlation of 0.03. With about 50 effective independent instruments
  that takes 2.7 years at the 5-session horizon; 4.2 years are reserved. At the 20-session horizon it would take
  10.9 years, which would leave too little to learn from; the specification says in advance that the 20-session
  horizon may be only weakly testable or not testable, and the readiness report states which once breadth is measured.
* Development must hold at least two bear markets. 1999 to 2020 holds three (2000–2002, 2007–2009, 2020).
* The holdout holds a bear market (2022) and a recovery, so it is not a single-regime test.

## How the seal is enforced

* The dataset builder removes the label values of both sealed segments before any row leaves it. Only whether a label
  can be built is counted, which reads dates and the existence of bars.
* `materialise` refuses a sealed segment (`SEALED_SEGMENT`).
* Breadth, the one quantity measured from labels, is measured on `DEVELOPMENT` only. A test changes prices inside
  the holdout and shows that no reported number moves, then changes prices inside development and shows that one does.
* Checkpoint 8 contains no code that opens a seal. Opening one is a Checkpoint 9 act with its own registration.
* Reading a sealed segment a second time makes it burned, and that is recorded.

## Historical holdout and forward holdout: the trade-off

| | Historical reserved holdout | Prospective forward holdout |
|---|---|---|
| Available | As soon as the data is licensed | Accumulates one session per day from 2026-10-05 |
| Untouched by this project's model selection | Yes, if the seal holds | Yes |
| Untouched by what is already known about markets | **No.** The period is in every textbook and paper; features and model families chosen today were shaped by it | **Yes.** Nothing chosen today can have seen it |
| Vendor revisions | Possible: prices are as the archive holds them today | None: each bar can be captured the evening it prints (tier A) |
| Time to a usable test | Immediate | About 2.7 years at 5 sessions with 50 effective instruments; less if breadth is higher, never less than a year |
| Risk | A leak through repeated reads or exploratory runs | Slow; a regime change during the wait changes what is being tested |

**Both are reserved.** The historical holdout is the Checkpoint 9 confirmation. The forward holdout is the final and
slower confirmation before any trading trial is proposed: a model frozen at a registered date is measured only on
sessions after that date, once, and not before its smallest detectable rank correlation is at most 0.05 at the
horizon being confirmed. A model meant for the forward test may train on everything before its freeze date,
including the burned window.

**Forward capture is not running.** Tier A data requires each day's bars to be stored before the next session opens.
Nothing does that today, and Checkpoint 8 adds no schedule. Until the operator decides how that capture is done, the
forward holdout accrues as tier B (downloaded later from the archive), which is still untouched by model selection.

## What is not decided here

* Which horizon is modelled. Checkpoint 9's plan chooses, in writing, before it sees a metric.
* The fold boundaries inside development. The minimums are fixed; the plan fixes the dates.
* Whether a benchmark fund replaces the equal-weighted universe mean in the excess label.
