# Trial 16: gem_dual_momentum_vti_efa_agg v1 — NOT_PROVEN

Recipe sha256 `7f58dfe5734dcf76ba7e9daa2aa615aa0471aed546a46e7fd255a16e4d3e3737`. Dataset `bars.csv` sha256 `36ea39c94463b5d4a89a01b03001677404e8afee56349bdf0feff3fa7ddcfa6a`, 2005-01-03 → 2026-09-29 (21.74 years), label **CERTIFIED_ETF_HISTORY**, split_only_price_return_no_dividends.

Window 2006-01-04 → 2026-09-29, $25,000 start.

| | Strategy | VTI |
|---|---|---|
| CAGR after all tax | 3.95% | 8.31% |
| Volatility | 15.8% | 19.8% |
| Sharpe (rf 0) | 0.324 | 0.535 |
| Max drawdown | 40.9% | 56.6% |
| Trades | 91 | 1 |

Excess vs VTI (pre-tax): -4.75%/yr, 90% interval -9.06% to -0.68%; information ratio -0.332.

Walk-forward: 249 monthly out-of-sample folds, 22% beat VTI.

Deflated Sharpe: probability 0.024 after counting 16 trials.

**NOT_PROVEN** — certified dataset AND 90% interval of excess > 0 AND deflated Sharpe probability >= 0.95 AND after-tax CAGR above VTI. never automatic: a PASS only allows a shadow (Adventure) run; Official needs a signed amendment.

| Year | Excess log growth vs VTI |
|---|---|
| 2006 | +6.16% |
| 2007 | +3.50% |
| 2008 | +39.86% |
| 2009 | -18.68% |
| 2010 | -6.78% |
| 2011 | -14.29% |
| 2012 | -10.37% |
| 2013 | -8.82% |
| 2014 | +0.00% |
| 2015 | -10.13% |
| 2016 | -4.24% |
| 2017 | -6.32% |
| 2018 | +1.34% |
| 2019 | -22.46% |
| 2020 | -20.67% |
| 2021 | +0.00% |
| 2022 | +2.12% |
| 2023 | -13.60% |
| 2024 | +0.00% |
| 2025 | -9.56% |
| 2026 | -5.36% |

Time held: VTI 57%, EFA 22%, AGG 21%; 45 switches. Price-only bias estimate against the strategy: 0.96%/yr.

Secondary benchmark (buy_and_hold_60pct_VTI_40pct_EFA_no_rebalancing): 6.62%/yr after tax, Sharpe 0.45, max drawdown 59.2%. Strategy excess over it: -3.12%/yr (90% -7.39% to +1.01%).

| Period (pre-tax CAGR) | strategy | vti | vti60_efa40 |
|---|---|---|---|
| pre_publication | 4.85% | 5.95% | 3.84% |
| post_publication | 3.25% | 11.38% | 9.92% |
