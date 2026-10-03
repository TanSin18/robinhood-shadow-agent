# Checkpoint 6 feature catalog

Registry-linked calculation inventory, not a claim of live data availability.
Detailed conventions: [approved design](../superpowers/specs/2026-10-03-checkpoint6-research-features-design.md).

## Shared contract for every entry

- Known-at is no earlier than every contributing source, publication, acceptance
  and confirmation time. Historical session date never establishes availability.
- Missing required inputs, incompatible periods, insufficient history, zero
  denominators and invalid units produce null plus a specific reason, never zero.
- Decimal precision34; formula changes require a version bump; source/code hashes
  and exact observation references remain in each stored result.
- Current live feature availability: NOT YET VALIDATED. OHLCV/intraday unavailable;
  closes exist. SEC fields partial, Fed/PCE factual inputs exist, other macro
  sources remain unavailable. Registry presence alone never promotes capability.
- Every feature is descriptive only: no predictive value, trade recommendation,
  composite score, or implicit bullish/bearish interpretation.
- Close-only structure does not describe intraday extremes. Returns use provider
  price closes, not total return. Sector mappings are not historical GICS.
- Lookback0 means event-driven; listed positive minima do not bypass contiguous
  session rules, seed history or pivot confirmation. Exact missingness is per row.

## Inventory

### trend

#### `sma20`

- Version: `sma20_v1`; unit: `price`; lookback: 20; cadence: daily.
- Formula: mean(last 20 closes).
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma20_ratio`

- Version: `sma20_ratio_v1`; unit: `fraction`; lookback: 20; cadence: daily.
- Formula: C/SMA20.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma20_distance`

- Version: `sma20_distance_v1`; unit: `fraction`; lookback: 20; cadence: daily.
- Formula: C/SMA20-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma20_slope5`

- Version: `sma20_slope5_v1`; unit: `fraction`; lookback: 25; cadence: daily.
- Formula: SMA20(t)/SMA20(t-5)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma50`

- Version: `sma50_v1`; unit: `price`; lookback: 50; cadence: daily.
- Formula: mean(last 50 closes).
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma50_ratio`

- Version: `sma50_ratio_v1`; unit: `fraction`; lookback: 50; cadence: daily.
- Formula: C/SMA50.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma50_distance`

- Version: `sma50_distance_v1`; unit: `fraction`; lookback: 50; cadence: daily.
- Formula: C/SMA50-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma50_slope5`

- Version: `sma50_slope5_v1`; unit: `fraction`; lookback: 55; cadence: daily.
- Formula: SMA50(t)/SMA50(t-5)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma100`

- Version: `sma100_v1`; unit: `price`; lookback: 100; cadence: daily.
- Formula: mean(last 100 closes).
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma100_ratio`

- Version: `sma100_ratio_v1`; unit: `fraction`; lookback: 100; cadence: daily.
- Formula: C/SMA100.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma100_distance`

- Version: `sma100_distance_v1`; unit: `fraction`; lookback: 100; cadence: daily.
- Formula: C/SMA100-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma100_slope5`

- Version: `sma100_slope5_v1`; unit: `fraction`; lookback: 105; cadence: daily.
- Formula: SMA100(t)/SMA100(t-5)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma200`

- Version: `sma200_v1`; unit: `price`; lookback: 200; cadence: daily.
- Formula: mean(last 200 closes).
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma200_ratio`

- Version: `sma200_ratio_v1`; unit: `fraction`; lookback: 200; cadence: daily.
- Formula: C/SMA200.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma200_distance`

- Version: `sma200_distance_v1`; unit: `fraction`; lookback: 200; cadence: daily.
- Formula: C/SMA200-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma200_slope5`

- Version: `sma200_slope5_v1`; unit: `fraction`; lookback: 205; cadence: daily.
- Formula: SMA200(t)/SMA200(t-5)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sma_ordering`

- Version: `sma_ordering_v1`; unit: `ordering`; lookback: 200; cadence: daily.
- Formula: descending labels with equal groups.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### momentum

#### `return5`

- Version: `return5_v1`; unit: `fraction`; lookback: 6; cadence: daily.
- Formula: C(t)/C(t-5)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return10`

- Version: `return10_v1`; unit: `fraction`; lookback: 11; cadence: daily.
- Formula: C(t)/C(t-10)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return20`

