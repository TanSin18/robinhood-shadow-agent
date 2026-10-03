# Earnings events — factual event data only

Written 2026-10-03 for Checkpoint 4. Implementation: `firm_lab_collectors/earnings.py`; stored in
`earnings_event_observations`; capability `earnings_events`.

**FACTUAL EVENT DATA ONLY — NO EARNINGS SIGNAL.** An event is a filing: an 8-K (or 8-K/A) that reports under
Item 2.02, "Results of Operations and Financial Condition". The release is not opened, read, summarised, scored or
compared with anything. There is no sentiment, tone, surprise, estimate, prediction or model, and the table has no
column for one: a record carrying a field with such a name is refused (`SIGNAL_FIELD_NOT_ALLOWED`).
`earnings_transcripts` stays `UNAVAILABLE`; no transcript is collected.

| Field | Meaning |
|---|---|
| `instrument`, `cik`, `accession_number`, `form`, `items` | from the SEC filing index |
| `event_date` | the SEC "period of report" of the 8-K |
| `accepted_timestamp` | the filing-header acceptance time (authoritative). The JSON time is kept as sent, with `acceptance_time_conflict` |
| `acceptance_session` | where the acceptance falls on the New York clock: `before_market_open` (before 09:30), `during_market_hours`, `after_market_close` (16:00 or later). Clock only; holidays and early closes are not known |
| `filing_url`, `primary_document_url` | the filing's index page and its primary document |
| `release_document_url`, `release_document_type` | the first EX-99 exhibit in the filing's document list, or `UNAVAILABLE`. The list is read from the filing's `-index-headers.html` page (the short `.hdr.sgml` header has none). A file name is never guessed |
| `fiscal_period_end`, `periodic_accession_number`, `fiscal_period_basis` | the periodic report (10-Q or 10-K) the release is taken to be about, or `UNAVAILABLE` |
| `transcript_available` | always false |

**The fiscal-period link is a stated rule, not a reading of the release:** the periodic report with the latest period
end before the event date, at most 100 days before it, and itself filed no earlier than 7 days before the event. The
periodic report is often filed a day or two after the release, so the link is made when the event is ingested; the
event's own known-at stays the 8-K acceptance time.

**Cross-checks.** When the filing header lists its items or its period, they must agree with the filing index
(`ITEMS_DISAGREE`, `EVENT_DATE_DISAGREES`). A header that cannot be read refuses the answer.

**"Basic reported values"** are not stored on the event. `/firm-lab` shows revenue, net income and diluted EPS for
the linked period by reading the stored company facts of the linked periodic report, each with that report's own
acceptance time. They are the company's filed figures, not figures taken from the release.
