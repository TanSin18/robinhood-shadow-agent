# Checkpoint 5 — market-data decision

Verified from official documentation on 2026-10-03. Documentation review, not a
latency/completeness test of an activated feed. No account, purchase, credential,
subscription or feed was activated.

`RECOMMENDED_PROVIDER = NONE`

The technical front-runner is Massive for its longer history, but neither
provider's public materials establish all required local-retention/non-display
rights for this research application. Obtain written entitlement confirmation
before selecting or paying. This does not change the older provider registry or
activate its planned choice.

## Products and coverage

| Requirement | Massive Stocks Advanced | Alpaca Algo Trader Plus / SIP |
|---|---|---|
| Advertised monthly price | $199, individual/non-professional | $99 |
| Historical 1-minute bars | Yes | Yes, `1Min` |
| Real-time minute bars | Yes | Yes; updated bars handle late trades |
| Tick trades | Historical REST/files, live WebSocket | Historical REST, live WebSocket |
| Quotes / NBBO | Historical and live NBBO | Consolidated SIP bid/ask quotes; not depth |
| Consolidated coverage | US consolidated trades/quotes | CTA and UTP, all US exchanges; NOT free IEX |
| Pre-/post-market | Included in stocks coverage | Minute stream explicitly includes both |
| History | Stocks archive starts 2003-09-10, subject to ticker/listing and entitlement | Since 2016; cannot supply 2008 |
| REST / live API | REST + WebSocket + flat files | REST + WebSocket |
| Rate limit | Paid pricing advertises unlimited API calls; not unlimited network throughput/SLA | 10,000 historical requests/min; unlimited stream symbols on paid plan |
| Corporate actions | Splits/dividends/reference endpoints | Bar adjustments: split/dividend/spinoff/all or raw |
| Symbol changes | Point-in-time tickers; ticker-events currently documents only `ticker_change` | Historical bars `asof` mapping across ticker changes |
| Delisted securities | Vendor states historical delisted data retained; per-symbol QA still needed | Full delisted-universe completeness not established by reviewed docs |

Prices and plan limits: [Massive pricing](https://massive.com/pricing?product=stocks),
[Alpaca market-data plans](https://docs.alpaca.markets/us/docs/about-market-data-api).
These are advertised tiers, not a quote for any additional licensing rights.

Historical availability: [Massive archive](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have),
[Massive stocks coverage](https://www.massive.com/stocks).
Exact dates per security, corrections, holidays, gaps and symbol transitions
require subsequent sample validation; product marketing does not prove them.

API identities: [Massive historical NBBO](https://www.massive.com/docs/rest/stocks/trades-quotes/quotes),
[Alpaca bars and adjustments](https://docs.alpaca.markets/us/reference/stockbars),
[Alpaca historical quotes](https://docs.alpaca.markets/us/reference/stockquotes-1),
[Alpaca trades](https://docs.alpaca.markets/us/reference/stocktradesingle-1),
[Alpaca live channels](https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data).
Extended-hours minute bars do not imply overnight consolidated SIP coverage;
Alpaca lists BOATS/overnight as distinct feeds. Do not silently splice them.

[Massive ticker-events](https://massive.com/docs/rest/stocks/corporate-actions/ticker-events)
currently names `ticker_change` only. Do not promise merger/delisting event
normalization merely from a broader reference-data marketing description.

## Licensing and local research storage

| Question | Massive | Alpaca |
|---|---|---|
| Non-professional eligibility | Personal status must satisfy vendor/exchange definitions; operator must attest | Account/subscriber classification and agreements must be confirmed by operator |
| Separate exchange agreements | UTP and NYSE subscriber terms incorporated; signing is separate from payment | Nasdaq OMX / market-data-display agreements apply where relevant |
| Redistribution | Individual tier is not permission to share raw data or derived works with third parties | No redistribution right established by reviewed public plan documentation |
| Local storage | Flat-file downloads exist, but do not establish perpetual retention rights | Historical endpoints exist; local archive/retention permission not established here |
| Non-display/automated research | Terms require appropriate license for non-display use and derived investment strategies | Confirm precise research/automated-use entitlement in writing |
| After cancellation | Published terms require stopping use and deleting held market data | Retention/deletion obligations need written confirmation |

Sources: [Massive market-data terms](https://massive.com/legal/market-data-terms-of-service),
[Massive agreement/account guidance](https://massive.com/knowledge-base/categories/account),
[Massive downloadable datasets](https://massive.com/docs/flat-files/stocks/overview),
[Alpaca terms linked by its documentation](https://s3.amazonaws.com/files.alpaca.markets/disclosures/library/TermsAndConditions.pdf).
This is an implementation gate, not legal advice. Do not put licensed raw data
or derived restricted datasets in GitHub, model prompts or shared review files.

Later operator action: ask both vendors to confirm personal, non-display local
research, raw/derived retention including cancellation, backups, and any exchange
fees/agreements. Then approve a specific entitlement and price. A technical
recommendation would still not authorize a purchase.

## What a licensed trades + quotes feed could unlock

These are future research capabilities, not implemented signals:

| Capability | Required evidence | Both candidate feeds technically support inputs? |
|---|---|---|
| VWAP | Eligible trades/volume, session definition and correction handling | Yes |
| Opening range | Timestamped minute bars or trades and session calendar | Yes |
| Time-of-day RVOL | Consistent historical intraday volume windows | Yes; Alpaca starts 2016 |
| Bid/ask spread | Synchronized valid bid/ask quotes | Yes |
| Trade signing | Trade price relative to preceding quote, clock/order safeguards | Yes, inferred classification only |
| Aggressive-buy/sell volume proxies | Signed trade sizes; ambiguous/crossed/late observations excluded | Yes, proxies NOT observed trader intent |
| Depth imbalance / queues | Multiple book levels / order events from specified venues | No, not from SIP top-of-book alone |

`TICK_TRADES_QUOTES_SUFFICIENT_FOR_FIRST_FIRM_TRIAL = YES`

`LEVEL_2_REQUIRED_FOR_FIRST_FIRM_TRIAL = NO`

No first-trial hypothesis currently requires queue position or depth imbalance.
SIP trades and quotes supply the proposed first-stage inputs; minute bars alone
cannot establish signed flow. Signing remains uncertain, not ground truth.
Full depth can add depth-at-price, imbalance and queue/book dynamics, but needs
venue-specific coverage and synchronization. Databento's
[MBO schema](https://databento.com/docs/schemas-and-data-formats/mbo) is relevant
only if a later concrete depth hypothesis justifies it. No depth subscription
or Databento price quote is needed for this checkpoint.
