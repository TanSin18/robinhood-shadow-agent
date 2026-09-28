# Robinhood access revocation

Keep paper activity paused throughout this drill. The operator—not Codex or an agent—performs Robinhood login, MFA, consent, disconnect confirmation, and reauthorization.

1. Verify that paper activity is paused before starting. In the private deployment,
   as `robinhoodproxy`, run `python3 -B -E -s -m broker_proxy.revocation begin` from
   the private `app` folder, using its sibling `python/bin/python3` interpreter.
   This verifies a real allowed read using the current, unexpired bearer without
   OAuth refresh. It records a private token fingerprint (never exported),
   timestamps and config/preregistration hashes. Do not use the older
   `scripts.robinhood_revocation_drill` CLI placeholder as live evidence.
2. In the Robinhood app, disconnect the Agentic Trading connection. If that control is unavailable or activity is unrecognized, contact Robinhood Support through the app.
3. Run the private module's `verify-revoked` action. The same previously working,
   still-unexpired bearer must receive HTTP 401/403. Expiry is checked again
   after the probe. A timeout, socket failure, malformed response, policy error,
   replaced token or token expiry is not proof. Do not rerun authorization yet.
4. Only after remote failure is proven, run `remove-local-credentials`. A durable
   deletion-in-progress state precedes deletion. Retry that same action after an
   interruption; it checks that tokens, timing metadata and registration are all
   absent. It cannot delete a replacement authorization by mistake.
5. As the `robinhoodproxy` user, run the authorization flow and complete Robinhood consent personally.
6. Run `verify-reauthorized`, requiring a different credential and a fresh allowed
   read. Separately verify the exact eleven-method, zero-write proxy greeting
   under the current config and preregistration hashes before passing the Phase 0
   capability gate. Drill completion alone is not scheduled-cycle proof.

Deleting local Keychain data does not revoke Robinhood access. The drill is complete only after both remote failure and a fresh post-authorization read are recorded.
