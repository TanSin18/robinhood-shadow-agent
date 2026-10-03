# Checkpoint 4 — free research data foundation

Written 2026-10-03. The question this checkpoint answers: can Firm Lab rebuild trustworthy total-return rulers and
point-in-time company facts from free, authoritative sources? It does not answer which stock to buy, and nothing
built here is a feature, a score or a selection. Firm Lab stays in BUILD / OBSERVE with no fills.

## Sources used (all free, all public)

| Data | Source | Credential | Detail |
|---|---|---|---|
| Company facts (ten reported values) | SEC XBRL company-facts API | the operator's declared SEC User-Agent | `sec_xbrl_normalization.md` |
| Earnings-release filings | SEC EDGAR filing index and headers | same | `earnings_events.md` |
| VTI cash distributions | the issuer's published list (Vanguard) | none | `vti_total_return_methodology.md` |
| 13-week bill auctions | U.S. Treasury Fiscal Data | none | frozen methodology, unchanged |
| VTI closes | Control A's recorded closes (read-only) | none | unchanged |

Not connected, by instruction: Massive, Sharadar, ThetaData, Benzinga, ORATS, Zacks. Their adapters stay dormant.
Since this checkpoint no paid provider is the chosen source for `fundamentals` or `corporate_actions`.

## What was looked at and found not usable

* Nasdaq's public dividend endpoint: for VTI it answers "Dividend History for Non-Nasdaq symbols is not available".
* Vanguard's distribution-dates PDF for 2026: not found at the expected address (HTTP 404); the 2025 PDF holds
  dates, not amounts.
* The SEC's short header file (`.hdr.sgml`) holds no document list, so the earnings-release exhibit is looked up on
  the filing's `-index-headers.html` page instead.

## Hand-started commands (nothing is scheduled)

    python -m firm_lab_collectors.cli xbrl            # company facts, five companies, four latest periodic reports each
    python -m firm_lab_collectors.cli earnings        # earnings-release filings, same companies
    python -m firm_lab_collectors.cli distributions   # issuer VTI distributions, then the total-return rulers

`xbrl` and `earnings` need `FIRM_LAB_SEC_USER_AGENT` in the shell that runs them. `distributions` needs nothing.

## Capabilities after this checkpoint

`fundamentals`, `earnings_events`, `vti_total_return` and `total_return_ruler` become `AVAILABLE` only from stored,
validated rows, by the rules in the three documents above. `fundamentals` needs all eight required fields for every
company (operator rule, 2026-10-03) and is `PARTIAL_EXISTING` today. `corporate_actions` can reach `PARTIAL_EXISTING`
at most (VTI cash distributions only, benchmark-only). `macro_regime` and `sector_engine` are `NOT_STARTED`. `earnings_transcripts` stays `UNAVAILABLE`. `ml_ranker` and `options_strategy` stay
`NOT_STARTED`. No new scheduled job, no order, fill, position or cash table, no trial.

## Live results, 2026-10-03

* **Issuer distributions and total return (run 13:50 ET).** Vanguard answered a plain research request. Six
  distributions stored (ex-dates 2025-06-30 to 2026-09-28), every validation check passed, each issuer reinvestment
  price within 0.25% of the stored close on its ex-date. Stored: 378 sessions each of the VTI price-return index, the
  VTI total-return index and the 70/30 total-return ruler (1,134 new observations; the 1,134 earlier ones untouched).
  On the 2026-09-30 session, base 2025-03-31 = 100: VTI price return 136.166497, VTI total return 138.526274, legacy
  70/30 126.616677, total-return 70/30 128.149523. An independent recomputation from the stored inputs matched all
  three new series on every session (largest difference below 0.000001).
* **SEC company facts (run 14:55 ET, rules version 2).** 51 requests, all answered. Five companies, the four latest
  periodic reports each (20 filings). 906 watched raw facts read; **531 normalized facts stored**; no company answer
  refused; no value differing from a filing document; 530 confirmed in the filing documents and 1 not found.
  A second run two minutes later stored nothing new (531 duplicates recognised).
  Unresolved, with the exact reasons:
  * MSFT, total debt, all four filings: `SHORT_TERM_DEBT_NOT_REPORTED` (only long-term debt is tagged; absence is not
    taken as zero). Required field: blocks.
  * GOOGL, total debt, 10-Q for 2026-03-31: `SHORT_TERM_DEBT_NOT_REPORTED` (no commercial paper figure tagged for that
    date). Required field: blocks.
  * GOOGL, total debt, 10-Q for 2026-06-30: resolved (100,164 million) but `NOT_FOUND` in the filing document, because
    the filing nests the zero commercial-paper tag inside another tag and the document reader does not read the inner
    one. Kept and flagged; not counted as confirmed. Required field: blocks. The reader was not changed.
  * NVDA and AMZN, capital expenditure, all filings: `BROADER_CONCEPT_NOT_MAPPED` (optional; does not block).
  * AMZN and GOOGL, gross profit, all filings: `NOT_REPORTED_UNDER_A_MAPPED_CONCEPT` (optional; does not block).
  Total debt resolved and confirmed for AAPL, NVDA and AMZN in all four filings each. All 112 AAPL facts carry the
  acceptance-time flag (the SEC JSON time is the header time plus four hours; the header time is used).
  **`fundamentals = PARTIAL_EXISTING`**: reliable debt is not available across the sample (MSFT, GOOGL).
* **Earnings events (run 14:55 ET).** 46 requests, all answered. **20 events stored** (four per company), none
  refused. Every one was accepted at or after 4:00 PM New York time. The fiscal period was linked for all 20. The
  release document was resolved for all 20 from the filing's `-index-headers.html` page (each an EX-99.1 exhibit),
  so the live lookup works. Four AAPL events carry the acceptance-time flag. No sentiment, score, label or model
  exists. **`earnings_events = AVAILABLE`**; `earnings_transcripts` stays `UNAVAILABLE`.
* **Benchmark-only marking.** The six stored VTI distribution rows are marked `benchmark_only = true`; the stored
  series did not change (1,134 observations unchanged on recomputation).
* **Tests.** Cloud 899 passed, 1 skipped. Mac native (overlay) 844 passed, 4 failed: the same four as before this
  checkpoint (three older dashboard tests, and the installed-Codex isolation test that needs the Control A
  maintenance release).
