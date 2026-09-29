# Scheduled API preparation — 2026-09-28

## Scope

Connect the Phase 0 official daily runner to the registered, bounded Responses
transport. This is not Phase 1 approval and is not a scheduled-cycle proof.
Preregistration v1.4.2 is unchanged. Real broker orders remain blocked.

## Implemented and verified

- Official adapter requires a live database and the current cycle claim.
- Rechecks claim ownership and the safety stop after token counting and before
  generation. A lost claim during counting causes zero generation calls.
- Uses the three dated registered models, registered reasoning settings and
  hard output caps; no model tools, fallback or automatic retry.
- Reserves the full two-attempt, three-stage envelope before generation;
  uncertain charges retain their conservative bound.
- Code-only runs do not retrieve an API credential or contact the model API.
- A disposable background job verified access to the existing OpenAI Keychain
  item without disclosing its value. This is not a reboot/unlocked-keychain guarantee.
- Isolated synthetic official-ownership integration exercises all three stages.
- Development suite: 624 passed. Independent focused review: 23 passed.
- Fresh read-only Robinhood preflight passed through the separate-identity proxy,
  exactly 11 methods, bounded-cash authorization path, zero broker writes.

## Deployment

The installed runtime receives the reviewed adapter and matching private model
configuration. Existing runtime/configuration files are backed up privately.
The installed suite must pass and its source/configuration-bound manifest must
be regenerated before restarting the daily and maintenance jobs. The broker
proxy and dashboard release are not replaced.

## Explicit remaining gates

1. An authenticated installed-service cycle under this exact code/configuration
   has not yet been recorded. A skipped schedule or isolated rehearsal does not
   satisfy this gate. Target: 2026-09-29 at 10:00 America/New_York.
2. Shared-call lane cost settlement still uses equal shares, while the frozen
   registration requires input-token-share attribution. This existing accounting
   gap remains unresolved. Do not declare Phase 0 complete even if the automated
   scheduled receipt check passes. Phase 1 remains blocked.
3. News and broader discovery remain outside this Phase 0 deployment. A valid
   no-AI/no-trade result must not be presented as a full research-system proof.

Keep the Mac connected to power and the operator session available. Weekday
wake is set to 09:50; AC sleep is disabled. These settings cannot guarantee
network availability or successful provider responses tomorrow.
