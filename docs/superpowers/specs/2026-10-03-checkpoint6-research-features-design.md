# Checkpoint 6 — deterministic research feature layer

Status: detailed design for review. Architecture approved by the operator on
2026-10-03 in chat; detailed conventions below are proposed, not implemented.
Starting point: `85f6597eb47adb9a795f7304d99ac22ccea8c3e7`, Checkpoint 5 closed.
Development branch: `codex/checkpoint6-features`. No runtime activation implied.

## Purpose and boundaries

Answer what could objectively be measured and known at a time, not what to buy
or whether a feature predicts returns. No LLM, strategy, score, ranker, fitting,
threshold optimization, trial, orders, fills, sizing, scheduler or provider
activation. Read only existing validated research inputs. Manual generation
writes only the isolated Firm Lab DB. Dashboard reads with SQLite `mode=ro`.

Control A remains Release N with fingerprint
`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
No daily runner restart; Official Lane B stays PAUSED; real execution DISABLED;
BUILD_OBSERVE; no experiment; October stop not superseded. Codex maintenance
remains PREPARED_AND_PROVEN_NOT_INSTALLED. Frozen Treasury methodology and
benchmark-only distribution boundaries are unchanged. Checkpoint 7 is excluded.

## Observed inputs, not promises

Preflight on 2026-10-03 found 8,694 closes, 23 instruments, 378 sessions each
from 2025-03-31 to 2026-09-30. No validated OHLC/volume history or intraday bars.
The close history was captured later; historical session dates do not establish
historical availability. SEC normalized facts must have `CONFIRMED` filing
verification and resolved fields; never test that enum against boolean true.
Fed and PCE are available; CPI, labor, Treasury yields and market volatility
are unavailable. Those facts are rechecked at execution, not assumed permanent.

Library completeness and live feature coverage are separate. ATR, candles and
volume may be implemented and fixture-tested while every live row is unavailable.
Do not promote aggregate capabilities merely because functions exist.

## Architecture and interfaces

Keep legacy `firm_lab/features.py` and its `baseline-v1` rows unchanged.
Create package `firm_lab/research_features/` with:

| Module | Responsibility |
|---|---|
| `types.py` | Immutable input, definition, result and receipt contracts |
| `registry.py` | Fixed inventory, parameters, versions and dependency requirements |
| `inputs.py` | Read-only source adapters and point-in-time selection |
| `calendar.py` | XNYS session/close resolution using pinned exchange-calendars |
| `store.py` | Isolated additive schema, append-only results and provenance |
| `technical.py` | SMA, returns, RSI, EMA/MACD, volatility |
| `structure.py` | Confirmed close pivots, support/resistance, break/retest |
| `fibonacci.py` | Directed levels, immutable anchors and mechanical clusters |
| `ohlcv.py` | ATR, candle geometry, volume and limited interactions |
| `sector.py` | Versioned effective-dated mapping and relative descriptors |
| `fundamental.py` | Compatible-period SEC ratios and growth |
| `events.py` | Earnings and filing descriptors |
| `macro.py` | Fed and supported PCE descriptors only |
| `engine.py` | Pure dependency evaluation, deterministic ordering |
| `cli.py` | Explicit manual generation and coverage receipts |
| `view.py` | Read-only stored-result projection; no generator import |

UI: new `agents/desk/feature_explorer.py`, integrate existing
`agents/desk/firm_lab_page.py`; reuse local assets and existing CSP. No changes
to operational controls, broker, execution, preregistration or trading services.

Core API contracts (all timestamp strings canonical UTC with offset):

```python
@dataclass(frozen=True)
class SourceRef:
    table: str
    row_id: str
    content_hash: str
    known_at: str

@dataclass(frozen=True)
class Request:
    instrument: str
    as_of_session: str
    knowledge_cutoff: str

@dataclass(frozen=True)
class FeatureResult:
    instrument: str
    family: str
    name: str
    value: str | bool | dict | None
    unit: str
    as_of_session: str
    known_at: str | None
    availability: str
    missing_reason: str | None
    refs: tuple[SourceRef, ...]
    feature_version: str
    calculation_hash: str
    audit: dict
