# Trial 14: registered_momentum_126_200_top1 v1 — NOT_PROVEN

Recipe sha256 `e0f092593039cdf41a5d41597d7d70a70973ce0e93b9a7362381b5896827d268`. Dataset `bars.csv` sha256 `57f6fab28109eafb8f4525f253a07c5cf2453ecc2d27c4d81a638e5cbadbcdcc`, 2005-01-03 → 2026-09-29 (21.74 years), label **CERTIFIED_ETF_HISTORY**, split_only_price_return_no_dividends.

Window 2006-01-04 → 2026-09-29, $25,000 start.

| | Strategy | VTI |
|---|---|---|
| CAGR after all tax | 0.39% | 8.31% |
| Volatility | 3.7% | 19.8% |
| Sharpe (rf 0) | 0.123 | 0.535 |
| Max drawdown | 10.6% | 56.6% |
| Trades | 170 | 1 |

Excess vs VTI (pre-tax): -8.24%/yr, 90% interval -14.21% to -2.22%; information ratio -0.425.

Walk-forward: 249 monthly out-of-sample folds, 36% beat VTI.

Deflated Sharpe: probability 0.0001 after counting 14 trials.

**NOT_PROVEN** — certified dataset AND 90% interval of excess > 0 AND deflated Sharpe probability >= 0.95 AND after-tax CAGR above VTI. never automatic: a PASS only allows a shadow (Adventure) run; Official needs a signed amendment.

| Year | Excess log growth vs VTI |
|---|---|
| 2006 | -9.34% |
| 2007 | +0.95% |
| 2008 | +48.82% |
| 2009 | -20.54% |
| 2010 | -16.04% |
| 2011 | +2.13% |
| 2012 | -13.07% |
| 2013 | -26.92% |
| 2014 | -9.99% |
| 2015 | +1.62% |
| 2016 | -10.04% |
| 2017 | -17.41% |
| 2018 | +7.27% |
| 2019 | -24.84% |
| 2020 | -17.36% |
| 2021 | -21.55% |
| 2022 | +23.34% |
| 2023 | -21.57% |
| 2024 | -20.02% |
| 2025 | -14.57% |
| 2026 | -11.27% |
