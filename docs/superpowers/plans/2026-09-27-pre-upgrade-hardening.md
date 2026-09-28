# Pre-upgrade hardening implementation plan

Goal: implement the approved twelve-point review with executable regression evidence.
Spec: `docs/superpowers/specs/2026-09-27-pre-upgrade-hardening-design.md`.
Execution: inline, on the existing feature branch, preserving unrelated files.

- [x] Correct scoreboard, configuration/model split, proposal GOOD IF, risk holdings/cash/volatility checks; add tests, run red, implement, run green.
- [x] Add Codex authenticated transport with strict read allowlist, SDK model adapter, typed outputs, usage ledger, daily reservation and sanitized evidence; test rejected writes before subprocess, failures and successful output.
- [x] Add transactional SQLite paper lanes and persistent approval inbox with a localhost YES/NO UI; test restart, expiry, replay and lane isolation. Explicit simultaneous-writer stress testing remains unclaimed; SQLite BEGIN IMMEDIATE serializes writes.
- [x] Connect daily research/portfolio/critic through risk to inbox; add durable daily scheduling and basic weekly reports with history; test full fixture integration and date boundaries.
- [x] Run live read-only verification, full regression/golden tests and independent review; resolve findings; deliver evidence, sample card and scoreboard and accurate operation instructions.

Review focus: model-supplied prices never become authoritative risk data; closing sells need actual held quantities; options require verified legs and bounded payoff; approvals need fresh risk revalidation; costs must distinguish estimates from billing; daily claims must survive restart; missing prices cannot be reported as zero returns.

Rulings during implementation:

- The prior get_accounts probe establishes connectivity only; full cycle proof remains outstanding.
- Codex CLI cannot guarantee a per-request dollar cap. Reserve conservative estimates, stop later calls on exhaustion, and report any overrun honestly; never claim a hard billing ceiling without provider enforcement.
- Preserve Agents SDK runtime through a custom Model adapter for CLI-backed inference.
- Approval execution follows the approved spec: proposal-time quote counterfactual with current holdings/cash/kill-switch revalidation. It excludes response-time price movement and is never presented as achievable execution.
- Options maximum loss is calculated from contract/leg structure, never accepted just because a model supplies a number.
- Long calls/puts are enabled for paper; spreads remain rejected. This is narrower than the design's expanded spread list, because untested leg execution must not be presented as implemented. Cost: fewer option candidates.
- A full authenticated read-only cycle (user's explicit acceptance requirement), plus offline safety tests, gates service installation. The design's extra three-live-cycle gate is not used; three back-to-back manual cycles would conflict with the one-per-day and small-budget requirements. Cost: no live market-hours execution proof yet.
- Scheduled attempts are at-most-once, including failure, rather than automatic retries; an unknown-cost failure holds its reservation. Cost: a failed day can be missed, but no hidden repeat spending.
- The launchd interval checks Eastern time in Python, so host timezone/DST changes cannot shift the requested 10:00 ET trigger. If the Mac is asleep through that minute, the cycle is missed rather than run late.
- Option expiry in paper is intrinsic-value cash settlement using exact expiry-session historical closes, not physical exercise/assignment. Cost: this is not a realistic Robinhood assignment simulation.

Final evidence: 142 tests passed on 2026-09-27, risk19/19, golden24/24. Full live cycle e5c2e607a6a947b292574301b43c57a0, 16 quotes/14 volatility series/3 agents, no trade on closed market. Three launchd services installed and loaded; localhost inbox and Phoenix HTTP200.

Final review: all six Important findings fixed with red→green tests in tests/test_review_regressions.py, then the full suite passed. No Critical findings. Extra pre-inception weekly-report regression passed; an installation-time invalid report is retained and labeled, not presented as performance.

Final: Ruling: failed daily claims remain consumed — prevent uncertain-cost retries and duplicate inference — cost: missed cycle after transient failure. User can investigate before a separately authorized recovery.
Final: minor (deferred): richer integrated weekly analytics (weekly returns, calibration, approval value, combined view, historical comparison) beyond the basic stored digest. Existing evaluator components remain separately tested.
Final: Ruling: reviewer declined network semantics and CLI enforcement — use captured successful read-only event evidence plus pre-process allowlist tests, not an actual real order attempt — cost: no guarantee beyond observed provider behavior.
Final: Ruling: work remains on the user's existing local feature branch; no merge, push, cleanup, or cloud publication was requested or performed.
