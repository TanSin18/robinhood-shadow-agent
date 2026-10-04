# Firm Lab — provider evaluation matrix

> **2026-10-04, Checkpoint 8.** For daily historical research data this matrix is superseded by
> `CHECKPOINT8_PROVIDER_DECISION.md`, which was read from current vendor terms: Sharadar Prices (Full History) is
> recommended and awaits an operator purchase decision; Massive's individual plans are display-use only; FRED and
> ALFRED are not used (their terms prohibit storage and model training without written consent). The rows below are
> kept as they were written on 2026-10-01.

Checked 2026-10-01. Nothing here is connected or purchased, and no provider is selected. Fit labels are for the
stated domain only and rest on the evidence in the row; where the evidence does not support a choice, none is made.

**How the facts were gathered.** Vendor documentation and pricing pages were read through a fetch tool that
summarises pages; direct access to several sites was blocked. Treat every price and limit as needing one more
check on the linked page before money is spent. Items marked *unverified* could not be confirmed and are not used
to justify a label. Reliability (uptime, error rates) was not measured for any provider: no evidence was collected.

Labels: **STRONG FIT** meets the minimum requirements in `data_sources.md` on the evidence found.
**PARTIAL FIT** meets some, or meets them with an open question that matters. **WEAK FIT** misses a requirement
that matters. **NOT SUITABLE** cannot be used for this purpose (wrong kind of data, or no access path for an
individual).

## 1. Fundamentals

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Sharadar Core US Fundamentals (Nasdaq Data Link; Sharadar Direct since 2026-07-27) | STRONG FIT for research | As-reported dimensions (ARQ/ARY/ART) exclude restatements and are indexed to the filing date (`datekey`); about 18,000 tickers including 12,000 delisted; from 1998; updated within a day | Dates only, no acceptance time; current price and licence tier unverified |
| SEC EDGAR XBRL APIs | PARTIAL FIT | Authoritative, free, no key; submissions carry `acceptanceDateTime`; 10 requests/second with a declared User-Agent | Raw XBRL tags need normalising; frames returns the last-filed fact per period; per-fact filing fields unverified |
| Financial Modeling Prep | PARTIAL FIT | Statements carry `filingDate` and `acceptedDate`; separate as-reported endpoints; $22–$149/month | Restatement handling and delisted coverage unverified; display or redistribution needs a separate agreement |
| Tiingo fundamentals | PARTIAL FIT | `asReported` switch; 5,500+ US equities, 20+ years, delisted included | Add-on priced through sales; internal use only |
| Intrinio | PARTIAL FIT | Standardised and as-reported; available 20–30 minutes after filing; $150/month individual | Restatement history and rate limits unverified; history starts 2007–2010 |
| EODHD | WEAK FIT | `filing_date` present; $59.99/month | Restatement handling not stated |
| Massive (formerly Polygon.io) | WEAK FIT | `filing_date` is the date of the most recent filing that included the period, so it is not as-originally-reported | History from 2009 |
| Alpha Vantage | WEAK FIT | Vendor admits a risk of inconsistent taxonomy mapping | Filing-date fields unverified |
| Finnhub | not rated | Official pricing and history could not be read | Everything |

**Current recommendation:** none selected. Shortlist for a closer look: Sharadar for history, with EDGAR as the
independent check on filing times. **Unresolved:** price and licence for Sharadar; whether date-only filing dates
are precise enough.

## 2. Analyst estimates and revisions

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| FactSet Estimates (point-in-time consensus) | NOT SUITABLE (access) | Daily snapshots from December 2009: the right data | Sales only; no individual licence path found |
| LSEG I/B/E/S | NOT SUITABLE (access) | US history from 1976 | Sales only; no individual licence path found |
| S&P Capital IQ / Visible Alpha | NOT SUITABLE (access) | Delivered inside Capital IQ Pro | No self-serve option |
| Zacks consensus history | PARTIAL FIT | Mean, median, high, low, standard deviation, analyst count, updated daily; history from 1979 (annual EPS) | Snapshot frequency, price and individual eligibility unverified |
| Estimize | PARTIAL FIT | Crowdsourced, 2,000+ stocks since 2012, point-in-time preserved | A different population from sell-side consensus; individual pricing unverified |
| EODHD | WEAK FIT | Average, high, low, analyst count, and the trend 7/30/60/90 days ago | A rolling lookback, not an archive of dated snapshots |
| Financial Modeling Prep | WEAK FIT | One row per fiscal period with low/high/average and analyst count | No snapshot history documented |
| Alpha Vantage | not rated | Lists "analyst count & revision history" | Depth and form of that history unverified |

