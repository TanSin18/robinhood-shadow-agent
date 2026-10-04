# Historical market data — storage, known-at, adjustment and survivorship policy

Checkpoint 8, written 2026-10-04. Policy version `historical-market-data-v1`. Research only. Nothing here is read by
Control A or by any trading path, and no table here can hold an order, a fill, a position or cash.

This policy is separate from the SEC and macro publication rules (`CHECKPOINT8_SOURCES_PIT.md`). Those sources publish
a timestamp for each fact. A daily bar has no publication timestamp, so its availability is bounded, not measured.

## 1. Where the data lives

* One separate file, `firm_lab_history.db`, beside the research database. Role `CHECKPOINT8_HISTORICAL_RESEARCH`,
  mode `BUILD_OBSERVE`. The registered (Control A) database is never opened for writing and the path check refuses it.
* Licensed vendor data lives only in that file. It is never committed to Git, never copied into a report, a prompt,
  a review file or the dashboard overlay. The readiness page reads a small summary file that holds counts and
  hashes, not prices.
* If the licence ends, the vendor's terms require the raw data to be deleted within 30 days. Deleting that one file
  does it. Derived research outputs that cannot reproduce the data (reports, counts, model files) may be kept.

## 2. Raw observations are append-only and versioned

* Every ingested file is recorded as a **capture**: file name, SHA-256, size, table kind, rows read, stored,
  duplicate and rejected, the adapter version and the capture time. That record is the validation receipt.
* Bars are stored per security and calendar year as one content-addressed block of the provider's own text values.
  Storing the same content again adds nothing. Different content for the same security and year is stored as the
  **next version**; the earlier version stays. Nothing is updated or deleted (database triggers refuse both).
* A new version records what changed: `SCALE_ONLY` when every price moved by one common factor and volume by its
  inverse (the vendor re-adjusting for a new split), `EXTENDED` when sessions were only added, or `VALUE_CHANGE`
  when a past value differs in any other way. A `VALUE_CHANGE` is a vendor revision of history; it is counted on the
  readiness page, because it is evidence against treating that value as first-published.
* Corporate actions, security-master rows and index-membership events are stored the same way: content-addressed,
  with the capture they came from.

## 3. Validation: reject, never repair

Each row is checked when it is read. A failing row is not stored as a bar. It is stored as a rejection with every
reason that applies, and the capture counts it.

| Reason | Check |
|---|---|
| `MISSING_FIELD` | open, high, low, close, volume, unadjusted close and session date are all present |
| `NOT_FINITE` | every number parses and is finite |
| `NON_POSITIVE_PRICE` | open, high, low, close and unadjusted close are above zero |
| `LOW_ABOVE_OPEN_OR_CLOSE` | `low <= min(open, close)` |
| `HIGH_BELOW_OPEN_OR_CLOSE` | `high >= max(open, close)` |
| `LOW_ABOVE_HIGH` | `low <= high` |
| `NEGATIVE_VOLUME` | `volume >= 0` |
| `NOT_AN_EXCHANGE_SESSION` | the date is a New York Stock Exchange session |
| `SESSION_NOT_COMPLETE_AT_CAPTURE` | the session had closed before the capture time |
| `UNKNOWN_SECURITY` | the symbol resolves to exactly one security in the stored security master |
| `AMBIGUOUS_SECURITY` | the symbol resolves to more than one security |
| `CONFLICTING_DUPLICATE` | two rows in one file for the same security and session differ: both are rejected |
| `CURRENCY_NOT_USD` | the security's price currency is U.S. dollars |

An identical duplicate row is kept once and counted. A file whose columns are not the documented ones is refused
whole (`UNEXPECTED_FILE_LAYOUT`).

**Consistency with corporate actions** is checked per security after bars and actions are both stored. The ratio of
unadjusted close to split-adjusted close is the cumulative split factor. It must be constant between split dates and
must step, at each recorded split date, by that split's ratio. The tolerance is 0.5% plus the largest error that
rounding of the two printed prices can cause, taken from the number of decimals the vendor printed. A step with no
recorded split (`SPLIT_FACTOR_WITHOUT_ACTION`), or a recorded split with no step (`ACTION_WITHOUT_SPLIT_FACTOR`), is
recorded as a **break** at that session: prices before it and after it cannot be compared. A feature whose lookback
reaches across a break is unavailable, and a label whose window contains one is excluded. Nothing is corrected. The
universe screen is not affected by a break: dollar volume does not change under a split, and the minimum-price screen
reads the printed close, not the factor.

## 4. Price basis

Every stored series names its basis. Bases are never mixed inside one calculation.

| Field | Basis |
|---|---|
| open, high, low, close, volume | `SPLIT_ADJUSTED_AS_OF_CAPTURE`: adjusted for splits up to the capture date; not adjusted for cash dividends or spin-offs |
| unadjusted close | `UNADJUSTED`: the price printed on the day |
| total-return close | `SPLIT_DIVIDEND_SPINOFF_ADJUSTED_AS_OF_CAPTURE`: the vendor's method; stored, not yet validated, used by nothing |

