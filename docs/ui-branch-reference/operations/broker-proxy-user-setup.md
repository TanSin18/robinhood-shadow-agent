# Dedicated broker proxy user setup

Phase 0 requires a non-admin macOS user named `robinhoodproxy` and a shared group named `robinhoodreaders`. The operator and proxy users must both belong to that group. The proxy user's home and Keychain remain private; do not widen their permissions.

An administrator must create the user and group through macOS Users & Groups or approved administrative tooling, add both users to the group, and then sign in to `robinhoodproxy` once so that user can unlock its own Keychain. Codex does not create users, change group membership, unlock Keychains, or handle passwords/MFA.

Create `/Users/Shared/RobinhoodShadow/run` owned by `robinhoodproxy:robinhoodreaders` with mode `0770`, and `/Users/Shared/RobinhoodShadow/logs` private to the proxy user. Run the identity checker before installation. The socket itself must be `0660`, and the proxy additionally verifies the connecting operator UID with macOS peer credentials.

Keep paper activity paused during setup. Authorization is performed while signed in as `robinhoodproxy`; the main app never receives the OAuth token. See [Robinhood access revocation](./robinhood-access-revocation.md) for the required revoke/reauthorize drill.
