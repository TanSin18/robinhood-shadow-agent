# Historical research universe

Checkpoint 8, written 2026-10-04. Universe version `liquid-us-listed-v1`. Code: `firm_lab/history/universe.py`.
Research only: a list of securities to study, not a list to trade.

## The rule

On the last exchange session of each calendar month (the formation session R), every security that has bars from the
provider's stock-price table, delisted securities included, is screened using bars up to and including R and nothing
else. Which table a bar came from is recorded with the bar when it is stored; the present-day security master does
not decide who is screened.

1. At least 252 bars of history up to R.
2. A bar on R with an **unadjusted** close of at least $5.00.
3. A bar on at least 60 of the last 63 exchange sessions.
4. Ranked by the median daily dollar volume of those 63 sessions, highest first; the security identifier breaks
   ties. The first 1,000 are members. Dollar volume is the **unadjusted** close times the shares traded on the day
   (the vendor's adjusted volume divided by the confirmed split factor). It is not the product of two adjusted
   numbers, so it does not depend on how the vendor rounded prices it reprinted after a later split.

Membership takes effect on the session after R and lasts through the next formation session. The 1,000 is the
sufficiency target; the minimum acceptable is 500.

## Why this rule and not an index

* **Not the S&P 500.** Membership is a committee decision that responds to past performance, and a 500-name universe
  is at the minimum of the breadth bar. The provider's S&P 500 additions and removals are stored as a reference
  universe with their effective dates; they are not the research universe.
* **A liquidity screen is reproducible from prices alone.** Nothing is needed that was not in the bars on the day.
* **Dollar volume, not market value.** Shares outstanding at a past date need a point-in-time fundamentals source;
  dollar volume needs none, and a split does not change it (the price falls as the volume rises).
* **The printed price for the price screen.** A price adjusted for later splits is not the price on the day: a stock
  that later split 40-for-1 would look like a penny stock. A test proves the screen is unchanged by a later split.

## What the rule does not read

No sector, industry, security category, market value, index membership, analyst coverage, and no row of the
security master. The vendor's classifications and its master describe a company as it is today; applying them to
2005 would be a present-day label on the past. The only attribute used besides the bars is which price table the
bars were delivered in. A test changes a member's present-day master row and shows that no past membership moves.

## Known-at

Every input is a bar on or before R. Under `bar-known-at-v1` those are usable by the open of the next session, which
is the first session the membership applies to. Each formation record stores its formation session, effective dates,
`known_at`, the members, how many were screened out and why, and the rule's hash. Membership is tier B.

A test builds the universe from data ending in 2021 and again from data ending in 2026 and shows that every record up
to 2021 is identical: later data cannot change earlier membership.

## Survivorship

* The builder refuses a source in which no delisted security has bars (`SURVIVOR_ONLY_SOURCE`). This catches only
  the total absence of failures; completeness is bar H4.
* A company is a member for as long as it qualified. If its last bar falls on a formation session it is named for
  one more month (the rule cannot see the future); it has no bars there, so it contributes no rows.
* Labels of a member that delists inside the label window are kept and flagged (`historical_market_data_policy.md` §7).
* The manifest reports how many distinct members later delisted.

## Versioning and reproducibility

One record per formation session, plus a manifest with the rule, the period, a hash over every current bar block
of the screened table, a hash over the stored corporate actions and a hash over the records. The same stored bars,
the same actions and the same rule give the same universe hash. A different rule is a different version; nothing is
overwritten.

**Staleness.** When bars or actions are added or revised after a universe was built, that universe no longer
describes the stored data. `is_current` says so, and counting or materialising a dataset refuses it
(`UNIVERSE_IS_STALE`) until the universe is rebuilt. A rebuild stores a second universe beside the first; each is
read by its own hash, and a read that does not say which is refused when more than one exists
(`UNIVERSE_HASH_REQUIRED`). Records that do not match their manifest are refused
(`UNIVERSE_RECORDS_DO_NOT_MATCH_MANIFEST`).

## Limitations

* The provider's coverage of delisted securities is its claim ("about 99% free of survivorship bias") until measured.
* Share classes are separate securities: both classes of a dual-class company can be members.
* American depositary receipts in the stock table are included; the rule does not classify.
* No sector balance is enforced or claimed. Sector bar H5 is `NOT MEASURABLE` until a historical classification
  exists (`CHECKPOINT8_SOURCES_PIT.md`).
