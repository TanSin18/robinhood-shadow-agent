# Historical market data — storage, known-at, adjustment and survivorship policy

Checkpoint 8, written 2026-10-04. Policy version `historical-market-data-v1`. Research only. Nothing here is read by
Control A or by any trading path, and no table here can hold an order, a fill, a position or cash.

This policy is separate from the SEC and macro publication rules (`CHECKPOINT8_SOURCES_PIT.md`). Those sources publish
a timestamp for each fact. A daily bar has no publication timestamp, so its availability is bounded, not measured.

## 1. Where the data lives

* One separate file, `firm_lab_history.db`, beside the research database. Role `CHECKPOINT8_HISTORICAL_RESEARCH`,
  mode `BUILD_OBSERVE`. The registered (Control A) database is never opened for writing. The path check refuses the
  registered file, its folder, any folder that holds an `agent.db`, and any Git work tree. The same check guards the
  readiness summary file, and a vendor file that sits inside a repository is refused before it is read
  (`VENDOR_FILE_INSIDE_A_REPOSITORY`).
* Licensed vendor data lives only in that file. It is never committed to Git, never copied into a report, a prompt,
  a review file or the dashboard overlay. The readiness page reads a small summary file that holds counts and
  hashes, not prices.
* If the licence ends, the vendor's terms require the raw data to be deleted within 30 days. Deleting that one file
  (and the files the operator downloaded) does it. Ingestion keeps its working rows in a private temporary database
  that the operating system removes when it is closed or when the process dies, so a run that was cut short leaves
  no vendor row beside the database. Derived research outputs that cannot reproduce the data (reports, counts, model
  files) may be kept.

## 2. Raw observations are append-only and versioned

* Every ingested file is recorded as a **capture**: file name, SHA-256, size, table kind, rows read, stored,
  duplicate and rejected, the adapter version and the capture time. That record is the validation receipt.
* **A capture is stored whole or not at all.** One file is one database transaction; a failure part-way leaves
  nothing behind.
* **Two clocks.** A capture made without a supplied time is stamped by the machine's clock and marked `SYSTEM`. A
  capture made with a supplied time is marked `SUPPLIED`: the time orders the versions and proves nothing, so a bar
  stored under it never counts as held at the time. A supplied time must be a real time with an offset
  (`INVALID_CAPTURE_TIME`), may not lie in the future (`CAPTURE_TIME_IN_THE_FUTURE`) and, like every capture time,
  may not be earlier than a capture already stored (`CAPTURE_TIME_NOT_MONOTONIC`). Times are compared as times,
  never as text. The commands always use the machine's clock.
* Bars are stored per security and calendar year as one block of the provider's own text values. A new capture for
  a security and year is compared with the **current** version. The same content adds nothing. Anything else becomes
  the **next version**, and the earlier one stays, also when the vendor returns to content it supplied before.
* **Extending and removing.** A capture that holds only some sessions of a year extends that year. Inside the span
  of sessions the capture does hold, a stored session it no longer mentions is **removed** from the new version: the
  vendor took the bar out, and that is a `VALUE_CHANGE`. Outside that span nothing is removed. A file that lists only
  scattered rows (for example the rows changed since a date) must be ingested as `sparse`; then nothing is removed.
* Every block is validated again at the point of storage, the capture-time check included (`INVALID_BAR_BLOCK`), so
  the store's own methods cannot store a bar the row checks would have rejected or a bar "captured" before its
  session closed. A clock cannot be claimed either: the store hands out the time and clock of a capture once, and a
  block is accepted only under that pair. The latest stored time is read from the database at every capture, so a
  second connection cannot be overtaken.
