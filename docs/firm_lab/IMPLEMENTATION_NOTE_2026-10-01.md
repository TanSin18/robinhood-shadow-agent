# Firm Lab — implementation note (written before any Firm Lab code was wired anywhere)

Date: 2026-10-01, evening ET. Author: Claude. Order: "CLAUDE: EXECUTE THE FIRM LAB REBUILD NOW".

## What exists on the Mac (observed read-only at about 20:33 ET; nothing was restarted to look)

| Item | State |
|---|---|
| Installed Control A release | Release N (source `claude/ai-trader` @ `2d8ebc3`) |
| Installed fingerprint | `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876` (240 files) |
| Registration layers installed | v1.4.2 base, amendments v1.5.0, v1.5.1, v1.5.2, v1.6.0. No v1.7 file exists on the Mac. |
| Trading runner (`com.openai.robinhood-daily`) | Running; `daily.log` ticking; `cycle_runs` for 2026-10-01 is COMPLETED. Not restarted. |
| Dashboard | Overlay v19 files (`claude/ui-v10` @ `2dff2bd`) in `robinhood-dashboard-releases/agent-desk.3K4Fam`. Whether the dashboard service was restarted after v19 is not known. |
| Official (registered) database | `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db` |
| Options | Lane B: $500 per arm, all cash; new option buys paused under the signed v1.6.0 amendment |
| Stop / pause | No `STOP_TRADING` file |
| Paper book | Lane A: $25,000 start per arm; each arm holds 2.32209 SOXX, about $23,684 cash |
| Real orders | Blocked in code; Robinhood access is read-only and operator-controlled |

## Latest relevant commits

- Control A runtime line: `claude/ai-trader` @ `2d8ebc3` (installed as release N). Untouched by this work.
- Dashboard line: `claude/ui-v10` @ `2dff2bd` (overlay v19).
- Withdrawn, never installed: `claude/withdrawn-v1.7-draft` (the v1.7 draft; superseded by this order because Control A is frozen).
- This work: `claude/firm-lab-foundation`, cut from `claude/ui-v10` so the Control A runtime line is not edited.

## Things found while reading that the operator should know

1. The trial-log row 18 is already used (`ai_trader_fwd_v1`, withdrawn) and row 19 (`multi_asset_trend_10m_6sleeve`,
   run not before 2026-11-01) is pre-registered. The order calls the future Firm trial "Trial 18". The name is kept in
   the UI as ordered, but the log number needs an operator decision before anything is registered.
2. The research freeze until 2026-10-31 (trial 17's recipe) is in force. Nothing here supersedes it.
3. Tonight's 19:30 ET re-run of the advisory team notes failed for all five seats, and two Ask Bubbles questions at
   18:14 ET failed at once. Likely cause: the API key in the Keychain is not readable while the Mac is locked.
   Not verified. It does not touch trading (the advisory desk is off the trading path).
4. Control A labels each daily close with the New York date of the bar's 00:00 UTC start, which is one calendar day
   before the session. Control A is not changed. Firm Lab stores the correct `exchange_session_date`.

## Plan (this checkpoint only)

1. No-fill boundary and Official read-only wall, with tests, before anything else.
2. Firm Lab database in `robinhood-diagnostics/firm_lab/firm_lab.db`, mode `BUILD_OBSERVE` persisted.
3. One feature family (completed-session close, count, MA200, above_ma200, momentum_126d), point in time.
4. `control_a_baseline_counterfactual`, labelled DEVELOPMENT_ONLY.
5. Capability registry; VTI ruler; 70/30 ruler slot left DEFINITION PENDING.
6. Dashboard wording fixes and the read-only `/firm-lab` page, delivered by the dashboard-only overlay path.
7. Report in the required format and stop. No strategy work, no schedule, no trial.
