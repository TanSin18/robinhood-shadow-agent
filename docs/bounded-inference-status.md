# Registered inference — isolated branch only

## Implemented, offline verified

Final verification: **615 passed, 0 failed, 34 warnings** in the full suite;
bounded inference plus rehearsal group: **26 passed**. Warnings remain SDK
asyncio deprecations and the module-entrypoint runpy warning. Independent review
covered budget/accounting, isolation and model-policy boundaries; both important
findings were fixed with regression tests before this full-suite run.

`agents.bounded_inference` reads models, reasoning efforts, pricing and token
envelopes from the hash-verified preregistration. The module accepts only a
what-if database, not official/fixture/replay state. Configuration mismatches
are rejected, never silently overridden. No preregistration or installed runtime
settings were changed.

The adapter uses Responses input-token counting with the exact prompt, schema
and reasoning settings. Oversized inputs are rejected before generation. Calls
send hard output caps of 6000/3000/2000 tokens for Research/Portfolio/Critic,
including reasoning, and low/medium/medium effort. Tools are empty, tool choice
is none, storage is disabled and SDK retries are disabled. Unavailable models
fail rather than falling back.

Standard pricing is explicitly requested with `service_tier=default`; responses
with a different or missing tier are rejected. Failed-run reports retain known
usage estimates and count uncertain calls whose full bounds remain reserved.
These two protections were added after independent safety review and verified
with failing-then-passing regression tests.

Before the first generation, the private ledger reserves **$0.1696**: two full
registered attempts for each stage, under the **$0.20** what-if ceiling. Each
stage permits at most two explicit calls; this adapter does not itself retry.
Uncertain calls retain their maximum reservation. Process failure leaves the
whole run reservation intact. `close()` reconciles known usage plus full bounds
for uncertain calls. Cost is a registered uncached-price upper estimate, not a
claim of invoice reconciliation. No official monthly/annual ledger is changed.

Truncated output raises `OUTPUT_TRUNCATED_AT_TOKEN_CAP`; invalid usage, model
substitution, unexpected tool output and schema failure are rejected. No partial
output is accepted as a decision. Responses API references:

- https://developers.openai.com/api/docs/guides/reasoning
- https://developers.openai.com/api/docs/guides/token-counting

## Integration and boundary

`agents.rehearsal --registered-api` selects the new path. It is mutually exclusive
with the operator diagnostic cap waiver. A separate local diagnostic config must
already contain the three registered dated model IDs. API access is read only
from `OPENAI_API_KEY`; there is no Codex-auth/Keychain fallback, and the endpoint
is explicitly the OpenAI API. Do not paste credentials into chat or Git.

The offline integration test runs Research → Portfolio → Critic against a fake
API client and synthetic market evidence without a cap waiver. It verifies all
three request envelopes and unchanged official records. This is not live model
availability, live billing or a scheduled-service proof.

## Remaining before deployment

- Operator-configured API access and live availability/usage verification.
- Match installed model config through a separately reviewed deployment.
- Wire official per-lane budgets and failure reporting; this adapter is diagnostic-only.
- Complete Phase 0 installed-service proof. Do not enable Phase 1 from these tests.

No paid requests were made while building this path. The installed runtime and
dashboards remain unchanged. News and broader discovery remain gated.
