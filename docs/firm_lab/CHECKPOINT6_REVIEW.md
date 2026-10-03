# Checkpoint 6 independent review and disposition

2026-10-03. Fresh reviewer, read-only, range `2a7dfa14..810be5c`.
Verdict at review: changes required; no expansion or merge. No critical
execution-boundary defect found. Reviewer independently ran86focused tests
(1.54s), inspected code and initial240-snapshot receipts. This is not a second
reviewer's certification of subsequent fixes; the current owner repairs them
with failing-first regressions and reruns validation.

## Important findings — owner repair pass

| Finding | Repair | Failing-first regression |
|---|---|---|
| Fundamental duration depends on input order | Latest economic end, then shortest explicit duration; selected duration audited | `test_same_end_duration_selection_is_stable_and_explicit` |
| Filing fiscal year misused as fact year | Match economic start/end approximately one year apart, same duration/concept/entity/unit/basis | `test_comparative_fact_uses_economic_period_not_filing_fiscal_year` |
| Leadership misses competitor provenance | Include all competitors and dated membership in references and known-at | `test_leadership_carries_every_competitor_and_membership_source` |
| Public engine accepts stale/gapped/calendar-day windows | Validate completed, contiguous XNYS windows centrally for closes/OHLCV/references | `test_engine_rejects_non_session_gapped_or_stale_bars` |
| Finished runs can include later partial-run results | Immutable exact result-ID manifest, count/identity/uniqueness validation; absent manifest fails closed | `test_completed_receipt_owns_exact_results_not_later_partial_run` |
| Missing sector calculator/adapter/persistence paths | Complete-constituent breadth/participation, dated membership reader, all comparator loading, immutable mapping storage; six current issuer mappings verified | `test_breadth_requires_complete_effective_dated_constituents`, `test_manual_cli_reads_and_persists_sector_evidence`, `test_default_comparator_set_is_versioned_not_historical`, `test_all_proposed_current_issuer_mappings_have_dated_evidence` |
| Same-date retrospective warning lost | Render explicit recorded temporal mode | `test_same_date_retrospective_receipt_is_labelled` |

Every listed regression was observed failing before its repair and passing
afterwards. Old initial sample data is retained as pre-repair evidence, not
presented as final-code validation. New initial/sample expansion results must
carry the repaired calculation hash.

## Lower-priority findings

Four were regraded as concrete approved-interface omissions and fixed in the
same pass: explicit equality/touch fields; separate nearest extension; current
close in level display; family coverage state labels. Tests:
`test_equal_level_and_distinct_touch_count_are_not_lost`,
`test_nearest_extension_is_separate_and_current_close_is_audited`,
`test_close_anchor_visual_audit_has_prices_dates_and_confirmations`.

Two remain **minor, deferred and visible**:

1. No authoritative complete FOMC meeting-coverage record is established by the
   existing adapter. Three-meeting aggregates remain unavailable; the boolean
   pure-calculator precondition is not proof that the manual path can establish
   completeness. Do not claim this live capability complete.
2. Some unavailable nontechnical metrics still have grouped reasons rather than
   distinguishing every absent operand, zero denominator and incompatible-period
   subcase. Values remain null; the operator gets less precise diagnostics.

## Reviewer scope exclusions and owner rulings

- Deployment/cloud/installed UI/service invariants: reviewer did not certify;
  owner checks separately below. Deployment explicitly withheld by operator.
- Full native/Firm Lab suite: reviewer reran only86focused; owner reruns the full
  suites. Known installed-Codex failure stays visible and unweakened.
- Every sample value: no exhaustive independent reimplementation of52,320rows;
  fixed formula fixtures, adversarial tests and generation counts are distinct.
- Live OHLCV/intraday: no validated data; pure-calculator tests do not activate it.
- Missing authoritative future schedules, transcripts, consensus and other
  unavailable macro sources: remain unavailable, no guessed providers or times.
- Predictive/strategy/model merit: excluded by Checkpoint6 boundaries.
- External issuer citations: owner verified official sources and documented
  internal-classification inference; reviewer did not independently re-fetch.
- Hostile filesystem replacement races/arbitrary direct SQL tampering: not a
  penetration test; alias/schema/query-only tests cover intended boundaries.
- Optional named candles, extra Fib ratios, Parkinson volatility and optional RSI
  variants: approved exclusions retained; not implemented covertly.

No review finding authorizes a strategy, official DB write or deployment.
