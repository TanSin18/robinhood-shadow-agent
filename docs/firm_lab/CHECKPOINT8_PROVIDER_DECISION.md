# Checkpoint 8 — market-data provider decision

Read from vendors' own pricing, documentation and terms pages on 2026-10-04. Documentation review only: no account was
created, nothing was purchased, no key exists and no feed was activated. Pages were read through a fetch tool that
summarises; every price and clause should be read once more on the linked page by the person who pays.
This is an engineering and compliance reading, not legal advice.

`OPERATOR PURCHASE DECISION REQUIRED`

`RECOMMENDED_PROVIDER = Sharadar` — product **Prices, Full History**, Personal Use License.

This supersedes the Checkpoint 5 result (`RECOMMENDED_PROVIDER = NONE`) for **daily historical research data only**.
Checkpoint 5 asked a different question (intraday, tick and quote feeds); for that question its result stands.

## Why a paid provider is required

The need is concrete: a survivorship-safe daily history long enough to hold two bear markets before a four-year
holdout (`CHECKPOINT8_DATA_SUFFICIENCY_SPEC.md`). What is free does not meet it:

| Free source | Why it is not enough |
|---|---|
| Closes already held (registered read path) | 23 instruments chosen today, close only, 378 sessions, captured after the fact |
| Alpaca free plan | History from 2016; delisted names not documented as retained; terms silent on local storage |
| Massive free plan | 2 years; individual terms are display-use only |

No free source was substituted to avoid asking.

## The recommended product

| | |
|---|---|
| Vendor and channel | Sharadar, sold directly at sharadar.com since 2026-07-27 ("Sharadar Direct") |
| Product and tier | **Prices** plan, **Full History** |
| Price | **$39 per month or $299 per year** (5-year tier $9 / $99; 10-year tier $19 / $199) |
| Tables included | stock prices, fund prices (ETFs), tickers, corporate actions, S&P 500 membership, daily metrics |
| History | From December 1997 |
| Coverage | About 21,000 stock tickers and 10,000 fund tickers, active and delisted |
| Fields | Open, high, low, close, volume (split-adjusted); unadjusted close; split, dividend and spin-off adjusted close |
| Corporate actions | Splits, cash dividends, spin-offs, ticker changes, ADR ratio changes, listings, delistings with reasons, acquirers; from 1998 |
| Index membership | S&P 500 additions and removals from 1998 |
| Delivery | Bulk download and a REST interface; works on macOS |
| Capability unlocked | `historical_ohlcv`, `corporate_actions` (historical), `historical_universe`, and through them `strict_pit_training_data` |

**Licence, as read** (sharadar.com/terms):

* Granted to natural persons for personal use. Professional, commercial or organisational use is excluded, as is
  trading or investing on behalf of others.
* No redistribution or sharing of the data.
* Local storage is not prohibited while subscribed. Within 30 days of termination every copy of the data must be
  deleted, including downloads, bulk files, caches and extracts.
* Research outputs, backtest results, models, summary statistics and similar derived work that cannot reproduce the
  data may be kept after termination.
* Cancelling stops future billing; nothing already paid is refunded.
* The terms do not mention machine learning by name. They name "models" among what may be kept, which implies that
  building models is a permitted personal use. If certainty is wanted, one question to the vendor settles it.

**What follows from the licence for this project**

* All raw vendor data sits in one file, `firm_lab_history.db`, outside any repository; deleting that file meets the
  deletion clause. Nothing licensed goes into Git, a report, a prompt or the dashboard overlay.
* The dataset exists only while the subscription does. A cancelled subscription means the raw history is deleted
  and must be bought again to be rebuilt; manifests and hashes say exactly what to rebuild.
* The vendor re-adjusts history after a split and rewires a renamed company's history onto its new ticker. Every
  capture is stored as a version, keyed by the vendor's permanent identifier, so a change is visible.

**Suggested path.** One month at $39. Download the five tables. Run the validation sample
(`historical_market_data_policy.md`, sufficiency bars O4 to O6). Decide on the annual plan after the review of
that sample.

**Optional, not required.** The Bundle ($69 per month or $499 per year) adds the vendor's as-reported fundamentals
from 1998, keyed to a filing date without a time. SEC data is the authoritative source with acceptance times and is
free; the Bundle would only matter for fundamentals before 2009, which no checkpoint has asked for.

## The other candidates

