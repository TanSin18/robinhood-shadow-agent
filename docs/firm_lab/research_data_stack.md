# Firm Lab — research data stack (Checkpoint 3, 2026-10-02)

Checkpoint 3 answers one question: **can the raw data be trusted and reproduced?** It does not answer "what should
we buy?". Nothing described here ranks, scores, selects or trades.

## What the operator chose (2026-10-01)

| Domain | Provider | State after this checkpoint |
|---|---|---|
| SEC filings | SEC EDGAR (free, public) | Adapter built. Runs when the operator declares a User-Agent. |
| Equity 1-minute bars, trades, NBBO quotes | Massive (formerly Polygon.io) | Adapter built. Needs an operator-purchased plan and key. |
| Fundamentals, corporate actions | Sharadar | Adapter built. Needs an operator-purchased subscription and key. |
| Options chains, provider Greeks | ThetaData | Adapter built. Needs an operator-purchased subscription and a running Theta Terminal. |
| 3-month Treasury-bill total return | Official U.S. Treasury data | Methodology drafted (`treasury_bill_total_return_methodology.md`). Not approved. Nothing computed. |
| Analyst estimates and revisions | none selected | `UNAVAILABLE`. No inferior substitute. |
| General news | none selected | `PARTIAL_EXISTING` (Google News RSS stays advisory only). |
| Earnings transcripts | none selected | `UNAVAILABLE`. Earnings-related SEC filings arrive with the filing index. |
| Order-book depth | none (Databento deliberately not connected) | `UNAVAILABLE`. |

A choice is not a connection, and a connection is not a capability. A capability becomes `AVAILABLE` only when
real rows are stored, every run of the latest sample passed validation, and each run carries complete provenance.
Configuration alone promotes nothing, and a later failed sample takes the status back.

## Two packages, one direction

```text
firm_lab_collectors/   the only place a network connection is opened      -> imports firm_lab
firm_lab/              schemas, validation, storage, registry, read view  -> imports the standard library only
agents/desk/firm_lab_page.py   read-only page                             -> reads firm_lab.view, never the collectors
```

`firm_lab_collectors` cannot trade. A test reads its source and fails if it imports anything except the standard
library, `firm_lab` and its own modules; if any file other than `transport.py` imports a network module; if it
imports the execution boundary, the Official reader or the ingest path; or if it mentions an order function, a
broker host, a service manager or a keychain entry of the brokerage. No launchd job, script or schedule starts it.
It is started by hand, by the operator.

The collector command is never given the location of the registered database and never opens it. It refuses to
create a Firm Lab database; it only writes to one that already exists.

## The transport

`firm_lab_collectors/transport.py`: HTTPS GET only (plain HTTP only to a vendor terminal on `127.0.0.1`), only to
hosts named in advance, no redirect to another host, a minimum interval between requests, a size limit, and no
retry. A failure comes back as a status and is recorded; it is not retried in a loop. Secret query values are
removed from every URL before it is stored as a source id.

Hosts: `www.sec.gov`, `data.sec.gov`, `api.massive.com`, `api.sharadar.com`, `data.nasdaq.com`, `127.0.0.1:25503`.

## Settings and credentials

Read from the environment at run time by `firm_lab_collectors/config.py`. They are never printed, logged or stored;
the status command reports only true or false per provider.

| Variable | Meaning |
|---|---|
| `FIRM_LAB_SEC_USER_AGENT` | `Name contact@example.com`. The SEC asks every automated client to identify itself. The operator sets it. |
| `FIRM_LAB_MASSIVE_API_KEY` | Massive key |
| `FIRM_LAB_SHARADAR_API_KEY`, `FIRM_LAB_SHARADAR_CHANNEL` | Sharadar key; `direct` (api.sharadar.com) or `nasdaq` (Nasdaq Data Link) |
| `FIRM_LAB_THETADATA_TERMINAL` | `1` once Theta Terminal is running locally. The adapter holds no ThetaData credential. |

Vendor keys belong in the macOS Keychain under a research-only service name and are passed to one run, for example:

```sh
FIRM_LAB_MASSIVE_API_KEY="$(security find-generic-password -s firm-lab-research -a massive -w)" \
  python -m firm_lab_collectors.cli massive
```

These are research-data credentials. Nothing here reads, needs or touches brokerage authentication. Claude does
not handle any of them and does not sign up for or pay for any provider.

## Commands (hand-started samples; no backfill, no schedule)

```sh
python -m firm_lab_collectors.cli status
python -m firm_lab_collectors.cli edgar      [--symbols SPY,VTI,SOXX,AAPL,NVDA] [--days 365] [--max-filings 5]
python -m firm_lab_collectors.cli massive    [--symbols ...] [--session-date YYYY-MM-DD] [--no-ticks] [--min-interval SECONDS]
python -m firm_lab_collectors.cli sharadar   [--symbols AAPL,NVDA] [--years 3]
python -m firm_lab_collectors.cli thetadata  [--symbols SPY,QQQ,NVDA] [--session-date YYYY-MM-DD] [--expiration YYYY-MM-DD]
```

Each run: checks configuration (otherwise records `NOT_CONFIGURED` and fetches nothing); asks the provider through
its Firm Lab interface; records the run; stores rows only from an accepted answer; lets the registry follow the
evidence. One sample is judged as a whole: if any symbol's answer is refused, the capability is not claimed.

## SEC EDGAR

* Identity: ticker to CIK from the SEC's own `company_tickers.json`, then `company_tickers_mf.json` for funds. A
  ticker the SEC does not list is not guessed.
* Index: `data.sec.gov/submissions/CIK##########.json`, `filings.recent`.
* Stored per filing: instrument, CIK, accession number, form, filing date, report date, acceptance timestamp,
  document URL, ingestion timestamp, content hash. **Metadata only.** No document is read, summarised or scored.
* **Acceptance time.** The JSON field `acceptanceDateTime` ends in `Z` but is not reliably UTC: some values are the
  New York clock time with a `Z` on it, sometimes mixed in one file. So for every filing kept, the filing's own
  SEC header is read (`<ACCEPTANCE-DATETIME>YYYYMMDDHHMMSS`, New York clock; from `<accession>.hdr.sgml`, or the
  `-index-headers.html` page when that file is absent). `accepted_timestamp` is the header time in UTC,
  `accepted_timestamp_raw` is the JSON text as sent, and `accepted_timestamp_basis` says which reading the JSON
  matched. If the two disagree under both readings, or the header cannot be read, the response is refused.
* HTTP 403 or 429 is recorded as unavailable and not retried. The collector sends at most five requests a second.
* **First live run, 2026-10-02 10:23 ET (operator-run, 24 requests).** SPY, VTI and NVDA: 5 filings each accepted
  and stored (15 rows), every acceptance time verified against the filing header. The fund ticker file resolved VTI
  with its series and class. Both JSON conventions were seen in the same response: 13 values were true UTC and 2
  were the New York clock with a `Z`. SOXX and AAPL were **refused** (`ACCEPTANCE_TIME_CONFLICT`): for one filing
  each, filed 2026-10-01, the JSON value was exactly four hours later than the header time converted to UTC, which
  fits neither reading. Nothing from those two answers was kept and the capability was not promoted. Whether the
  SEC corrects such values later, and whether the header should be accepted alone in that case, is an operator
  decision; the rule was not relaxed to make the sample pass.
* Still not verified: the header file's availability for every form type.
* Control A's advisory EDGAR reader is a different module and was not changed.

## Massive

* 1-minute bars: `/v2/aggs/ticker/{T}/range/1/minute/{day}/{day}?adjusted=false`. Stored unadjusted, with the bar
  start in UTC, the provider's millisecond value as sent, the session (`pre_market` 04:00–09:30, `regular`
  09:30–16:00, `post_market` 16:00–20:00 New York time) and the exchange session date.
* Trades `/v3/trades/{T}` and NBBO quotes `/v3/quotes/{T}`: nanosecond timestamps kept as exact integers beside a
  UTC timestamp; exchange, conditions, sequence number, tape.