* A new version records what changed:

  | Class | Meaning |
  |---|---|
  | `EXTENDED` | only sessions after the previous last session were added |
  | `SCALE_ONLY` | every session before some date moved by one common factor (prices times k, volume divided by k) and the printed price did not move: the vendor re-adjusting for a later split. All four prices and the volume of every changed row must agree on one factor, within what the printing of both versions can explain. A volume is taken as rounded to a whole share at best, however it is printed, and at least one changed row must have traded |
  | `TOTAL_RETURN_READJUSTED` | only the total-return close differs: a later dividend |
  | `METADATA_ONLY` | only the provider's update stamp differs |
  | `VALUE_CHANGE` | anything else: one corrected print, a session that appeared in the past, a session that disappeared, a "rescale" that only some rows or some columns show, the same numbers printed otherwise |

  A `VALUE_CHANGE` is a vendor revision of history. It is counted on the readiness page ("Stored versions"). Every
  row of that version whose values differ from the version before is a **revised bar**: it is dated to the capture
  that revised it, and it is a restated value. A training row that reads a revised bar, in a feature or in its
  label, is tier C and is not a strict sample (§5); such rows are counted, not hidden. A bar the vendor **removed**
  is treated the same way: the rows that would have read it are tier C.
* Security-master rows, corporate actions and index-membership events are stored content-addressed with the capture
  they came from. A security-master row that returns to an earlier state is stored as a new row, so "the current row"
  is always the latest stored. Two securities claiming one identifier with different names is refused
  (`CONFLICTING_SECURITY_IDENTITY`).
* One store may hold more than one source, but bars of two sources are never read as one series: a read that does
  not name the source is refused when two exist (`SOURCE_REQUIRED`).
* **What append-only means.** Every connection this package opens refuses UPDATE, DELETE and REPLACE through database
  triggers. That protects against the package's own mistakes. It does not protect against a person with the file and
  a SQL prompt. What makes such a change detectable is that every block carries the hash of its content and every
  universe and dataset names the hash of the blocks it was built from.

## 3. Validation: reject, never repair

Each row is checked when it is read. A failing row is not stored as a bar. It is stored as a rejection with every
reason that applies, and the capture counts it.

| Reason | Check |
|---|---|
| `MISSING_FIELD` | open, high, low, close, volume, unadjusted close and session date are all present |
| `NOT_FINITE` | every number is written in ASCII digits as a decimal, with or without an exponent, and is finite; anything else (`nan`, `inf`, a plus sign, hexadecimal, digits of another script, underscores, spaces) is refused |
| `NON_POSITIVE_PRICE` | open, high, low, close and unadjusted close are above zero |
| `LOW_ABOVE_OPEN_OR_CLOSE` | `low <= min(open, close)` |
| `HIGH_BELOW_OPEN_OR_CLOSE` | `high >= max(open, close)` |
| `LOW_ABOVE_HIGH` | `low <= high` |
| `NEGATIVE_VOLUME` | `volume >= 0` |
| `INVALID_TOTAL_RETURN_CLOSE` | the total-return close may be absent; when present it is a positive number |
| `NOT_AN_EXCHANGE_SESSION` | the date is a New York Stock Exchange session |
| `SESSION_NOT_COMPLETE_AT_CAPTURE` | the session had closed before the capture time (compared as times) |
| `UNKNOWN_SECURITY` | the symbol resolves to exactly one security in the stored security master |
| `AMBIGUOUS_SECURITY` | the symbol resolves to more than one security |
| `CONFLICTING_DUPLICATE` | two rows in one file for the same security and session differ: both are rejected |
| `CURRENCY_NOT_USD` | the security's price currency is stated and is U.S. dollars; a blank currency is not assumed |

An identical duplicate row is kept once and counted. A file with a required column missing, or with a column
repeated in its header, is refused whole (`UNEXPECTED_FILE_LAYOUT`). A security-master row whose delisted flag is
not one of the provider's two values is rejected (`MALFORMED_SECURITY`); nothing is guessed from it.

**Consistency with corporate actions** is checked per security after bars and actions are both stored. One rule
governs every decision: what a row may read must not depend on a split that happened after it. After later splits
the vendor reprints early prices as small, coarsely rounded numbers, so anything decided from the reprinted prices
could differ between a stock that split later and one that did not.

* **A recorded split is applied as recorded**, from the first bar on or after its date; splits dated on one session
  multiply. Its value is read as new shares per old share.