- Version: `return20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: C(t)/C(t-20)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return63`

- Version: `return63_v1`; unit: `fraction`; lookback: 64; cadence: daily.
- Formula: C(t)/C(t-63)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return126`

- Version: `return126_v1`; unit: `fraction`; lookback: 127; cadence: daily.
- Formula: C(t)/C(t-126)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return252`

- Version: `return252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: C(t)/C(t-252)-1.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `momentum_acceleration20`

- Version: `momentum_acceleration20_v1`; unit: `fraction`; lookback: 41; cadence: daily.
- Formula: return20(t)-return20(t-20).
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return20_percentile252`

- Version: `return20_percentile252_v1`; unit: `percentile`; lookback: 272; cadence: daily.
- Formula: inclusive 252; midrank ties.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `rsi14_wilder`

- Version: `rsi14_wilder_v1`; unit: `index_0_100`; lookback: 15; cadence: daily.
- Formula: Wilder14; flat=50; recursive from first14 differences.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `ema12`

- Version: `ema12_v1`; unit: `price`; lookback: 12; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `ema26`

- Version: `ema26_v1`; unit: `price`; lookback: 26; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `macd_line`

- Version: `macd_line_v1`; unit: `price`; lookback: 26; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `macd_smoothing9`

- Version: `macd_smoothing9_v1`; unit: `price`; lookback: 34; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `macd_histogram`

- Version: `macd_histogram_v1`; unit: `price`; lookback: 34; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `macd_price_normalized`

- Version: `macd_price_normalized_v1`; unit: `fraction`; lookback: 26; cadence: daily.
- Formula: EMA SMA seed; alpha2/(n+1); MACD12-26; smoothing9; histogram difference; normalization/C.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### volatility

#### `realized_vol20`

- Version: `realized_vol20_v1`; unit: `annualized_fraction`; lookback: 21; cadence: daily.
- Formula: sample sd(20 log returns)*sqrt252.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `realized_vol63`

- Version: `realized_vol63_v1`; unit: `annualized_fraction`; lookback: 64; cadence: daily.
- Formula: sample sd(63 log returns)*sqrt252.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `realized_vol20_percentile252`

- Version: `realized_vol20_percentile252_v1`; unit: `percentile`; lookback: 272; cadence: daily.
- Formula: inclusive252; midrank ties.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `true_range`

- Version: `true_range_v1`; unit: `price`; lookback: 2; cadence: daily.
- Formula: TR=max(H-L,abs(H-priorC),abs(L-priorC)); Wilder14 ATR.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `atr14`

- Version: `atr14_v1`; unit: `price`; lookback: 15; cadence: daily.
- Formula: TR=max(H-L,abs(H-priorC),abs(L-priorC)); Wilder14 ATR.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `atr_price`

- Version: `atr_price_v1`; unit: `fraction`; lookback: 15; cadence: daily.
- Formula: TR=max(H-L,abs(H-priorC),abs(L-priorC)); Wilder14 ATR.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### support_resistance

#### `close_support_level`

- Version: `close_support_level_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_support_distance`

- Version: `close_support_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_support_pivot_count`

- Version: `close_support_pivot_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_support_age`

- Version: `close_support_age_v1`; unit: `sessions`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_prior_support_break_retest`

- Version: `close_prior_support_break_retest_v1`; unit: `state`; lookback: 7; cadence: daily.
- Formula: prior-session frozen confirmed level; strict cross; return within0.5% from crossed side within5sessions.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_resistance_level`

- Version: `close_resistance_level_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_resistance_distance`

- Version: `close_resistance_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_resistance_pivot_count`

- Version: `close_resistance_pivot_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_resistance_age`

- Version: `close_resistance_age_v1`; unit: `sessions`; lookback: 7; cadence: daily.
- Formula: trailing252 confirmed close pivots; bounded0.5% clusters; mean level; strict nearest side.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_prior_resistance_break_retest`

- Version: `close_prior_resistance_break_retest_v1`; unit: `state`; lookback: 7; cadence: daily.
- Formula: prior-session frozen confirmed level; strict cross; return within0.5% from crossed side within5sessions.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### breakout_structure

#### `close_distance_high20`

- Version: `close_distance_high20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_high20`

- Version: `close_new_high20_v1`; unit: `boolean`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high20_age`

