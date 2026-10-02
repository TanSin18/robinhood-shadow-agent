# 3-month U.S. Treasury-bill total return — construction methodology

**Status: DRAFT FOR OPERATOR REVIEW. Not approved. Not frozen. Nothing has been computed.**

Version: draft 1, 2026-10-02. Author: Claude (Firm Lab build). Reviewer and approver: the operator.

This document defines how the Treasury-bill leg of the fixed benchmark

> 70% VTI + 30% rolled 3-month U.S. Treasury-bill total return, rebalanced monthly on the first NYSE trading session of each calendar month

would be built from official U.S. Treasury data. Until the operator approves and freezes it:

* no index value, return or benchmark figure is calculated or stored;
* the benchmark's implementation status stays `DATA_SOURCE_PENDING`;
* the capability `treasury_total_return` stays `UNAVAILABLE`;
* `firm_lab.benchmarks.compute_fixed_70_30` refuses to run.

It answers "how would the ruler be built?" It does not build it.

---

## 1. What is ruled out

| Ruled out | Why |
|---|---|
| A bill ETF or money-market fund (BIL, SGOV, SHV, …) as a stand-in | The benchmark is defined on the bill itself. A fund has fees, its own roll rules and a market price. |
| Compounding a yield or discount-rate series day by day | A quoted rate is not a return. The Daily Treasury Bill Rates are indicative closing bid quotations on the most recently auctioned bill of each tenor; they are not the price path of any bill one could have held. |
| A vendor index (ICE BofA 3-Month Treasury Bill, Bloomberg) | Licensed data, not official Treasury data. Listed in section 12 as an alternative the operator may choose instead. |
| Any modelled or interpolated price for a specific bill | Firm Lab stores what a source published. It does not estimate market prices. |

## 2. Instrument

The 13-week U.S. Treasury bill: the security the Treasury auctions weekly and records with security type `Bill` and security term `13-Week`.

* A 13-week bill is normally a reopening of an earlier 26-week (sometimes 52-week) bill and carries that bill's CUSIP. It is identified by its auction record, not by a CUSIP list.
* Cash-management bills and every other tenor are excluded.
* The leg holds exactly one bill at a time.

## 3. Source data

Primary and only computational input: the U.S. Treasury **Fiscal Data — Treasury Securities Auctions Data** dataset

`https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query`

Fields used, exactly as published:

| Field | Use |
|---|---|
| `security_type`, `security_term` | selects `Bill`, `13-Week` |
| `cusip` | identity |
| `auction_date` | when the result became public |
| `issue_date` | purchase and settlement date |
| `maturity_date` | redemption date |
| `high_discnt_rate` | the single (stop-out) discount rate every successful bidder receives |
| `price_per100` | purchase price per $100 of face value |
| `closing_time_comp` | competitive closing time, for the known-at rule |
| `reopening`, `original_security_term` | recorded for audit; not used in the arithmetic |

Cross-checks only, never inputs to the index:

* TreasuryDirect auctioned-securities records for the same CUSIP (identity, dates, price).
* Daily Treasury Bill Rates, 13-week bank discount, on the auction date (sanity check on the level of the auction rate).

A disagreement in a cross-check is recorded as a data-quality finding. It does not change a stored value.

## 4. Purchase and roll rule

1. **Purchase at auction.** Each bill is bought on its issue date at its auction price `price_per100`. This is the price a non-competitive bidder pays: Treasury bill auctions are single-price, so every successful bidder pays the price of the highest accepted discount rate.
2. **Hold to maturity.** The bill is never sold. On its maturity date it pays $100 per $100 of face value.
3. **Roll on the maturity date.** The whole redemption amount is invested, the same day, in the 13-week bill whose issue date equals that maturity date, at that bill's auction price.
4. **No bill issued that day.** If no 13-week bill has an issue date equal to the maturity date (a cancelled or rescheduled auction), the money earns nothing until the next 13-week issue date and is invested then. Each such day is recorded as uninvested. No other tenor or instrument is substituted.

