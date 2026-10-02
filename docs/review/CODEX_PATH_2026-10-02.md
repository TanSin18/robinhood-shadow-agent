# Codex executable path — investigation, 2026-10-02

Control A was not changed. Fingerprint before and after: `901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
The trading runner was not restarted.

## What happened

The ChatGPT desktop app updated itself between 2026-10-01 22:43 ET and 2026-10-02 10:24 ET (now version 26.928.20755).
The update moved the Codex command-line executable:

| | Path |
|---|---|
| Before | `/Applications/ChatGPT.app/Contents/Resources/codex` (no longer exists) |
| Now | `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex` — a launcher script that starts `codex-cli/CodexCLI.app/Contents/MacOS/codex`; reports `codex-cli 0.159.0` |

`codex` is not on PATH: not in the operator's shell, and not on the PATH the launchd jobs get
(`/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`).

## What Control A does

`agents/codex_bridge.py` and `agents/isolated_session.py` resolve the executable as: `codex` on PATH, else the old fixed
path. Today that resolves to the old path, which is not a file. **The fallback is stale.**

Who uses the executable:

| Path through the code | Uses Codex? |
|---|---|
| Scheduled runs of `com.openai.robinhood-daily` (the registered desk rule) | No AI at all on most days (`AI_NOT_NEEDED`) |
| Scheduled runs when the AI gate does invoke | No. `configured_scheduled_bridge` uses the registered API path (`ScheduledInference`), not Codex |
| Brokerage reads | No. The read gateway and private proxy |
| Analyst desk, AI-trader hook, Ask Bubbles | No. The API |
| `agents/rehearsal.py` with `--operator-diagnostic-cap-waiver` | **Yes** (`CodexBridge`) |
| `tests/test_installed_isolation.py` (isolation evidence) | **Yes** |

## Is it only a test assumption, or a real risk?

* **Scheduled trading runs: not affected.** Today's 10:00 run completed after the app update. The last scheduled AI
  inference recorded in the database is from 2026-09-29, on the API path.
* **A waiver rehearsal through Codex would fail today**, at process start, with a file-not-found error. Nothing is
  recorded as an incident.
* **The next Control A release install would roll back.** `scripts/release_install.py` runs the installed test suite
  and rolls back on any failure; `tests/test_installed_isolation.py` now fails on this Mac. This is the real
  operational consequence, and it is independent of trading.

## A path-only fix is not enough

The overlay copy of the isolation test was pointed at the relocated executable and run natively (fake tool server, no
model call, no brokerage read):

* tool filtering still works, and an unexpected server is still denied;
* the plain session then fails: codex-cli 0.159.0 emits a `configWarning` — "`tools.view_image` is ignored" — and
  Control A treats any unknown notification as an unexpected capability and stops. That is the guard working: one of
  the hardening settings Control A passes is no longer recognised by this CLI version.

So with only the path corrected, a Codex run would start, hit that warning, and be recorded as an
`UNEXPECTED_CAPABILITY` safety incident (in a rehearsal, on the rehearsal copy). Today it fails earlier and quietly.
Fixing the path alone would make that case louder, not working.

## What was prepared, and what was not done

* Prepared, **not installed**: branch `claude/codex-path-fix`, commit `9548ff5` (base: release N). Path resolution only:
  explicit path, PATH, then both known locations; a missing executable raises the same `FileNotFoundError` as before
  with a message naming what was checked, and is never recorded as a safety incident. Four new tests; runtime suite
  868 passed, 1 skipped in the cloud. Files: `agents/isolated_session.py`, `agents/codex_bridge.py`,
  `tests/test_installed_isolation.py`, `tests/test_codex_path.py`.
  Source fingerprint if it were installed: `95d2cbc0dad12bff57b4e2a3d8d1fa56dbb5cc42c9fcb2efbd914c9b40d9e066` (241 files).
* **Recommendation: do not install it on its own.** It belongs in a release that also brings the isolation settings in
  line with codex-cli 0.159.0 (how image viewing is disabled in that version), reviewed as a safety change, not a path
  change. That was outside this instruction and was not attempted.
* In the dashboard overlay only (not Control A): `agents/desk/codex_locator.py`, a read-only diagnostic
  (`python -m agents.desk.codex_locator`), with tests for discovery, stale-fallback detection and the not-found error;
  and the overlay isolation test now looks for the executable where it actually is.

## Would an AI-required Control A run succeed today?

* A scheduled run that needs AI does not use Codex, so this problem does not stop it. Whether the API call itself
  would succeed was not tested (no call was made); the failed Ask Bubbles calls of 2026-10-01 18:14 were not
  investigated, as instructed earlier.
* A Codex-based run (waiver rehearsal) would not succeed today, and would not succeed with the path alone fixed.
