# Agent Desk: final plan (reviewer-approved direction)

Date: 2026-09-29. Status: plan for Codex. It is not approval to change preregistration, and it does not authorize live changes. Every step below still needs its normal operator approval.
Baseline reviewed: export commit `73be5a8` (2026-09-28 20:00 ET).

Stage 1 stays paper-only. Real orders stay blocked. Only the Agentic account is in scope. Account identifiers never appear in the UI or in reports.

---

## 0. Where we actually are (verified from the repo)

| Area | Status in code | Evidence |
| --- | --- | --- |
| Phase 0 safety (proxy user, 11 reads, bounded cash, tripwire, auth monitor, revocation) | Built | `broker_proxy/`, `agents/account_tripwire.py`, prereg v1.4.2 |
| Phase 0 installed scheduled-cycle proof | **Not proven in repo.** The 2026-09-29 10:00 ET run is the target | HANDOFF.md |
| Tests (clean Linux, Python 3.12) | 574 passed, 14 failed, 1 skipped. All 14 failures are environment-bound: tailnet URL vs loopback, missing `settings.local.yaml`, `operator_uid=0` under root, symlink checks. None are logic failures. | local run |
| Ledger | **Missing.** Every table is append-only `(id, created_at, payload_json)`. `PaperBroker` keeps positions in memory. There are no lots, marks, open items or peak-NAV tables. | `data/schema.sql`, `broker/paper.py` |
| Preregistered arms: `deterministic_no_ai`, `seeded_random`, `exposure_matched_vti`, `lane_b_delta_equivalent_underlying` | **Registered, not implemented** (no code references) | grep across `agents eval risk broker research` |
| Forecast scoring (Brier, base rates, shrinkage, `p_used`) | **Registered, not implemented** | same |
| Run-mode isolation (official / what-if / replay) | **Registered, not implemented.** Costs from manual recovery runs mix with official costs. | same |
| Recorded handoffs | Projected in `decision_room.py`. No `handoffs` table. | |
| Lanes | A: stocks/ETFs $500. B: paper long options $500 (`options_unlocked: true`). Option-chain reads are already approved. | `config/settings.yaml` |
| Universe | 14 hardcoded symbols plus a hardcoded bound | settings, HANDOFF |
| Models | Aliases (`gpt-5.6-luna`/`terra`), not dated snapshots. The Critic uses the same model as Portfolio. | settings |
| Approval expiry | 30 minutes. Preregistration says market close. | settings vs prereg |
| TradeLog-Pro scanners | **Not integrated.** `research/strategy_signals.py` has only momentum, trend and mean-reversion. | |
| News, Filings, Explainer, Ask, Tune | Off or read-only | HANDOFF |
| Runtime location | iCloud Documents, with files being offloaded | HANDOFF |

The honest summary: safety is strong, but the investment firm itself is thin. The system can't yet print its own book, and it can't yet show whether the AI beats no-AI. Those two gaps come before anything clever.

---

## 1. Roster (role keys in code, faces in the UI only)

Module and table names use the **role key**. Character names and faces live in one UI mapping file (`agents/desk/roster.py` or JSON). Fictional or franchise names never appear in code.

| Seat | Role key | Face | Kind | Authority |
| --- | --- | --- | --- | --- |
| Managing Partner | `operator` | You | Human | Cards, policy, admits, rearm after a lock |
| Floor Boss | `orchestrator` | **Pepper** | Code | Runs the day, checks seats, writes the receipt. Never sizes, vetoes or fills. |
| Bookkeeper | `ledger` | **Mochi** | Code | Single source of truth for cash, lots, marks, pending orders and corporate actions |
| Scout | `scout` | **Pip** | Code (LLM later) | Facts only: quotes, history, option chain. Every fact carries a timestamp and hash. |
| Quant | `quant` | **Pixel** | Code | Scores, size hints, correlation, liquidity. May output `do_nothing`. Top K ≤ 5. |
| Portfolio Manager | `pm` | **Maple** | LLM | At most one discretionary action, chosen from Quant's K |
| Critic | `critic` | **Pickle** | LLM (different family or snapshot from PM; exact pinned pair in settings) | Tries to kill the action. No critic means no card. |
| Risk | `risk` | **Nugget** | Code, never an LLM | Veto, resize or lock. Returns every reason, not just the first. |
| Card Writer | `card` | **Doodle** | Code | 150-word YES/NO card |
| Execution | `execution` | **Zippy** | Code | Paper fills across the preregistered arms |
| Auditor | `auditor` | **Olive** | Code (rare LLM) | Receipt, P&L vs arms, open items, weekly hold reviews, lessons |
| Filings/News | `filings` | **Biscuit** | Dark until Phase F | Evidence only, only on watch/tradable names |
| Explainer | `explainer` | **Bubbles** | Dark until Phase F | Plain language, no vote |

