# AI trader forward book (ai_trader_fwd_v1): what exists and how it starts

Registered 2026-09-30 (trial log row 18, `REGISTERED_NOT_STARTED`). Spec: `research/recipes/ai_trader_fwd_v1.yaml`
(sha256 `a5e85e29…acc83`); prompts sha256 `c90e6f03…1077` (pinned at first run; any change = new trial).

## What it is
A paper trading firm, scored only going forward (models can't be backtested honestly).
- **Seats:** Scout (gpt-5.4-nano), PM (gpt-5.4-mini), Critic (gpt-5.4); Risk and Clerk are code.
- **Books, $25,000 each:** A = AI alone; B = AI + operator (Yes / half size / No / Skip; unanswered = skip;
  never add size or a name); C = matched random control (same day, same notional fraction, same exit day as
  its A trade; seeded ticker).
- **Universe v1:** the 23 Official names, long shares only. S&P shortlist = watch only. No options until 50
  closed stock trades (then a separate hashed trial). No news.
- **Code-owned rules:** 5% per name, ≤5 names, ≤2 entries/day, 3% daily and 6% weekly book stops (block
  entries only), entries before 15:30 ET. Exits: the ticket's invalidation price and time stop (≤20 sessions),
  two sessions without a management card, and at 15:50 the v1.6 protective rule (8% under cost or under the
  200-day average). Stops are checked at the morning run and 15:50 only; gaps fill at the next check.
- **Budget:** $2/day, no rollover; each call reserves its registered worst case first; no new model call starts after six minutes of a morning run; Critic only runs on
  tickets that pass code checks; "nothing today" is a normal answer.
- **Scoring:** A/B/C vs VTI, Official lane A, random C and cash, after spreads, AI bill (A and B) and an
  estimated 35% tax on gains. Verdict: TOO_EARLY until 200 closed trades or 252 sessions; then PASS only if
  A beats VTI with the 90% interval above zero **and** beats C; LUCK_OR_BETA if it beats VTI but not C.

## Where the code is (nothing installed yet)
- Runtime: branch `claude/ai-trader` — `agents/ai_trader/*`, hook in `agents/daily_cycle.py` (inside the
  existing scheduled tick, after today's Official cycle COMPLETED; disabled until `init`). Release manifest
  `docs/review/release-2026-10-02e-manifest.json` (base c36f4ad, 22 files).
- Dashboard: branch `claude/card-inbox` — `/firm` (AI trader) and `/inbox` pages; carries an identical copy of
  `agents/ai_trader` for the overlay.

## Start sequence (operator)
1. **Thu Oct 1:** Official ops check only. Confirm the 10:00 run COMPLETED (Claude's 10:30 check).
2. **After Friday's close (or the weekend):** install release E (same procedure as release D:
   `release_install.py` dry run → `--install` → kickstart the inbox), then deploy the dashboard overlay from
   `claude/card-inbox` (backup first; include `agents/desk/*`, `agents/static/*`, `agents/cards.py`,
   `agents/ai_trader/*`, `research/recipes/ai_trader_fwd_v1.yaml`; exclude tests and `agents/dashboard_view.py`).
3. **Init (creates the book in WATCH_ONLY):**
   `$P/.venv/bin/python -m agents.ai_trader.cli init --official-database $P/data/agent.db`
4. **Mon Oct 5 or later:** `... cli start-paper --official-database $P/data/agent.db` (refuses before Oct 5
   or if the Oct 1 Official run did not complete). Until then the seats run watch-only (no fills).
5. Daily: answer book-B cards on `/firm` before 15:30 ET. `cli scoreboard` or the page for results.
6. To stop for good: `cli retire`.

Live copying stays off. Nothing here can place a real order.