```

Decimal numeric values serialize as decimal strings, never NaN/Infinity.
Use Decimal local context precision 34, ROUND_HALF_EVEN, including ln/sqrt;
do not change global precision. Hash canonical JSON, formulas/parameters and
source bytes, not path names or modification times. Schema records value type.

## Storage and temporal contract

New tables: `research_feature_definitions`, `research_feature_runs`,
`research_feature_results`, `research_feature_inputs`, `research_sector_mappings`.
Do not alter old economic rows. Store definition/formula versions, calculation
hash, instrument, family/name, value/type/unit, session, knowledge cutoff,
known-at, computed-at, availability/reason, immutable input refs and audit JSON.
Result content hash is unique: identical reruns do not duplicate results; each
invocation still gets a receipt with accepted/unavailable/duplicate counts.
Input revisions produce new results, never UPDATE an earlier calculation.
No order/fill/account/position tables. SQL constraints plus triggers reject
UPDATE/DELETE of definitions, results, provenance and mapping versions.

`as_of_session` is the economic session being described. `knowledge_cutoff`
is the latest permissible information time. `computed_at` is when code ran.
`known_at` is max of contributing source knowledge, authoritative publication/
acceptance and bar/session confirmation times. It is not claimed to be the
time this derived result was actually computed. Preserve both fields.

Two explicit modes:

1. Historical PIT: `--as-of <aware timestamp>` selects the last completed XNYS
   session and that same timestamp as cutoff. Date-only values resolve to that
   session's official close (including early closes); non-session dates reject.
2. Retrospective description: `--session YYYY-MM-DD --known-by <aware timestamp>`.
   Clearly label that it uses later-known inputs and is NOT historical availability.

Never invent source publication time. An exchange close is a calculation
boundary, not proof that an input was available then. A bar needs both a
completed session and source known-at <= cutoff. Source economic dates beyond
the requested session are excluded, except documented scheduled-event metadata
known by cutoff. Revised facts select the latest eligible version, not latest
database row. Tie/conflicting revisions reject rather than depend on row order.

Strict contiguous XNYS windows; missing sessions yield INCOMPLETE_WINDOW, not
compressed returns. Reject malformed, nonpositive prices, duplicate conflicting
bars, mixed currency/adjustment bases. Price basis is explicit provider-reported
close; never call it total return. Known unresolved splits/ticker changes across
a window give CORPORATE_ACTION_UNRESOLVED; unknown adjustment provenance is
shown as a limitation, not certified corporate-action completeness. No new
adjustment engine or rewrite of frozen total-return benchmarks in this checkpoint.

For historical mappings require effective range AND mapping known-at <= cutoff.
Unavailable results use null known-at, no fabricated publication, checked cutoff
in run metadata, and exact reason/dependency list. A valid numerical zero stays zero.

## Calculation conventions: version 1

All windows include current completed session unless explicitly stated. Fractions
are stored as fractions, percentages labeled/converted only in UI. Session age
uses XNYS; day age means elapsed calendar dates in America/New_York. No forward
returns are needed for this checkpoint.

### Trend, momentum, oscillators and realized volatility

- SMA n=20/50/100/200: arithmetic mean of n closes. Ratio C/SMA; distance
  C/SMA−1; slope SMA(t)/SMA(t−5)−1 (five-session fractional change).
- Ordering: serialize sorted labels C/SMA20/SMA50/SMA100/SMA200, with explicit
  equal groups; missing any operand makes the full ordering unavailable.
- Returns n=5/10/20/63/126/252: C(t)/C(t−n)−1, requiring n+1 prices.
- Excess return: difference of equally based, session-aligned simple returns,
  not difference of prices; label price-return comparison, not total return.
- Acceleration: return20(t)−[C(t−20)/C(t−40)−1].
- Percentiles: 252 valid consecutive feature observations, inclusive current;
  100×(count below + 0.5×count equal)/252. Short history is unavailable.
  Apply to return20 and realized-vol20 only; no arbitrary grid.
- RSI14 Wilder: seed average gains/losses from first 14 differences; subsequent
  average=(13×previous+current)/14. Loss=0/gain>0 =>100; gain=0/loss>0 =>0;
  both zero =>50, explicitly a flat-series convention. Name `rsi14_wilder_v1`.
- EMA12/26: seed first n closes with SMA; alpha=2/(n+1), then recursive update.
  MACD=EMA12−EMA26. Nine-period EMA of valid MACD observations uses its first
  nine values as seed. Name `macd_smoothing9`, avoiding ambiguous trade-signal
  wording; histogram=MACD−smoothing9; normalized MACD=MACD/C.
- Realized vol20/63: sample SD (ddof1) of n log returns ×sqrt(252), n+1 prices.
  Warmup starts at first contiguous eligible input; seed/window refs retained.

### Close structure and Fibonacci (operator-approved architecture)

Primary pivot `close_fractal_3x3_v1`: C(i) strictly greater/less than each of
three closes on BOTH sides; ties are not pivots. First valid at i+3 completed
session AND all seven inputs known. It never appears in as-of i/i+2 results.
No high/low or intraday extrema claim. Confirmed pivot records are immutable.

Construct alternating legs online: first confirmed pivot seeds; an opposite
type completes a leg; consecutive same-type pivots replace the pending endpoint
only when more extreme. Previously emitted legs/results never mutate. Active
leg is the most recent nonzero completed pair, with both endpoint confirmations.
Audit every result with endpoint prices/dates/types, confirmations, source refs,
direction, algorithm version, ratio and computed level. Revisions produce a
new input-set calculation, not silent anchor rewriting.

Let A=start, B=end, d=B−A. Retracements r=.236/.382/.5/.618/.786 are B−r×d.
Extensions r=1.272/1.618 are A+r×d. These are two-anchor directed projections,
not three-point price targets. Distance=(C−level)/level, optional (C−level)/ATR14;
missing ATR does not disable valid price-distance values. Nearest minimizes
absolute fractional distance; ties by ratio then anchor ID. Relation is
ABOVE/EQUAL/BELOW, never a recommendation.

Mechanical touch: close within 0.5% of level. Reaction count: number of entries
into that band after the leg became confirmable; persistent days inside count
once. Cross: consecutive eligible closes on opposite sides. No touches before
level availability. Latest three completed legs only for confluence; sort their
levels and use bounded clusters whose (max−min)/min <=0.005 (no chain bridging).
Cluster level=mean, density=count of distinct (leg,ratio,type) entries; nearest
cluster distance, overlap with support/resistance and SMAs within0.5%. This is
level density, not a score. Record tolerance and participating levels.

Support/resistance: confirmed close pivots in trailing252sessions; same 0.5%
bounded clustering, mean level, touch count, age from latest member. Nearest
level below/above current close; exact equality recorded separately. Mechanical
strength is only `confirmed_pivot_count`, not decision intelligence. Break/retest
uses a frozen prior-session level: strict cross; then within five sessions a
close returns to its 0.5% band from the crossed side. No test against a level
newly recomputed from the very observation being classified.

Breakouts: prior20/50/252 CLOSE maxima/minima, excluding current. Distances and
strict new-close-high/low booleans, normalized exceedance, sessions since most
recent strict breakout, with frozen-level five-session retest convention above.
Names include `close`; never advertise these as intraday/52-week high-low bars.

### OHLCV: implemented, live unavailable until validated inputs exist

Validate L<=min(O,C)<=max(O,C)<=H; O/H/L/C positive, volume nonnegative.
TR=max(H−L,abs(H−priorC),abs(L−priorC)); first prior close required. ATR14 seed
mean first14TRs then Wilder recursion; ATR/C. No close-only ATR approximation.
Geometry: abs(C−O), H−L, H−max(O,C), min(O,C)−L; divide by range when >0.
CLV=(2C−H−L)/(H−L); zero range makes ratios/CLV null but raw geometry zero.
Open-close=C/O−1; gaps O/priorC−1, O/priorH−1 and O/priorL−1.

Volume means20/63 use PRIOR n sessions; RVOL=V/current prior20mean; percentile
uses252 sessions convention above; change=V/priorV−1. Prior zero denominator
is undefined, not infinity. Interactions limited to return1×RVOL,
sign(return1)×volume percentile, (range/prior20mean range)×RVOL,
close breakout20distance×RVOL. No institutional/aggressor inference.
Optional RSI variants, Parkinson, named candles and extra extension ratios
are excluded from v1; no hidden parameter search.

## Sector and corporate descriptors

Document internal taxonomy, not licensed/point-in-time GICS. Proposed stock
mapping: AAPL/MSFT/NVDA→technology/XLK; AMZN→consumer-discretionary/XLY;
GOOGL/META→communication-services/XLC. Each mapping needs cited official issuer
business description, sector ETF mandate, effective-from and capture known-at.
Map remaining existing stocks only with equivalent evidence. Broad ETFs do not
receive a fictional single sector. SOXX is a semiconductor thematic instrument,
not the entire technology sector; optional comparison to XLK labeled proxy.
Do not fetch/activate new providers. Absent reference ETF closes => unavailable.

Sector returns and vol use identical calendar/basis rules. Relative momentum is
stock minus mapped ETF at registered return horizons. Leadership rank uses20d
returns across a fixed, versioned observed ETF set, average ties; rank change
over5sessions only with identical membership. Subset status visible. Breadth
and above-SMA50 participation require an explicit effective-dated constituent
snapshot and complete eligible prices; do not call the current23-symbol sample
sector-wide breadth. Otherwise unavailable.

Fundamentals require source filing confirmation, accepted timestamp and known-at.
All paired values agree on currency/unit/concept/entity and reporting basis.
YoY pairs same fiscal duration/quarter, prior fiscal year; QoQ only explicitly
reported standalone3M periods. Never subtract YTD cash flows to create quarters.
Growth=(current−prior)/abs(prior), prior0 => unavailable; label signed-base growth.
Margins and OCF/net-income use exact matching duration start/end; denominator0
=>unavailable. Cash/revenue and debt/revenue or OCF use balance-sheet date equal
to duration end and label the duration (3M/6M/9M/12M), never mix durations as
one metric. Share growth compares weighted-average diluted shares on equivalent
durations, not outstanding shares. Dilution trend is latest comparable share
growth direction, not a score. No valuation ratios. Missing debt stays null.

Earnings: authoritative event time, acceptance/known-at; sessions since last
event and until future scheduled event only if schedule was already known.
Before-open/regular-session/after-close via XNYS; unknown exact time stays unknown.
Filing ages/counts for10Q/10K/8K in30/90calendar days, de-duplicate accession,
count amendments separately and label them; no claim that every8K is material.
No consensus, sentiment, transcript or beats. Event factual changes reuse only
validated comparable fundamental fields with their provenance.

## Macro and future registry

Fed midpoint=(lower+upper)/2; latest reported bps; days since decision; last3
distinct meetings sum of reported changes and hike/cut/hold counts. Revisions
are not new meetings; require complete3meeting coverage, never partial sum.
PCE current validated headline/core MoM percent and days since publication;
keep publisher units and revision lineage. No invented YoY/index level.
CPI/labor/yields/market volatility unavailable, no substitutes.

Intraday registry only: VWAP, VWAP distance, opening range high/low/breakout,
time-of-day RVOL, intraday range/ATR, NBBO spread, quote imbalance, signed volume,
aggressive-buy/sell proxies. Requirements describe timestamps, sessions, trades/
quotes/volume and licensed coverage; values absent, family UNAVAILABLE.
`macro_regime`, `options_strategy`, `ml_ranker` remain NOT_STARTED.

## UI and operations

Read-only selected instrument/session/cutoff explorer. Permanent text:
**RESEARCH FEATURES ONLY — NOT A TRADE SIGNAL**. Separate live input coverage
from calculation-library status. Show source, unit, known-at, computed-at,
version, exact missing reason. Retrospective mode gets a conspicuous label.
Expandable family panels, neutral colors, no sentiment or buy/sell styling.
Fibonacci SVG uses stored anchors/levels only, with accessible table and both
confirmation times. No animation implying live calculation or predictive value.
GET never computes, ingests or updates capability metadata; unknown != available.

Manual CLI requires explicit research DB and temporal mode; default dry-run.
`--write` adds only derived research rows. No network, broker, official DB handle
or model import. Protect canonical official path, symlinks, same inode/hardlinks,
official DB signature and official parent directory before opening writable.
Reject existing non-Firm-Lab DBs. Use bounded transactions and a SQLite backup
before any approved live research migration. No replacement with a development DB.

Initial validation: VTI/SPY/AAPL/MSFT/NVDA/AMZN/GOOGL/SOXX and existing eligible
sector ETF history only. Latest30sessions plus explicit warmup sufficient for
longest dependencies; unavailable warmup reported. Independent review before
expansion to existing23instruments. No extra collection to inflate coverage.

## Acceptance

Fixtures prove formulas, missingness and source typing. Adversarial tests prove
late capture/revision/confirmation/acceptance cannot leak. Reordered input gives
same hashes/results. Independent review covers leakage, anchor stability,
imputation, capability labels, official writes and hidden strategy scoring;
no critical finding deferred. Focused, all Firm Lab, full native and cloud tests
reported separately. Cloud absent => NOT RUN, not native-equivalent success;
seek an explicit closure exception if still unavailable. Existing installed Codex
configWarning test is neither weakened nor installed-maintenance work here.

Deployment only after review/tests: additive research migration, validated rows,
read-only UI; restart dashboard only if required. Recheck exact Control A
fingerprint and all experiment invariants. Closure report follows all section51
headings of user specification, coverage counts and exact invariant lines.
Only then CHECKPOINT6=CLOSED; stop without Checkpoint7.
