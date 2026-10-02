# Treasury-bill index and 70/30 ruler — implementation note (2026-10-02)

The frozen methodology (`treasury_bill_total_return_methodology.md`, version 1) says what is computed. This note records
how the code reads the points the methodology leaves open. It changes nothing in the methodology. If any reading here
turns out to be wrong, the fix is a new methodology version, not an edit.

Code: `firm_lab/treasury.py` (arithmetic), `firm_lab/benchmarks.py` (`compute_fixed_70_30`, the frozen-hash check),
`firm_lab_collectors/treasury.py` (auction records from Fiscal Data). Command: `python -m firm_lab_collectors.cli treasury`.

| Point | Methodology | Reading used in the code |
|---|---|---|
| Rounding of the price check | "P = 100 × (1 − d × r / 360), rounded to six decimals" | A published price passes if it equals the formula rounded half-up **or** truncated at six decimals. Nothing looser. Which one matched is not stored. |
| "No bill issued that day" (4.4) versus "no auction record is found" (11) | Both are an absent record | If a later 13-week bill is stored, rule 4.4 applies: the money earns nothing until that bill's issue date, and every such day is recorded. If no later bill is stored, the series stops (`DATA_GAP`) on the maturity date. |
| Where a gap starts | "from the first affected date" | The day the missing or unusable bill is needed: the start date, or the maturity date of the bill held. No observation is stored for that day or after it. |
| A refused record at ingestion | "A record whose published price does not equal the formula is refused" | The whole response is refused and nothing from it is stored, as for every Firm Lab provider. This is stricter than section 11, which stops only for a bill the index needs. |
| Republished records | "Both versions are kept and the index is not silently recomputed" | Both rows are kept. From the issue date of that bill the series stops with `RECORDS_DISAGREE`. Observations already stored are left as they are; a recomputation that would change one raises an error instead. |
| Two different 13-week bills with one issue date | Not addressed | Treated as unusable (`AMBIGUOUS_ISSUE_DATE`); the series stops if that date is needed. |
| Known-at for records ingested after the fact | "5:00 p.m. on the auction date, or the moment Firm Lab ingested it if that is later" | History ingested on 2026-10-02 is known from 2026-10-02. Each stored observation carries the later of its session's 4:00 p.m. close and the known-at of the bills used up to it. |
| Results not yet known when fetched | Not addressed | An auction whose 5:00 p.m. known-at lies after the fetch time is left out of the stored records and counted (`left_out.not_yet_known`). |
| NYSE session dates | "the dates for which a completed VTI session close is stored" | As written. In addition, if two consecutive stored VTI sessions are more than four calendar days apart, the ruler stops (`VTI_SESSION_GAP`) rather than treat a hole as a holiday. |
| Inception | "fixed when a Firm trading trial is registered" | No trial is registered. Observations are stored on a **development base**: the first stored VTI session = 100, and the base date is written into every observation's source text. They are rebased when a trial is registered. |
| VTI leg | Not part of this methodology | Price return (stored closes, split-adjusted by their provider). Dividends are not included, because no validated dividend source exists. The observation kind says so: `index_70_30_vti_price_return_basis`. |
| Precision | "at least twelve decimal places internally; stored to six" | 40 significant digits internally; six decimals stored, rounded half-up. |

Not verified before the first live run: the exact response format of the Fiscal Data API (values as text, missing
values as the text "null", `meta.total-pages`). A response in any other form is refused, not adapted.
