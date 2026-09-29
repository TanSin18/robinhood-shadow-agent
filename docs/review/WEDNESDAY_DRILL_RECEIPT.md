# Wednesday drill / renewal preparation

Operator-selected window: **Wednesday 2026-09-30, after 16:30 America/New_York**
(20:30 UTC). No automatic job, consent, revocation or deployment is scheduled.
The reported expiry is Thursday 2026-10-01 13:00 ET; recheck provider metadata
before the drill. Do not wait until after expiry: expiry is not revocation proof.

## Receipt command — prepared, not installed yet

The branch adds `receipt` to `broker_proxy.revocation`. After that narrowly
reviewed helper change is separately approved and installed in the private
proxy bundle, the operator runs this **as the logged-in robinhoodproxy user**:

```sh
cd /Users/Shared/RobinhoodShadow/private/current/app
../python/bin/python3 -B -E -s -m broker_proxy.revocation receipt
```

It reads the existing local drill state and prints only its allowed status,
four drill timestamps and `receipt_generated_at`. COMPLETED requires all four
events in monotonic order. It does not contact Robinhood, access Keychain, refresh tokens,
modify state or prove a new drill. Missing evidence remains missing; no synthetic
receipt is generated. This command will not exist in the current installed
helper until that reviewed update is deployed. Do not run it from an operator
checkout or widen proxy file permissions to make it work.

## Operator-driven order that Wednesday

1. Verify the helper version, current authorization validity, exact proxy scope
   and an approved after-market maintenance/pause procedure.
2. As proxy owner, run existing `begin`; operator disconnects the connection
   personally in Robinhood. Run `verify-revoked` while the old token is unexpired.
3. Successful verification records `REMOTE_REJECTION_VERIFIED` from an actual
   authentication rejection. This is the implementation's equivalent evidence
   for the requested AUTH_REVOKED event, not an expired-token timeout.
4. Run `remove-local-credentials` only after verified remote rejection. The
   operator completes new login/consent through the established authorization
   flow; no credentials or verification codes go into chat.
5. Run `verify-reauthorized` and then the `receipt` command above. Confirm the
   read-only proxy's eleven-method inventory independently before rearming.
6. Paste only sanitized output into CODEX_STATUS. Codex records the timestamps,
   checks the gates and reports any blocker. Do not paste raw private state.

The receipt action alone does not reset a kill switch, rearm a tripwire or restart
a service. No automated consent and no duplicate runner. This document is a
preparation checklist, not proof the future drill has happened.

## Gate check after approved helper installation and the actual drill

The branch verifier requires a reviewed, sanitized receipt at
`outputs/revocation-drill-receipt.json`. Do not copy private state there.
After this verifier is separately approved/deployed, the Wednesday check is:

```sh
.venv/bin/python -m scripts.verify_operations --drill-not-before 2026-09-30T16:30:00-04:00
```

This checks the begun/revoked/removed/reauthorized event chronology and the
requested window, not just when an old receipt was reprinted. Scheduled-cycle
success cannot mask missing drill evidence. Code tests are not a performed drill.

## Installation and rollback preparation — still blocked on owner metadata

The operator-user read of `/Users/Shared/RobinhoodShadow/private/current` is
denied as expected. No attempt was made to bypass that boundary. Therefore the
exact current release target, manifest and rollback target have NOT been
verified; do not run a guessed copy or symlink replacement.

Before Wednesday 16:00 ET, obtain a sanitized owner-side inventory: current
release path, manifest hash, receipt-module hash, interpreter path and service
label, with no credential files or identifiers. Then pin the reviewed helper
commit/hash, stage an immutable private release preserving owner/group/modes,
verify that only the helper and its manifest entry changed, and record the old
release target. Present those resolved install commands for operator approval.
Installation must be after market close; no daytime service restart.

Rollback: restore the recorded previous release target atomically under the
proxy owner; restart only the affected proxy service if the approved install
required it; verify its eleven-read inventory and health. Never roll back token
or drill state, copy credentials, or automatically rearm the tripwire. Keep the
failed release for diagnosis. Exact runnable rollback commands depend on the
owner metadata above and are deliberately not invented here.
