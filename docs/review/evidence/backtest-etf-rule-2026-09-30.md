# ETF rule backtest

## Verdict

- Registered rule (as sized live): 0.4%/yr after tax vs VTI 8.3%/yr; max drawdown 11% vs 57%; invested on 28% of days.
- Signal alone (100% in the top pick): 1.7%/yr after tax, Sharpe 0.202 vs VTI 0.535; 90% interval for annual excess over VTI (pre-tax): -14.8% to +1.4%.
- The registered 10% drawdown breaker latched on 2010-07-12 and never reset, so the book stopped buying for good. Without breakers the same sizing made 4.3%/yr (Sharpe 0.529, max drawdown 15%): lower risk, lower return, no edge.
- NOT PROVEN: the rule does not clearly beat buy-and-hold VTI after costs and tax. Do not add AI, options or capital on the strength of this rule.

Data: 2005-01-03 → 2026-09-29 (5468 sessions), Robinhood read gateway via research.history_backfill (split-adjusted, price only, no dividends). ETF list is today's reviewed list; funds that closed are absent.

## Results ($500.0 start)

| Strategy | CAGR after all tax | CAGR pre-liquidation | Sharpe | Max DD | Trades | Invested days | Tax | Costs |
|---|---|---|---|---|---|---|---|---|
| registered_rule | 0.39% | 0.39% | 0.123 | 10.5% | 140 | 28% | $13.28 | $4.20 |
| registered_rule_no_guards | 4.34% | 4.47% | 0.529 | 15.0% | 656 | 99% | $122.73 | $24.44 |
| registered_rule_v142_8etfs | 0.29% | 0.29% | 0.103 | 11.8% | 188 | 33% | $21.50 | $4.64 |
| signal_full_invest_top1 | 1.74% | 2.02% | 0.202 | 61.6% | 955 | 90% | $72.91 | $421.31 |
| signal_full_invest_top3 | 3.27% | 3.53% | 0.284 | 40.2% | 2242 | 99% | $92.29 | $317.30 |
| vti_buy_hold | 8.31% | 9.01% | 0.535 | 56.6% | 1 | 100% | $0.00 | $0.60 |
| spy_buy_hold | 8.34% | 9.04% | 0.545 | 56.5% | 1 | 100% | $0.00 | $0.55 |
| equal_weight_spdr_sectors | 6.71% | 6.91% | 0.457 | 55.2% | 0 | 100% | $180.96 | $7.03 |

## Excess over VTI (block bootstrap, pre-tax)

| Strategy | Annual excess | 90% interval | Draws > 0 |
|---|---|---|---|
| registered_rule | -8.24% | -14.22% to -2.22% | 1% |
| signal_full_invest_top1 | -6.65% | -14.83% to +1.37% | 9% |
| signal_full_invest_top3 | -5.18% | -10.91% to +0.52% | 7% |
| equal_weight_spdr_sectors | -1.94% | -3.34% to -0.42% | 2% |

## Regimes (total return in window)

| Window | equal_weight_spdr_sectors | registered_rule | signal_full_invest_top1 | vti_buy_hold |
|---|---|---|---|---|
| GFC 2008-09 → 2009-03 | -47.7% | -0.6% | -9.9% | -47.6% |
| Q4 2018 selloff | -17.6% | +0.0% | -15.9% | -20.1% |
| COVID crash 2020 | -36.6% | +0.0% | -20.1% | -35.0% |
| COVID rebound 2020 | +48.4% | +0.0% | +13.6% | +58.9% |
| Rate shock 2022 | -14.2% | +0.0% | +2.0% | -21.3% |
| Mega-cap grind 2023-25 | +41.0% | +0.0% | +33.8% | +76.1% |

## Parameter sensitivity (signal alone, full invest)

| Setting | CAGR after tax | Sharpe | Max DD | Trades |
|---|---|---|---|---|
| mom63_ma100 | 0.18% | 0.116 | 63.8% | 1183 |
| mom63_ma150 | 1.18% | 0.161 | 57.0% | 1183 |
| mom63_ma200 | 1.32% | 0.168 | 52.9% | 1177 |
| mom126_ma100 | -0.63% | 0.083 | 70.6% | 1069 |
| mom126_ma150 | 1.46% | 0.185 | 64.3% | 965 |
| mom126_ma200 | 1.74% | 0.202 | 61.6% | 955 |
| mom252_ma100 | 4.16% | 0.295 | 52.7% | 903 |
| mom252_ma150 | 8.26% | 0.494 | 48.0% | 797 |
| mom252_ma200 | 8.10% | 0.482 | 46.9% | 721 |

## Calendar years

| Year | registered_rule | signal_full_invest_top1 | vti_buy_hold |
|---|---|---|---|
| 2006 | +1.3% | +5.9% | +11.2% |
| 2007 | +4.5% | +0.0% | +3.5% |
| 2008 | +0.4% | +11.4% | -38.4% |
| 2009 | +2.6% | -0.9% | +26.0% |
| 2010 | -1.9% | -6.5% | +15.2% |
| 2011 | +1.2% | +9.5% | -1.0% |
| 2012 | +0.0% | -26.7% | +14.0% |
| 2013 | +0.0% | +19.4% | +30.9% |
| 2014 | +0.0% | -4.5% | +10.5% |
| 2015 | +0.0% | -13.1% | -1.6% |
| 2016 | +0.0% | +19.2% | +10.6% |
| 2017 | +0.0% | +21.1% | +19.0% |
| 2018 | +0.0% | -16.0% | -7.0% |
| 2019 | +0.0% | -25.9% | +28.2% |
| 2020 | +0.0% | -8.4% | +19.0% |
| 2021 | +0.0% | +6.8% | +24.0% |
| 2022 | +0.0% | +4.0% | -20.8% |
| 2023 | +0.0% | -7.1% | +24.1% |
| 2024 | +0.0% | +10.9% | +22.2% |
| 2025 | +0.0% | +25.3% | +15.7% |
| 2026 | +0.0% | +46.4% | +11.9% |

## Assumptions

- Execution: next session open after the signal close; buys pay half-spread + 0.1% slippage; sells at the bid.
- Tax: 35% short-term / 15% long-term on net realized gains yearly, loss carry-forward, liquidation tax at the end for every line.
- Prices are split-adjusted without dividends for every line, so absolute returns are understated by roughly 1.5–2%/yr for equity funds and more for TLT/XLU/XLRE.
- AI: not included; the ETF rule uses no AI. $0.40/day would be ~$100/yr, i.e. 20%/yr of a $500 book.
- Equal-weight sectors rebalance monthly and pay the same costs and tax.
