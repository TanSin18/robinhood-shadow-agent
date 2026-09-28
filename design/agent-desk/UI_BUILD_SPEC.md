# Agent Desk: UI build spec (v2, fitted to this codebase)

Status: design approved by the operator. It replaces the current "Shadow" dashboard look and navigation.
Build order: finish the Phase 0 gate → build-week budget policy → this UI (milestones U1–U7, §9).
This version was written after reading the repository as of 2026-09-28 17:20 ET (`agents/inbox_web.py`, `agents/dashboard.py`, `agents/dashboard_view.py`, `agents/decision_room.py`, `agents/static/*`, `data/agent.db`, `config/settings.yaml`). Where this spec and the code disagree, raise it before building.

---

## 0. How to use this pack

| Path | What it is | How to use it |
|---|---|---|
| `UI_BUILD_SPEC.md` | This file. It is the authority. | Build from it. |
| `avatars/*.svg` | Final artwork for the six team avatars. | Serve from `agents/static/avatars/` (or inline the SVG markup). Do not redraw. |
| `reference-mockup/*.dc.html` | Source of the approved clickable mockup. | **Reference only.** Read the markup for copy, layout, colors and spacing, and each file's `renderVals()` for interaction logic and sample data shapes. Do not port the `<x-dc>`/`support.js` runtime. All numbers in it are sample data. |
| `screenshots/` | PNG exports of the mockup, added by the operator. | The visual target. |

---

## 1. What exists today (verified in the repo)

**Server and rendering**
- `agents/inbox_web.py` runs a stdlib `ThreadingHTTPServer` on port 8765. It accepts only the loopback host and the Tailscale host from `notifications.dashboard_base_url` (this is how the phone reaches it).
- HTML is server-rendered as Python f-strings in `agents/dashboard_view.py` (`shell()`, `render_dashboard()`, `decision_room_view()`, `card_view()` …). Data comes from `agents/dashboard.py::dashboard_snapshot()`.
- Static assets (`dashboard.css`, `dashboard.js`, `decision-room.js`) are served from an explicit allowlist in `do_GET`.
- CSP: `default-src 'none'; style-src 'self'; script-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'`.
- POST actions use a per-process CSRF token and an Origin check. Account IDs are masked in every response.
- Tests: `tests/test_dashboard.py` (large), `tests/test_decision_room.py`, `tests/test_dashboard_resources.py`, `tests/test_inbox_web.py`.

**Decision room today**
- `agents/decision_room.py::project_decision_room(records, cards)` groups `local_traces` by `trace_id` and projects six fixed stages: `evidence, research, portfolio, critic, risk, final`. Each has a summary, details and an inspector.
- It already refuses to infer anything missing ("no-inference rule") and does not show hidden chain-of-thought. **Keep both rules.**

**Data (SQLite `data/agent.db`)**
- Most tables are append-only `(id, created_at, payload_json)`: `local_traces`, `run_states`, `api_costs`, `daily_values`, `cards`, `alerts`, `lessons`, `improvement_proposals`, and others.
- Keyed tables: `cycle_runs(day)`, `cycle_events`, `paper_accounts(lane,track)`, `approval_inbox`, `cost_reservations`, `safety_incidents`, `notification_outbox/deliveries`, `weekly_reports`, `database_role`.
- `local_traces` holds `stage_completed` events per role (`research`, `portfolio`, `critic`) with public outputs, plus `cycle_terminal`.
- `api_costs` holds per-call model, tokens and estimated cost.
- `cycle_events` holds `trigger` (e.g. `manual`), `recovery_of`, and `temporary_api_budget_usd`.

**Gaps this UI depends on (found while reading)**