The Treasury moves issue and maturity dates together around holidays (a Thursday holiday moves both to the next business day), so step 4 is expected to be rare. It is a rule, not an assumption that it never happens.

## 5. Auction input, not a secondary-market input

The leg uses **auction prices only**. No secondary-market price is used anywhere.

Reason: the official free data has no price history for an individual bill after its auction. The Daily Treasury Bill Rates follow whichever bill was auctioned most recently, so one week after purchase they describe a different bill. Marking the held bill to market would need per-CUSIP end-of-day prices (section 12, alternative B) or a model, and a model is ruled out.

Consequence, stated plainly: between a bill's issue and maturity the index is an **accrual**, not a market value (section 7). Over every complete holding period it equals the realised hold-to-maturity return exactly.

## 6. Settlement convention

* A bill bought at auction settles on its issue date. The purchase is dated the issue date.
* Redemption is received on the maturity date and is reinvested the same day (rule 4.3). There is no settlement gap inside the leg.
* Monthly rebalancing against VTI (section 9) is computed at the close of the rebalance session with no settlement lag, no transaction cost and no bid/ask spread. The benchmark is a ruler, not a tradable account. This is a stated simplification: in a real account both VTI and secondary-market bill trades settle one business day later.
* Face amounts are not rounded to the $100 minimum denomination; the index is pure arithmetic.

## 7. Day count and valuation between issue and maturity

Official price formula (31 CFR 356, Appendix B), used to **verify** each auction record:

```
P = 100 × (1 − d × r / 360)        rounded to six decimals
```

`d` is the discount rate as a decimal, `r` the actual number of days from issue to maturity. A record whose published price does not equal this formula applied to its published rate and dates is refused (section 11).

Illustration of the check only (this is not an index value): the 13-week bill auctioned 2026-09-28, issued 2026-10-01, maturing 2026-12-31 (91 days) at a high discount rate of 4.110% has a published price of 98.961083, and `100 × (1 − 0.04110 × 91 / 360) = 98.961083`.

Value of the held bill on calendar day `t`, per $100 of face, for `issue ≤ t ≤ maturity`:

```
V(t) = P + (100 − P) × (t − issue) / (maturity − issue)
```

with both differences in actual calendar days. This is the bill re-priced each day at its own auction discount rate on the official actual/360 basis: the discount accretes in a straight line from the purchase price to par. `V(issue) = P` and `V(maturity) = 100` exactly.

Interest accrues on every calendar day, including weekends and holidays.

## 8. The index

```
I(start) = 100
I(t)     = I(issue of the bill held on t) × V(t) / P        for every calendar day t
```

On a roll date the index is continuous: the maturing bill is worth 100, and the new bill is bought at its price with all of the proceeds.

* **Total return.** A bill pays no coupon. Its entire return is the accretion from purchase price to par, which the index captures in full, with full reinvestment at every roll.
* **Reinvestment.** 100% of redemption proceeds, at each roll, into the next bill. Nothing is withdrawn or added inside the leg.
* **Precision.** Decimal arithmetic, at least twelve decimal places internally; stored to six.
* **Taxes, fees, costs.** None.

## 9. Session and holiday alignment

* The index is defined for every calendar day (section 7), so it has a value on every NYSE session, including NYSE sessions on which the bond market is closed (for example Columbus Day and Veterans Day). No bond-market price is needed on those days.
* Benchmark observations are produced for NYSE session dates only, aligned with VTI.
* The monthly rebalance date is the first NYSE trading session of each calendar month. Firm Lab holds no exchange-calendar file; the session dates are the dates for which a completed VTI session close is stored. The rebalance for a month is therefore computed only after that session's close is stored.
* On the rebalance session the 70/30 weights are reset using that session's VTI close and `I(t)` for the same date.

## 10. Publication timing and known-at

