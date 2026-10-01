# Research harness results (research only; never Official)

Branch `claude/research-harness`. Recipes: `research/recipes/*.yaml` (hashed; any edit is a new trial).
Runner: `python -m research.harness run --recipe … --bars … --log <own dir>/trials.db --out … --md …`.
Dataset: `bars.csv` sha256 `57f6fab28109eafb8f4525f253a07c5cf2453ecc2d27c4d81a638e5cbadbcdcc` (Robinhood, split-adjusted,
no dividends, 17 ETFs, 2005-01-03 → 2026-09-29; SOXX from 2010, XLRE 2015, XLC 2018), label CERTIFIED_ETF_HISTORY.

| Trial | Recipe | Excess vs VTI /yr (pre-tax) | 90% interval | Deflated Sharpe prob. | Verdict |
|---|---|---|---|---|---|
| 1–13 | exploratory looks of 2026-09-30 (counted, not promotable) | — | — | — | — |
| 14 | registered_momentum_126_200_top1 | −8.2% | −14.2% to −2.2% | 0.0001 | NOT_PROVEN |
| 15 | dual_trend_vol_target_etf17 | −5.0% | −9.7% to −0.4% | 0.02 | NOT_PROVEN |
| 16 | gem_dual_momentum_vti_efa_agg (dataset `36ea39c9…`, VTI/EFA/AGG) | −4.75% | −9.1% to −0.7% | 0.024 | NOT_PROVEN |
| 17 | sector_top3_12_1_ma10_spdr9 (recipe `3d04a7e3…`, committed before the run) | −3.55% | −8.1% to +0.9% | 0.042 | NOT_PROVEN |

Dual trend ran at ~8.5% volatility vs VTI's 19.8%, so raw excess understates it; on a risk-adjusted basis it is still
behind (Sharpe 0.47 vs 0.54, information ratio −0.32). Max drawdown 17.8% vs 56.6%.

Not run, by instruction: any S&P 500 or stock recipe (refused by the harness until a point-in-time dataset exists).
Scaffolds only: `research/adventure.py` (separate Adventure book), `research/postmortem.py` (labels agents propose, operator decides).
Draft (unsigned): `docs/superpowers/plans/preregistration-amendment-v1.6.1-breaker-reset.draft.yaml`.

Trial 16 (GEM, the single Path B trial agreed 2026-09-30): after tax 3.95%/yr vs VTI 8.31% and vs a never-traded
60/40 VTI/EFA 6.62%. Pre-publication (2006–2014) 4.85% vs VTI 5.95%; post-publication (2015–2026) 3.25% vs 11.38%.
45 switches; beat VTI in 22% of months. Price-only bias against it ~1%/yr, far smaller than the shortfall, so
NOT_PROVEN rather than INCONCLUSIVE. Per the operator's rule, the Path B hunt stops here.

Trial 17 (sector top-3, 12-1, 10-month MA; aim and stopping rule inside the hashed recipe): after tax 5.07%/yr vs
VTI 8.31%; Sharpe 0.42 vs 0.54; max drawdown 24.5% vs 56.6%; 2006–2015 4.08% vs 5.17%, 2016–2026 6.35% vs 12.83%
(pre-tax); beat VTI in 46% of months; all 3 slots filled 77% of months. The interval crosses zero, but the
deflated Sharpe (0.04) and after-tax CAGR both fail, so NOT_PROVEN.

**Stopping rule in force (from the recipe): no more research trials until 2026-10-31.**