* Refused whole: duplicate or out-of-order records (ordering is checked on the exact nanoseconds), a high below a
  low, an open or close outside the range, a price at or below zero, a negative size, bid above ask, a bar outside
  04:00–20:00, a future timestamp, an answer for another ticker, an answer not marked unadjusted, a continuation
  on another host, more pages than the sample allows.
* A quote side with price 0 and size 0 means no quote on that side and is stored as sent.
* Diagnostics stored beside each run, used for nothing else: bars per session, regular-session minutes with no bar
  (a minute with no eligible trade has no bar), and the last regular-session bar close next to the stored daily
  close. The 1-minute close is not the closing-auction price, so a small difference is expected.
* No VWAP signal, relative volume, opening range or flow measure is computed. Those capabilities stay `UNAVAILABLE`.
* Not verified: no live call has been made. Formats follow the vendor documentation read on 2026-10-01.

## Sharadar

* Fundamentals: one stored row per reported value, with dimension, reporting basis, fiscal period, period end,
  provider datekey, last-updated date, units and currency.
* **As reported and restated are kept apart.** AR dimensions (ARQ, ARY, ART) exclude restatements and are indexed
  to the filing date; MR dimensions (MRQ, MRY, MRT) include restatements and are indexed to the report period. A
  restated value is a new row; it never replaces an as-reported one.
* **Filing time.** Sharadar gives a filing date, not a time. `filing_timestamp` is stored as `UNAVAILABLE`. No
  acceptance time is made from the date. For restated rows `filing_date` is `UNAVAILABLE` too.
* Currency comes from the TICKERS table. An amount of money without a currency is refused.
* Delisted companies are accepted and flagged.
* Corporate actions: raw events only (split, cash dividend, symbol change, delisting, spin-off, merger, other).
  `announcement_timestamp` is `UNAVAILABLE`: the source supplies none and none is derived from the effective date.
  No price is adjusted.
* **SEC cross-check** (`firm_lab/crosscheck.py`, read-only): each as-reported filing date is matched to the stored
  periodic SEC filing with the same instrument and filing date. A match shows the SEC acceptance time next to the
  report; it is read at query time and never written into the fundamental row.
* No ratio, score, rank or composite is computed.
* Not verified: the Sharadar Direct JSON and error formats, the meaning of the corporate-action `date` and `value`
  fields, and the filter names on the direct channel. No live call has been made.

## ThetaData

* End-of-day option quotes, open interest and the provider's end-of-day Greeks for one expiration per underlying
  (the nearest listed on or after the session date, unless one is named), through the operator's Theta Terminal.
* Every Greek is stored under the vendor's name (`thetadata_provider_delta`, `thetadata_provider_implied_volatility`,
  …) together with who computed it, the documented model and settings, and its timestamp. A bare `delta` is refused
  by validation and again by storage. A Greek the provider did not send is absent, not estimated.
* A chain is refused whole if a contract lacks open interest or provider implied volatility. So a ThetaData tier
  without implied volatility cannot fill this table; that is deliberate.
* Timestamps arrive on the New York clock without an offset; they are converted to UTC and the original is kept.
* No contract is scored, ranked or recommended. No fill exists.
* Not verified: the v3 field names for end-of-day quotes and Greeks. Fields are read by name and a response missing
  a required field is refused.

## Storage

Raw tables in the Firm Lab database, each row with provider, source id, source timestamp, known-at, ingested-at,
schema version, content hash and run id: `filing_observations`, `intraday_bar_observations`, `trade_observations`,
`quote_observations`, `fundamental_observations`, `corporate_action_observations`, `option_chain_observations`.
`provider_runs` records every request (including refused and unavailable ones, with the reasons);
`provider_connections` records what is known about reaching each provider, never a credential.

Rows are only inserted. The unique key includes the content hash, so an identical record is ignored on a repeat run
and a changed record is kept beside the old one. There is still no order, fill, position, cash or portfolio table.

## What was deliberately not built

Ranking, alpha scores, machine-learning models, Firm paper trades, option recommendations, sector rotation,
news-driven trading, a portfolio optimizer, VWAP / relative-volume / flow features, fundamental scores, earnings-tone
models, bulk backfills, schedules. No Firm trading trial is registered.
