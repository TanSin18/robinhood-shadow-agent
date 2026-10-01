# Trial 15: dual_trend_vol_target_etf17 v1 — NOT_PROVEN

Recipe sha256 `54b30010f1b8a8b92ce3d8c09eb45924f5e3d6440e3a3e8c65fdabdedbeefe22`. Dataset `bars.csv` sha256 `57f6fab28109eafb8f4525f253a07c5cf2453ecc2d27c4d81a638e5cbadbcdcc`, 2005-01-03 → 2026-09-29 (21.74 years), label **CERTIFIED_ETF_HISTORY**, split_only_price_return_no_dividends.

Window 2006-01-04 → 2026-09-29, $25,000 start.

| | Strategy | VTI |
|---|---|---|
| CAGR after all tax | 3.65% | 8.31% |
| Volatility | 8.5% | 19.8% |
| Sharpe (rf 0) | 0.471 | 0.535 |
| Max drawdown | 17.8% | 56.6% |
| Trades | 1680 | 1 |

Excess vs VTI (pre-tax): -5.00%/yr, 90% interval -9.66% to -0.43%; information ratio -0.321.

Walk-forward: 249 monthly out-of-sample folds, 40% beat VTI.

Deflated Sharpe: probability 0.0197 after counting 15 trials.

**NOT_PROVEN** — certified dataset AND 90% interval of excess > 0 AND deflated Sharpe probability >= 0.95 AND after-tax CAGR above VTI. never automatic: a PASS only allows a shadow (Adventure) run; Official needs a signed amendment.

| Year | Excess log growth vs VTI |
|---|---|
| 2006 | -4.24% |
| 2007 | +1.92% |
| 2008 | +40.56% |
| 2009 | -18.93% |
| 2010 | -12.28% |
| 2011 | +1.42% |
| 2012 | -10.47% |
| 2013 | -9.67% |
| 2014 | -1.77% |
| 2015 | -5.42% |
| 2016 | -5.08% |
| 2017 | -2.92% |
| 2018 | -2.12% |
| 2019 | -16.74% |
| 2020 | -15.15% |
| 2021 | -10.82% |
| 2022 | +13.85% |
| 2023 | -16.38% |
| 2024 | -11.41% |
| 2025 | -7.84% |
| 2026 | -9.89% |
