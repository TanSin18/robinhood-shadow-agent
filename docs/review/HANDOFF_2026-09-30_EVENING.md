# Handoff: Wednesday 2026-09-30, 16:10 ET (Claude → any assistant)

Read this first. It is self-contained. Detailed chronology: `docs/review/CLAUDE_RETURN.md`.
Rules for every assistant: `AGENTS.md`, `CLAUDE.md`. **Do not start a second trading runner.**
The operator does all Robinhood login, MFA and consent on the Mac. Never ask for or print
credentials, codes, tokens or account numbers. Paper only: real orders are blocked.

## 1. What is live on the operator's Mac right now

| Piece | Where | State |
|---|---|---|
| Trading runtime (installed copy, not a git checkout) | `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent` | Release C installed 16:00 ET: source `0062ee8` (manifest `docs/review/release-2026-09-30c-manifest.json`), 771 tests passed, fingerprint `0a1726f0…`. Rollback backups: `../release-rollback.{clgfw0j3,2zwyvqe1,…}` |
| Rules | `preregistration.yaml` (v1.4.2 root, unchanged) plus signed amendment layers `preregistration-amendment-v1.5.0.yaml`, `-v1.5.1.yaml`, `-v1.5.2.yaml` | All three switch on at **2026-10-01 09:30 ET** (verified on the Mac: False now, True at 09:31) |
| Local config | `config/settings.local.yaml` | 23 tickers (8 original ETFs + 6 stocks + 9 SPDR sector ETFs). Original kept as `settings.local.yaml.before-sector-etfs`. Never commit this file |
| Dashboard (port 8765) | `/Users/tanmaysinnarkar/LocalProjects/robinhood-dashboard-releases/agent-desk.3K4Fam` (UI overlay; loads the runtime above for everything else) | UI = git `claude/ui-decision-room-v2` @ `abe080d` (desk and static files only). Backups `agent-desk.3K4Fam.{before-v2,v2,v3,v4,v5}-20260930`. Service `com.openai.robinhood-inbox` |
| Robinhood connection | proxy under macOS user `robinhoodproxy` | Re-authorized 15:26 ET after the revocation drill (receipt `outputs/revocation-drill-receipt.json`). Old token expiry problem solved |
| Paper activity | the dashboard's Controls | **Running** (resumed 15:38 ET). No pending cards, no incidents |

## 2. Git branches (github.com/TanSin18/robinhood-shadow-agent)

- `claude/continuation-2026-09-30`: **the runtime source of truth.** Everything installed, plus docs and evidence. `etf-exit` and `universe-screen` are merged in.
- `claude/ui-decision-room-v2`: Agent Desk UI (based on `ui/agent-desk` 7c80fd6). Live overlay = `abe080d`.
- `claude/universe-screen`, `claude/etf-exit`: feature branches, already merged.
- Codex branches: untouched.

## 3. What happens Thursday 2026-10-01

- 09:30 ET: v1.5 turns on.
  - Desk-rule ETF entries, fractional shares, 23 tickers, decision capsules.
  - The ETF exit rule (v1.5.1) and the AI-stock backstop exit (v1.5.2).
- 10:00 ET official run. Expected from the rehearsals (`docs/review/evidence/full-rehearsal-v15-*.json`):
  - `DESK_ENTRY` SOXX: agent_alone and deterministic_no_ai fill about 0.0449 shares; the with_approvals card is PENDING (the operator answers YES or NO).
  - No AI unless a stock qualifies.
  - Run tag: "Official · v1.5 · Counts toward results".