- Version: `close_breakout_high20_age_v1`; unit: `sessions`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high20_retest`

- Version: `close_breakout_high20_retest_v1`; unit: `boolean`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_distance_low20`

- Version: `close_distance_low20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_low20`

- Version: `close_new_low20_v1`; unit: `boolean`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low20_age`

- Version: `close_breakout_low20_age_v1`; unit: `sessions`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low20_retest`

- Version: `close_breakout_low20_retest_v1`; unit: `boolean`; lookback: 21; cadence: daily.
- Formula: prior20 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_distance_high50`

- Version: `close_distance_high50_v1`; unit: `fraction`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_high50`

- Version: `close_new_high50_v1`; unit: `boolean`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high50_age`

- Version: `close_breakout_high50_age_v1`; unit: `sessions`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high50_retest`

- Version: `close_breakout_high50_retest_v1`; unit: `boolean`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_distance_low50`

- Version: `close_distance_low50_v1`; unit: `fraction`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_low50`

- Version: `close_new_low50_v1`; unit: `boolean`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low50_age`

- Version: `close_breakout_low50_age_v1`; unit: `sessions`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low50_retest`

- Version: `close_breakout_low50_retest_v1`; unit: `boolean`; lookback: 51; cadence: daily.
- Formula: prior50 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_distance_high252`

- Version: `close_distance_high252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_high252`

- Version: `close_new_high252_v1`; unit: `boolean`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high252_age`

- Version: `close_breakout_high252_age_v1`; unit: `sessions`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_high252_retest`

- Version: `close_breakout_high252_retest_v1`; unit: `boolean`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_distance_low252`

- Version: `close_distance_low252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_new_low252`

- Version: `close_new_low252_v1`; unit: `boolean`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low252_age`

- Version: `close_breakout_low252_age_v1`; unit: `sessions`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_breakout_low252_retest`

- Version: `close_breakout_low252_retest_v1`; unit: `boolean`; lookback: 253; cadence: daily.
- Formula: prior252 closes excluding current; strict cross, frozen breakout level, five-session retest.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### fibonacci

#### `close_fib_retracement_0.236`

- Version: `close_fib_retracement_0.236_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.236_distance`

- Version: `close_fib_retracement_0.236_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.236_atr_distance`

- Version: `close_fib_retracement_0.236_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.236_relation`

- Version: `close_fib_retracement_0.236_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.236_touch_count`

- Version: `close_fib_retracement_0.236_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.236_cross_count`

- Version: `close_fib_retracement_0.236_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382`

- Version: `close_fib_retracement_0.382_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382_distance`

- Version: `close_fib_retracement_0.382_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382_atr_distance`

- Version: `close_fib_retracement_0.382_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382_relation`

- Version: `close_fib_retracement_0.382_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382_touch_count`

- Version: `close_fib_retracement_0.382_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.382_cross_count`

- Version: `close_fib_retracement_0.382_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5`

- Version: `close_fib_retracement_0.5_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5_distance`

- Version: `close_fib_retracement_0.5_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5_atr_distance`

- Version: `close_fib_retracement_0.5_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5_relation`

- Version: `close_fib_retracement_0.5_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5_touch_count`

- Version: `close_fib_retracement_0.5_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.5_cross_count`

- Version: `close_fib_retracement_0.5_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618`

- Version: `close_fib_retracement_0.618_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618_distance`

- Version: `close_fib_retracement_0.618_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618_atr_distance`

- Version: `close_fib_retracement_0.618_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618_relation`

- Version: `close_fib_retracement_0.618_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618_touch_count`

- Version: `close_fib_retracement_0.618_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.618_cross_count`

- Version: `close_fib_retracement_0.618_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786`

- Version: `close_fib_retracement_0.786_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786_distance`

- Version: `close_fib_retracement_0.786_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786_atr_distance`

- Version: `close_fib_retracement_0.786_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786_relation`

- Version: `close_fib_retracement_0.786_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786_touch_count`

- Version: `close_fib_retracement_0.786_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_retracement_0.786_cross_count`

- Version: `close_fib_retracement_0.786_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272`

- Version: `close_fib_extension_1.272_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272_distance`

- Version: `close_fib_extension_1.272_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272_atr_distance`

