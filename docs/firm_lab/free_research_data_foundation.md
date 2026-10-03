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
validated rows, by the rules in the three documents above. `corporate_actions` can reach `PARTIAL_EXISTING` at most
(VTI cash distributions only). `earnings_transcripts` stays `UNAVAILABLE`. `ml_ranker` and `options_strategy` stay
`NOT_STARTED`. No new scheduled job, no order, fill, position or cash table, no trial.

## Live results, 2026-10-03

* **Issuer distributions and total return (run 13:50 ET).** Vanguard answered a plain research request. Six
  distributions stored (ex-dates 2025-06-30 to 2026-09-28), every validation check passed, each issuer reinvestment
  price within 0.25% of the stored close on its ex-date. Stored: 378 sessions each of the VTI price-return index, the
  VTI total-return index and the 70/30 total-return ruler (1,134 new observations; the 1,134 earlier ones untouched).
  On the 2026-09-30 session, base 2025-03-31 = 100: VTI price return 136.166497, VTI total return 138.526274, legacy
  70/30 126.616677, total-return 70/30 128.149523. An independent recomputation from the stored inputs matched all
  three new series on every session (largest difference below 0.000001).
* **SEC company facts and earnings events.** Not yet run live: both hand-started runs on 2026-10-03 reported
  `NOT_CONFIGURED` (no `FIRM_LAB_SEC_USER_AGENT` in the shell) and made no request. The collectors were checked
  against the operator's captured SEC samples instead (see `sec_xbrl_normalization.md`). `fundamentals` and
  `earnings_events` stay `UNAVAILABLE` until the two runs succeed.
* **Tests.** Cloud 895 passed, 1 skipped. Mac native (overlay) 840 passed, 4 failed: the same four as before this
  checkpoint (three older dashboard tests, and the installed-Codex isolation test that needs the Control A
  maintenance release).