- **10:30 ET check (read-only):**
  - status COMPLETED, capsule_status RECORDED, option_screen recorded, 23-ticker collection, accounting SETTLED, no incidents
  - the dashboard shows it tagged Official
  - update this file and CLAUDE_RETURN

  (A reminder is scheduled in Claude's session only; another assistant must do this itself.)
- The readiness blocker left is "fresh scheduled full cycle", which the run clears.

## 4. How things work (for a new assistant)

- **Selling / exits** (`agents/etf_exit.py`, hooked in `run_cycle` after entries on both paths):
  - ETFs: sold when close ≤ 200-day average or 126-day momentum ≤ 0. Immediate arms sell; with_approvals gets a SELL card.
  - AI-bought stocks: the AI reviews them daily. Backstop sells on a 200-day-average break or at 20 completed sessions since the last buy.
  - Options: AI sells, or they settle at expiry.
  - ETF holdings no longer wake the AI (ETF AI voting is forbidden in v1.5).
- **Run categories** (UI `agents/desk/run_category.py`): Build phase (before Oct 1 09:30), Official, Scheduled, Manual re-run, Budget override, Interrupted, Unconfirmed. Only clean scheduled live runs after 09:30 Oct 1 count.
- **Dashboard pages:** Today · Portfolio (real Agentic snapshot next to paper) · Approvals/History/Controls (operational `/legacy`, same look) · Decision room (flow, inspector, run log) · Checks & charts (all checks, strategy matrix, charts, options screen, AI model/tools).
- **Rehearsal (market hours, disposable):** `python -m agents.rehearsal --official-database … --config … --output-dir <new dir> --v15-preview`. Keep temporary configs **out of `config/`** (they change the source fingerprint and the installer refuses).

## 5. Release procedure (operator runs it; after the close unless the operator overrides)

1. Build the manifest from the installed base:
   `scripts/build_release_manifest.py --base <installed source commit> --before-fingerprint <installed fingerprint> --amendment <each root amendment> --out docs/review/release-…-manifest.json`
2. The operator runs, in the main user's Terminal, from `~/.codex/worktrees/robinhood-live-rehearsal` (fetch the branch, detached):
   - `release_install.py …` (dry run, must print VERIFIED)
   - then the same with `--install` (prints INSTALLED, or ROLLED_BACK automatically)
   - then `launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox`
3. UI-only changes:
   - Pack `git diff --name-only 7c80fd6..HEAD` from the UI branch, **excluding tests/ and agents/dashboard_view.py**.
   - Extract with `tar --overwrite` into a copy (`agent-desk.v2-staging`), render every route against the live DB, back up the live dir, extract into `agent-desk.3K4Fam`.
   - Restart the inbox service.

## 6. Known gaps and follow-ups (ranked)

1. **S&P 500 screen: shadow only.**
   - First night: drill checklist step 7c (downloads SPY/IVV holdings, builds the universe, fetches the first 120 histories).
   - Still to build: a nightly launchd job, the Checks page "Universe screen" section, the morning shortlist hookup.
   - Then at least 5 clean nights and a v1.6 amendment to activate. Design: `docs/superpowers/specs/2026-09-30-universe-screen-design.md`.
2. **revocation.py divergence.** The primary's `broker_proxy/revocation.py` (ba0db784…) and the proxy app's copy have no `receipt` action; the repo's does (c83d00a9…). Tonight's receipt was built with the repo's `receipt()` from operator-pasted drill output. Reconcile both installs.
3. **Portfolio real-account detail.** Buying power and position names are not recorded, only cash, quantities and order counts from the tripwire snapshot. Adding them needs a runtime change.
4. **Corporate-action exclusions with `instrument: null`** (3 on Sep 30). Trace the source in `data/corporate_actions.py`.
5. **Options lane is structurally idle** at $500: SOXX calls cost more than a lane. A broader universe with cheaper names is the real fix (item 1).
6. `outputs/rehearsal-configs/settings.rehearsal23.local.yaml` (temporary; the operator can delete it).

## 7. Evidence index (`docs/review/evidence/`)

- `desk-rehearsal-2026-09-30-1.json`: desk path, live
- `full-rehearsal-v15-2026-09-30-1432.json`: full cycle, 14 tickers
- `full-rehearsal-v15-23tickers-2026-09-30-1450.json`: full cycle, 23 tickers
- `drill-2026-09-30.json`: revocation/reauthorization drill COMPLETED

Manifests: `docs/review/release-2026-09-30{,b,c}-manifest.json`.