| Provider | Product read | Price | Daily history | Delisted | Corporate actions | Local storage and modelling rights | After cancelling | Result |
|---|---|---|---|---|---|---|---|---|
| Massive | Stocks Starter / Developer / Advanced | $29 / $79 / $199 per month; 20% less annually | 5 years / 10 years / from 2003-09-10 | Kept, marked inactive | Splits, dividends, ticker changes; no merger, spin-off or delisting events | Market Data Terms: "strictly for display use only" unless otherwise agreed; non-display use and derived investment strategies need a licence | Delete all market data | **Not usable** for model research on an individual plan; the business tier is $2,499 per month |
| Alpaca | Free and Algo Trader Plus | $0 / $99 per month | From 2016 on both | Not documented as retained; no endpoint for historical assets | Sixteen types; creation time not guaranteed | Terms forbid copying to another computer "for publication or distribution or for any commercial enterprise"; silent on private research storage | Not stated | **Not sufficient**: one bear market, survivorship not established |
| Databento | US equities summary and Nasdaq datasets | Usage-based or $199 per month | From 2018 (Nasdaq only) or 2023–2024 (consolidated) | Within those windows only | Separate reference product, 6 years | Internal use including non-display, as read | Unverified | **Not sufficient**: history too short |
| Norgate Data | US Stocks Platinum / Diamond | Not readable (calculator page) | From 1990 / 1950 | Yes | Adjustment modes; separate table unverified | Personal use, export and processing allowed | Delete all content; derived parameters may be kept | **Not usable here**: the updater runs on Windows only. Strongest on index history (S&P 500 from 1957, Russell from 1990) |
| Tiingo | Power | $30 per month | From 1962 | Partial: only tickers not yet reused | Splits and dividends (beta); no mergers or delisting reasons | "Internal use"; full terms could not be read | Unverified | **Not sufficient**: delisted coverage partial, terms unread |
| EODHD | EOD Historical Data, personal | $19.99 per month | From 1962 | Yes; before 2018 without splits or dividends | Splits and dividends; no ticker changes or delisting reasons | Storing and analysing for private use is explicitly permitted | Not addressed | **Not sufficient**: no delisting reasons, no identity across renames |

Sources: massive.com/pricing, massive.com/legal/market-data-terms-of-service, massive.com/legal/individuals-terms-of-service;
docs.alpaca.markets (about-market-data-api, market-data-faq, stockbars), files.alpaca.markets terms; databento.com
(pricing, catalog, corporate-actions); norgatedata.com (packages, ndu-faq, eula); tiingo.com/about/pricing;
eodhd.com (pricing, terms-conditions, delisted data); sharadar.com (subscribe, prices, terms, docs).

## What stays unresolved after a purchase

* **Post-delisting returns.** Sharadar gives the delisting date and reason, not the return a holder realised
  afterwards. No individually licensable source of that was found. Labels through a bankruptcy or regulatory
  delisting stay biased upward and are counted.
* **Historical sector classification.** The vendor's sector and industry fields describe a company as it is today.
* **Index membership other than the S&P 500.** Not in the product.
* **Announcement times of corporate actions.** The vendor gives an effective date only.
* **Whether the vendor's bulk file layout matches its documentation.** The reader refuses a file whose columns are
  not the documented ones; the validation sample is where this is found out.
* **How the vendor prints re-counted volume.** Volume comes only on today's share basis. If it is rounded to whole
  shares, the early volume of a stock that later went through very large reverse splits is known only as a range:
  its universe membership can be undecided, and the volume features are withheld from every row of a dataset that
  would read such a bar. The first file shows how many security-months are affected.
* **How finely the vendor prints adjusted prices.** Open, high and low come only split-adjusted. For a stock that
  later split, the reprinted early prices must still hold the day's price to a twentieth of a cent; otherwise the
  features that read a high, low or open are withheld from every row of the dataset
  (`historical_market_data_policy.md` §4), and only the close-based features remain. Two decimals never suffice once
  any member has a later forward split; four decimals carry a cumulative later split of about 10, six decimals about
  1,000. This cannot be known before a file is read. It is the
  first thing the validation sample measures (bar O7), and a reason to take one month before the annual plan. If it
  fails, the remedy is a second source of unadjusted open, high and low, which is a new provider decision.

## A second licensing finding: FRED and ALFRED

The Federal Reserve Bank of St. Louis terms of use for FRED services (which name FRED, ALFRED and the API) prohibit,
without the Bank's prior written consent, storing, caching or archiving FRED content and using FRED services or
content "in connection with the development or training of any software program or system or machine learning".
A research dataset stored locally for model research is both.

* No FRED key is used. Checkpoint 8 did not request one and reads none.
* The Checkpoint 5 sample-capture command asked FRED and ALFRED for sample files; those requests are removed, the
  macro store no longer accepts FRED as a source, and a regression test holds both. No FRED value was ever stored in
  the research database (the parser refused date-only vintages). **Operator action:** if the capture command was run
  on the Mac, the `fred_*.csv`, `fredapi_*.json` and `alfred_*.csv` files in its output folder should be deleted.
* Macro history comes from the agencies that publish it (public domain): BLS, BEA, the Treasury, the Federal Reserve
  Board, and the Philadelphia Fed real-time data set for vintages (`CHECKPOINT8_SOURCES_PIT.md`).
* If ALFRED vintages are wanted later, the route is a written request to the Bank.