Required seats every session: orchestrator, ledger, scout, quant, risk, execution, auditor. If any is missing, the orchestrator stops the day and writes the receipt anyway. PM and Critic run only when Quant says there is a decision worth words (the existing AI-needed gate).

Avatars: `design/agent-desk/avatars/*.svg`. Six existing faces plus six new ones: pepper, mochi, pixel, doodle, zippy, olive.

---

## 2. Sequence

Each gate must pass before the next begins on the **primary runtime**. Preview 8766 and branch work can proceed in parallel as long as nothing touches the primary runtime.

### Gate 0: Phase 0 proof (now)

1. Produce the installed scheduled-cycle receipt for the 2026-09-29 10:00 ET run and run the operational gate.
2. If the run failed or went stale, diagnose it and retry at the next session's 10:00. Do not rerun it manually as "official" (`manual_official_rerun_allowed: false`).
3. Report: receipt, gate result, drill evidence (`AUTH_REVOKED`, then reauthorization), cost vs cap, and any cloud-only files.

**Done when:** the gate passes on the installed service.

### Step 1: Stabilize (same week as the gate)

- Move the runtime out of iCloud as a separately approved move. Re-verify the proxy socket paths and services afterward.
- Swap the Agent Desk onto 8765, dashboard-only, after acceptance. 8766 stays as the preview.
- Fix GET-expiry on dashboard routes: a GET must never mutate.
- Make the 14 environment-bound tests portable (fixtures for the uid, local config and host). The suite passes in a clean checkout.
- Set approval expiry to market close, per the preregistration.

### Phase A: Ledger (Mochi)

New transactional tables. They are not JSON-only, and every row carries `lane`, `arm` and `run_mode`:

`accounts(lane, arm, settled, unsettled, peak_nav, as_of)`, `lots`, `marks(bid, ask, mid, ts, source_hash, age)`, `orders`, `fills`, `pending_limits`, `open_items(kind, symbol, due, status, payload)`, `cycle_receipts`, `handoffs(run_id, seq, from_role, to_role, candidate_id, summary, record_ref, ts)`.

- `run_mode ∈ {official, what_if, replay, manual_diagnostic}` goes on cycles, costs, cards and fills. Non-official modes cannot write official results. This is already preregistered and is enforced by a separate connection plus the SQLite authorizer.
- Option lots are required because Lane B already exists: strike, expiry, multiplier and type. Mechanical expiry and sell-to-close only. **No rolls yet.**
- NAV = settled + unsettled + Σ(qty × bid × multiplier). A stale mark is tagged, and Risk treats it as missing for any new risk.
- Order before ideas: settle, then expire, then apply corporate actions, then re-mark, then rebuild open items.
- A fill that cannot post to a lot fails the cycle.
- Backfill from existing blobs if the reconstruction is exact. Otherwise start a dated book and label the old blobs historical.

**Tests:** buy, sell, partial fill, expire worthless, ITM near expiry, stale mark, missing lot, duplicate order id, cross-mode write rejected.

**Done when:** "print the book" works with no model involved and reconciles with fills.

### Phase B: Split into seats (no behavior change)

- Extract modules: `desk/orchestrator.py`, `ledger.py`, `open_items.py`, `scout.py` (wraps `market_reader`), `quant.py`, `pm.py`, `critic.py`, `risk.py` (adapter over `risk/engine.py` and `breakers.py`), `card.py`, `execution.py` (adapter over `paper.py`), `auditor.py`.
- `daily_cycle.py` becomes the orchestrator script, about 200 lines or less.
- The LLM subgraph is only PM ← Scout packet → Critic. Quant, Risk and Ledger stay outside it.
- Every seat hop writes a `handoffs` row. This is the only source for Decision-room edges.
- Golden replay of existing fixtures must produce identical decisions before and after.

### Phase C: Prove the AI (preregistered, unbuilt) and manage the book

