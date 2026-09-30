# Universe expansion: draft for operator review (UNSIGNED, NOT ACTIVE)

Status: draft. Nothing here changes behaviour until the operator signs an
amendment, a reviewed release ships the code, and the operator edits the local
config. Tomorrow's run (2026-10-01) uses the registered 14 tickers.

## Why only 14 today

- Registration v1.4.2 fixes the traded set in `config.risk.instrument_whitelist`:
  8 ETFs (SPY, QQQ, VTI, SOXX, XLE, XLU, GLD, TLT) and 6 stocks (AAPL, MSFT,
  NVDA, AMZN, GOOGL, META).
- `research/strategy_signals.ETF_UNIVERSE` limits momentum rotation to those
  8 ETFs. Mean reversion checks all 14.
- Option contracts are fetched only for whitelisted underlyings, and only calls
  on an underlying with a buy signal are considered.
- The v1.5 draft has broad universe rules (S&P 500 current constituents plus
  reviewed ETFs, filtered by liquidity). The signed v1.5.0 amendment
  deliberately left them off.

## Proposal: two steps

### Step 1 — sector ETFs (small; could ship in a reviewed after-close release)

Add the nine SPDR sector ETFs the registration already names for sector
benchmarks: **XLC, XLY, XLP, XLF, XLV, XLI, XLB, XLRE, XLK**. This takes the
universe to 23 tickers and the ETF momentum ranking to 17.

- Same rules as today: price above its 200-day average, positive 126-day
  momentum, top-1 ranking, $50M median dollar volume, spread within 0.3%.
- About 9 more quote and history reads per run, and more option chains.
- Needs:
  1. a signed amendment (v1.6.0) listing the tickers
  2. a code change to `ETF_UNIVERSE`, with tests
  3. the operator adding the tickers to `settings.local.yaml`
- Trade-off: changing config or code resets the readiness proof. The first
  scheduled run under the new set becomes the new baseline.

### Step 2 — broad equity screen (larger; needs its own design review)

Apply the v1.5 draft `universe:` rules to S&P 500 current constituents:
- price at least $5, at least 253 sessions of history, $50M median dollar
  volume, median spread at most 0.3%
- shortlist 30 names, verify 20 with live quotes, send up to 8 to AI research

Open questions:
- broker read budget and rate limits for about 500 symbols
- the survivorship-bias label, until Norgate historical membership is validated
- the AI token budget when 8 names go to research
- whether the options lane should follow the wider set

## Operator decision needed

- [ ] Step 1 now (target: next after-close release)
- [ ] Step 2 design first
- [ ] Keep 14 for Phase 0 proof, revisit after sign-off
