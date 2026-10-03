# Firm Lab — data sources

Checkpoint 2, written 2026-10-01. This document answers "what data should the future Firm trust?". It does not
answer "what should the Firm buy?". No provider is connected, nothing here feeds a ranking, a selection or a
trade, and no measure is computed from any of it.

Companion documents: `provider_matrix.md` (candidate providers, with evidence and fit labels) and
`ARCHITECTURE.md` (isolation rules).

**Checkpoint 4 update (2026-10-03).** Fundamentals, earnings-release filings and VTI distributions now come from
free, authoritative sources (the SEC and the fund issuer); see `free_research_data_foundation.md`,
`sec_xbrl_normalization.md`, `earnings_events.md` and `vti_total_return_methodology.md`. Where the domain notes
below name a paid provider as chosen, that choice is superseded for fundamentals and corporate actions.

## Rules that apply to every domain

1. **Interfaces fail cleanly.** With no provider connected an interface returns `UNAVAILABLE` and no records.
   It never falls back to a guessed value, a stale hard-coded value, a web search or a model-written number.
2. **Responses are checked, never repaired.** A response that fails the schema or a quality check is `REJECTED`
   whole, with the reasons. Records are passed on exactly as received.
3. **Provenance is mandatory.** Every response carries: provider, source ID, source timestamp (as sent), ingestion
   timestamp, known-at timestamp, exchange session date where it applies, schema version, and a content hash where
   practical (`firm_lab/provenance.py`).
4. **Point in time.** A value may be used only from its known-at moment onward. A field that proves the value is
   a dated snapshot is required wherever history matters.
5. **AVAILABLE is earned.** A capability becomes `AVAILABLE` only from stored data that passed validation, with
   the evidence recorded. It is never declared in code.
6. **Greeks keep their origin.** `provider_delta` when the source supplied it; `model_estimated_delta` if Firm Lab
   ever computes one. The same for gamma, theta, vega and implied volatility. A bare `delta` is rejected.

Data-quality checks (`firm_lab/quality.py`): stale timestamp, future timestamp, missing identifier, duplicate
records, impossible values, conflicting instrument identity, missing units or currency, non-monotonic timestamps,
incomplete historical windows; plus unparseable or timezone-less timestamps, a missing point-in-time field, an
un-namespaced Greek, a yield offered as a total return, and incomplete provenance.

## Current sources, stated honestly

| Source | Where it is used today | What it gives | What it does not give |
|---|---|---|---|
| Robinhood read path (operator-authorised, read-only) | Control A's registered runs only | Daily bars (the gateway refuses anything but `interval=day`, `bounds=regular`, `adjustment_type=split`; at most 550 days and 10 symbols per call); bid/ask quote snapshots at run time; option chain listings and option quotes; account state | Intraday bars, trades, a quote stream, order-book depth, dividends or other corporate actions, fundamentals, estimates. Closes are split-adjusted, not dividend-adjusted. Firm Lab does not call it: it reads the closes Control A recorded |
| Google News RSS (`agents/analyst/news.py`) | Control A's advisory notes | Recent headlines for discovery | No stable archive (a feed returns roughly 100 entries), aggregator redirect links instead of publisher URLs, coarse timestamps, no ticker mapping, unsupported by Google and characterised as personal, non-commercial use. Not usable for historical news research |
| SEC EDGAR submissions API (`agents/analyst/news.py`) | Control A's advisory notes | The authoritative index of a company's recent filings | Not a fundamentals provider (no normalised statements), no estimates, no transcripts, no earnings calendar |

Firm Lab ingests none of the three. The only data in the Firm Lab store is the daily closes Control A recorded.

## Domains

Each domain lists: what Firm Lab needs, whether the repository already has a source, the minimum required fields,
point-in-time requirements, update frequency, historical depth, live requirements, licensing and API
considerations, and the current status. Field names are those in `firm_lab/schemas.py`.

### 1. Fundamentals
- **What Firm Lab needs:** reported financial statements and the inputs to valuation, profitability, leverage and
  cash-flow measures, as they were known on each date. No alpha feature is computed from them at this checkpoint.