- Version: `close_fib_extension_1.272_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272_relation`

- Version: `close_fib_extension_1.272_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272_touch_count`

- Version: `close_fib_extension_1.272_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.272_cross_count`

- Version: `close_fib_extension_1.272_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618`

- Version: `close_fib_extension_1.618_v1`; unit: `price`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618_distance`

- Version: `close_fib_extension_1.618_distance_v1`; unit: `fraction`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618_atr_distance`

- Version: `close_fib_extension_1.618_atr_distance_v1`; unit: `ATR`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: validated_atr14.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618_relation`

- Version: `close_fib_extension_1.618_relation_v1`; unit: `relation`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618_touch_count`

- Version: `close_fib_extension_1.618_touch_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_extension_1.618_cross_count`

- Version: `close_fib_extension_1.618_cross_count_v1`; unit: `count`; lookback: 7; cadence: daily.
- Formula: directed confirmed close leg A→B; retrace B-r(B-A); extend A+r(B-A); touches after confirmation within0.5%.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_nearest`

- Version: `close_fib_nearest_v1`; unit: `level`; lookback: 7; cadence: daily.
- Formula: latest3 completed close legs; bounded0.5% clusters; nearest fractional distance.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `close_fib_clusters`

- Version: `close_fib_clusters_v1`; unit: `levels`; lookback: 7; cadence: daily.
- Formula: latest3 completed close legs; bounded0.5% clusters; nearest fractional distance.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### candlestick_geometry

#### `body`

- Version: `body_v1`; unit: `price`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `range`

- Version: `range_v1`; unit: `price`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `upper_wick`

- Version: `upper_wick_v1`; unit: `price`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `lower_wick`

- Version: `lower_wick_v1`; unit: `price`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `body_fraction`

- Version: `body_fraction_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `upper_wick_fraction`

- Version: `upper_wick_fraction_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `lower_wick_fraction`

- Version: `lower_wick_fraction_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `clv`

- Version: `clv_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `open_close_return`

- Version: `open_close_return_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `gap_close`

- Version: `gap_close_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `gap_high`

- Version: `gap_high_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `gap_low`

- Version: `gap_low_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: validated OHLC raw geometry; zero range ratios null.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### volume

#### `volume`

- Version: `volume_v1`; unit: `shares`; lookback: 1; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `volume_mean20`

- Version: `volume_mean20_v1`; unit: `shares`; lookback: 21; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `volume_mean63`

- Version: `volume_mean63_v1`; unit: `shares`; lookback: 64; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `rvol20`

- Version: `rvol20_v1`; unit: `ratio`; lookback: 21; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `volume_change`

- Version: `volume_change_v1`; unit: `fraction`; lookback: 2; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `volume_percentile252`

- Version: `volume_percentile252_v1`; unit: `percentile`; lookback: 252; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `return_rvol`

- Version: `return_rvol_v1`; unit: `interaction`; lookback: 21; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `signed_return_volume_percentile`

- Version: `signed_return_volume_percentile_v1`; unit: `interaction`; lookback: 252; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `range_expansion_rvol`

- Version: `range_expansion_rvol_v1`; unit: `interaction`; lookback: 21; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `breakout_distance_rvol`

- Version: `breakout_distance_rvol_v1`; unit: `interaction`; lookback: 21; cadence: daily.
- Formula: prior20/63 means; inclusive252 midrank; ratios/limited products.
- Required inputs: validated_daily_ohlcv. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### sector

#### `excess_vti_price_return5`

- Version: `excess_vti_price_return5_v1`; unit: `fraction`; lookback: 6; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return5`

- Version: `sector_excess_price_return5_v1`; unit: `fraction`; lookback: 6; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return5`

- Version: `sector_etf_price_return5_v1`; unit: `fraction`; lookback: 6; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `excess_vti_price_return10`

- Version: `excess_vti_price_return10_v1`; unit: `fraction`; lookback: 11; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return10`

- Version: `sector_excess_price_return10_v1`; unit: `fraction`; lookback: 11; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return10`

- Version: `sector_etf_price_return10_v1`; unit: `fraction`; lookback: 11; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `excess_vti_price_return20`

- Version: `excess_vti_price_return20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return20`

- Version: `sector_excess_price_return20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return20`

- Version: `sector_etf_price_return20_v1`; unit: `fraction`; lookback: 21; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `excess_vti_price_return63`

- Version: `excess_vti_price_return63_v1`; unit: `fraction`; lookback: 64; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return63`