**Current recommendation:** none. No individually licensable source with verified dated consensus history was
found. **Unresolved:** whether Zacks history is obtainable; the alternative of collecting dated snapshots
ourselves going forward gives clean data from the start date onward and no backtest history, and needs an operator
decision.

## 3. Earnings and transcripts

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| SEC EDGAR 8-K | STRONG FIT for the release time | Authoritative acceptance timestamp for each earnings release; free | No transcripts, no calendar of future dates |
| API Ninjas | PARTIAL FIT | Transcripts for 8,000+ companies from 2005 with timestamps; calendar from 2000; $39–$99/month | Timing flag and call timestamp are premium fields; transcript accuracy not assessed |
| Financial Modeling Prep | PARTIAL FIT | Transcripts for 8,200 companies, 10+ years | Ultimate plan ($149/month) per the pricing page; another page implies a lower tier |
| Benzinga (direct, or $99/month per dataset through Massive) | PARTIAL FIT | Earnings and guidance with confirmation and update timestamps, from 2012 | Whether `time` is a clock time or a session flag is unverified; direct pricing not public |
| Quartr | PARTIAL FIT | Events, live and post-event transcripts, 16,000+ companies | Contact sales; history depth unverified |
| EODHD calendar | WEAK FIT | `report_date` and before/after-market flag, back to the 1990s | Calendar only |

**Current recommendation:** none selected. EDGAR 8-K acceptance time is the natural anchor for "when was it
public"; a transcript vendor would be chosen separately. **Unresolved:** storage terms for transcript text.

## 4. SEC filings

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| SEC EDGAR | STRONG FIT | The primary source; free; indexes from 1994 Q3; submissions and full index available | Firm Lab would need its own research-only reader; full-text search has no documented API |

**Current recommendation:** EDGAR, when a research-only collector is approved. **Unresolved:** none on the data.

## 5. General news

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Benzinga | PARTIAL FIT | Own newsroom; ticker, CUSIP and ISIN tags; timestamps to the second; REST and websocket; history to 2015 through Alpaca | Pricing, archive depth and storage licence unverified |
| Massive news | PARTIAL FIT | Title, publisher, RFC3339 time, URL, tickers; history to 2016-06-22; included in stock plans | "Updated hourly"; deduplication behaviour unverified |
| Alpha Vantage | WEAK FIT | Ticker and topic filters, minute precision | 25 requests/day free; history depth unverified |
| Tiingo news | WEAK FIT | Internal use only | Pricing page shows three months of queryable history |
| GDELT | WEAK FIT | Free | No ticker tags, three-month window, 250 records per query |
| NewsAPI.org | NOT SUITABLE | Free tier is delayed 24 hours and for development only; real-time is $449/month | No article body |
| Google News RSS (current source) | NOT SUITABLE for historical research | About 100 entries per feed, redirect links, coarse times, no ticker mapping, unsupported | Remains usable for discovery in the advisory notes |
| RavenPack; Dow Jones Newswires / Factiva | NOT SUITABLE (access) | Institutional archives with entity mapping | No public individual pricing |

**Current recommendation:** none selected. **Unresolved:** storage and redistribution terms for every candidate.

## 6. Intraday bars

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Massive (formerly Polygon.io) | STRONG FIT for research | Consolidated SIP feeds; 1-minute and 1-second bars 04:00–20:00 ET; history from 2003; raw or split-adjusted; delisted tickers kept; $29 (5 years, delayed) to $199 (20+ years, real-time) | No session flag (session is inferred from the timestamp); live latency unpublished; individual plans are non-professional only |
| Alpaca Market Data (SIP plan) | STRONG FIT for research | Full SIP at $99/month; 1-minute bars since 2016; raw, split, dividend or all adjustments; `asof` across renames | Non-professional and display terms unverified; latency unverified |
| EODHD | PARTIAL FIT | 1-minute from 2004 including pre- and post-market, UTC; $29.99/month | Bars finalised hours after the close; licence terms unverified |
| Databento | PARTIAL FIT | Nanosecond timestamps; 7 years of OHLCV on the $199 plan | Direct proprietary feeds, not the consolidated tape |
| Interactive Brokers API | PARTIAL FIT | Adjusted and unadjusted bars; low cost with an account | 60 historical requests per 10 minutes; no delisted securities; history depth unverified |
| Twelve Data | WEAK FIT | 1-minute bars | Real-time from about 5% of US volume; extended-hours bars carry no volume |
| Tiingo | WEAK FIT | IEX only (about 2.5–3% of volume), from August 2017 | Not consolidated |
| Charles Schwab Trader API | WEAK FIT | About 48 days of minute history | Official documentation not readable |