* Competitive bidding for bills normally closes at 11:30 a.m. New York time on the auction date, and results are released within minutes. The record's `closing_time_comp` is stored.
* **Known-at rule.** An auction result is treated as known from **5:00 p.m. New York time on its auction date**, or from the moment Firm Lab ingested it if that is later. The cushion is deliberate: it is always after the real release, including auctions that close later than usual.
* A bill is first used on its issue date, normally three calendar days after its auction. So every price is known before the first day it affects the index.
* `I(t)` depends only on bills issued on or before `t`. It is known at the close of session `t`; nothing published later can change it.
* Auction records are final when published. If the Treasury ever republishes a record with different values, both versions are kept and the index is not silently recomputed (section 11).

## 11. Missing or inconsistent observations

The index stops, with status `DATA_GAP` from the first affected date, when for a bill it needs:

* no auction record is found;
* a required field is missing;
* the published price does not match the official formula applied to the published rate and dates;
* the issue date is not before the maturity date, or the term is outside 80–100 days;
* two records for the same auction disagree.

Nothing is filled forward. No other tenor, quoted rate, vendor value or estimate is used to bridge a gap. The gap is shown as a gap until the operator decides what to do.

## 12. What this construction is not, and the alternatives

**It is an accrual index.** Between issue and maturity it ignores changes in market rates. A bill's market value moves when rates move; this index does not show that movement, so it is smoother than a market-value index. Each complete 13-week holding period is exact. For a bill of 91 days or less, a one-percentage-point move in rates changes its market value by at most about a quarter of one percent, and that difference is gone by maturity. In a 30% sleeve the effect on a monthly benchmark return is a few hundredths of a percentage point at most and does not accumulate.

It is not the ICE BofA US 3-Month Treasury Bill Index, which holds one bill for a calendar month, values it at market prices and rolls it at month end.

Alternatives the operator may choose instead of, or later in place of, this draft:

| | Construction | Needs | Trade-off |
|---|---|---|---|
| **A (this draft)** | Buy at auction, hold to maturity, roll every 13 weeks; accrual between | Auction records only | Fully official, reproducible, known in advance. Not a market value. |
| B | Monthly roll, valued at market each day | Official per-CUSIP end-of-day prices (TreasuryDirect FedInvest historical prices). **Not verified**: availability, history and terms have not been confirmed | Closest to "rolled, marked to market". Depends on a source that has not been checked. |
| C | Weekly ladder of thirteen bills, each held to maturity | Auction records only | Smoother and closer to how bills are actually rolled. Thirteen positions instead of one. |
| D | Licensed vendor index | A paid licence | Industry standard. Not official Treasury data, and not reproducible from public records. |

## 13. Starting value

* `I = 100.000000` on the benchmark's inception date.
* The inception date is fixed when a Firm trading trial is registered. No date is chosen here and no trial is registered.
* If the inception date is not an issue date, the leg starts in the 13-week bill with the latest issue date on or before inception, entered at its accrued value `V(inception)`. Because the index is rebased to 100, its history before inception does not matter.

## 14. Not verified

Stated so that nothing here is taken on trust:

* The terms of use of the Fiscal Data dataset (expected to be public U.S. government data; not confirmed).
* The exact minute auction results are released (the 5:00 p.m. rule does not depend on it).
* FedInvest per-CUSIP historical prices (alternative B).
* Any NYSE or bond-market holiday calendar. The method does not use one.

## 15. Decisions for the operator

1. Approve construction A, or choose B, C or D.
2. Approve the accrual valuation in section 7 (straight-line accretion at the auction discount rate).
3. Approve the known-at rule in section 10.
4. Approve the zero-return rule for uninvested days (4.4) and the stop-on-gap rule (section 11).
5. Confirm that rebalancing is computed without settlement lag or costs (section 6).

## 16. Approval and freeze

On approval, by an explicit dated operator instruction:

1. this file's SHA-256 is recorded in the benchmark definition (`treasury_bill_series`);
2. the methodology status changes from `DRAFT_FOR_OPERATOR_REVIEW` to `APPROVED_AND_FROZEN`;
3. only then may an ingestion and a computation be built, validated and, if validation passes, reported.

A frozen methodology is never edited. A change is a new version with a new date, applied going forward only.

```
Approved by: ______________________     Date: ______________     File SHA-256: ______________________
```
