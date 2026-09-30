# Broad universe screen: design (DRAFT for operator review)

Status: design only. No code, config or registration change. The operator chose
(2026-09-30 14:37 ET) to design the broad S&P 500 screen before adding any tickers.
Tomorrow's run keeps the registered 14.

## 1. Why the system checks only 14 today (measured, not assumed)

| Limit | Where | Effect |
|---|---|---|
| `instrument_whitelist` (14) | `config/settings*.yaml` | The read gateway refuses quotes, history or option chains for anything else (`broker/read_gateway.py`) |
| Hard guard `len(symbols) > 14 → BrokerError` | `agents/market_reader.py` | A deliberate "reviewed discovery bound" |
| One symbol per history call, 550 days | `market_reader.collect` | The provider rejects multi-symbol history, so the cost is 1 call per symbol per run |
| `ETF_UNIVERSE` (8) | `research/strategy_signals.py` | Momentum rotation ranks only these |
| Option discovery | `market_reader.collect` | Every whitelisted underlying: first 2 expiries 7–45 days out, strikes within ±10%, up to 40 contracts |
| AI budget | `daily_api_budget_usd: 0.40` | Caps how many names AI can research |

Today's live rehearsal (14:32 ET) measured:
- **Reads:** 14 symbols = 14 history calls, 12 option chains, about 70 option-instrument pages and 28 option-quote batches, finishing in 45 s.
- **Options:** 547 contracts, 0 usable. SOXX calls near the money cost more than the $500 lane can pay, and 498 contracts were on tickers with no buy signal.
- **So:** with only expensive underlyings, the options lane is structurally idle. A broader universe with cheaper names is also what would make options possible.

## 2. Goal

Screen every current S&P 500 constituent plus a reviewed list of liquid ETFs with the registered rules. Hand the morning run a small, fresh, fully explained shortlist. Keep:
- the 10:00–10:20 window
- read-only broker access
- the $0.40/day AI budget
- every existing risk and approval gate

## 3. Architecture: move the heavy work to the night before

```
16:45 ET nightly screen (maintenance service, read-only)      10:00 ET official run
┌──────────────────────────────────────────────┐              ┌────────────────────────────────┐
│ pinned universe file (~500 stocks + ETFs)    │              │ live quotes for shortlist (≤30)│
│ → incremental daily-bar cache (1 short call  │  shortlist   │ → spread ≤0.3% check (≤20 left)│
│   per symbol; full 550-day backfill spread   │ ───────────▶ │ → option chains only for names │
│   over several nights)                        │  + hashes    │   with a buy signal            │
│ → features + registered filters               │              │ → AI gate → research ≤8        │
│ → ranked shortlist (30), recorded + hashed   │              │ → Critic, risk, cards (as now) │
└──────────────────────────────────────────────┘              └────────────────────────────────┘
```

### 3.1 Universe file (source of truth)

- `universe/sp500-current-YYYY-MM-DD.csv`: symbol, name, sector, source, retrieval date, content SHA-256. It is committed, and each new version needs a signed amendment line.
- Source: needs an operator decision (see §8). Until Norgate historical membership is validated, every result is labelled **SURVIVORSHIP-BIASED**, as the v1.5 draft already requires.
- Reviewed ETF list: today's 8, plus the 9 SPDR sector funds and any others the operator approves by name. No leveraged or inverse funds, and nothing traded OTC.

### 3.2 Nightly screen (new, read-only)

- It runs after the 16:30 daily summary, in the existing maintenance service, with its own claim and lock. It never overlaps the official run.
- **Bar cache:** a new table `daily_bars(symbol, day, close, volume, source_hash)`.
  - First fill: 550 days for each symbol, capped at about 120 symbols a night, so all 500 are filled within 5 nights.
  - After that: one short request per symbol per night (last 5 sessions), about 500 calls. At the measured roughly 1–2 s per call that's 8–15 minutes, which is fine at night. It needs a per-night call budget and a stop-on-error rule.