* **The vendor's factor is an audit, not the source.** The ratio of unadjusted close to split-adjusted close is the
  vendor's cumulative split factor. It is asked only whether it contradicts the record beyond what its own rounding
  can explain. The tolerance is 0.5% plus the rounding of the two printed prices, taken from the decimals of **that
  bar's own row** (the most decimals among its open, high, low and close). Only the bar's own row is read: a
  precision taken over the whole column would let one later print change how every earlier bar is judged. A correct
  record is never contradicted, however coarse the reprint. It is counted as confirmed where the step is visible and
  as unchecked (`splits_unchecked`) where the step is too small to see there.
* **Continuity** across a split is asked of the unadjusted close and the recorded ratio, never of the reprinted
  closes.
* **A break** is recorded where the factor steps with no recorded split (`SPLIT_FACTOR_WITHOUT_ACTION`), where the
  record and the factor contradict each other (the same reason when a step is visible,
  `ACTION_WITHOUT_SPLIT_FACTOR` when none is), and where a split is recorded the other way round. Prices before and
  after a break cannot be compared: a feature whose lookback reaches across it is unavailable, and a label whose
  window contains it is excluded. Nothing is corrected.
* **The two readings of the action table** that all of this rests on are stated in the code and counted against the
  cases the prices can show: a split's value is new shares per old share (`split_convention`), and a dividend's value
  is the amount paid per share on the day (`dividend_basis`). When a visible case contradicts either reading, no
  dataset is built (`SPLIT_VALUE_CONVENTION_CONTRADICTED`, `DIVIDEND_AMOUNT_BASIS_CONTRADICTED`) until the adapter is
  corrected. The validation sample is where this is found out.
* **What still depends on the reprint** is whether an *error* in the vendor's own tables is caught: an unrecorded
  split or a wrong ratio is seen under a fine print and can be missed under a coarse one. A check that cannot be
  made is not a failure. Where a vendor drops trailing zeros, a bar whose four prices are all round is judged coarser
  than it is: that withholds the high, low and open families (cautious) and widens the audit's tolerance at that bar
  (less able to catch a vendor error there). A declared print format for the vendor would remove both; it is a
  registered change to make after a real file has been read, not before.

The universe screen is not affected by a break: dollar volume does not change under a split, and the minimum-price
screen reads the printed close, not the factor.

## 4. Price basis

Every stored series names its basis. Bases are never mixed inside one calculation.

| Field | Basis |
|---|---|
| open, high, low, close, volume | `SPLIT_ADJUSTED_AS_OF_CAPTURE`: adjusted for splits up to the capture date; not adjusted for cash dividends or spin-offs |
| unadjusted close | `UNADJUSTED`: the price printed on the day |
| total-return close | `SPLIT_DIVIDEND_SPINOFF_ADJUSTED_AS_OF_CAPTURE`: the vendor's method; checked only for being a positive number; read only to size a recorded distribution, never as a price |

**Why a later split does not leak, and where it could.** A split after session T multiplies every price at or before
T by the same number. A feature that is a ratio of prices (a return, a distance to an average, a wick over a range)
is unchanged by that number. Checkpoint 8 features are restricted to such ratios; a feature in dollars is never a
model input.

That holds for exact numbers. A vendor's reprinted adjusted prices are rounded to a fixed number of decimals, and for
a stock that later split many times the early adjusted prices are small numbers rounded coarsely. The coarseness
depends on the future. Two rules close that channel:

* **The exact close.** Across sessions, the close is rebuilt from the unadjusted close (the price printed on the day)
  and the confirmed split ratios. The vendor's adjusted prints are used only within one bar: its open, high and low
  relative to its own close. A test reprints a history at three decimals after a large later split and shows that no
  close-based feature before the split moves.
* **Print precision: all rows or none.** Where the adjusted close is printed more coarsely than 0.05% of its value,
  the shape of the bar cannot be trusted. Withholding the features that read a high, low or open only on those rows
  would mark exactly the stocks that split later, which is information from the future. So those feature families
  are used for every row of a dataset or for none: as soon as one row of the dataset would read a coarsely printed
  bar, they are withheld from every row. The share of coarse rows is reported (sufficiency bar O7); the decision
  does not wait for a threshold. A test prints one stock as after a 40-for-1 split six years later and shows that
  the rows of that stock cannot be told from the others by what is missing.