**Current recommendation:** none selected; Massive and Alpaca SIP both meet the minimum on the evidence, and the
evidence does not separate them. **Unresolved:** licence terms for an individual, and how much history is needed.

## 7. Live quotes and trades

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Massive (Advanced, $199) | STRONG FIT | NBBO quotes and trades with condition codes; SIP, participant and TRF timestamps in nanoseconds | Real-time needs signed exchange agreements; latency unpublished |
| Alpaca (SIP plan, $99) | STRONG FIT | Trades, quotes, corrections, LULD and imbalances over websocket; nanosecond timestamps | Latency and tick-history start unverified |
| Databento | PARTIAL FIT | Trades and top of book with PTP nanosecond timestamps; claimed 590 µs over the internet | Not SIP; its "mini NBBO" is synthetic and starts 2023-03-28 |
| Interactive Brokers API | PARTIAL FIT | Tick-by-tick with conditions | Standard streaming is 250 ms snapshots; 1,000 historical ticks per request |
| Tiingo, EODHD, Twelve Data | WEAK FIT | Single-venue or partial feeds | Not consolidated; EODHD trade conditions are empty |
| Robinhood read path (current) | NOT SUITABLE | Bid/ask snapshots only, during Control A's runs | No stream, no trades |

**Current recommendation:** none selected. **Unresolved:** as for intraday bars.

## 8. Order flow and market microstructure

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Databento | STRONG FIT for depth research | Order-by-order (MBO), 10-level (MBP-10), top of book and imbalance, e.g. Nasdaq TotalView; historical data needs no exchange licence | Live TotalView is commercial-licence only; which plan and price applies to US equities is unverified ($199 and $4,000 both appear) |
| Massive | PARTIAL FIT | Tick trades and NBBO allow each trade to be signed against the quote | No Level 2 or order book |
| Alpaca (SIP) | PARTIAL FIT | Historical trades and quotes | No depth |
| Interactive Brokers API | WEAK FIT | Market depth for 3 instruments at once | Odd lots excluded; no depth history |

**Current recommendation:** none selected. The domain is `UNAVAILABLE`, not `BLOCKED`: candidates exist.
**Unresolved:** whether book imbalance is needed at all, which decides between a tick feed and a depth feed.

## 9. Options chains and 10. Options Greeks

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Theta Data | STRONG FIT for research | $40–$160/month; tick history from 2016 or 2012 on higher tiers; Greeks from the Standard tier | Personal use only; Greeks method unverified |
| ORATS | STRONG FIT for implied volatility and Greeks history | End-of-day from 2007, 1-minute from 2020; IV, Greeks and theoretical prices from ORATS's own model; $199–$899/month | Model method not described on the pages read; live tiers need data agreements |
| Massive options | PARTIAL FIT | OPRA feed; chain snapshot with Greeks, IV and open interest; $29–$199/month | Greeks are computed by Massive and exist on the snapshot only, not in history |
| Cboe DataShop | PARTIAL FIT | End-of-day and interval quotes from 2012, optional IV and Greeks | Prices not displayed; API from $2,499/month |
| Databento OPRA | PARTIAL FIT | Raw consolidated quotes and trades from 2013, nanosecond timestamps | No IV and no Greeks, so it misses a minimum field on its own |
| Tradier | PARTIAL FIT | Real-time for account holders; Greeks from ORATS, hourly | Real-time Greeks are separately entitled |
| Interactive Brokers API | PARTIAL FIT | OPRA Level 1 at $1.50/month non-professional; model Greeks delivered | Expired-option history unverified |
| Alpaca | WEAK FIT | OPRA on the $99 plan | History only since February 2024 |
| Charles Schwab Trader API | WEAK FIT | Chains with Greeks | No option price history |
| EODHD | WEAK FIT | End-of-day with Greeks, $29.99/month | Two years of history |
| Robinhood read path (current) | NOT SUITABLE as a research source | Contract listings and bid/ask quotes | No history; IV, Greeks and open-interest fields unverified |

