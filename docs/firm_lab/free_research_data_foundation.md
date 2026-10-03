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
