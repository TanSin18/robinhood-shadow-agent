# VTI total return and the 70/30 total-return ruler — methodology

Version 1, written 2026-10-03 for Checkpoint 4. Implementation: `firm_lab/total_return.py` (arithmetic),
`firm_lab/benchmarks.py::compute_total_return` (validation and storage), `firm_lab_collectors/distributions.py`
(the issuer source). Implementation name in the database: `EX_DATE_REINVESTMENT_V1`.

This is a ruler. Nothing reads it to rank, select or trade, and nothing here changes Control A.

## 1. What is built

| Series | Benchmark id | Observation kind | Status |
|---|---|---|---|
| VTI closes, as stored | `VTI_100` | `close_price_return_basis` | unchanged, kept |
| VTI price-return index | `VTI_TOTAL_RETURN` | `vti_price_return_index` | new, separate |
| VTI total-return index | `VTI_TOTAL_RETURN` | `vti_total_return_index` | new |
| 13-week bill accrual index | `FIXED_70_30` | `tbill_13w_accrual_index` | unchanged (frozen methodology) |
| 70/30 with VTI price return — `LEGACY_PRICE_RETURN_RULER` | `FIXED_70_30` | `index_70_30_vti_price_return_basis` | unchanged, kept |
| 70/30 with VTI total return — `TOTAL_RETURN_RULER` | `FIXED_70_30_TOTAL_RETURN` | `index_70_30_vti_total_return` | new |

Nothing stored before this checkpoint is overwritten, renamed or recomputed. The two earlier benchmark definitions
are locked and are not edited; the labels `LEGACY_PRICE_RETURN_RULER` and `TOTAL_RETURN_RULER` live in the code and on
the page.

## 2. Inputs

1. **Prices.** The completed-session VTI closes already in the Firm Lab store (read from Control A's decision
   capsules; split-adjusted by their provider, not dividend-adjusted). No vendor "adjusted close" and no vendor
   total-return index is used, now or as a fallback.
2. **Distributions.** The fund issuer's own published list: `https://investor.vanguard.com/vmf/api/VTI/distribution`
   (public, no credential). Per distribution it gives the type, the amount per share with a dollar sign, the record
   date, the "reinvestment date", the payable date and the "reinvestment price".
   * **Ex-dividend date** = the feed's `reinvestmentDate`. The issuer's own fund page shows this field under the
     heading "Ex-dividend date" for an ETF (and "Reinvest date" for a mutual fund). It is not inferred from the
     record date.
   * **Currency** = USD, from the dollar sign. An amount without it is refused.
   * **Announcement time** = `UNAVAILABLE`. The feed gives no declaration time and none is made up.
   * Only the type `Dividend` is understood. Any other type (for example a capital-gain distribution) makes the
     issuer answer unusable until a rule for it is written here. It is not skipped.
   * The feed holds only the most recent distributions (six on 2026-10-03). Older ones are not reconstructed from
     any other source.
3. **The bill leg.** The frozen 13-week bill accrual index (`treasury_bill_total_return_methodology.md`, version 1,
   SHA-256 `c954c81b…40c4`), recomputed from the stored auction records exactly as before. That file is not edited.

## 3. Known-at and look-ahead

* A distribution is known to Firm Lab from the moment it was fetched and stored (`known_at` of its row). It is
  never treated as known earlier, even though the issuer declared it earlier.
* The computation uses only distributions known at the time it runs.
* Every stored observation carries a known-at: the latest of the session's 16:00 New York close, the known-at of the
  stored close, the known-at of every distribution applied up to that session and, for the ruler, the known-at of
  the bills used. So an observation after an ex-date that was computed from a distribution fetched on 2026-10-03
  says 2026-10-03, not the ex-date.

## 3a. Benchmark use is not predictive-feature use (operator rule, 2026-10-03)

* **Benchmark use.** Historical distributions may be used to rebuild an after-the-fact benchmark total-return series.
  That is what this document does, and all it does.
* **Predictive-feature use.** A historical distribution amount may not be treated as information that was known on
  its ex-date unless Firm Lab holds a validated publication or announcement time proving it was known then. The
  issuer feed gives none.
* Therefore every stored VTI distribution row is marked `benchmark_only = true`, with the reason in
  `use_restriction`. The mark is set at storage from the row itself (any corporate action without a validated,
  timezone-aware announcement time), not supplied by a provider, and it is not part of the record's content hash.
  Rows stored before the column existed were marked when the database was next opened (event
  `USE_RESTRICTION_MARKED`); nothing else on them changed. A mark is never removed.