- Version: `sector_excess_price_return63_v1`; unit: `fraction`; lookback: 64; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return63`

- Version: `sector_etf_price_return63_v1`; unit: `fraction`; lookback: 64; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `excess_vti_price_return126`

- Version: `excess_vti_price_return126_v1`; unit: `fraction`; lookback: 127; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return126`

- Version: `sector_excess_price_return126_v1`; unit: `fraction`; lookback: 127; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return126`

- Version: `sector_etf_price_return126_v1`; unit: `fraction`; lookback: 127; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `excess_vti_price_return252`

- Version: `excess_vti_price_return252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_excess_price_return252`

- Version: `sector_excess_price_return252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_etf_price_return252`

- Version: `sector_etf_price_return252_v1`; unit: `fraction`; lookback: 253; cadence: daily.
- Formula: aligned same-basis simple price returns; difference for excess.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_vol20`

- Version: `sector_vol20_v1`; unit: `annualized_fraction`; lookback: 51; cadence: daily.
- Formula: effective-dated mapping; fixed observed membership; no historical imputation.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_leadership_rank20`

- Version: `sector_leadership_rank20_v1`; unit: `rank`; lookback: 51; cadence: daily.
- Formula: effective-dated mapping; fixed observed membership; no historical imputation.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_leadership_change5`

- Version: `sector_leadership_change5_v1`; unit: `rank_change`; lookback: 51; cadence: daily.
- Formula: effective-dated mapping; fixed observed membership; no historical imputation.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_breadth`

- Version: `sector_breadth_v1`; unit: `fraction`; lookback: 51; cadence: daily.
- Formula: effective-dated mapping; fixed observed membership; no historical imputation.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sector_sma50_participation`

- Version: `sector_sma50_participation_v1`; unit: `fraction`; lookback: 51; cadence: daily.
- Formula: effective-dated mapping; fixed observed membership; no historical imputation.
- Required inputs: close. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### fundamentals

#### `revenue_yoy`

- Version: `revenue_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `operating_income_yoy`

- Version: `operating_income_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `net_income_yoy`

- Version: `net_income_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `eps_diluted_yoy`

- Version: `eps_diluted_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `operating_cash_flow_yoy`

- Version: `operating_cash_flow_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `diluted_shares_weighted_average_yoy`

- Version: `diluted_shares_weighted_average_yoy_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: (current-prior)/abs(prior), equivalent fiscal duration and quarter.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `revenue_qoq`

- Version: `revenue_qoq_v1`; unit: `fraction`; lookback: 0; cadence: event.
- Formula: standalone3M periods only; no YTD subtraction.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `operating_margin`

- Version: `operating_margin_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `net_margin`

- Version: `net_margin_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `gross_margin`

- Version: `gross_margin_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `ocf_net_income`

- Version: `ocf_net_income_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `ocf_margin`

- Version: `ocf_margin_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `cash_revenue`

- Version: `cash_revenue_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `debt_revenue`

- Version: `debt_revenue_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `debt_ocf`

- Version: `debt_ocf_v1`; unit: `ratio`; lookback: 0; cadence: event.
- Formula: compatible units, exact duration match; balance instant equals duration end.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `dilution_trend`

- Version: `dilution_trend_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: direction of comparable weighted-average diluted-share YoY change.
- Required inputs: confirmed_sec_normalized_facts. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### earnings_events

#### `days_since_10q`

- Version: `days_since_10q_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: calendar days since accepted filing.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `latest_filing_is_10q`

- Version: `latest_filing_is_10q_v1`; unit: `boolean`; lookback: 0; cadence: event.
- Formula: latest eligible accepted filing form.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `days_since_10k`

- Version: `days_since_10k_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: calendar days since accepted filing.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `latest_filing_is_10k`

- Version: `latest_filing_is_10k_v1`; unit: `boolean`; lookback: 0; cadence: event.
- Formula: latest eligible accepted filing form.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `days_since_8k`