| # | Gap | Why it matters for the UI |
|---|---|---|
| G1 | No per-candidate hand-off records. Decisions and reasons are stored per cycle, not per idea. | The Decision room map plays an idea's path. Without per-candidate hand-offs it can only show cycle-level stages. |
| G2 | No explicit run `mode` (official / learning / what_if / diagnostic / test). `trigger: manual` and `temporary_api_budget_usd: 5` recovery runs sit beside scheduled ones. | This is why "Estimated AI cost today" showed $1.43 against a $0.40 cap. The UI must never sum modes. |
| G3 | Portfolio calls use about 212k input tokens (about $0.43 per call). Research uses about 197k. | Cost panels will look alarming, and the build-week budget will run out quickly. Packet size needs trimming (tracked separately; the UI shows tokens per stage). |
| G4 | `config/settings.yaml` uses model aliases (`gpt-5.6-luna`, `gpt-5.6-terra`), and **Critic and Portfolio are the same model**. | Conflicts with preregistration (dated IDs; Critic must differ). The UI shows the model per agent and must flag this as a health warning until fixed. |
| G5 | `approval_expiry_minutes: 30` versus the preregistered same-day close. | The approval card countdown must read the effective rule. |
| G6 | The whitelist is still the 14-symbol list. | Funnel, radar and hits/misses will be sparse until the full universe lands. Show "Universe: 14 symbols (interim)". |

Fix G1 and G2 in milestone U1. Report G3–G6 to the operator; they belong to other work but must be visible on the Health screen.

---

## 2. Implementation constraints (match the existing stack)

1. **Keep the stack.** Stdlib HTTP server, server-rendered HTML in Python, vanilla JS in `agents/static/`. No frameworks, bundlers, CDNs or remote fonts. The dashboard must work fully offline.
2. **Keep the CSP strict.** Add only `img-src 'self'` and `font-src 'self'` (for avatars and self-hosted Geist). Nothing else.
   - **No inline `style=""` attributes and no inline scripts.** CSP blocks them. Use classes in `dashboard.css`.
   - For data-driven sizes (bar widths, chart points), prefer SVG attributes (`width`, `x`, `points`). Alternatively, JS can set CSS custom properties via `element.style.setProperty('--w', '42%')` from `data-*` attributes; CSP allows that.
3. **Split the views.** Move from the single `dashboard_view.py` into `agents/desk/`, with one module per screen (`today.py`, `decision_room.py`, `portfolio.py`, `money.py`, `scoreboard.py`, `controls.py`, `health.py`) plus `desk/components.py` for shared pieces (avatar, chip, bar, card). Keep projections (data shaping) separate from rendering, the way `decision_room.py` and `dashboard_view.py` are split today.
4. **Routes:** one path per tab (`/`, `/room`, `/portfolio`, `/money`, `/scoreboard`, `/controls`, `/health`) instead of hash anchors. Add each new static asset to the explicit allowlist in `do_GET`.
5. **Progressive enhancement.** Every screen must be readable with JS off (server-rendered state). JS adds Play, filters, tab switching and live updates.
6. **Keep every existing safety behavior:** Host allowlist, CSRF on all POSTs, account masking, `Cache-Control: no-store`, pause/resume semantics, and the incident latch that ordinary Resume cannot clear.
7. **Phone:** the same pages, reached over Tailscale. Layouts must collapse to one column under 720px. Approval actions must be comfortable on a phone.
8. **Tests:** update the existing dashboard tests rather than deleting their guarantees. Add tests per §10.

---

## 3. Principles (non-negotiable)

1. **Plain language everywhere.** Every number has a label saying what it means ("Most we can lose: $1.75").
2. **Never invent data.** Missing means "Not recorded" plus the reason. Never a fake zero, never a reconstructed sentence. This extends the existing no-inference rule.
3. **No hidden reasoning.** Hand-off messages are short public summaries of structured outputs, never chain-of-thought.
4. **AI vs code is always visible.** Violet means an AI step (costs money, can be wrong). Cyan means a code step (free and deterministic).
5. **Modes are never mixed.** Official, learning, what-if, diagnostic and test runs each get their own badge and their own totals.
6. **The UI can never place real orders or edit the preregistration.** Tweaks only create side tests (challengers).
7. **Pictures first.** Maps, bars, timelines and avatars before tables.

---

## 4. Design tokens (match exactly; dark theme)