- **Existing source in the repository:** none.
- **Minimum required fields:** `instrument`, `fiscal_period`, `period_end`, `statement`, `filing_timestamp`,
  `known_at`, `currency`, `units`. Values as available: `revenue`, `operating_income`, `ebitda`, `eps_diluted`,
  `gross_profit`/`gross_margin`, `operating_margin`, `free_cash_flow`, `operating_cash_flow`,
  `capital_expenditure`, `total_debt`, `cash_and_equivalents`, `shares_outstanding`, ROIC components
  (`invested_capital`, `tax_expense`, `operating_income`), valuation inputs (`market_capitalization`,
  `enterprise_value`).
- **Point-in-time:** as-originally-reported values keyed to the filing timestamp. A source that overwrites prior
  periods when a company restates is not enough.
- **Update frequency:** within a day of each filing.
- **Historical depth:** at least 10 years, including delisted companies.
- **Live requirements:** none beyond the daily update.
- **Licensing and API:** most retail plans are personal or internal use with no redistribution.
- **Current status:** `UNAVAILABLE`. Sharadar is chosen; the adapter is built and needs operator access
  (`research_data_stack.md`). Interface: `FundamentalsProvider`.

### 2. Analyst estimates and revisions
- **What Firm Lab needs:** consensus EPS and revenue, the number of analysts, dispersion, and how the consensus
  changed over time.
- **Existing source in the repository:** none.
- **Minimum required fields:** `instrument`, `fiscal_period`, `metric`, `consensus_estimate`, `prior_consensus`,
  `revision_magnitude`, `analyst_count`, `dispersion`, `effective_timestamp`, `snapshot_timestamp`, `currency`.
- **Point-in-time:** mandatory. A provider that exposes only today's consensus, without dated historical
  snapshots, is insufficient for clean backtesting. The schema rejects a record without `snapshot_timestamp`.
- **Update frequency:** daily snapshots.
- **Historical depth:** at least 10 years of dated snapshots.
- **Live requirements:** none beyond daily.
- **Licensing and API:** the sources with true snapshot history are institutional and sold through sales teams.
- **Current status:** `UNAVAILABLE`. Interface: `EstimatesProvider`.

### 3. Earnings and transcripts
- **What Firm Lab needs:** when each company reported, the release, the call transcript and guidance, with
  timestamps and source links. No earnings alpha is built.
- **Existing source in the repository:** none (EDGAR 8-K index entries are visible to the advisory desk only).
- **Minimum required fields:** `instrument`, `fiscal_period`, `event_timestamp`, `session_timing` (pre-market,
  during market, post-market), `release_source_url`; then `transcript_source_url`, `transcript_timestamp`,
  `guidance_sections`, `prior_fiscal_period`.
- **Point-in-time:** the event timestamp and the transcript timestamp, each as published.
- **Update frequency:** same day as the event.
- **Historical depth:** at least 10 years.
- **Live requirements:** none at this stage.
- **Licensing and API:** transcript text is licensed content; storage terms must be read before any is kept.
- **Current status:** `UNAVAILABLE`. Interface: `EarningsProvider`.

### 4. SEC filings
- **What Firm Lab needs:** the filing index with acceptance timestamps, as the primary source for when something
  became public.
- **Existing source in the repository:** yes, for Control A's advisory notes only.
- **Minimum required fields:** `instrument`, `accession_number`, `form_type`, `accepted_timestamp`, `url`.
- **Point-in-time:** the EDGAR acceptance timestamp.
- **Update frequency:** continuous during EDGAR hours; indexes are rebuilt nightly.
- **Historical depth:** indexes from 1994 Q3.
- **Live requirements:** none.
- **Licensing and API:** free; a declared User-Agent is required; 10 requests per second.
- **Current status:** `PARTIAL_EXISTING` until the operator runs Firm Lab's own research-only EDGAR reader and
  its sample validates (`research_data_stack.md`). Interface: `FilingsProvider`.

### 5. General news
- **What Firm Lab needs:** headlines with source, precise publication time, a stable URL, entity mapping and
  duplicate grouping. Nothing is ranked from news at this checkpoint.
- **Existing source in the repository:** Google News RSS, for Control A's advisory notes only.
- **Minimum required fields:** `source`, `headline`, `published_timestamp`, `ingestion_timestamp`, `url`,
  `deduplication_key`; then `snippet`/`body` only if licensed, `instruments`/`entities`, `event_type`,
  `duplicate_group`.
