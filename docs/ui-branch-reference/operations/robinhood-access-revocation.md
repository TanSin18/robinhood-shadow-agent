# Robinhood access revocation

Keep paper activity paused throughout this drill. The operator—not Codex or an agent—performs Robinhood login, MFA, consent, disconnect confirmation, and reauthorization.

1. Start the local drill. It latches the safety stop and records only timestamps and configuration hashes.
2. In the Robinhood app, disconnect the Agentic Trading connection. If that control is unavailable or activity is unrecognized, contact Robinhood Support through the app.
3. Return to the drill and verify that an allowed `get_accounts` read fails specifically as unauthorized or revoked. A timeout, socket failure, malformed response, or policy error is not proof.
4. Only after remote failure is proven, remove the dedicated proxy user's local Keychain tokens and dynamic client registration.
5. As the `robinhoodproxy` user, run the authorization flow and complete Robinhood consent personally.
6. Verify reauthorization with a fresh allowed read and the exact eleven-method, zero-write proxy greeting under the current config and preregistration hashes.

Deleting local Keychain data does not revoke Robinhood access. The drill is complete only after both remote failure and a fresh post-authorization read are recorded.
