# Approval record — 3-month U.S. Treasury-bill total return methodology, version 1

| | |
|---|---|
| Methodology file | `docs/firm_lab/treasury_bill_total_return_methodology.md` |
| Version | 1 (the text headed "draft 1, 2026-10-02") |
| File SHA-256 | `c954c81b330aa3d43d97f4e19184321cf9f1c67fb974458f82443185d5fe40c4` |
| Status | `APPROVED_AND_FROZEN` |
| Approved by | the operator, by instruction in the working session |
| Approved at | 2026-10-02 10:31 ET (`2026-10-02T10:31:00-04:00`, to the minute) |

## What the operator approved

1. Construction A: each 13-week bill is taken at its auction price on its issue date, held to maturity and rolled the
   same day into the bill issued that day.
2. Straight-line accrual valuation between issue and maturity (section 7).
3. The known-at rule: 5:00 p.m. New York time on the auction date, or the moment of ingestion if that is later (section 10).
4. Zero return while temporarily uninvested (rule 4.4).
5. The stop-on-gap rule (section 11).
6. Benchmark rebalancing with no settlement lag and no transaction cost (section 6).

## How the freeze works

* The methodology file is frozen **exactly as it was approved**. It is never edited again, not even to fill in its own
  approval block or to change the word "draft" in its heading; that is why this record is a separate file. The file's
  status is what this record and `firm_lab/benchmarks.py` say it is.
* `firm_lab.benchmarks.require_frozen_methodology` computes the SHA-256 of the file on disk and refuses to compute
  anything unless it equals the hash above. A test fails if the file changes by a single byte.
* A change of any kind is a new methodology version: a new file, a new hash, a new approval record. It applies going
  forward only; observations already stored are never recomputed.

## What the approval allows, and nothing more

Treasury auction ingestion; validation of the published `price_per100` against the official formula; the 13-week bill
accrual index; the monthly 70/30 benchmark calculation; benchmark observations.

The benchmark is a ruler only. No trading logic is connected to it, no Firm trading trial is registered, and the
October research stop is not superseded.