```
--bg:#0f1012  --card:#17181b  --card-2:#1d1f23  --border:#2a2c31  --border-soft:#23252a
--text:#f2f3f5  --text-2:#cfd3da  --text-3:#a1a6b0  --text-4:#8a8f99 (lowest allowed for text)
--cyan:#3dc6ff (on-cyan #06202b)   code / primary / links    tint #1d2a31
--violet:#b9a3ff                   AI                        tint #2a2340
--green:#3fd08f                    good / gain               tint #1a2a22
--red:#ff8a6b                      stopped / loss            tint #2a1f1b
--amber:#f5b54a                    warning / uncertain       tint #2a2114
--stop:#ff5c3a (on-stop #1b0a05)   the STOP button only
```

- Fonts: Geist and Geist Mono, self-hosted in `agents/static/fonts/`. Use Mono for all money, percentages and IDs.
- Radius 14–16px for cards, 10px for controls, 999px for chips. Card padding 22–28px.
- Touch targets at least 44px, text contrast at least 4.5:1, aria-labels on icon-only buttons. Color is never the only signal (pair it with ✓ ✕ ? – or words).
- Motion: only the active hand-off arrow and the LIVE badge animate, and only under `prefers-reduced-motion: no-preference`.

---

## 5. The team

| Code stage key | Display name | Role label | Kind | Avatar | Halo |
|---|---|---|---|---|---|
| `research` (earnings specialist after v1.5.0) | **Pip** | Earnings Analyst | AI | `pip-earnings-analyst.svg` | #2a2340 |
| `research` (filings/news specialist after v1.5.0) | **Biscuit** | Filings & News Analyst | AI | `biscuit-filings-news.svg` | #2a2340 |
| `portfolio` | **Maple** | Portfolio builder | AI | `maple-portfolio.svg` | #2a2340 |
| `critic` | **Pickle** | Critic | AI | `pickle-critic.svg` | #2a2340 |
| `risk` | **Nugget** | Safety rules | **Rules, not AI** (always labeled) | `nugget-safety-rules.svg` | #1d2a31 |
| explainer (new) | **Bubbles** | Explainer | AI, read-only | `bubbles-explainer.svg` | #1a2a22 |
| `evidence` | Scanners | Code: finds and filters | code | radar icon | #1d2a31 |

- Put the names in one config mapping (`agents/desk/team.py`) so they can change without touching templates.
- Until Research is split, map `research` to Pip and show Biscuit dimmed as "Not active yet: joins when research is split (v1.5.0)".
- Until Bubbles exists (U7), hide Talk/Ask boxes rather than faking answers.

---

## 6. Screens

Top bar on every screen:
- Logo "Agent Desk" and the tabs.
- A mode badge when viewing non-official data.
- A status pill: "Paper only · real orders blocked" with a green dot. It turns red, with the reason, on any safety incident, tripwire latch or kill switch.

Tabs in order: **Today · Decision room · Portfolio · Road to money · Is the AI working? · Controls · Tweaks and health**.

