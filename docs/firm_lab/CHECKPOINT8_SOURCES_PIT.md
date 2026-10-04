# Checkpoint 8 — point-in-time sources other than market bars

Written 2026-10-04. What each non-price source can honestly claim today, what a historical backfill needs, and what
stays unavailable. Market bars are in `historical_market_data_policy.md`.

A value from one of these sources is tier B (`PUBLISHER_DATED_HISTORICAL`) only when the publisher's own timestamp
dates its availability **and** the stored value is the one first published. A later value is a later row; it never
replaces the earlier one.

## Fundamentals (SEC)

**Stored today.** 531 normalized facts from 20 periodic filings of 5 companies, each with the SEC acceptance
timestamp of the filing that reported it (header time, reconciled with the JSON time). Versions and restatements are
kept in acceptance order; a restated value is invisible before its restating filing was accepted (tested). These
rows are tier B. They are a sample, not a history.

**Rules that do not change.** Ten normalized fields under `sec_xbrl_normalization.md`: the same economic period,
duration, concept, unit and entity are required; no year-to-date subtraction; no missing-debt imputation; a value that
differs from the filing document makes the answer unusable. Nothing is loosened for coverage.

**What a history needs, and what blocks it.**

| Need | State |
|---|---|
| Companies keyed by CIK, delisted ones included | The reader resolves a ticker through SEC's **current** ticker file, which lists survivors only. A historical universe needs CIKs from the security master (the vendor's ticker table carries each company's SEC link). **Depends on the market-data purchase.** |
| Filings older than the recent list | The reader uses the "recent" block of the submissions file (about 1,000 filings or one year). Older filings sit in additional files it does not page. **Not built.** |
| Acceptance timestamps in bulk | SEC's Financial Statement Data Sets (quarterly archives from 2009) carry `accepted` per filing and the values as filed. Free, reusable without permission. **Not read yet.** |
| Check against the filing document | Possible per filing, about one request each. For a full universe that is several hundred thousand requests at SEC's 10 per second: feasible over days, by hand, not in one sitting. |

**Proposed order, for the operator to accept or change.**

1. *Validation sample now (free, no purchase needed):* the existing collector on the five stored companies with a
   deeper window, to bring real multi-year filings and at least one real restatement into the store. It is limited to
   what the "recent" block holds.
2. *After the universe exists:* a CIK-keyed history reader that pages older submissions, run for a 50-company sample
   across sectors and decades, delisted companies included, with the document check on.
3. *Then the bulk path:* the Financial Statement Data Sets as the source of acceptance times and as-filed values for
   the whole universe, mapped through the unchanged normalization rules. Because the per-document check cannot run at
   that scale in one pass, bulk rows would carry their own evidence label (`AS_FILED_BULK_NOT_DOCUMENT_CHECKED`) and
   would not be mixed with document-checked rows without saying so. **This is a rule decision and is not taken here.**

XBRL exists from 2009 for the largest filers and from 2011 for all. Before that there is no free tier B fundamentals
source. Price-only features are the only ones that span the full history.

## Earnings events (SEC)

**Stored today.** 20 earnings-release filings (8-K, Item 2.02) of 5 companies: accession, acceptance timestamp, fiscal
period, session timing, the EX-99.1 release document. Tier B. A sample.

**History.** The same three blockers as fundamentals (CIK keying, older filings, scale). Item 2.02 exists from
August 2004.

**Not added.** No consensus estimate and so no surprise: no legitimate point-in-time consensus source is licensed
(see analyst estimates below).

## Earnings transcripts

`earnings_transcripts = UNAVAILABLE`, unchanged. Candidates read at Checkpoint 2 (API Ninjas, Financial Modeling
Prep, Quartr) sell transcripts; none has been checked for storage and model-use terms, and transcripts are not
required for a daily tournament. Nothing is scraped.

## News