What remains is bounded and stated: on rows that are used, a reprinted high, low or open can be off by up to 0.05%
of the price, and how far depends on later splits. The measure is deliberately blunt: a vendor that prints two
decimals makes every bar under $10 coarse by it, whether or not a split followed.

* **What a coarse reprint may not decide.** Whether a recorded split is applied, whether a distribution is large and
  what a label is worth are all taken from numbers a later split cannot change: the recorded actions and the
  unadjusted close (§3, and the label below). The vendor's adjusted prints are read for two things only: the shape of
  a bar (its open, high and low relative to its own close), under the all-or-none rule above, and the audit of §3.

The one place a true price level is needed, the universe's minimum-price screen, uses the unadjusted close.

**Return methodology for targets: split-adjusted price return** (`forward-close-to-close-price-return-v3`). One
method across the whole universe. For a row at session T the label at horizon h is `close[T+1+h] / close[T+1] - 1`
on the exact close. The decision time is the open of T+1; the entry is the close of T+1, the first price after the
decision that no later split can blur. The vendor supplies the open only split-adjusted and reprinted, and a label
built from reprinted opens was measured in review to be off by a median of 0.7% (up to 4%) for a stock whose later
splits left its adjusted price near 0.40 at two decimals. Cash dividends are not added back. Known effects, stated
rather than hidden:

* The move from the open to the close of T+1 is not part of the label.
* An ordinary dividend lowers the price return on its ex-date by the dividend yield (typically under 1%).
* A spin-off or a large one-off distribution produces a price gap that is not a loss. It is a **break**: a feature
  whose lookback reaches across it is unavailable, the recursive averages (ATR, RSI) restart there, and a label whose
  window contains it is excluded (`LABEL_WINDOW_HAS_BREAK`). "Large" is a single cash distribution of at least 5% of
  the prior close, sized by its **recorded amount over the unadjusted close of the session before**. A distribution
  recorded without an amount cannot be sized from anything a later split leaves alone and is a break
  (`DISTRIBUTION_WITHOUT_AMOUNT`). The excluded count is reported.
* The vendor's total-return close is never used as a price and decides nothing. It is read for one tally: whether
  the vendor's own factor agrees that the recorded amounts are per share on the day (`dividend_basis`). A
  total-return label can replace the price-return label only after the factor is reconciled against the recorded
  dividends and spin-offs across the universe; the reconciliation exists as an audit.

## 5. Known-at for a daily bar (`bar-known-at-v1`)

* A bar describes one exchange session. It cannot be known before that session closes (early closes included, from
  the exchange calendar).
* No source gives the time at which a historical end-of-day bar was first published, and none is invented. The bar
  is treated as available **no later than the open of the next exchange session**. That is a bound, computed from
  the exchange calendar (`eligible_from`), with the basis `EXCHANGE_SESSION_COMPLETE_NEXT_OPEN_BOUND`. It is not a
  stored column.
* The time Firm Lab actually received a bar is the creation time of the stored version it sits in, and is never used
  as a historical known-at for a publisher-dated bar. A bar is held at the time only when the value **read today**
  was stored, by the machine's own clock, before `eligible_from`. A pure rescale for a later split does not change
  that; a revision does. A historical bar from a licensed archive is tier B.
* **What a row reads, and its tier.** A row's features read its last 253 bars (the 252-session return needs both
  ends), and further back where the pivot or leg it stands on began earlier. Its label reads the bars from T+1 to its
  exit. The row is tier A only if every bar its features read was held at the time; it is tier C, and not a strict
  sample, if any bar its features or its longest label read was revised by the vendor after it was first stored;
  otherwise tier B. (Wilder's smoothing carries a weight below one part in a hundred million from bars older than
  that window; it is not followed further.)
* Consequence for a training row: features use bars up to and including session T; the decision time is the open
  of session T+1; the label starts at the close of T+1. No label uses a price at or before the last feature bar.