**Why a series adjusted as of today does not leak.** A split after session T multiplies every price at or before T
by the same number. A feature that is a ratio of prices (a return, a distance to an average, a wick over a range)
is unchanged by that number, so it has the value it would have had on T. Checkpoint 8 features are restricted to
such ratios; a feature in dollars is never a model input. A test applies a later split to a series and proves the
features before it do not move. The one place a true price level is needed, the universe's minimum-price screen,
uses the unadjusted close.

**Return methodology for targets: split-adjusted price return.** One method across the whole universe, as in
Checkpoint 7. Cash dividends are not added back. Known effects, stated rather than hidden:

* An ordinary dividend lowers the price return on its ex-date by the dividend yield (typically under 1%).
* A spin-off or a large one-off distribution produces a price gap that is not a loss. A feature whose lookback
  contains such an ex-date is unavailable for that row (`DISTRIBUTION_IN_WINDOW`), and a label whose window contains
  one is excluded (`LABEL_WINDOW_HAS_DISTRIBUTION`). "Large" is a single cash distribution of at least 5% of the
  prior unadjusted close. The excluded count is reported.
* A total-return label can replace this only after the vendor's total-return factor is reconciled against the
  recorded dividends and spin-offs across the universe. The reconciliation exists as an audit; until it passes on
  real data the total-return close is not used.

## 5. Known-at for a daily bar (`bar-known-at-v1`)

* A bar describes one exchange session. It cannot be known before that session closes (early closes included, from
  the exchange calendar).
* No source gives the time at which a historical end-of-day bar was first published, and none is invented. The bar
  is treated as available **no later than the open of the next exchange session**. That is a bound, stored as
  `eligible_from`, with the basis `EXCHANGE_SESSION_COMPLETE_NEXT_OPEN_BOUND`.
* The time Firm Lab actually received the bar is stored separately as `captured_at` and is never used as a
  historical known-at for a publisher-dated bar. A bar Firm Lab itself captured before `eligible_from` is tier A;
  a historical bar from a licensed archive is tier B.
* Consequence for a training row: features use bars up to and including session T; the decision time is the open
  of session T+1; the label starts at the open of T+1. No label uses a price at or before the last feature bar.

**What tier B does and does not claim for bars.** It claims that the session closed before the decision time and
that the price is the exchange's price for that session as the archive holds it. It does not claim Firm Lab held
the bar then, and it cannot rule out that the vendor corrected an erroneous print after the fact. Two safeguards
bound that: versioned captures expose any later `VALUE_CHANGE`, and closes Firm Lab already holds from another
source are compared one by one (bar O6 of the sufficiency specification).

## 6. Corporate actions

Stored as the provider reports them: type, effective date, value, counterparty. Types kept: split, cash dividend,
spin-off, symbol change, merger or acquisition, delisting (with the provider's reason). The provider gives an
effective date and no announcement time; `announcement_timestamp` is stored as `UNAVAILABLE`.

* A split takes effect in the adjusted series on its date; see §3 for the consistency check.
* A symbol change does not alter identity. Securities are keyed by the provider's permanent identifier, never by
  ticker, so a renamed company is one series and a reused ticker is two.
* An action is usable by a feature only from its effective date. No feature may use an action before it.

## 7. Survivorship

* The whole provider table is stored, delisted securities included, before any universe is formed. A universe
  formed only from securities trading today is refused by the builder (`SURVIVOR_ONLY_SOURCE`) when the stored
  security master holds no delisted security.
* The universe at a past date is formed only from bars up to that date (`historical_universe.md`). A company that
  later failed or was acquired is a member for as long as it qualified.
* **Labels through a delisting.** When a member's last bar falls inside a label window, the label uses the last
  available price as the exit and is marked `EXIT_AT_LAST_PRICE_BEFORE_DELISTING` with the provider's delisting
  reason. These rows are kept; dropping them would remove exactly the failures and takeovers.
* **Stated limitation.** No free or individually licensed source found gives a post-delisting return. For an
  acquisition the last price is close to the deal value. For a bankruptcy or a regulatory delisting the last price
  overstates what a holder recovered, so such labels are biased upward. The count of such rows per year and per
  reason is reported, and the limitation is shown on the readiness page.
* Coverage is the provider's claim until measured. The check that is possible is made: the number of securities
  with a last bar in each year, against the delisting actions recorded for that year.

## 8. Reproducibility

A dataset manifest names the capture identities and file hashes of every source table, the security-master and
action versions, the universe version and its hash, each feature-set version with the code hash, the target version
and the split version. The same captures and the same code give the same dataset hash; a test builds twice and
compares.