This phase implements what v1.4.2 already promises. Note that `AGENTS.md` rule 4 requires the v1.5 preregistration review before **any** Phase 1 runtime work on the primary runtime. So v1.5.0 is drafted and approved after Gate 0 and before Phase A lands there. It covers the pulse definition, `cycle_kind`, fill `origin`, role keys and the pinned Critic pair. Universe, TradeLog-Pro and admit caps can ride in v1.5.0 or a later v1.6.0. Branch development of A–C can proceed before approval.

- Arms: `agent_alone`, `agent_with_approvals`, `deterministic_no_ai` (Quant's top pick through the same Risk, sizing and exit rules, with no PM or Critic), `seeded_random` (logged seed formula), `vti`, `cash`, `exposure_matched_vti`, and `lane_b_delta_equivalent_underlying`. All use the same snapshot, timestamps, sizing and risk engine.
- Forecasts: `p_agent_raw`, base rate, shrinkage to `p_used`, Brier score vs base rate, the resolution job, and every immutable logged field.
- API cost is attributed to the AI arms only.
- Managing the book:
  - a daily hold/sell board per lot, where hold is explicit
  - an option DTE and moneyness pipeline with mechanical recommendations
  - a weekly thesis review
  - open items ranked above new ideas
- Model hygiene: dated snapshots in settings, and a Critic from a different family or snapshot than the PM.
- Cost hygiene: trim model inputs from about 200k tokens to a bounded packet (top-K only, summarized history). Target ≤ $0.10 per full LLM cycle.
- If v1.5.0 did not include them, draft **v1.6.0** for Phase D: universe policy, TradeLog-Pro scanners, what-if budget.

**Done when:** the scoreboard shows every arm side by side with sample size, cost and an "inconclusive" label until significance is reached.

### Phase D: Wide watch, narrow tradable, plus TradeLog-Pro (needs an approved preregistration covering it)

- Watch: a committed, dated S&P 500 plus core-ETF file. Scout rotates deep pulls. It is never called "agent-discovered."
- Tradable: the seed 14 plus names admitted through `admit_symbol` cards. At most 1 admit per day and at most 25 names at first. Raising the cap takes a policy card.
- Risk's admit checks: a resolvable instrument, a history window, a liquidity floor (spread and dollar volume), sector/issuer cap, data budget, not already tradable. A drop requires a flat position or a paired sell.
- **TradeLog-Pro scanners** are ported as deterministic, point-in-time Quant candidate sources. Each candidate records `source_scanner`. The scoreboard shows hit rate per scanner. Scanners that don't beat the base rate are demoted by policy.
- No social-media lists. No tickers from LLM prose.

### Phase E: A harsher paper market

Gaps, partial fills and pending orders carried across days. An assignment that fails a cash or share check is an incident. Option rolls are allowed only here: later expiry, same type and underlying, defined risk, sized by Risk.

### Phase F: Filings/News, Explainer, Ask/Tune

- Biscuit: filings and news evidence only on watch/tradable names. Any new read method needs an amendment.
- Bubbles: scoped to the run, agent and candidate. Every claim cites a record. Separate budget. Disabled with the reason shown until enabled.
- Tune and side tests: challengers run as `what_if` with a separate budget. Promotion goes through a card and a preregistration version bump.

### Real money

Not in this plan. The preregistered readiness gates decide it: after-cost beating `deterministic_no_ai`, sample minimums, and no unresolved incidents. The UI shows progress honestly as "not enough data" until then.

---

## 2b. Session heartbeat: one official meeting, a live floor all session

The 10:00 claim stays the only **decision** meeting. The desk does not go to sleep at 10:01, though. The existing `maintenance` service (launchd, every 300 s: auth check, card expiry, notifications) grows into the pulse. Preregistration already allows `code_only_intraday_checks`, and entry triggers expire at 15:30.

| Loop | When | Seats | May do | Record |
| --- | --- | --- | --- | --- |
| Official open | 10:00 ET, one atomic claim | Full roster (PM/Critic only if Quant needs words) | Mechanical start-of-day work + at most one discretionary action | `cycle_kind=official_open` |
| Pulse | Every 2 min, 10:00–16:00, trading days | Scout (marks for **held + pending + armed triggers only**), Ledger, Risk breakers, Execution, Auditor | Re-mark, fill or reject resting paper limits, evaluate already-approved entry triggers, run breakers, raise DTE/assignment alarms | `cycle_kind=pulse` (its own receipt table; never the official row) |
| Halt | On tripwire, auth fault, breaker or kill-file | Orchestrator, Risk, Execution | Freeze new buys, apply only closes that are already policy-mandated, page the operator | incident |
| Close sweep | 15:50 ET | Ledger, Risk, Execution, Auditor | Expiry-day options, cancel stale limits, expire cards at close, final marks, day receipt | `cycle_kind=close_sweep` |

Pulse rules:
- No PM, Critic, new thesis, admit or model call. Pulse cost is infrastructure only. An LLM attached to a pulse is `what_if` and never official.
- No new read methods. Tripwire and order-history scans keep their current cadence and call caps; they do not run every 2 min.
- The pulse must not take the official claim or hold a write lock during the 10:00 cycle. It skips while the claim is active.
- Discretion found by a pulse (e.g. sell an ITM call now) is handled one of two ways. If a written rule already decides it (an unfunded assignment must close), it executes mechanically and identically across every arm. Otherwise it opens an operator card that counts against `max_orders_per_day`. It never trades silently and never becomes a second PM meeting.
- Every fill records `origin ∈ {official_open, resting_limit_pulse, trigger_pulse, mechanical_rule, close_sweep}` and its decision `run_id`, so arms are credited for decisions, not for timing luck.
- Tie-break: emergency open items can use the official discretionary slot; admits wait for a quiet day.
- Health shows pulse gaps. A sleeping Mac means no pulse, shown as unknown and never green. The session runs with the Mac awake and on power (`caffeinate`/`pmset` documented, not silently changed).

Phase placement:
- Gate 0/Step 1: no pulse changes on the primary runtime.
- Phase A: the ledger accepts marks, pending fills and expiries outside a full cycle.
- Phase B: the orchestrator exposes `run_official_open()`, `run_pulse()`, `run_close_sweep()` and `run_halt()`; `maintenance` calls the pulse.
- Phase C: the scoreboard separates fills by `origin`.
- Phase E: gaps and partials are built on top of the pulse.
- If v1.4.2 wording is narrower than "non-discretionary maintenance of already-approved or pending state," define the pulse in the v1.5.0 draft.

---

## 3. Budget

- Official: one atomic 10:00 ET claim per session (preregistered). Most days run code only.
- `what_if` learning runs are allowed only after `run_mode` exists (Phase A): $3/day and $20/week hard stops, cost recorded separately, never official.
- Daily official cap stays $0.40 until the Phase C input trim lands. Then report actual cost per cycle.

---

## 4. Agent Desk UI changes from this plan

- The Decision room shows all 13 seats. Code seats carry a "Rules, not AI" badge, and dark seats sit greyed on a "joins later" bench.
- Edges come **only** from `handoffs` rows. Historical runs show a dashed expected workflow.
- New **Book** view (the Portfolio "Paper experiment" tab) comes from the ledger:
  - NAV and cash by lane and arm
  - every lot with mark age and P&L
  - pending limits
  - open items by urgency
  - last Quant board
  - last Risk reasons
  - cards waiting
  - receipt: seats present, skipped or failed
- The Agentic account tab shows only stored, sanitized, read-only snapshots, never merged with paper.
- Road to money uses Phase C arm comparisons. Before that it says "not built yet," with no synthesized series.
- Unknown is never green. A dark seat is never shown as a live feed.

---

## 5. Do not

- Let the PM keep the books, or let any model edit the ledger.
- Dump the watch set into a prompt, or let an LLM mint tickers.
- Auto-admit Quant favorites, or unlock options on admit day.
- Treat animation as a working seat, or draw an edge that wasn't recorded.
- Edit the YAML whitelist mid-cycle instead of using an admit card.
- Use character or franchise names in code, tables or logs.
- Mix official and non-official costs or results.
- Restart or change the primary runtime before Gate 0 passes.

## 6. Operator decisions needed

1. Gate 0 result, and approval of the iCloud move.
2. Backfill vs a fresh dated book for Phase A.
3. Which model family or snapshot the Critic uses.
4. v1.5.0 contents before Phase D: the TradeLog-Pro scanner list, admit caps, what-if budget.

## 7. Operating law

Mochi knows the book. Pixel ranks the work. Maple argues for one action. Pickle tries to kill it. Nugget can kill it for real. You approve it. Doodle writes the card. Zippy posts it. Olive remembers it. Pepper only runs the meeting.
