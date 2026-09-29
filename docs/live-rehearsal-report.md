# Isolated live rehearsal — September 28, 2026

## Latest result: three live model stages completed under operator exception

The operator approved waiving the diagnostic spending cap and proceeding with
the current runtime models. A new isolated run
`01362a8c955e4af8bfaa5ac7555ef611` completed in **60.15 seconds**:
live read-only collection → Research → Portfolio → Critic → final quote refresh.
All three model calls completed. Final collection retained 14 equity quotes
and 14 volatility series. The regular market session was closed, so the
execution/risk issuance branch did not run. News remained disabled.

Estimated API-equivalent cost: **$0.0481896**, not a verified API bill (transport
uses Codex authentication and the existing runtime pricing table). No cards or
fills were created. Official business-record digest and installed source
fingerprint remained unchanged. No services restarted.

This is labeled `diagnostic_noncompliant=true`, `cap_waiver=true`, and
`scheduled_proof=false`. It proves live orchestration with the current models,
not preregistered-model compliance, market-hours fills, or the scheduled gate.
The flag is opt-in per invocation, rejected for official runs, and does not
change config or preregistration. Without it the original cap guard remains.

Fresh verification after this change: **594 passed, 7 known baseline failures,
31 warnings**; rehearsal-focused tests **12 passed**. The same seven failures
and causes are listed below. Two added tests prove the waiver cannot apply to
official runs and that a three-stage diagnostic leaves business tables empty.

The sections below retain the preceding blocked attempt and transport audit.

## Partial proof, not a completed agent cycle

Live proxy collection and deterministic discovery completed in 35.74 seconds.
The AI gate found an eligible candidate, but stopped with
`HOLD_OPERATIONAL: REHEARSAL_MODEL_CAP_NOT_CERTIFIED`. The existing transport
cannot certify the registered $0.20 what-if ceiling with hard output-token caps.
No ceiling was relaxed, model substituted, or model call made. API cost: $0.

| Evidence | Result |
|---|---|
| Rehearsal run | `4a64a679135b4a8fb597516e96c2eda6` |
| Parent official run | `2e8ceaa588fa42d49a2a165bdca40b8f` |
| Quotes, including options | 537 |
| Volatility series | 14 |
| Quotes fresh within 60 seconds | 13 |
| Stale or future-dated quotes | 524 |
| Regular market session | Closed |
| News | Disabled, untested |
| Model stages / downstream risk | Not run |
| Cards / fills | 0 / 0 |
| Official business-record digest | Unchanged |

The configured universe remains 14 underlyings. Hundreds of option quotes do
not mean broader stock discovery. Freshness is timestamp-based, not proof of
tradability or execution quality. Overnight prices do not override session rules.
This rehearsal is not a scheduled-service receipt or a Phase 0 gate pass.

## Isolation and launch fix

Branch: `codex/live-readonly-rehearsal`. The installed runtime, dashboards,
services and preregistration were not changed. Official SQLite input uses
`mode=ro` and `query_only=ON`; paper states are held in memory. A fresh private
what-if database persists diagnostics and health checks only. API guards,
managed-connection authorization and SQL triggers reject claims, cards, fills,
scoreboard and lessons writes. Order history stays in health handling, not
model prompts or reports. Private output databases are excluded from Git.

The first two launches failed before data collection: running the module as
`__main__` created a second class identity rejected by the cycle's isolation
guard. The entry point now calls the canonical module. A failing-then-passing
regression test covers this; the isolation guard was not weakened.

Installed source fingerprint verified unchanged:
`81d8038cfcab12fe650112ad0a205e21706c21a61fbdac87935d2363c6b6414a`.

## Tests and accepted baseline failures

Full suite: **592 passed, 7 failed, 28 warnings**.
Rehearsal suite: **10 passed**.
Clean export baseline: **582 passed, the same 7 failed**.
The operator approved continuing while documenting these failures. The full
suite is not green. These are not the older UI branch's 13 collection errors.

| Existing failing test | Cause |
|---|---|
| `test_config_and_schemas.py::test_default_config_is_stage_one_paper_only` | Assumes private Tailnet URL; export template intentionally uses loopback. |
| `test_config_and_schemas.py::test_installed_service_config_uses_private_phone_dashboard_url` | Private `settings.local.yaml` absent. |
| `test_inbox_web.py::test_exact_configured_tailnet_host_and_https_origin_are_allowed` | Assumes HTTPS Tailnet; export template uses loopback HTTP. |
| `test_operational_readiness.py::test_configuration_fingerprint_is_stable_across_processes` | Private local settings absent. |
| `test_operational_readiness.py::test_verifier_cli_reports_missing_evidence_without_writing_account` | Private local settings absent. |
| `test_private_proxy_bundle.py::test_bundle_has_no_execution_adapters_or_operator_symlinks` | Private `broker-proxy.local.yaml` absent. |
| `test_private_proxy_bundle.py::test_bundle_rejects_python_symlink_to_operator_home` | Missing proxy config fails before the intended symlink assertion. |

Warnings comprise 27 SDK asyncio deprecations and one runpy warning from the
entry-point regression test. No private settings were copied to make tests pass.

## Next permitted work

Certify a bounded inference transport before another AI-stage rehearsal. Do
not bypass the registered cap. Then repeat with current data and unchanged risk
gates. The installed scheduled proof remains separate. News, broader discovery,
Phase 1 and a complete live Research/Portfolio/Critic cycle remain unproven here.

## Follow-up transport audit — September 28, 2026

The installed `codex-cli 0.154.0-alpha.6.2` generated its experimental JSON
protocol schemas locally. Neither `TurnStartParams` nor `ThreadStartParams`
exposes an explicit maximum-output-token field. A schema-bundle search found
no `max_output_tokens`, `maxOutputTokens`, `output_token_limit`, or
`model_max_output` field. This does not establish that arbitrary configuration
overrides enforce a limit; no undocumented override was used. The existing
bridge reserves an estimate and reconciles usage after completion, which is
not a hard per-call cap. No inference was dispatched during this audit.

Runtime configuration still names `gpt-5.6-luna` for Research and
`gpt-5.6-terra` for both Portfolio and Critic. The preregistration instead pins
`gpt-5.4-nano-2026-03-17`, `gpt-5.4-mini-2026-03-17`, and
`gpt-5.4-2026-03-05`, respectively. Runtime alignment is unfinished, not a
reason to silently amend the registration or claim compliance.

Recommended next path, pending operator approval for separate API access:
use the registered Responses API transport in this isolated branch, with the
registered model IDs, input limits, output limits including reasoning, no model
tools, disabled SDK automatic retries, and reservation before dispatch. Treat
token-cap truncation as its own failure, never a partial valid decision.
Verify actual model availability before sending research data. Keep official
runtime, services and preregistration untouched.

Official documentation confirms that Responses `max_output_tokens` bounds
reasoning, visible output and formatting tokens, and that exhaustion returns
an incomplete response:
https://developers.openai.com/api/docs/guides/reasoning

No `OPENAI_API_KEY` is present in the current process environment. This is not
a claim that no credential exists elsewhere; no credential stores were searched
or copied. Operator setup must happen locally, never by pasting a key into chat.
This follow-up changed documentation only; prior test counts remain historical
results of the immediately preceding rehearsal, not newly rerun results.
