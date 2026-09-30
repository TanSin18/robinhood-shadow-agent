# Handoff: Wednesday 2026-09-30, 16:10 ET (Claude → any assistant)

Read this first. It is self-contained. Detailed chronology: `docs/review/CLAUDE_RETURN.md`.
Rules for every assistant: `AGENTS.md`, `CLAUDE.md`. **Do not start a second trading runner.**
The operator does all Robinhood login, MFA and consent on the Mac. Never ask for or print
credentials, codes, tokens or account numbers. Paper only: real orders are blocked.

## 0a. UPDATE 19:50 ET
- Proxy restarted by the operator 19:26 ET; authorization VALID again from 19:30 ET.
- **Release D INSTALLED 19:32 ET** (797 passed; backup release-rollback.78pvi9lh; fingerprint 5a441956…).
  Verified on the Mac: v1.5/1.5.1/1.5.2/1.6 all False now, all True at 2026-10-01 09:31 ET.
- Backfill done (238 calls, 2005→2026 for 15 ETFs; SOXX 2010, XLRE 2015, XLC 2018).
  **Backtest verdict NOT PROVEN** (docs/review/evidence/backtest-etf-rule-2026-09-30.md): registered rule
  0.4%/yr after tax vs VTI 8.3%; the live 10% drawdown latch (`peak_breaker_latched`, never cleared)
  froze buying in July 2010. Signal alone 1.7%/yr, Sharpe 0.20 vs 0.54. Independent re-implementation
  agrees. 252-session momentum looks better (≈VTI after costs) but is a post-hoc pick: shadow-test only.
- Nightly screen service install failed: Permission denied on /Users/Shared/RobinhoodShadow/launch
  (needs `sudo`). Operator asked to rerun with sudo.
- Follow-up found: Robinhood daily bars begin 00:00Z, so ET conversion labels each session one day
  early (live features are still correct: the 10:00 run used the prior session's close). Affects
  date-keyed lookups: option expiry-close settlement and the 20-session backstop count (±1).
  Fix in data parsing before options resume.
- Follow-up: the permanent 10% drawdown latch will eventually freeze the $25k book too; needs an
  explicit, registered reset rule.

## 0. UPDATE 19:30 ET

- **Robinhood read proxy DOWN since 16:25 ET** (maintenance log: authorization status `PROXY_UNAVAILABLE`
  on every check; last VALID ~16:20). The history backfill's first read at 16:21 got `UPSTREAM_READ_FAILED`
  (no incident, no writes). The operator must restart it from the `robinhoodproxy` macOS account:
  `launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-read-proxy`, then
  `../python/bin/python3 -B -E -s -m broker_proxy.revocation verify-reauthorized` from
  `/Users/Shared/RobinhoodShadow/private/current/app`. If AUTH_EXPIRED: redo drill step 5. Without it,
  Thursday 10:00 cannot read the market (fails safe, no trades).
- **v1.6.0 signed** by the operator 16:25 ET (answers: Lane A paper capital $25,000; effective
  2026-10-01 09:30 ET; 8% hard stop). Amendment `preregistration-amendment-v1.6.0.yaml` (sha 86c891cd…),
  code `agents/v16_policy.py`: capital rebase at the first v1.6 cycle (build-phase Lane A archived in
  `capital_rebases`), option buys paused, 15:50–15:58 ET protective exit inside the existing service tick.
- **Statistical promotion gate** `eval/promotion_stats.py` (200 decisions or 252 sessions, 90% block
  bootstrap above 0, official runs only). **Nightly S&P 500 screen service** `agents/nightly_screen.py`
  (16:50 ET weekdays, read-only, own store). Fix: no-AI arm now settles T+1.
- **Release D NOT YET INSTALLED.** Steps: `docs/review/RELEASE_D_TONIGHT.md` (manifest
  `release-2026-09-30d-manifest.json`, 17 files + v1.6.0 root file, verified against HEAD; cloud suite
  795 passed, 6 known environment failures). If it is not installed before 09:30 Thursday, v1.6 stays
  inert (the pinned file is absent on the Mac) and Thursday runs v1.5 as rehearsed.
- Dashboard overlay v7 (`claude/ui-decision-room-v2` @ `ae6d2ef`, Measurement panel) is already copied
  into the live release; it loads at the next inbox restart (release D step 1). Backup `.v6-20260930`.
- **Backtest** (`research/backtest_etf_rule.py`, 6 tests) is waiting for data: RELEASE_D step 4 runs the
  read-only backfill (needs the proxy), then run
  `python -m research.backtest_etf_rule --bars <B>/bars.csv --out <B>/report.json --md <B>/report.md`.

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
