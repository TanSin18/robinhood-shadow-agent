# Release D — 2026-09-30 evening (v1.6 + measurement)

Manifest: `docs/review/release-2026-09-30d-manifest.json` (base `0062ee8`, installed fingerprint
`0a1726f0…d363`, 17 files + `preregistration-amendment-v1.6.0.yaml`).

What it ships (behaviour changes only from 2026-10-01 09:30 ET; paper only):
- v1.6 amendment (operator-signed 16:25 ET): Lane A paper capital $25,000 (build-phase ledger archived at the
  first v1.6 cycle), options buys paused, 15:50 ET protective exit (200-day break / ETF momentum / 8% stop).
- Statistical promotion gate (`eval/promotion_stats.py`), weekly report line.
- Nightly S&P 500 shadow screen service definition (`agents/nightly_screen.py`), installed separately (step 3).
- Research: `research/history_backfill.py`, `research/backtest_etf_rule.py`.
- Fix: the rules-only (no AI) paper arm now settles sale proceeds T+1 (it never did before).

## 1. Install (main user, Terminal)

```sh
P=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent; cd ~/.codex/worktrees/robinhood-live-rehearsal \
 && git fetch -q origin claude/continuation-2026-09-30 && git switch -q --detach FETCH_HEAD && git log --oneline -1 \
 && $P/.venv/bin/python scripts/release_install.py --primary $P --source . --manifest docs/review/release-2026-09-30d-manifest.json | tee /tmp/relD.json \
 && grep -q '"VERIFIED"' /tmp/relD.json \
 && $P/.venv/bin/python scripts/release_install.py --primary $P --source . --manifest docs/review/release-2026-09-30d-manifest.json --install \
 && launchctl kickstart -k gui/$(id -u)/com.openai.robinhood-inbox && sleep 3 && curl -s -o /dev/null -w "dashboard %{http_code}\n" http://127.0.0.1:8765/
```
Expect `VERIFIED`, then `INSTALLED` with the suite passing, then `dashboard 200`. `ROLLED_BACK` means nothing changed.

## 2. Dashboard
Already copied into the dashboard folder (overlay `ae6d2ef`, backup `agent-desk.3K4Fam.v6-20260930`).
Step 1's kickstart loads it: Checks & charts now opens with the Measurement panel.

## 3. Nightly S&P 500 screen service (needs a short pause)
Controls → **Pause**, then:
```sh
P=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent; $P/.venv/bin/python $P/scripts/install_shadow_services.py --install --service universe-screen
```
Expect `Installed application services.` Then Controls → **Resume** (required for Thursday's run).

## 4. Price history for the backtest (read-only; retry of the earlier command)
```sh
P=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent; B=/Users/tanmaysinnarkar/LocalProjects/robinhood-diagnostics/backtest; \
cd $P && $P/.venv/bin/python -m research.history_backfill --config $P/config/settings.local.yaml --official-database $P/data/agent.db --store $B/history.db --export $B/bars.csv
```
Claude then runs the backtest and writes `robinhood-diagnostics/backtest/report.json` (shown on Checks & charts).
