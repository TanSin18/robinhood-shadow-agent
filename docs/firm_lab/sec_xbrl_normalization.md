# SEC XBRL company facts — normalization rules

Rules version `sec-xbrl-normalization-v1`, written 2026-10-03 for Checkpoint 4. Implementation:
`firm_lab/fundamentals.py` (rules), `firm_lab/ixbrl.py` (reading the filing's own document),
`firm_lab_collectors/xbrl.py` (the SEC source). Stored in `fundamental_fact_observations`.

Raw and normalized facts only. No ratio, margin, growth rate, score, rank or composite is computed from them.

## Source

All from the SEC, with the operator's declared User-Agent:

| What | Where |
|---|---|
| Every tagged value the company filed, with the filing it appeared in | `data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| The company's filing index | `data.sec.gov/submissions/CIK##########.json` |
| The acceptance time | the filing's own header (`<ACCEPTANCE-DATETIME>`), as for all filing metadata |
| The check | the filing's own primary document (Inline XBRL) |

## What is kept for each fact

Instrument, CIK, taxonomy (`us-gaap`), concept, normalized field, mapping rule, unit, value, period type, period
start and end, whether it is the filing's current period or a comparative, the filing's form, accession number and
filing date, the SEC's fiscal-year and fiscal-period labels for the filing, the SEC frame when given, the acceptance
time (header) and the JSON time as sent with the conflict flag, version, restatement flag and prior value, whether the
value was confirmed in the filing document, the source URL, the filing document URL, and the usual provenance
(provider, source id, ingestion time, schema version, content hash, run id).

## The ten fields

A field is filled only from the concepts in "Accepted". If more than one accepted concept is reported for the same
period they must be equal; otherwise the field is unresolved for that period. "Not accepted" lists related concepts
that are deliberately not treated as the same thing; seeing one explains why the field is unresolved.

| Field | Accepted us-gaap concepts | Unit | Not accepted (reason) | Critical |
|---|---|---|---|---|
| `revenue` | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet` | USD | `RevenueFromContractWithCustomerIncludingAssessedTax`, `RevenuesNetOfInterestExpense` | yes |
| `gross_profit` | `GrossProfit` | USD | `CostOfRevenue`, `CostOfGoodsAndServicesSold`: never derived by subtraction | no |
| `operating_income` | `OperatingIncomeLoss` | USD | — | no |
| `net_income` | `NetIncomeLoss` | USD | `ProfitLoss` (includes non-controlling interests), `NetIncomeLossAvailableToCommonStockholdersBasic` | yes |
| `eps_diluted` | `EarningsPerShareDiluted` | USD/shares | `EarningsPerShareBasicAndDiluted`, `EarningsPerShareBasic` | yes |
| `operating_cash_flow` | `NetCashProvidedByUsedInOperatingActivities` | USD | `…ContinuingOperations` | yes |
| `capital_expenditure` | `PaymentsToAcquirePropertyPlantAndEquipment` | USD | `PaymentsToAcquireProductiveAssets`, `PaymentsToAcquireOtherPropertyPlantAndEquipment` (`BROADER_CONCEPT_NOT_MAPPED`) | no |
| `cash_and_equivalents` | `CashAndCashEquivalentsAtCarryingValue` | USD, instant | totals including restricted cash | no |
| `total_debt` | `DebtLongtermAndShorttermCombinedAmount` | USD, instant | `LongTermDebt`, `LongTermDebtNoncurrent`, `LongTermDebtCurrent`, `CommercialPaper`, `ShortTermBorrowings`, `DebtCurrent`, `LongTermDebtAndCapitalLeaseObligations` (`NEEDS_COMPONENT_RULE`): components are never added together | no |
| `diluted_shares_weighted_average` | `WeightedAverageNumberOfDilutedSharesOutstanding` | shares | — | no |

"Diluted shares outstanding" is stored as the weighted-average diluted share count the company reports for the
period (the figure used for diluted EPS). It is not a point-in-time share count.

"Critical" is a choice made in this version, recorded here so it can be challenged: the `fundamentals` capability
requires the four critical fields for the current period of every filing read. The other six may stay unresolved,
and when they do the capability text names them.

## Periods

* A balance (`cash_and_equivalents`, `total_debt`) is an instant.
* A flow is named by its length only: `3M` (80–100 days), `6M` (170–190), `9M` (260–285), `12M` (350–380). Anything
  else is unresolved (`UNCLASSIFIED_PERIOD`). A 12-month period is not called a fiscal year: some companies also
  report trailing twelve months in a quarterly report.
* The cash-flow statement of a quarterly report covers the fiscal year to date. It is stored as reported (6M, 9M).
  A single quarter is never computed by subtraction.
* Every period a filing reports is its own observation: the quarter, the year to date, and the prior-year
  comparatives. `relation_to_filing` says `current` when the period ends on the filing's report date.

## Why a field can be unresolved

`NOT_REPORTED_UNDER_A_MAPPED_CONCEPT`, `BROADER_CONCEPT_NOT_MAPPED`, `NEEDS_COMPONENT_RULE`, `CONFLICTING_CONCEPTS`
(two accepted concepts, two numbers), `CONFLICTING_VALUES` (one concept, two numbers), `UNEXPECTED_UNIT`,
`UNEXPECTED_PERIOD_KIND`, `UNCLASSIFIED_PERIOD`, `UNPARSEABLE_VALUE`. Unresolved entries are kept in the run's
validation report (`provider_runs.diagnostics_json`), per company, and shown on `/firm-lab`.

## Known-at, versions and restatements

* A fact is known from the SEC acceptance time of the filing it appeared in (the header time).
* Every appearance of a fact in a periodic filing is its own row. Nothing is updated in place.
* `version` is counted over the company's complete periodic history in the company-facts file, ordered by filing
  date and then accession number: 1 for the first report of a field and period, plus one in each filing where the
  value changes. `is_restatement` marks the filing where it changed, with `prior_value`. Because the history is
  complete, the numbering does not depend on which filings Firm Lab has read or in what order.
* `fundamentals.as_of(rows, time)` returns, per field and period, the latest observation accepted at or before that
  time. A restatement is invisible before the restating filing was accepted.
* Only 10-K, 10-Q and their amendments are read. An amendment with no financial facts is left out and named; an
  original report with none makes the company's answer unusable (`NO_FACTS_FOR_FILING`).

## The check against the filing itself

For every filing read, the primary document is fetched and its Inline XBRL facts are read (company totals only: a
context with a dimension, such as a product line, is ignored; a number in a format the reader does not know is
skipped, never guessed). Each kept value is then looked up by concept and period:

* `CONFIRMED`: the document carries the same value.
* `NOT_FOUND`: the document carries no such fact. The row is kept and flagged.
* A different value: the whole company answer is refused (`FACT_DIFFERS_FROM_FILING`). Nothing is stored.
* A document that cannot be read: refused (`FILING_DOCUMENT_UNREADABLE`).

## When `fundamentals` is AVAILABLE

All of: every run of the latest sample was accepted; rows are stored with complete provenance; every stored fact has
its acceptance time; for every company, the four critical fields are resolved for the current period of every filing
read and each is `CONFIRMED` in the filing document. Otherwise the capability is `PARTIAL_EXISTING` (rows stored, with
the reason) or `UNAVAILABLE` (nothing stored).

## Checked against real filings (2026-10-03)

Run against the operator's captured SEC samples (one latest periodic report each for AAPL, MSFT, NVDA, AMZN, GOOGL):
140 facts accepted, 140 confirmed in the filing documents, none differing, none not found. Unresolved:
`total_debt` for all five (reported in parts); `capital_expenditure` for NVDA and AMZN (a broader line);
`gross_profit` for AMZN and GOOGL (no gross profit line is reported).
