# Trial 17: sector_top3_12_1_ma10_spdr9 v1 — NOT_PROVEN

Recipe sha256 `3d04a7e36ead4b5eb9e6b116669ab857774d14db86462a6721330b5b07089420`. Dataset `bars.csv` sha256 `57f6fab28109eafb8f4525f253a07c5cf2453ecc2d27c4d81a638e5cbadbcdcc`, 2005-01-03 → 2026-09-29 (21.74 years), label **CERTIFIED_ETF_HISTORY**, split_only_price_return_no_dividends.

Window 2006-01-04 → 2026-09-29, $25,000 start.

| | Strategy | VTI |
|---|---|---|
| CAGR after all tax | 5.07% | 8.31% |
| Volatility | 14.8% | 19.8% |
| Sharpe (rf 0) | 0.418 | 0.535 |
| Max drawdown | 24.5% | 56.6% |
| Trades | 567 | 1 |

Excess vs VTI (pre-tax): -3.55%/yr, 90% interval -8.07% to +0.94%; information ratio -0.242.

Walk-forward: 249 monthly out-of-sample folds, 46% beat VTI.

Deflated Sharpe: probability 0.0415 after counting 17 trials.

**NOT_PROVEN** — certified dataset AND 90% interval of excess > 0 AND deflated Sharpe probability >= 0.95 AND after-tax CAGR above VTI. never automatic: a PASS only allows a shadow (Adventure) run; Official needs a signed amendment.

| Year | Excess log growth vs VTI |
|---|---|
| 2006 | -11.69% |
| 2007 | +3.73% |
| 2008 | +36.50% |
| 2009 | -4.81% |
| 2010 | -16.33% |
| 2011 | +0.60% |
| 2012 | -9.29% |
| 2013 | +1.93% |
| 2014 | -5.59% |
| 2015 | -5.45% |
| 2016 | -8.53% |
| 2017 | -4.32% |
| 2018 | +3.63% |
| 2019 | -15.76% |
| 2020 | -4.94% |
| 2021 | -12.73% |
| 2022 | +11.93% |
| 2023 | -15.65% |
| 2024 | -3.14% |
| 2025 | -6.82% |
| 2026 | -6.63% |

| Period (pre-tax CAGR) | strategy | vti |
|---|---|---|
| first_half | 4.08% | 5.17% |
| second_half | 6.35% | 12.83% |