**Current recommendation:** none selected. Whatever is chosen, Greeks are stored as `provider_*` together with
the vendor's name, because every vendor computes them with its own model. **Unresolved:** each vendor's method.

## 11. Risk-free: 3-month Treasury-bill total return

A yield series is not a total-return series. What each candidate actually is:

| Candidate | What it is | Fit | Evidence and limits |
|---|---|---|---|
| ICE BofA US 3-Month Treasury Bill Index (G0O1) | Total-return index of the single bill closest to three months | STRONG FIT on definition; NOT SUITABLE without a licence | Not on FRED; ICE terms are internal use only with no redistribution; no free source found |
| S&P U.S. Treasury Bill indices (0–3 month and others) | Total-return indices | PARTIAL FIT | Storing the levels in a database needs written permission from S&P; free export unverified; 0–3 months is not the 3-month bill |
| Bloomberg 1–3 Month T-Bill index | Total-return index | NOT SUITABLE (access) | Off-terminal data needs a firm-level licence |
| U.S. Treasury official data (auction results; Daily Treasury Bill Rates, CC0, from 2002) | Prices per $100 at auction and daily discount rates | PARTIAL FIT | Free and official; a rolled 13-week-bill total-return series could be built from it, but it would be our own construction with roll, day-count and settlement choices, not an official index |
| FRED DTB3, DGS3MO, TB3MS | Yields and discount rates | NOT SUITABLE as a total return | Rates only; usable at most as an input to a constructed series |
| T-bill ETFs: TBIL (3-month bill, from 2022-08-09), BIL (1–3 month, 2007), SGOV (0–3 month, 2020), SHV | Traded funds | PARTIAL FIT as a proxy only | Net of fees, tracking difference, and total return needs distribution-adjusted prices; choosing one would change the benchmark, so it needs an explicit operator decision |
| Kenneth French library RF | One-month bill return | WEAK FIT | One month, not three; about a month behind; use requires permission |
| CRSP Treasury files | Risk-free series | NOT SUITABLE (access) | Institutional subscription; the 3-month series is a yield |

**Treasury source selected (2026-10-02): YES — path (b), official Treasury auction records under the frozen
methodology.** Computation: built; available once a validated auction sample is stored. (Before that decision this
line read: source selected NO, ruler `DATA_SOURCE_PENDING`.)
**Paths for an operator decision:** (a) license a 3-month bill total-return index; (b) build a series from
official Treasury data under a written methodology; (c) explicitly redefine the 30% leg as a named fund.
Calendar for "first NYSE trading session of each month": the NYSE holidays and hours page is the authority;
`exchange_calendars` (XNYS) is a community-maintained package already used by the runtime.

## 12. Corporate actions and dividends

| Provider | Fit | Evidence | Open questions |
|---|---|---|---|
| Sharadar (prices and actions) | STRONG FIT for research history | Actions table with ticker changes, splits, dividends, spin-offs and delisting reasons; 21,000 tickers active and delisted, from 1997; unadjusted and adjusted closes | Daily only; current price and licence unverified; announcement times unverified |
| Databento corporate actions | PARTIAL FIT | 61 event types, described as point-in-time, with adjustment factors | About six years of history; base price unverified |
| Alpaca | PARTIAL FIT | 16 action types including spin-offs, mergers and name changes | "No guarantees on the creation time" |
| Massive | PARTIAL FIT | Splits, dividends and ticker-change events; delisted tickers kept | No merger, spin-off or delisting event types; history not linked across renames |
| Tiingo, Twelve Data, EODHD | WEAK FIT | Splits and dividends | Partial or beta coverage |
| Robinhood read path (current) | NOT SUITABLE | Provides split-adjusted closes only | No dividend or event data |

**Current recommendation:** none selected. **Unresolved:** whether any candidate gives a reliable announcement
timestamp, which the point-in-time rule needs.