* `firm_lab/usage.py` is the single gate. `distribution_rows(..., purpose='benchmark')` is what the ruler reads;
  `purpose='feature'` returns only rows with a validated announcement time at or before the asking time that are
  not marked, which today is none. Every feature-store write passes `require_feature_source_allowed`, which refuses
  benchmark-only material (`BENCHMARK_ONLY_DATA_NOT_ALLOWED_IN_FEATURES`).
* The total-return series built here are benchmark observations, not features, and are refused by the same gate.
* Enforced by `tests/test_firm_lab_total_return.py::test_distributions_are_benchmark_only_and_never_reach_the_feature_store`.

## 4. Validation (all must pass, or nothing is computed)

1. The latest issuer run was accepted whole (schema, provenance, no opinion-like field).
2. At least one issuer distribution has its ex-date after the first stored session and up to the last.
3. **Cadence.** No hole longer than 110 days between the first stored session, the ex-dates, and the last stored
   session. The fund pays quarterly; a longer hole means a distribution is missing from what is stored.
4. **Ex-date is a session.** Each ex-date is a stored VTI session.
5. **Share basis and date cross-check.** The issuer's reinvestment price is within 1% of the stored close on the
   ex-date. This compares two independent sources (the issuer and the closes Control A recorded). A wrong date, or a
   split between the distribution and the stored closes, shows up here.
6. **No conflicting records.** The same source never gave two different amounts for one distribution.
7. **Independent sources.** If distributions from any other source are stored, they must match the issuer's exactly
   (same ex-dates, same amounts). None is stored today: `independent_confirmation = NONE_STORED`. Nasdaq's public
   dividend endpoint answers "Dividend History for Non-Nasdaq symbols is not available" for VTI (captured
   2026-10-03), so it is not a source.
8. No split record is stored for VTI. If one ever is, the computation stops until a split rule is approved
   (`SPLIT_RECORD_NEEDS_A_RULE`); the arithmetic for it exists (`per_adjusted_share`) but is not applied.

A failed validation is recorded with its reasons (`firm_meta.vti_total_return_status`), shown on `/firm-lab`, and the
capabilities `vti_total_return` and `total_return_ruler` stay, or go back to, `UNAVAILABLE`.

## 5. Arithmetic

Sessions are the stored VTI sessions in order; `P(t)` is the stored close; `D(t)` is the sum of cash distributions
whose ex-date is session `t`.

* Price return: `PR(t) = 100 × P(t) / P(first)`.
* Total return: `TR(first) = 100`, `TR(t) = TR(t−1) × (P(t) + D(t)) / P(t−1)`.
  The distribution is reinvested at the close of its ex-dividend session. No tax, no cost, no delay to the payable
  date.
* 70/30 total-return ruler: the same construction as the legacy ruler (70% / 30%, weights reset at the close of the
  first stored session of each calendar month, no settlement lag, no cost), with `TR` in place of the VTI close.
* Decimal arithmetic with 40 significant digits; stored values are rounded to six decimals.
* The base (100) is the first stored VTI session, a development base. It is rebased when a Firm trading trial is
  registered. None is.

## 6. Stopping

The series stops, and nothing is stored from that session on, when: more than four calendar days pass between stored
sessions; a distribution's ex-date is not a stored session; a distribution is not in USD or not positive; the bill
index stops (the ruler only).

## 7. Never rewritten

A stored observation is never changed. If a later computation would give a different value for a session already
stored (for example a distribution that was learned after sessions beyond its ex-date were stored), the computation
stops with `BENCHMARK_OBSERVATION_CONFLICT` and changes nothing. A corrected series would be a new, separately named
version.

## 8. Limits, stated plainly

* The amounts rest on the issuer's own publication. No second source confirms them inside Firm Lab.
* Splits, symbol changes, spin-offs, mergers and delistings have no source. `corporate_actions` therefore says
  `PARTIAL_EXISTING` (VTI cash distributions only), not `AVAILABLE`.
* The fund's name changed in 2026; the ticker did not. Firm Lab checks the ticker against the SEC's fund list
  (series `S000002848`, class `C000007808`) when it reads SEC filing metadata; it holds no history of symbol changes.
* The history reaches back only as far as the stored closes and the issuer's list overlap.