- Version: `days_since_8k_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: calendar days since accepted filing.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `latest_filing_is_8k`

- Version: `latest_filing_is_8k_v1`; unit: `boolean`; lookback: 0; cadence: event.
- Formula: latest eligible accepted filing form.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `filing_count30`

- Version: `filing_count30_v1`; unit: `count`; lookback: 0; cadence: event.
- Formula: distinct accessions, amendments distinct, accepted in trailing calendar days.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `filing_count90`

- Version: `filing_count90_v1`; unit: `count`; lookback: 0; cadence: event.
- Formula: distinct accessions, amendments distinct, accepted in trailing calendar days.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sessions_since_earnings`

- Version: `sessions_since_earnings_v1`; unit: `sessions`; lookback: 0; cadence: event.
- Formula: authoritative factual event timing; no filing-time substitution.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `sessions_until_earnings`

- Version: `sessions_until_earnings_v1`; unit: `sessions`; lookback: 0; cadence: event.
- Formula: authoritative factual event timing; no filing-time substitution.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `earnings_timing`

- Version: `earnings_timing_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: authoritative factual event timing; no filing-time substitution.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `earnings_event_age`

- Version: `earnings_event_age_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: authoritative factual event timing; no filing-time substitution.
- Required inputs: validated_filing_or_earnings_event. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### macro_context

#### `fed_target_lower`

- Version: `fed_target_lower_v1`; unit: `percent`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_target_upper`

- Version: `fed_target_upper_v1`; unit: `percent`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_target_midpoint`

- Version: `fed_target_midpoint_v1`; unit: `percent`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_latest_change_bps`

- Version: `fed_latest_change_bps_v1`; unit: `basis_points`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `days_since_fomc`

- Version: `days_since_fomc_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_change_last3`

- Version: `fed_change_last3_v1`; unit: `basis_points`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_hikes_last3`

- Version: `fed_hikes_last3_v1`; unit: `count`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_cuts_last3`

- Version: `fed_cuts_last3_v1`; unit: `count`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `fed_holds_last3`

- Version: `fed_holds_last3_v1`; unit: `count`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `pce_headline_mom_sa`

- Version: `pce_headline_mom_sa_v1`; unit: `percent_change_mom_sa`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `pce_core_mom_sa`

- Version: `pce_core_mom_sa_v1`; unit: `percent_change_mom_sa`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `days_since_pce`

- Version: `days_since_pce_v1`; unit: `days`; lookback: 0; cadence: event.
- Formula: eligible original-source facts; point-in-time revisions; distinct Fed meeting periods.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `cpi_feature_family`

- Version: `cpi_feature_family_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: no validated input; never substitute a proxy.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `labor_feature_family`

- Version: `labor_feature_family_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: no validated input; never substitute a proxy.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `treasury_yield_feature_family`

- Version: `treasury_yield_feature_family_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: no validated input; never substitute a proxy.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

#### `market_volatility_feature_family`

- Version: `market_volatility_feature_family_v1`; unit: `state`; lookback: 0; cadence: event.
- Formula: no validated input; never substitute a proxy.
- Required inputs: validated_fed_or_pce. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; no live availability asserted until validated generation.

### intraday_future

#### `vwap`

- Version: `vwap_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `vwap_distance`

- Version: `vwap_distance_v1`; unit: `fraction`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `opening_range_high`

- Version: `opening_range_high_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `opening_range_low`

- Version: `opening_range_low_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `opening_range_breakout`

- Version: `opening_range_breakout_v1`; unit: `fraction`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `time_of_day_rvol`

- Version: `time_of_day_rvol_v1`; unit: `ratio`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `intraday_range`

- Version: `intraday_range_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `intraday_atr`

- Version: `intraday_atr_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `nbbo_spread`

- Version: `nbbo_spread_v1`; unit: `price`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `quote_imbalance`

- Version: `quote_imbalance_v1`; unit: `fraction`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `signed_volume`

- Version: `signed_volume_v1`; unit: `shares`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `aggressive_buy_proxy`

- Version: `aggressive_buy_proxy_v1`; unit: `shares`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.

#### `aggressive_sell_proxy`

- Version: `aggressive_sell_proxy_v1`; unit: `shares`; lookback: 0; cadence: intraday.
- Formula: registry only; licensed time-stamped trades/quotes/bars required.
- Required inputs: validated_intraday_trades_quotes_bars. Optional: none.
- Availability/missingness/timing/interpretation: shared contract above; UNAVAILABLE, registry only, no generated input data.