**What tier B does and does not claim for bars.** It claims that the session closed before the decision time and
that the price is the exchange's price for that session as the archive holds it. It does not claim Firm Lab held
the bar then, and it cannot rule out that the vendor corrected an erroneous print after the fact. Two safeguards
bound that: versioned captures expose any later `VALUE_CHANGE`, and closes Firm Lab already holds from another
source are compared one by one (bar O6 of the sufficiency specification). Rejected rows are measured per file: bar
O4 is the largest rejected share in any one bar file, so ingesting a clean file again cannot dilute a bad one.

## 6. Corporate actions

Stored as the provider reports them: type, effective date, value, counterparty. Types kept: split, cash dividend,
spin-off, symbol change, merger or acquisition, delisting (with the provider's reason). The provider gives an
effective date and no announcement time; `announcement_timestamp` is stored as `UNAVAILABLE`.

* A split takes effect in the adjusted series on its date; see §3 for the consistency check.
* A symbol change does not alter identity. Securities are keyed by the provider's permanent identifier, never by
  ticker, so a renamed company is one series and a reused ticker is two.
* An action is usable by a feature only from its effective date. No feature may use an action before it.

## 7. Survivorship

* The whole provider table is stored, delisted securities included, before any universe is formed. The builder
  refuses a source in which **no delisted security has bars** (`SURVIVOR_ONLY_SOURCE`); a delisted row in the master
  with no price history behind it does not pass. That guard catches only the total absence of failures. The measure
  of how complete they are is bar H4, below.
* The universe at a past date is formed only from bars up to that date (`historical_universe.md`). A company that
  later failed or was acquired is a member for as long as it qualified.
* **Labels through a delisting.** A delisting is taken from a **dated record** (a delisting, or an acquisition by
  another company) within five sessions of the security's last bar. The present-day delisted flag of the master is
  not used: it says nothing about when, and it would turn the mere end of the stored data into an exit. With such a
  record, a label whose window runs past the last bar uses the last close as the exit and has the state
  `EXIT_AT_LAST_PRICE_BEFORE_DELISTING` with the provider's reason. Bars that stop on the last session stored for
  any security have not been shown to stop at all, and a record dated after that session describes something the
  stored data cannot show: neither makes an exit. These rows are kept; dropping them would remove exactly the failures
  and takeovers. Such a label covers fewer sessions than its horizon (down to a single session); it is flagged so
  that a later plan can treat it apart.
* **Bars that end without a record.** A member whose bars stop before the end of the stored data with no such record
  gets no label there (`WINDOW_PAST_STORED_HISTORY`) and is counted (`members_whose_bars_end_without_a_delisting_record`). A large
  count is evidence that the vendor's action table is incomplete.
* **Stated limitation.** No free or individually licensed source found gives a post-delisting return. For an
  acquisition the last price is close to the deal value. For a bankruptcy or a regulatory delisting the last price
  overstates what a holder recovered, so such labels are biased upward. The count of such rows per year and per
  reason is reported (`delisting_exits_by_year`), and the limitation is shown on the readiness page.
* Coverage is the provider's claim until measured. What is reported: the number of delisted securities by the year
  of their last bar, the delisting exits by year and reason, and the members whose bars end with no record. A
  comparison against an independent count of delistings per year is not made; no such count is held.

## 8. Reproducibility

A dataset manifest names the capture identities and file hashes of every source table, the hash of the current bar
blocks, the hash of the corporate actions, the universe version and its hash, each feature-set version with the code
hash, the target version and the split version. The same captures and the same code give the same dataset hash; a
test builds twice and compares. The dataset hash covers label states and evidence tiers as well as values.

A universe records the bar blocks and actions it was formed from. When either changes, the stored universe is
**stale**: counting and materialising refuse it (`UNIVERSE_IS_STALE`) until it is rebuilt. A rebuild adds a new
universe beside the old one; the old one stays readable by its hash.

These hashes are integrity checks, not authentication. A person who can write the file can write a matching hash.
The readiness page says what it read and from where; it does not claim more.