### 6.1 Today (`/`; mockup `Main.dc.html`)
- **Header:** the date, "Last official run finished at HH:MM", and experiment day N.
- **What happened today:** Bubbles' story (after U7). Before U7, show a code-built summary from the latest `cycle_terminal` reason and outcomes.
- **Needs you:** approval card from `approval_inbox` (reuse today's POST `/decision` flow and CSRF). Show side, name, approximate $, most we can lose, chance it works, why, the Critic's worry, the exit plan, and the effective expiry (G5). After an answer, show the result.
- **Funnel:** checked → signal → tradable → read by AI → picked → survived Critic → sent to you. Counts come from U1 candidate records. Bars use a square-root scale.
- **Money cards:** AI account, no-AI arm (once it exists), VTI, and AI cost this year. Each carries a one-line meaning and shows "Not tracked yet" when the arm doesn't exist.
- **This week:** 5 day cards (title and cost) that can be selected, with a one-paragraph summary.
- **Is the AI helping yet?** A mini verdict linking to the scoreboard.
- **Live banner** (U6): "Team is working…" with the current stage and elapsed time.

### 6.2 Decision room (`/room`; mockup `Pipeline.dc.html`), the centerpiece
1. **Run picker and idea chips.** The run picker covers date and mode (official/learning). Chips list each candidate from the run, with a colored dot, the name and the final outcome.
2. **Team map** (SVG plus positioned nodes; coordinates are in the mockup's `pos` and `E` objects).
   - Flow: Scanners → Pip and Biscuit → Maple ⇄ Pickle ("one reply allowed") → Nugget → You.
   - A fund bypass runs Scanners → Nugget along the bottom.
   - Bubbles sits top-right with a dotted line labeled "listens to every hand-off".
   - Each node has a badge: `waiting` / `handled it` / `now` / `stopped it` / `not sure` / `your turn` / `listening`. Nodes that weren't involved are dimmed.
   - Edges light up cyan as the idea passes, and the current edge animates.
3. **Speech bar:** the current speaker's avatar, "From → To", and their message in quotes.
4. **Player:** Back, Play/Next/Replay, Show whole path, step dots, "Step X of Y". Keyboard: ←/→ step, Space play.
5. **Hand-off log:** the chat list for the selected idea. Clicking a line jumps the map to that step.
6. **Character card** (click an avatar):
   - Portrait, role, AI/rules label and motto.
   - Report card: calls scored, right, cost so far, honesty.
   - Gets work from / hands work to.
   - The model name and tokens for this run, from `api_costs`.
   - **Talk** (U7): Bubbles speaks as that agent, from that agent's records only, with a source line.
   - **Tune:** preregistered settings shown as "Rulebook X → test Y". Safety rules are locked. "Test my changes on the side" creates a challenger (§8).
7. **Fallback for historical runs without hand-offs:** show today's six-stage view (the existing `project_decision_room` output) restyled in the new theme, with the note "This run predates idea-by-idea records."

### 6.3 Portfolio (`/portfolio`; no mockup, use the same system)
- **What we own:** a donut per lane (cash vs holdings) from `paper_accounts`, plus holding tiles (the picker's avatar, value, gain/loss, days held, stop, time-exit countdown).
- **Value over time:** from `daily_values` paper valuations, with ▲ buy and ▼ sell markers from `fills`. Hover shows who decided and why. Toggles: no-AI arm, VTI, cash.
- **Position stories:** a timeline per closed position (entry → reviews → exit), the exit reason, and the result after costs.
- **Where the money came from:** P&L by scanner, by agent decision, and your yes/no effect.
- Tracks: show `with_approvals` by default, with a toggle for `agent_alone`.

### 6.4 Road to money (`/money`; mockup `Money.dc.html`)
- **Ready for real money?** One row per preregistered gate, with a met mark, a plain explanation, a progress bar and the current value, plus "N of 5 met" and a projected date labeled as an estimate.
- **Is the AI paying for itself?** AI-added profit vs the no-AI arm, AI cost, timing cost, and the net. Official records only.
- **Hits and misses:** ideas resolved at 20 trading days, with what we did, who decided, the result, a lesson and a verdict. Filters: All, Missed gains, Avoided losses, Bad buys.
- **Opportunity radar:** today's 30-minute scans as bars (violet where the AI woke) and earnings counts for the next 5 days.
- **What we learned this week:** 3 lessons (from the `lessons` table or Bubbles), each with "Test on the side".
- **Real-money ladder** (Paper → $50 → $100 → $250 copies → Review), plus a locked **copy-to-Robinhood card** that is instructions only ("I placed it" records the real fill), and **paper vs real fills**.
- **There is no code path from this screen to any broker write.**

### 6.5 Is the AI working? (`/scoreboard`; mockup `Scoreboard.dc.html`)
- Four test tiles: money, picking, honesty and cost.
- An all-arms value chart with legend toggles.
- A scanner leaderboard.
- An honesty chart (stated chance vs what happened, with n).
- Agent report cards using the team names.
- Choosing vs timing, your yes/no effect, and stop-rule progress. Reuse `eval/scoreboard.py` for the data.

### 6.6 Controls (`/controls`; mockup `Controls.dc.html`)
- **Safety bar:** Running/Paused/Stopped, Pause/Resume (existing `/control` flow), and a big **STOP everything** with an inline two-step confirm (no browser dialogs).
  - STOP engages the global kill switch: new buys are blocked; exits and safety sells still work.
  - Restart requires a recorded review. The existing incident latch still cannot be cleared by Resume.
- **Research a stock:** starts a *learning* run (separate budget, never official) and shows the estimated cost and remaining learning budget.
- **Risk style** (Careful/Normal/Bold) and **idea-source switches:** both create or update challengers only.
- **Budget and runs:** sliders limited to the approved build-week policy; show "most this week could cost" (never above the hard stop).
- **Side tests running:** progress, comparison with official, and **Promote**, which sends a new preregistration version for approval (never an instant switch).
- **Your phone:** notification preferences. Problems and safety alerts are locked on. Reuse the existing "Send test notification".

### 6.7 Tweaks and health (`/health`; mockup `Tuning.dc.html`)
- Suggested tweaks with the evidence behind them, and "Test it on the side".
- The dials explained: each preregistered value, shown with one plain sentence.
- System health:
  - broker proxy (8 of 8 read tools, 0 write);
  - Agentic account bounds and tripwire;
  - daily blocked-order test;
  - scheduler (`launchctl` state already read in `inbox_web.py`);
  - price freshness;
  - data feeds (news enabled/disabled);
  - AI budget by mode;
  - auth expiry;
  - notification delivery (`notification_deliveries`);
  - **config warnings G4–G6** until they are fixed.
- Rulebook history.

### 6.8 Live mode (U6)
- **Endpoint:** `GET /events`, a Server-Sent Events stream (same origin, so `connect-src 'self'` already allows it). Keep the handler thread-safe with `ThreadingHTTPServer`, send a heartbeat every 15s, and close cleanly on disconnect.
- **Events:** run started, stage started/finished, hand-off written, scan completed, card issued, safety state changed. Each event carries only IDs; the page fetches the rendered fragment or JSON from a read-only endpoint.
- **Decision room:** a pulsing LIVE badge plays hand-offs as they are written. **Today:** the "Team is working…" banner. **Radar:** bars appear as scans finish.
- If the stream drops, show "Live updates paused — reconnecting" and poll every 15 seconds. Never present stale data as live.

---

## 7. Data changes (milestone U1)

Follow the existing append-only pattern `(id, created_at, payload_json)` unless noted.

1. **`handoffs`** (new, fixes G1). Written by orchestration code at each stage boundary, never reconstructed.
   Payload: `cycle_id, mode, candidate_id, symbol, seq, from_actor, to_actors[], kind (pass|question|answer|stop|unsure|operator_decision), message (≤240 chars, public summary only), evidence_ids[], stage_key, created_at`.
2. **`mode` on every cycle record** (fixes G2). Add it to `cycle_events`/`cycle_runs` payloads and `api_costs`: `official|learning|what_if|diagnostic|test|recovery`. Existing rows with `trigger: manual` should be backfilled as `recovery` or `diagnostic`, with a note. All cost and result queries filter by mode.
3. **Candidate records.** Per cycle, write each candidate with `source_scanners[], final_outcome, stage_reached, stop_reason_code, stop_reason_text`. This feeds the funnel, chips and hits/misses.
4. **Tokens per stage** are already in `api_costs`. Surface them per agent card (helps G3).
5. **`challengers`**: config diff, start date, status, and comparison summary.
6. **`explanations`** (U7): Bubbles outputs with cited record IDs and the fact-check result.

Read-only JSON endpoints (all GET, same Host/CSP rules):
`/api/today`, `/api/runs?date=&mode=`, `/api/runs/<id>/candidates`, `/api/runs/<id>/candidates/<cid>/handoffs`, `/api/agents/<key>/card?run=`, `/api/portfolio`, `/api/money`, `/api/scoreboard`, `/api/health`.

Write endpoints (POST, CSRF + Origin):
- existing `/decision` and `/control`;
- new `/challengers` (creates a side test only);
- `/learning-runs` (starts a learning run within budget);
- `/stop` (engages the kill switch);
- `/explain` (U7; Bubbles, read-only inputs).

---

## 8. Side tests, Bubbles, "Show me" charts

- **Side tests (challengers):** same snapshots, same risk engine, run on paper in parallel, labeled everywhere, excluded from official results, reported after 8 weeks. They never edit `preregistration.yaml`. Promotion requires operator approval plus a new preregistration version.
- **Bubbles (U7):** read-only with no tools and a separate budget. Inputs are only the stored records in scope. Every factual sentence cites record IDs; code checks numbers and dates against those records, and a mismatch blocks the answer and shows the raw record instead. Bubbles powers the daily story, Talk answers (first person as the selected agent), the daily lesson and "Show me" charts.
- **"Show me" charts:** a plain-English request maps to one template from a fixed chart library (value-over-time, bars-by-category, stated-vs-actual, timeline, funnel, table) plus an allow-listed parameterized query. Code renders the chart; no model-written chart code or SQL. Every chart shows its query name and data time, and charts can be pinned to "My charts" on Today.
- **Learning mode:** tap-to-explain on terms and numbers from `agents/desk/glossary.yaml`, plus a daily "one thing to learn" card.

---

## 9. Milestones (each ends with tests passing and a short demo note)

| # | Milestone | Done when |
|---|---|---|
| U1 | Data: `handoffs`, `mode`, candidate records, `challengers`; backfill notes | Tests prove hand-offs are written at every stage boundary, modes are never summed, and old rows are labeled |
| U2 | Shell: theme, fonts, avatars, 7 routes, CSP additions, phone layout | All tabs render with JS off; CSP unchanged except `img-src`/`font-src 'self'` |
| U3 | Today + Decision room (map, player, log, character card without Talk) | A real run's candidates play step by step; historical runs fall back correctly |
| U4 | Portfolio + Road to money + Scoreboard | Every number traces to a query; missing arms say "Not tracked yet" |
| U5 | Controls + Tweaks and health | STOP / challenger / learning-run flows tested; G4–G6 visible as warnings |
| U6 | Live mode (SSE) | Hand-offs appear within 2s of being written; reconnect and fallback tested |
| U7 | Bubbles: story, Talk, lessons, "Show me" | Fact-check blocks a planted wrong number; no write tools available |

---

## 10. Acceptance checklist

- [ ] Seven tabs match the mockup screenshots on the dark theme; one column under 720px.
- [ ] Every page works with JS off. No inline styles or scripts (CSP intact).
- [ ] The Decision room plays real stored hand-offs; missing ones show "Not recorded". No chain-of-thought shown.
- [ ] Official / learning / what-if / diagnostic / test / recovery are never summed in any total or chart.
- [ ] STOP engages the kill switch with an inline two-step confirm, blocks new buys only, and needs a recorded review to restart. The incident latch still can't be cleared by Resume.
- [ ] Every side-test control creates a challenger only; nothing edits the preregistration without an approved new version.
- [ ] The copy-to-Robinhood card is instructions only; there is no code path to any broker write.
- [ ] Readiness, AI-pays-for-itself and hits-and-misses are computed from official records; projections are labeled as estimates.
- [ ] Health shows G4–G6 until fixed.
- [ ] Every AI-written sentence has record IDs; the fact-check blocks a planted mismatch.
- [ ] Live mode reconnects and falls back to polling; stale data is never shown as live.
- [ ] Keyboard navigation through the map and player; 44px targets; contrast ≥ 4.5:1; reduced motion respected.
- [ ] Existing guarantees in `tests/test_dashboard.py`, `tests/test_inbox_web.py` and `tests/test_decision_room.py` still hold (or are consciously replaced with equivalent tests).