Not required for the next tournament. No adequate licensed point-in-time archive with storage and model-use rights
has been identified. `news_catalysts` stays as it is (advisory headlines for Control A's notes only).

## Analyst estimates and revisions

`analyst_revisions = UNAVAILABLE`, unchanged. The point-in-time consensus archives (FactSet, I/B/E/S, Visible Alpha)
have no individual licence path. Nothing is reconstructed from present-day estimates.

## Sector history

**Stored today.** Six internal issuer classifications effective 2026-10-03. Not historical, and never used before
their effective date.

**What exists.**

* The market-data vendor's sector and industry fields are a present-day classification. Stored with the name
  `sector_current`; never used as a historical input.
* **SIC codes as filed.** Each filing in SEC's Financial Statement Data Sets carries the filer's SIC code at that
  filing, with the acceptance timestamp. That is a dated, authoritative industry code from 2009, coarser than GICS.
  It is the only free historical classification found. Not read yet.
* Sector ETF bars are in the vendor's fund table and would be tier B like any other bar.
* Historical ETF constituents: no free authoritative source.

**Consequence.** Sector balance bar H5 is `NOT MEASURABLE`. Full breadth by sector stays unavailable; any subset
measure stays labelled a subset.

## Macro

**Stored today.** Federal funds target range (3 decisions) and PCE monthly changes (4 months; 6 rows per series, 2 of
them later vintages) for mid-2026, each with its official release time. Tier B. CPI, labor and Treasury yields: not stored.

**FRED and ALFRED are not used.** Their terms prohibit storing the data and using it to train models without written
consent (`CHECKPOINT8_PROVIDER_DECISION.md`). The collector no longer asks them, and the macro store no longer accepts
FRED as a source.

**Sources that can establish first-published values and release times** (all public):

| Series | Value as first published | Release time | Revisions |
|---|---|---|---|
| FOMC target range | Federal Reserve Board statements and the open market operations record | Statement time (in the release) | Not revised |
| CPI | BLS release archive; unadjusted CPI-U is final when issued; seasonally adjusted indexes are revised for up to five years | BLS release schedule, 8:30 AM, archived by year | Philadelphia Fed real-time data set (monthly vintages) for the adjusted series |
| Employment Situation | BLS: first, second and third estimates of the monthly payroll change, 1979 to present | BLS release schedule, 8:30 AM | The same BLS table |
| PCE, GDP | BEA release archive | BEA release schedule, 8:30 AM | Philadelphia Fed real-time data set (quarterly and monthly vintages from 1965) |
| Treasury par yields | Treasury daily yield curve | Quotes near 3:30 PM, published by about 6:00 PM | Method changed 2021-12-06; restatement of history unverified |

**Rules that do not change.** An exact release time is required. A vintage identified only by a month or quarter
(the Philadelphia Fed files) dates a value to the end of that period at the earliest; it is stored as a vintage, not
as a release time, and cannot be used inside the month it is dated to. No latest value is written into an earlier date.

**Not built in this checkpoint.** Historical collectors for these archives. The operator runs every collector by
hand; the parsers for the current-period releases exist and are tested.

## Regime coverage

Descriptive only (`firm_lab/history/regimes.py`): bear markets, corrections, volatility quintiles on an expanding
window, rate periods from dated decisions. Measured today on the only series stored, the 378 closes of the
Checkpoint 7 window: no bear market, one correction, two high-volatility episodes. That window is not a training
period. Coverage of the reserved development period needs a stored broad-market fund series and the full record of
policy decisions; until then it is `NOT MEASURABLE` and the regime bar is not met. No regime model exists.

## Intraday data: deferred

**Question.** Will daily OHLCV with expanded point-in-time fundamentals and events give enough training evidence for
a second tournament?

**Answer: yes for deciding, so intraday is deferred.** The binding constraint found at Checkpoint 7 was the number of
effective independent observations at 5 to 20 sessions. That is set by years of history and by breadth across
instruments. Intraday bars add neither: they describe the same sessions and the same instruments in finer detail.
They would matter for a horizon measured in minutes or for execution research, which no checkpoint has proposed.
A daily history is also the only one an individual licence covers back to 1998; consolidated intraday history under
terms that allow model research was not found at an individual price (`CHECKPOINT5_MARKET_DATA_DECISION.md`,
`CHECKPOINT8_PROVIDER_DECISION.md`). `intraday_bars` stays `UNAVAILABLE`. If daily data proves insufficient after it
is measured, the plan to revisit is: one question to a vendor about non-display rights, then a sample, then a decision.