## The eighteen criteria, by multi-domain provider

"n/e" means no evidence was collected. Costs are per month, individual tier, as read on 2026-10-01.

| Criterion | Massive | Alpaca | Databento | Sharadar | FMP | EDGAR |
|---|---|---|---|---|---|---|
| Data quality | SIP consolidated | SIP on paid plan; IEX only when free | Direct exchange feeds | Curated from filings | Derived from EDGAR | Primary source |
| Timestamp quality | Nanosecond SIP and participant times | Nanosecond RFC-3339 | Nanosecond, PTP-synchronised | Dates only | Filing and accepted dates | Acceptance timestamps |
| Historical depth | From 2003 | Bars from 2016 | Equities from 2018; OPRA from 2013 | From 1997–1998 | Up to 30+ years | Indexes from 1994 |
| Point-in-time history | Fundamentals weak; prices raw or adjusted | Raw and adjusted bars | Corporate actions point-in-time | Yes, as-reported keyed to filing date | Partial | Partial |
| Corporate actions | Splits, dividends, ticker events | 16 types | 61 types, 6 years | Actions table incl. delistings | n/e | None |
| Live latency | Unpublished | n/e | 590 µs claimed over internet | Not live | Not live | Under 1 second for submissions |
| Options coverage | OPRA; Greeks on snapshot only | OPRA since 2024 | OPRA raw; no Greeks | None | None | None |
| Intraday granularity | 1 second and 1 minute; ticks | 1 minute; ticks | Ticks, order-by-order | Daily only | n/e | None |
| Fundamentals | Yes, weak point-in-time | None | None | Yes | Yes | Raw XBRL |
| Estimates and revisions | Benzinga add-on only | None | None | None | Today's consensus only | None |
| Earnings transcripts | Add-on | None | None | None | Yes, top tier | None |
| Rate limits | "Unlimited" on paid plans | 10,000 calls/minute on paid plan | 10 live sessions per dataset | 5,000 per 10 minutes | 300–3,000 per minute | 10 per second |
| Reliability | n/e | n/e | n/e | n/e | n/e | n/e |
| API complexity | REST, websocket, flat files | REST, websocket, Python SDK | Binary TCP; Python, C++, Rust | REST tables, bulk | REST | REST, bulk files |
| Cost | $29–$199 | $0–$99 | $199 and up; usage-based history | From $9 for prices; fundamentals unverified | $22–$149 | Free |
| Licensing restrictions | Non-professional, no redistribution | Unverified | Live depth feeds need commercial licences | Personal and professional tiers | No display or redistribution | Fair-access rules |
| Suitability for research | High for prices and ticks | High for prices | High for microstructure | High for fundamentals and actions | Medium | High as the primary record |
| Suitability for real-time use | Yes, top tier with agreements | Yes, paid plan | Yes, with licences | No | No | No |

## Main sources

Massive: massive.com/pricing, massive.com/docs, massive.com/knowledge-base. Databento: databento.com/pricing,
databento.com/catalog, databento.com/corporate-actions. Alpaca: docs.alpaca.markets. Tiingo: tiingo.com/about/pricing.
Twelve Data: twelvedata.com/pricing. EODHD: eodhd.com/pricing. Interactive Brokers: interactivebrokers.github.io/tws-api
and interactivebrokers.com pricing pages. Sharadar: sharadar.com. SEC: sec.gov/page/sec-api-documentation,
sec.gov/os/accessing-edgar-data. FMP: site.financialmodelingprep.com. Intrinio: intrinio.com/pricing.
Zacks: zacksdata.com. FactSet, LSEG, S&P: vendor product pages. API Ninjas: api-ninjas.com. Benzinga: docs.benzinga.com.
Quartr: quartr.com/docs. ORATS: orats.com/data-api. Theta Data: thetadata.net/pricing. Cboe: datashop.cboe.com.
FRED: fred.stlouisfed.org (DTB3, DGS3MO, TB3MS). ICE: indices.ice.com and ICE index terms. S&P Dow Jones Indices:
spglobal.com/spdji. Treasury: home.treasury.gov daily bill rates; TreasuryDirect auction results.
Kenneth French data library: mba.tuck.dartmouth.edu. NYSE: nyse.com/trade/hours-calendars.