- **Point-in-time:** the publication timestamp, to the second, plus Firm Lab's own ingestion timestamp.
- **Update frequency:** at least hourly.
- **Historical depth:** a queryable archive of several years.
- **Live requirements:** none yet.
- **Licensing and API:** storing article bodies is usually restricted; headlines and metadata vary by vendor.
- **Current status:** `PARTIAL_EXISTING` (useful for discovery, not institutional-quality history).
  Interface: `NewsProvider`.

### 6. Intraday bars
- **What Firm Lab needs:** a major dependency. At least 1-minute OHLCV with exchange and session timestamps,
  pre-market and after-hours flags where possible, and reliable historical depth.
- **Existing source in the repository:** none. The current gateway supplies daily bars only.
- **Minimum required fields:** `instrument`, `bar_start`, `interval` (`1m`), `open`, `high`, `low`, `close`,
  `volume`, `session`, `exchange_session_date`.
- **Point-in-time:** bars as published, with adjustment state recorded; unadjusted bars must be obtainable.
- **Update frequency:** per minute when live; daily backfill otherwise.
- **Historical depth:** at least 5 years; 10 or more preferred.
- **Live requirements:** live quote updates and bars with a known feed (consolidated versus single venue).
- **Licensing and API:** real-time consolidated data needs exchange agreements and non-professional status.
- **Current status:** `UNAVAILABLE`. Massive is chosen; the adapter is built and needs operator access
  (`research_data_stack.md`). Interface: `IntradayMarketDataProvider.bars_1m`.
- Only after such a provider exists can Firm Lab legitimately calculate VWAP, time-of-day RVOL, opening range,
  intraday volatility or aggressive-flow proxies. None is calculated now.

### 7. Live quotes and trades
- **What Firm Lab needs:** preferred additions to the bars: trades, bid/ask quotes, NBBO where available, trade
  conditions and quote conditions.
- **Existing source in the repository:** partly. Control A reads bid/ask snapshots during its own runs. There is
  no stream and no trade data.
- **Minimum required fields:** quotes: `instrument`, `quote_timestamp`, `bid`, `ask`, `bid_size`, `ask_size`,
  `feed`. Trades: `instrument`, `trade_timestamp`, `price`, `size`, `feed`; then `conditions`, `exchange`.
- **Point-in-time:** exchange or SIP timestamps, preserved as sent.
- **Update frequency:** streaming.
- **Historical depth:** at least 2 years of ticks for research.
- **Live requirements:** a streaming connection with stated latency.
- **Licensing and API:** as for intraday bars.
- **Current status:** `PARTIAL_EXISTING`. Interface: `IntradayMarketDataProvider.quote_snapshots` and `.trades`.

### 8. Order flow and market microstructure
- **Buyer count vs seller count is not a valid concept**, because every trade has both a buyer and a seller.
- **What Firm Lab needs:** data capable of estimating aggressive buyer or seller initiation, signed trade volume,
  bid/ask pressure, quote imbalance, book imbalance and trade intensity.
- **Existing source in the repository:** none.
- **Minimum required fields:** tick trades and quotes as in domain 7 (to sign each trade against the prevailing
  quote); for book imbalance, depth data by price level or by order.
- **Point-in-time:** exchange timestamps at sub-second precision.
- **Update frequency:** every event.
- **Historical depth:** at least 1 year of ticks; depth history as available.
- **Live requirements:** streaming with low, stated latency.
- **Licensing and API:** live full-depth feeds carry exchange licences that an individual may not obtain.
- **Current status:** `UNAVAILABLE` (not `BLOCKED`: candidate providers supply tick trades and quotes, and at
  least one supplies depth). Nothing is derived from daily bars.

### 9. Options chains
- **What Firm Lab needs:** full chains with quotes and timestamps. No strategy recommendation is built.
- **Existing source in the repository:** partly. The registered read path lists contracts and bid/ask quotes;
  Firm Lab has a storage table and ingests nothing.
- **Minimum required fields:** `contract_id`, `underlying`, `option_type`, `strike`, `expiration`, `bid`, `ask`,
  `quote_timestamp`, `volume`, `open_interest`, `provider_implied_volatility`.