- **Filters,** in the order of the v1.5 draft's `universe:` block:
  - price at least $5
  - at least 253 sessions of history
  - median 20-day dollar volume at least $50M
  - not OTC, leveraged or inverse
- **Signals:** the same registered strategies.
  - Mean reversion covers all names: above the 200-day average and down 3% or more last session.
  - Momentum rotation stays on the reviewed ETF list only. Adding stock momentum would be a new strategy and needs its own registration.
- **Shortlist:** up to 30 names, ranked by signal strength, ties broken by symbol ascending. Names already held are always included for review.
- **Record:** the whole funnel is saved, with counts per filter, every rejected name and its reason, the file hash and the bar-cache hash. The Checks page shows it as a new "Universe screen" section (same pattern as the options screen).

### 3.3 Morning changes

- The `len(symbols) > 14` guard becomes a registered bound of **30** on the live set. The nightly screen has its own separate bound.
- The whitelist becomes: the shortlist, plus held positions, plus the reviewed ETFs. It's derived from the signed universe file and the recorded shortlist, never edited by hand.
- **Live verification:** fresh quotes for the shortlist, then the spread rule (0.3%); at most 20 names continue.
- **Options:** chains only for names with a buy signal (not all 30). This keeps option reads at or below today's level.
- **AI:** research gets at most 8 names. The budget allocator already reserves before calling.
  - Estimate from today's Sep 29 run: research on 14 names used 6,008 input tokens on nano. 8 names with fuller features is on the same order, well inside $0.40.
  - This must still be measured in shadow mode, not assumed.

## 4. Rollout

1. **Build (about 2 evening releases):**
   - universe file and loader, bar cache, nightly screen
   - funnel record, Checks page section, and tests on synthetic data
2. **Shadow period (at least 5 trading days):** the screen runs nightly and is recorded, but the official run still uses the 14.
   - Each morning the dashboard shows "what the broad screen would have shortlisted" next to what actually ran.
   - We review cost, read time, data gaps and survivorship labels.
3. **Activation:** a signed amendment (v1.6.0) that pins the universe file hash, the bounds (30 / 20 / 8), the nightly call budget and the effective date, delivered by an after-close release. It starts a new readiness baseline.

## 5. Safety and honesty rules

- The nightly screen can only read. It shares the existing read gateway, which gets a separate "screen" bound. There are no write tools.
- The official run never uses a shortlist older than the previous session's close. If the screen failed or went stale, the run falls back to the registered 14 and the record says so.
- No ticker enters from news or AI. Only the signed universe file can add names.
- Every number shown on the dashboard comes from recorded fields, as today.

## 6. What it changes for you

- The Checks page gains a Universe screen funnel. For example: 503 → price → history → liquidity → signal → 30 shortlisted → 20 verified → 8 to AI, with every exclusion listed.
- The options lane becomes meaningful, because cheaper underlyings can fit one contract in the $500 lane.
- There are more AI days (more signals), but it stays within the $0.40 cap.

## 7. Risks

- Read volume and provider rate limits: unknown until measured, so start with the capped backfill.
- Survivorship bias in any backtest or claim: labelled everywhere.
- More candidates means more AI calls and more Critic rejections. Watch cost per decision in the shadow period.
- Sector concentration: the existing risk engine limits position size, not sector. Consider a sector cap in v1.6.

## 8. Operator decisions needed

1. Constituent source for the universe file:
   - a manually downloaded public index-holdings file (for example an S&P 500 ETF's published holdings)
   - or a paid data provider (Norgate)
2. Nightly call budget: default 600 calls and 20 minutes.
3. Shadow period length: default 5 trading days.
4. Bounds: shortlist 30 / verified 20 / AI 8 (from the v1.5 draft), or tighter.
5. Should the sector ETFs join now as part of the reviewed ETF list, or with the broad screen?
