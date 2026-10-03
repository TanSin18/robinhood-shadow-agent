# Control A maintenance — Codex compatibility (prepared and proven, NOT installed)

Written 2026-10-03 for Checkpoint 4, section 2. Classification: **maintenance**. No strategy behaviour changes.
Follows `CODEX_PATH_2026-10-02.md` (the investigation).

Control A as installed is unchanged: release N, source fingerprint
`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876` (240 files), re-checked 2026-10-03 13:41 ET.
The trading runner was not restarted. Nothing was installed.

## The change (branch `claude/codex-path-fix`, commit `ca4aacf`, base = release N)

Four files, 148 lines added, 7 removed:

| File | Change |
|---|---|
| `agents/isolated_session.py` | `find_codex` / `require_codex`: an explicit path, then PATH, then both known app locations (the old `…/Resources/codex` and the current `…/Resources/codex-cli/bin/codex`). The hardening list passes `features.view_image=false` instead of `tools.view_image=false`. Nothing else in the list changes. |
| `agents/codex_bridge.py` | Uses `find_codex`; a missing executable raises `FileNotFoundError` before the guarded section, so it is never recorded as a safety incident. |
| `tests/test_installed_isolation.py` | Looks for the executable where it actually is. |
| `tests/test_codex_path.py` | Eight regression tests (below). |

Not touched: strategy code, preregistration, configuration, the read gateway, the proxy, the real-order block, the
notification allow-list.

## Why `features.view_image=false` is the right replacement

codex-cli 0.159.0 no longer recognises `tools.view_image` and says so with a `configWarning`. Control A treats every
unknown notification as an unexpected capability and stops; that guard is kept exactly as it is. The warning is
**not** whitelisted.

From the codex source at tag `rust-v0.159.0`:

* the feature key is `view_image` (`codex-rs/features/src/lib.rs`, stable, on by default);
* the image tool is registered only `if environment_mode.has_environment() && features.enabled(Feature::ViewImage)`
  (`codex-rs/core/src/tools/spec_plan.rs`);
* the strict-config message for the old key reads "Use [features].view_image to configure the image tool."

So the new key switches off the same tool the old key did, and the CLI accepts it without a warning.

## What stays enforced (unchanged)

`--strict-config`; `environments: []`; read-only sandbox; `approvalPolicy: never`; the tool-server inventory must be
empty and every inherited server is disabled by name; `features.apps`, `plugins`, `shell_tool`, `unified_exec`,
`multi_agent`, `tool_suggest` = false; `project_doc_max_bytes=0`; `web_search="disabled"`; and the turn guard, which
refuses any item other than the user message, the agent message and reasoning, and refuses every server request.

## Tests

| Where | What | Result |
|---|---|---|
| Cloud, runtime suite with the change | full suite | 872 passed, 1 skipped |
| Mac sandbox, staging tree `control-a-maint-staging-ca4aacf` | isolation subset | 28 passed, 1 skipped (the installed-Codex test cannot run there) |
| **Mac native, same staging tree, real codex-cli 0.159.0** (operator, 2026-10-03 13:23 ET) | isolation subset, including the installed-Codex test | **29 passed** |
| **Mac native, same staging tree** (operator, 2026-10-03 13:24 ET) | full suite | **873 passed, 0 failed** |

On 2026-10-02 the installed-Codex isolation test failed natively on the `configWarning`. With this change it passes:
the CLI starts, emits no warning, the fake tool server is filtered, and an unexpected server is still denied.

`tests/test_codex_path.py` covers: discovery at the new location; the relocation case; a clear error when the
executable is nowhere; no safety incident for a missing executable; a snapshot of the hardening list (so a setting
cannot be dropped silently); inherited servers disabled; `configWarning` never tolerated; an unexpected capability
still refused.

## If it were installed

Source fingerprint: `fe260b5103707e528e550bcea72b966756a7401e2496a93a8597805f98906dab` (241 files).
`scripts/release_install.py` would run the installed suite first and roll back on any failure. The staging tree
differs from the installed tree in four unrelated files (`broker_proxy/revocation.py`,
`config/broker-proxy.local.yaml`, `tests/test_proxy_revocation.py`, `tests/test_sanitized_drill_receipt.py`), which is
why the fingerprint above is computed from release N plus this change, not from the staging folder.

## Why it is not installed in this checkpoint

1. A release install is the operator's step, and the checkpoint says not to restart the trading runner unless a
   maintenance release absolutely requires it. Nothing that runs on a schedule uses Codex, so nothing requires it.
2. One review point remains open, and it is older than this change. codex-cli 0.159.0 has about 150 feature flags,
   roughly 50 on by default, and several of those are not named in Control A's hardening list (for example
   `image_generation`, `browser_use`, `computer_use`, `hooks`, `skill_search`, `realtime_conversation`,
   `remote_plugin`). Control A does not rely on naming them: with no environment, an empty tool inventory and the turn
   guard, any use of one stops the run as an unexpected capability, and the native isolation test passes. But the list
   was written for an older CLI. Whether to name the new default-on flags explicitly is a hardening decision for a
   release review, not something to slip into a path fix.

## Effect of leaving it uninstalled

* Scheduled Control A runs: none. They do not use Codex.
* `agents/rehearsal.py --operator-diagnostic-cap-waiver` would fail at start (file not found), without an incident.
* **The next Control A release install would roll back** on the installed isolation test until this change is part of
  it. Any future release should therefore include `ca4aacf`.