- **Point-in-time:** the quote timestamp on every row.
- **Update frequency:** end of day for research; intraday later.
- **Historical depth:** at least 5 years of end-of-day chains.
- **Live requirements:** consolidated (OPRA) quotes if ever used live.
- **Licensing and API:** personal-use plans exist; live OPRA needs agreements.
- **Current status:** `BUILD_ONLY`. ThetaData is chosen; the adapter is built and needs operator access
  (`research_data_stack.md`). Interface: `OptionsMarketDataProvider`.

### 10. Options Greeks
- **What Firm Lab needs:** preferred: provider delta, gamma, theta, vega, the underlying quote and a theoretical
  price.
- **Provenance rule:** a value the source supplies is stored as `provider_delta` (and `provider_gamma`,
  `provider_theta`, `provider_vega`, `provider_implied_volatility`). A value Firm Lab computes later is stored as
  `model_estimated_delta` (and so on). The two namespaces are never merged; a value the provider did not supply
  stays empty.
- **Existing source in the repository:** none. No Greek or implied volatility has ever been captured.
- **Minimum required fields:** the chain fields plus the provider's name for the model that produced the Greeks.
- **Point-in-time:** the quote timestamp of the row the Greek belongs to.
- **Update frequency / historical depth / live requirements:** as for chains.
- **Licensing and API:** vendors compute Greeks with their own models; the method must be recorded.
- **Current status:** `UNAVAILABLE`.

### 11. Risk-free: 3-month Treasury-bill total return
- **What Firm Lab needs:** a clean total-return series for the 3-month U.S. Treasury bill, for the fixed 70/30
  ruler (70% VTI + 30% bill total return, rebalanced monthly on the first NYSE trading session of each month).
- **A yield series is not automatically a total-return series.** The schema accepts only `TOTAL_RETURN_INDEX` or
  `PERIOD_TOTAL_RETURN`; a yield or discount rate is rejected as `YIELD_IS_NOT_TOTAL_RETURN`. The 70/30 ruler is
  not computed from a yield series, and no proxy asset is substituted silently.
- **Existing source in the repository:** none.
- **Minimum required fields:** `series_id`, `measure`, `observation_date`, `value`, `published_timestamp`; then
  `methodology_url`.
- **Point-in-time:** publication timestamp of each observation.
- **Update frequency:** daily preferred; monthly is the minimum the rebalancing rule needs.
- **Historical depth:** back to the start of any comparison window.
- **Live requirements:** none.
- **Licensing and API:** the true index series are proprietary and restrict storage and redistribution.
- **Current status:** `UNAVAILABLE` until a validated auction sample is stored and the index computes without a gap.
  The construction methodology from official Treasury auction data (`treasury_bill_total_return_methodology.md`) was
  approved and frozen by the operator on 2026-10-02; the index is an accrual between auction and maturity, not a
  market value. See `research_data_stack.md`.
  Interface: `RiskFreeBenchmarkProvider`.

### 12. Corporate actions and dividends
- **What Firm Lab needs:** total-return-correct data. Cash dividends, splits, spin-offs, symbol changes, mergers
  and delistings.
- **Existing source in the repository:** none. Stored closes are split-adjusted by the provider; nothing else is
  recorded. No Firm Lab result may be called a total return until these are accounted for.
- **Minimum required fields:** `instrument`, `action_type`, `effective_date`, `announced_timestamp`; then
  `cash_amount` with `currency`, `split_ratio`, `new_instrument`, `ex_date`, `record_date`, `pay_date`.
- **Point-in-time:** the announcement timestamp, so an action is not known before it was announced.
- **Update frequency:** daily.
- **Historical depth:** as deep as the price history, including delisted names.
- **Live requirements:** none.
- **Licensing and API:** as for the price source.
- **Current status:** `UNAVAILABLE`. Sharadar is chosen; the adapter is built and needs operator access
  (`research_data_stack.md`). Interface: `CorporateActionsProvider`.

## What a provider connection involves

A deliberate operator choice of source; a research-only collector that cannot import trading code; raw responses
stored with provenance; validation; only then a capability promoted to `AVAILABLE`. The `firm_lab` package itself
contains no network code, and a test keeps it that way. The collectors built at Checkpoint 3 are described in
`research_data_stack.md`.
