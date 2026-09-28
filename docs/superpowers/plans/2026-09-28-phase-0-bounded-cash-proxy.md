# Phase 0 Bounded-Cash Read Proxy Implementation Plan

> **For the implementer:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task in the current workspace. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-scope zero-cash fallback with the operator-approved $1,200 bounded-cash fallback while confining Robinhood OAuth to an eleven-method read proxy running as a dedicated macOS user, classifying broker-state changes, monitoring authorization expiry, and proving revocation and re-authorization before the Phase 0 scheduled-cycle gate.

**Architecture:** A dedicated `broker_proxy` process runs as the non-admin `robinhoodproxy` macOS user and alone imports OAuth storage and Robinhood MCP transport. Its token and files live in that user's Keychain/home. The operator-user application reaches eleven preregistered reads through a `robinhoodreaders` group socket while the server admits only the registered operator UID. The main application performs bounded-cash, authorization-status, and broker-state tripwire checks on redacted read results, but has no OAuth, Keychain, or remote-MCP object. SQLite stores protected snapshots, acknowledgements, incident state, and redacted revocation receipts; reports expose only booleans, reason codes, timestamps, and hashes.

**Tech Stack:** Python 3.14, Pydantic, MCP Python SDK, macOS Keychain via `keyring`, Unix-domain sockets, SQLite, `launchd`, pytest, Pushover.

**Spec:** `docs/superpowers/specs/2026-09-28-intelligent-agentic-investment-organization-design.md`

## Global Constraints

- Preregistration version is `1.4.1`; Phase 1 remains blocked.
- Stage 1 is paper/shadow only; no real order, cancel, exercise, transfer, deposit, withdrawal, or settings mutation may be dispatched.
- The fallback is `full_scope_bounded_cash_fallback` with `max_agentic_cash_usd = 1200.00`.
- The bounded predicate is `0 <= cash <= 1200.00` and `buying_power == unleveraged_buying_power == cash`, with finite provider values.
- The main process and agent processes never receive OAuth tokens and never instantiate or import the Keychain OAuth store or remote MCP client.
- The proxy runs as `robinhoodproxy`; its files and Keychain item are unavailable to the operator user. The socket parent is `robinhoodproxy:robinhoodreaders` mode `0770`, the socket is mode `0660`, and peer authorization accepts only the registered operator UID.
- The proxy exposes exactly eleven preregistered reads: the original market/account reads plus equity, option, and crypto order histories used only by the tripwire.
- Reports, dashboard records, notification bodies, logs, and revocation receipts contain no balances, quantities, cost basis, account identifiers, tokens, or token hashes.
- An in-cap cash increase with unchanged positions/orders records `ACCOUNT_CASH_INCREASE_BENIGN` without paging or latching. A cash decrease, position change, new/changed order activity, or above-cap cash pages through Pushover, engages the persistent global kill switch, creates no model call/card/fill, and requires explicit operator acknowledgement to rearm.
- Stored authorization expiry pages once at three days and one day remaining; refresh failure pages immediately; expired authorization returns `HOLD_OPERATIONAL: AUTH_EXPIRED` before discovery or inference.
- Robinhood login, MFA, consent, disconnect confirmation, and re-authorization are performed only by the operator; no password or verification code is requested.
- A real installed-service scheduled cycle remains the final Phase 0 proof; interactive reads are diagnostic only.

## Review Focus

- **Stale or hostile socket path:** installation and startup must reject symlinks/non-sockets, remove only a proxy-owned stale socket, preserve `0770`/`0660` group access, and reject every peer UID except the registered operator.
- **Identity boundary:** tests run the client and server under distinct effective identities or an equivalent kernel-credential harness, prove operator denial on the proxy Keychain/home, and prove an unrelated UID cannot use the socket even if it can name the path.
- **Oversized or malformed frames:** requests above 64 KiB and responses above 8 MiB, invalid JSON, duplicate fields, unknown methods, and truncated frames must fail closed without MCP dispatch.
- **Concurrent or stacked incidents:** acknowledging one tripwire event must not clear another unresolved incident, a user-owned pause, or a changed latch file.
- **Refresh after remote revoke:** a refresh-token attempt must not make the post-disconnect proof look successful; the proof requires an allowed live read to fail before local credential deletion.
- **Partial re-authorization:** client metadata without a usable token, a token without the exact effective read inventory, or a proxy greeting from a different config/preregistration hash must not complete the drill or Phase 0 gate.
- **Expiry races:** a refresh cannot reset warning deduplication for the old authorization; expiry is calculated from the time the proxy stores each provider token, and expired tokens fail before an upstream read.

---

### Task 1: Freeze v1.4.1 in the runtime and split main versus proxy configuration

**Files:**
- Modify: `agents/preregistration.py`
- Modify: `config/loader.py`
- Modify: `config/settings.yaml`
- Modify: `config/settings.local.yaml`
- Create: `broker_proxy/__init__.py`
- Create: `broker_proxy/config.py`
- Create: `config/broker-proxy.yaml`
- Create locally, never commit: `config/broker-proxy.local.yaml`
- Modify: `.gitignore`
- Modify: `tests/test_preregistration_phase0.py`
- Modify: `tests/test_config_and_schemas.py`
- Modify: `tests/test_robinhood_oauth.py`

**Interfaces:**
- Produces: `Phase0Registration.max_agentic_cash_usd: Decimal` and `Phase0Registration.allowed_fallback_path: Literal["full_scope_bounded_cash_fallback"]`.
- Produces: `BrokerProxyConfig(server_url, callback_url, keychain_service, requested_scope, socket_path, proxy_user, socket_group, operator_uid)` loaded only by proxy/authorization entry points.
- Produces: main `AppConfig.broker_proxy_socket: Path`; removes `AppConfig.oauth` entirely. The main config contains no proxy Keychain identifier or proxy-private path.
- Consumes: canonical SHA-256 of the amended committed `preregistration.yaml` (`c03b7b87a95f607a404bde53dac9c9a31b4b5fddeebfaa2c65c472d34b68956f`), never the superseded draft hash.

- [ ] **Step 1: Write failing preregistration and configuration-separation tests**

```python
def test_phase0_registration_exposes_bounded_cash_policy(tmp_path):
    registration = load_phase0_registration(Path("preregistration.yaml"))
    assert registration.version == "1.4.1"
    assert registration.allowed_fallback_path == "full_scope_bounded_cash_fallback"
    assert registration.max_agentic_cash_usd == Decimal("1200.00")

def test_main_config_has_socket_but_no_oauth_or_keychain_identifier():
    config = load_config("config/settings.yaml")
    assert config.broker_proxy_socket == Path("data/runtime/robinhood-read.sock")
    assert not hasattr(config, "oauth")
    assert "keychain" not in json.dumps(config.model_dump(mode="json")).casefold()
```

The production break these tests catch is accepting a different preregistration or leaving credential coordinates available to main-process configuration.

- [ ] **Step 2: Run the tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_preregistration_phase0.py tests/test_config_and_schemas.py tests/test_robinhood_oauth.py`

Expected: failures naming version `1.4.0`, missing bounded fields, and the still-present `AppConfig.oauth`.

- [ ] **Step 3: Implement the typed split**

Update `agents/preregistration.py` to validate version `1.4.1`, the amended canonical hash, fallback literal, and exact `max_agentic_cash_usd == 1200.00`. Move `OAuthConfig` out of `config/loader.py` into `broker_proxy/config.py`; main settings retain only:

```yaml
broker_proxy_socket: data/runtime/robinhood-read.sock
```

Proxy settings contain the official endpoint, callback, requested scope, Keychain service, and the same socket path. Add `config/broker-proxy.local.yaml` to `.gitignore` before creating the local copy.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_preregistration_phase0.py tests/test_config_and_schemas.py tests/test_robinhood_oauth.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/preregistration.py config/loader.py config/settings.yaml .gitignore broker_proxy config/broker-proxy.yaml tests/test_preregistration_phase0.py tests/test_config_and_schemas.py tests/test_robinhood_oauth.py
git commit -m "feat: activate bounded cash preregistration"
```

Do not add `config/settings.local.yaml` or `config/broker-proxy.local.yaml` if either contains local identifiers.

### Task 2: Build the exact-eleven cross-user Unix-socket read proxy

**Files:**
- Create: `broker/read_contracts.py`
- Create: `broker/proxy_client.py`
- Create: `broker_proxy/oauth.py`
- Create: `broker_proxy/mcp_client.py`
- Create: `broker_proxy/protocol.py`
- Create: `broker_proxy/server.py`
- Modify: `agents/market_reader.py`
- Modify: `scripts/authorize_robinhood.py`
- Modify: `scripts/diagnose_robinhood.py`
- Delete after consumers migrate: `broker/oauth.py`
- Delete after consumers migrate: `broker/mcp_client.py`
- Modify: `broker/policy.py`
- Create: `tests/test_broker_proxy.py`
- Modify: `tests/test_mcp_client.py`
- Modify: `tests/test_robinhood_oauth.py`
- Modify: `tests/test_market_reader.py`
- Modify: `tests/test_direct_read_gateway.py`

**Interfaces:**
- Produces: `READ_METHODS = frozenset({"get_accounts", "get_portfolio", "get_equity_positions", "get_equity_quotes", "get_equity_historicals", "get_option_chains", "get_option_instruments", "get_option_quotes", "get_equity_orders", "get_option_orders", "get_crypto_orders"})`, `REQUEST_MAX_BYTES = 65_536`, `RESPONSE_MAX_BYTES = 8_388_608`, and method-specific argument/cardinality limits.
- Produces: `BrokerProxyClient(socket_path).open()`, `.authorization_evidence()`, `.list_remote_tools()`, `.call_read(name, arguments)`, `.close()` matching the existing effective-gateway client surface. The first two are local projections of immutable greeting metadata, not callable socket methods; the only broker operations accepted after the greeting are the exact eleven reads.
- Produces: greeting fields `protocol_version`, `selected_path`, `granted_scope_names`, `keychain_retrieval`, `remote_catalog_hash`, `effective_read_tools`, `effective_write_tool_count`, `preregistration_hash`, and `config_hash`—never secrets or account data.
- Consumes: proxy-only `KeychainOAuthStorage` and proxy-only remote `RobinhoodMCPClient`.

- [ ] **Step 1: Write failing protocol and isolation tests**

Use a real temporary Unix socket and a fake upstream read transport. The critical tests are:

```python
@pytest.mark.parametrize("method", KNOWN_WRITE_NAMES | MALFORMED_VARIANTS)
def test_proxy_rejects_every_non_allowlisted_method_before_upstream(tmp_path, method):
    server, upstream = running_proxy(tmp_path)
    response = raw_request(server.socket_path, {"id": "1", "method": method, "arguments": {}})
    assert response["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert upstream.calls == []

def test_main_proxy_client_completes_when_keyring_fails_on_use(tmp_path, monkeypatch):
    monkeypatch.setattr(keyring, "get_password", lambda *a: (_ for _ in ()).throw(AssertionError("main touched Keychain")))
    client = BrokerProxyClient(running_proxy(tmp_path).socket_path).open()
    assert client.call_read("get_accounts", {})["structuredContent"]["data"]["accounts"]

def test_proxy_socket_is_group_only_and_rejects_oversize_or_malformed_frames(tmp_path):
    server, upstream = running_proxy(tmp_path)
    assert stat.S_IMODE(server.socket_path.stat().st_mode) == 0o660
    assert rejected_without_dispatch(server, b"{" * 65_537, upstream)
```

Define `running_proxy`, `raw_request`, and `rejected_without_dispatch` as test-only utilities in `tests/test_broker_proxy.py`. `running_proxy` starts the real server class on a temporary socket with a fake object implementing only `list_remote_tools()` and `call_read()`; `raw_request` sends the production length-prefixed frame; `rejected_without_dispatch` asserts an error frame and an unchanged `upstream.calls` list.

Known write names include order placement/replacement/cancellation, order preview/review, option exercise, transfer, deposit, withdrawal, and settings mutation. Malformed variants include namespaced, suffixed, leading/trailing whitespace, case changes, NFKC confusables, duplicate JSON keys, a non-object `arguments` field, and argument collections one item above each registered per-method maximum. Add a kernel-credential test that admits the configured operator UID and rejects a different UID before upstream dispatch; the filesystem test proves the socket is owned by `robinhoodproxy:robinhoodreaders` with mode `0660` and the parent directory is `0770`.

The production breaks caught are widening the method surface, importing Keychain from main, unsafe socket permissions, or dispatching malformed input.

- [ ] **Step 2: Run proxy tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_broker_proxy.py tests/test_mcp_client.py tests/test_robinhood_oauth.py tests/test_market_reader.py tests/test_direct_read_gateway.py`

Expected: import failures for the absent proxy modules and missing socket behavior.

- [ ] **Step 3: Implement the protocol and move credential-owning code**

`broker_proxy.protocol` parses one length-prefixed UTF-8 JSON object at a time with duplicate-key rejection. It checks the exact `READ_METHODS` member before validating arguments and before calling upstream. The server refuses a symlink or non-socket path, removes only a `robinhoodproxy`-owned stale socket, binds inside the `robinhoodproxy:robinhoodreaders` mode-`0770` runtime directory, chmods the socket `0660`, and requires macOS `getpeereid()` to return the configured operator UID. Absence or failure of peer-credential verification is fatal; there is no permissive fallback.

Move—not copy—the Keychain OAuth and remote MCP classes under `broker_proxy`. Migrate `agents.market_reader`, both diagnostics, and direct-gateway tests to `BrokerProxyClient`; migrate only the interactive authorization entry point to proxy-owned OAuth/MCP modules. The proxy's upstream wrapper exposes no generic public dispatcher: its sole public call accepts the exact `READ_METHODS` enum and rechecks it immediately before the private MCP SDK call. `broker.proxy_client` imports only standard-library socket/protocol code and shared read-contract schemas. No file reachable from `agents.market_reader` imports `keyring`, `mcp.client.auth`, `broker_proxy.oauth`, or `broker_proxy.mcp_client`.

- [ ] **Step 4: Run proxy tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_broker_proxy.py tests/test_mcp_client.py tests/test_robinhood_oauth.py tests/test_market_reader.py tests/test_direct_read_gateway.py`

Expected: all selected tests pass, with zero upstream calls for rejected requests.

- [ ] **Step 5: Commit**

```bash
git add broker/read_contracts.py broker/proxy_client.py broker/policy.py broker_proxy agents/market_reader.py scripts/authorize_robinhood.py scripts/diagnose_robinhood.py tests/test_broker_proxy.py tests/test_mcp_client.py tests/test_robinhood_oauth.py tests/test_market_reader.py tests/test_direct_read_gateway.py
git rm broker/oauth.py broker/mcp_client.py
git commit -m "feat: isolate Robinhood reads in local proxy"
```

### Task 3: Enforce bounded cash without reporting amounts

**Files:**
- Modify: `broker/read_gateway.py`
- Modify: `agents/market_reader.py`
- Modify: `agents/readiness.py`
- Modify: `scripts/diagnose_robinhood.py`
- Modify: `tests/test_direct_read_gateway.py`
- Modify: `tests/test_market_reader.py`
- Modify: `tests/test_operational_readiness.py`

**Interfaces:**
- Produces: `EffectiveReadGateway(client, config, incident_handler, clock=None, evidence_cache=None, *, max_agentic_cash_usd: Decimal, snapshot_handler: Callable[[dict], object] | None = None)`.
- Produces on success: redacted `account_bounds = {"status": "VERIFIED", "checked_fields": ["cash", "buying_power", "unleveraged_buying_power"]}`.
- Produces on failure: `CapabilityError("AGENTIC_ACCOUNT_OUTSIDE_BOUNDS")` after the incident handler; never includes values.
- Consumes: proxy greeting selected path and raw `get_accounts`/`get_portfolio` reads.

- [ ] **Step 1: Replace zero-cash tests with failing bounded-cash behavior tests**

```python
@pytest.mark.parametrize("cash", ["0", "500", "1200.00"])
def test_bounded_fallback_accepts_nonmargin_cash_at_or_below_cap(tmp_path, cash):
    _, config = setup_runtime(tmp_path)
    client = FakeDirectClient(
        account=_account(config),
        portfolio=_portfolio(
            cash=cash, buying_power=cash, unleveraged_buying_power=cash,
        ),
    )
    subject = EffectiveReadGateway(
        client, config, lambda code: None,
        max_agentic_cash_usd=Decimal("1200.00"),
    )
    evidence = subject.preflight(
        scope_path="full_scope_bounded_cash_fallback"
    )
    assert evidence["account_bounds"]["status"] == "VERIFIED"
    assert cash not in json.dumps(evidence)

@pytest.mark.parametrize("cash,buying,unleveraged", [
    ("1200.01", "1200.01", "1200.01"),
    ("500", "550", "500"),
    ("500", "500", "499.99"),
    ("NaN", "NaN", "NaN"),
    ("-1", "-1", "-1"),
])
def test_bounded_fallback_holds_outside_cap_or_on_margin(
    tmp_path, cash, buying, unleveraged
):
    _, config = setup_runtime(tmp_path)
    incidents = []
    client = FakeDirectClient(
        account=_account(config),
        portfolio=_portfolio(
            cash=cash,
            buying_power=buying,
            unleveraged_buying_power=unleveraged,
        ),
    )
    subject = EffectiveReadGateway(
        client,
        config,
        incidents.append,
        max_agentic_cash_usd=Decimal("1200.00"),
    )
    with pytest.raises(CapabilityError, match="AGENTIC_ACCOUNT_OUTSIDE_BOUNDS"):
        subject.preflight(scope_path="full_scope_bounded_cash_fallback")
    assert incidents == ["AGENTIC_ACCOUNT_OUTSIDE_BOUNDS"]
```

Add a report-redaction test with a distinctive balance and account identifier and assert neither appears in diagnostic JSON, readiness JSON, exception text, or incident notification body.

- [ ] **Step 2: Run bounded-cash tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_direct_read_gateway.py tests/test_market_reader.py tests/test_operational_readiness.py`

Expected: old fallback name and zero-only checks fail.

- [ ] **Step 3: Implement the exact predicate and redacted evidence**

Parse `cash`, nested `buying_power.buying_power`, and `buying_power.unleveraged_buying_power` as finite `Decimal` values. For the full-scope fallback require exact equality and cap; for a proven provider read-only scope, record `NOT_REQUIRED_FOR_READ_ONLY_SCOPE`. Replace amount-bearing `account_cash` evidence with `account_bounds` and checked field names. `LiveReader` constructs `BrokerProxyClient` from `config.broker_proxy_socket` and passes the preregistered cap.

- [ ] **Step 4: Run bounded-cash tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_direct_read_gateway.py tests/test_market_reader.py tests/test_operational_readiness.py`

Expected: all selected tests pass and no report fixture contains an amount/account identifier.

- [ ] **Step 5: Commit**

```bash
git add broker/read_gateway.py agents/market_reader.py agents/readiness.py scripts/diagnose_robinhood.py tests/test_direct_read_gateway.py tests/test_market_reader.py tests/test_operational_readiness.py
git commit -m "feat: enforce bounded Agentic cash fallback"
```

### Task 4: Add the classified cash, position, and order-activity tripwire

**Files:**
- Create: `agents/account_tripwire.py`
- Modify: `agents/safety_events.py`
- Modify: `agents/market_reader.py`
- Modify: `agents/inbox_web.py`
- Modify: `agents/dashboard.py`
- Modify: `agents/dashboard_view.py`
- Modify: `agents/reporting.py`
- Create: `tests/test_account_tripwire.py`
- Modify: `tests/test_safety_events.py`
- Modify: `tests/test_dashboard.py`
- Modify: `tests/test_pushover.py`

**Interfaces:**
- Produces: `evaluate_snapshot(database, *, cash, positions, equity_orders, option_orders, crypto_orders, max_agentic_cash_usd, cycle_id, now, dashboard_base_url) -> TripwireDecision`.
- Produces: `acknowledge_change(database, *, incident_id, expected_snapshot_hash, change_class, expires_at, csrf_confirmed, now) -> None`; the acknowledgement is expiring and one-shot for that already observed pending hash and authorizes no future change window.
- Produces tables `broker_state_snapshots` and `broker_change_acknowledgements`; snapshot payload is local-only, report projection is redacted.
- Consumes: the same preflight account, portfolio, and equity-position reads used by the cycle.

- [ ] **Step 1: Write failing state-machine tests**

```python
def test_first_verified_snapshot_seeds_without_page(tmp_path):
    result = evaluate_snapshot(
        tmp_path / "agent.db", cash="500", positions=[], equity_orders=[],
        option_orders=[], crypto_orders=[], max_agentic_cash_usd=Decimal("1200"),
        cycle_id="c1", now=NOW,
        dashboard_base_url="http://127.0.0.1:8765",
    )
    assert result.status == "BASELINE_CREATED"
    assert not (tmp_path / "INCIDENT_STOP").exists()

def test_unacknowledged_position_change_pages_latches_and_stops_before_model(tmp_path):
    path = tmp_path / "agent.db"
    evaluate_snapshot(path, cash="500", positions=[], equity_orders=[], option_orders=[],
                      crypto_orders=[], max_agentic_cash_usd=Decimal("1200"), cycle_id="c1", now=NOW,
                      dashboard_base_url="http://127.0.0.1:8765")
    with pytest.raises(TripwireViolation, match="AGENTIC_ACCOUNT_UNACKNOWLEDGED_CHANGE"):
        evaluate_snapshot(
            path, cash="500", equity_orders=[], option_orders=[], crypto_orders=[],
            max_agentic_cash_usd=Decimal("1200"),
            positions=[{"instrument_id": "instrument-1", "quantity": "1", "direction": "long"}],
            cycle_id="c2", now=NOW + timedelta(days=1),
            dashboard_base_url="http://127.0.0.1:8765",
        )
    assert incident_active(path)
    with sqlite3.connect(path) as db:
        title, body = db.execute(
            "SELECT title,body FROM notification_outbox ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    assert title == "Agentic account change detected"
    assert "Review and revoke access if unrecognized" in body
    assert "instrument-1" not in body
```

Add table-driven cases using the same literal fixtures for: identical snapshot (`VERIFIED_UNCHANGED`, no page); an in-cap cash increase with unchanged positions/orders (`ACCOUNT_CASH_INCREASE_BENIGN`, baseline advances, weekly-summary row, no page/latch); cash decrease (latched); above-cap cash (latched with `AGENTIC_ACCOUNT_OUTSIDE_BOUNDS`); any position change (latched); new or changed equity/option/crypto order activity (latched); restoration after mismatch (still latched); acknowledgement promotes the pending hash; acknowledgement with a second unresolved incident leaves both stop markers; a user-owned `STOP_TRADING` marker remains byte-identical; and dashboard/Pushover projections omit the distinctive strings `512.34`, `17.25`, `instrument-secret`, order IDs, and the configured account number.

Also test that an expired acknowledgement, a wrong incident ID, a wrong pending hash, or a wrong change class leaves the latch engaged and creates no new verified baseline.

Use literal snapshots and assert one model-call sentinel remains untouched after a tripwire. The break caught is treating external account mutation as normal cycle input or allowing a broad resume action to clear an incident.

- [ ] **Step 2: Run tripwire tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_account_tripwire.py tests/test_safety_events.py tests/test_dashboard.py tests/test_pushover.py`

Expected: missing tripwire module/tables/routes and absent operator rearm logic.

- [ ] **Step 3: Implement canonical snapshots and latched acknowledgement**

Canonicalize only the selected Agentic account's cash, sorted positions keyed by stable instrument ID with quantity/direction, and sorted order-history records keyed by provider order ID with type/status/timestamps. Normalize decimals so provider formatting such as `500`, `500.0`, and `500.00` produces the same canonical value. Hash canonical JSON with SHA-256. Store protected snapshot JSON in SQLite, but expose only hash, changed categories, timestamps, and status to dashboard/report code.

On an in-cap cash increase with unchanged positions and order histories, record `ACCOUNT_CASH_INCREASE_BENIGN`, promote the snapshot, and add the redacted event to the weekly summary without Pushover or a latch. On a cash decrease, position change, new/changed order activity, or above-cap cash, insert the pending snapshot and critical incident, call the existing Pushover path, and raise before agent construction. Add a CSRF-protected POST `/tripwire/acknowledge` that requires the exact unresolved incident ID, pending snapshot hash, derived change class (`cash_decrease`, `positions`, `order_activity`, `cash_above_cap`, or a deterministic combination), an explicit near-term expiry, plus `confirm=yes`. Code rejects an expired acknowledgement and consumes a valid one in the same transaction, so it cannot pre-authorize a future mutation. Resolution is transactional: mark the acknowledgement consumed, promote the pending snapshot, resolve that incident, and remove safety-owned latch files only when no unresolved incident remains and inode/owner checks still match. A user-owned pause remains.

- [ ] **Step 4: Run tripwire tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_account_tripwire.py tests/test_safety_events.py tests/test_dashboard.py tests/test_pushover.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add agents/account_tripwire.py agents/safety_events.py agents/market_reader.py agents/inbox_web.py agents/dashboard.py agents/dashboard_view.py agents/reporting.py tests/test_account_tripwire.py tests/test_safety_events.py tests/test_dashboard.py tests/test_pushover.py
git commit -m "feat: latch unacknowledged broker state changes"
```

### Task 5: Monitor authorization expiry and refresh failures

**Files:**
- Modify: `broker_proxy/oauth.py`
- Modify: `broker_proxy/mcp_client.py`
- Create: `broker_proxy/auth_monitor.py`
- Modify: `broker_proxy/server.py`
- Modify: `agents/notifications.py`
- Create: `tests/test_auth_expiry.py`
- Modify: `tests/test_robinhood_oauth.py`
- Modify: `tests/test_pushover.py`

**Interfaces:**
- Produces Keychain metadata record `token_timing = {stored_at, expires_at, authorization_id}` adjacent to, but never containing, token material.
- Produces `authorization_status(now) -> {status, expires_at, warning_threshold}` where status is `VALID`, `WARNING_3_DAYS`, `WARNING_1_DAY`, `EXPIRED`, or `REFRESH_FAILED`.
- Produces deduplicated page keys `(authorization_id, threshold)` and proxy error code `AUTH_EXPIRED`.

- [ ] **Step 1: Write failing timing and notification tests**

Use a fake Keychain backend and a fixed UTC clock. Test provider tokens with `expires_in=767302` and literal expected timestamps. Prove storing or refreshing a token writes a new `stored_at`/`expires_at`; crossing three days and one day creates exactly one Pushover page per threshold; repeated checks do not duplicate pages; refresh failure pages immediately; an expired token raises `OAuthUnavailable("AUTH_EXPIRED")` before a remote MCP session is opened; and no token, refresh token, token hash, account field, or raw exception appears in Keychain timing metadata, logs, proxy frames, or notification bodies.

The production breaks caught are treating `expires_in` as an absolute timestamp, resetting warnings without token rotation, allowing an expired token upstream, or leaking credential material through monitoring.

- [ ] **Step 2: Run expiry tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_auth_expiry.py tests/test_robinhood_oauth.py tests/test_pushover.py`

Expected: missing timing metadata/monitor and no `AUTH_EXPIRED` path.

- [ ] **Step 3: Implement expiry metadata, warnings, and fail-closed refresh handling**

`KeychainOAuthStorage.set_tokens()` records `stored_at=clock.now()` and derives `expires_at = stored_at + expires_in`; missing, nonpositive, or nonfinite expiry fails authorization. The proxy checks expiry before opening MCP and reports only secret-free status in its greeting. The monitor persists warning deduplication in SQLite through the existing notification outbox; a newly stored provider token receives a new random authorization ID and its own thresholds. MCP refresh exceptions are normalized to `AUTH_REFRESH_FAILED`, paged once immediately, and never expose upstream text. At or after expiry, return `HOLD_OPERATIONAL: AUTH_EXPIRED` before discovery or model construction.

- [ ] **Step 4: Run expiry tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_auth_expiry.py tests/test_robinhood_oauth.py tests/test_pushover.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add broker_proxy/oauth.py broker_proxy/mcp_client.py broker_proxy/auth_monitor.py broker_proxy/server.py agents/notifications.py tests/test_auth_expiry.py tests/test_robinhood_oauth.py tests/test_pushover.py
git commit -m "feat: monitor Robinhood authorization expiry"
```

### Task 6: Add the revocation runbook and evidence-producing drill

**Files:**
- Create: `docs/operations/robinhood-access-revocation.md`
- Create: `scripts/robinhood_revocation_drill.py`
- Modify: `scripts/authorize_robinhood.py`
- Modify: `broker_proxy/oauth.py`
- Modify: `agents/readiness.py`
- Create: `tests/test_revocation_drill.py`
- Modify: `tests/test_operational_readiness.py`

**Interfaces:**
- Produces subcommands: `begin`, `verify-revoked`, `remove-local-credentials`, and `verify-reauthorized`.
- Produces SQLite table `oauth_revocation_drills(id, begun_at, revoked_read_failed_at, local_credentials_removed_at, reauthorized_read_passed_at, status, preregistration_hash, config_hash)` with booleans/timestamps only.
- Produces: `KeychainOAuthStorage.delete_tokens_and_client_info()` used only by the proxy-owned drill command.
- Consumes: one exact allowed `get_accounts` read to prove failure/success; discards payload without storing identifiers.

- [ ] **Step 1: Write failing drill tests**

```python
def test_local_delete_without_failed_remote_read_cannot_complete_revocation(tmp_path):
    drill = RevocationDrill(tmp_path / "agent.db", config_hash="c" * 64,
                            preregistration_hash="p" * 64)
    drill.begin(NOW)
    with pytest.raises(RevocationStateError, match="failed revoked-credential read"):
        drill.record_local_credentials_removed(NOW + timedelta(minutes=1))

def test_reauthorization_requires_fresh_allowed_read_and_exact_eleven_greeting(tmp_path):
    drill = completed_revoked_drill(tmp_path)
    wrong = {"effective_read_tools": ["get_accounts"], "effective_write_tool_count": 0}
    with pytest.raises(RevocationStateError, match="exact read inventory"):
        drill.verify_reauthorized(greeting=wrong, read_succeeded=True,
                                  now=NOW + timedelta(minutes=3))

def test_revocation_receipt_is_redacted(tmp_path):
    receipt = completed_drill_receipt(tmp_path, distinctive_payload={
        "access_token": "token-secret", "cash": "512.34",
        "quantity": "17.25", "account_number": "account-secret",
    })
    encoded = json.dumps(receipt, sort_keys=True)
    for forbidden in ("token-secret", "512.34", "17.25", "account-secret"):
        assert forbidden not in encoded
```

`completed_revoked_drill` and `completed_drill_receipt` are test-only builders that drive the real state machine through `begin`, an authentication-class failed read, local deletion, and reauthorization. Also test that timeout, socket refusal, policy error, and malformed response are rejected as revocation proof; and that client metadata without a usable token remains `AWAITING_REAUTHORIZATION`.

The production break caught is claiming remote revocation from local deletion or claiming reauthorization from token presence alone.

- [ ] **Step 2: Run drill tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_revocation_drill.py tests/test_operational_readiness.py`

Expected: missing drill state machine and readiness gate.

- [ ] **Step 3: Implement the fail-closed drill**

`begin` engages the incident latch and prints the official in-app disconnect instruction without opening or automating Robinhood. `verify-revoked` requires the proxy's allowed read to fail with an authentication-class error; a timeout, malformed response, socket outage, or policy rejection is not accepted as proof. `remove-local-credentials` is allowed only after that failure and deletes token, timing metadata, and dynamic client information from the dedicated proxy user's Keychain. After the operator reruns authorization, `verify-reauthorized` requires a new live allowed read plus the exact-eleven greeting under current preregistration/config hashes.

The runbook states: disconnect the Agentic Trading connection directly in the Robinhood app; if the control is unavailable or activity is unrecognized, contact Robinhood Support through the app; then return to the local drill. It explicitly says local Keychain deletion is not remote revocation.

- [ ] **Step 4: Run drill tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_revocation_drill.py tests/test_operational_readiness.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add docs/operations/robinhood-access-revocation.md scripts/robinhood_revocation_drill.py scripts/authorize_robinhood.py broker_proxy/oauth.py agents/readiness.py tests/test_revocation_drill.py tests/test_operational_readiness.py
git commit -m "feat: prove Robinhood revocation and reauthorization"
```

### Task 7: Install the cross-user proxy service and migrate all live reads

**Files:**
- Modify: `scripts/install_shadow_services.py`
- Create: `scripts/check_broker_proxy_identity.py`
- Create: `docs/operations/broker-proxy-user-setup.md`
- Modify: `agents/daily_cycle.py`
- Modify: `agents/market_reader.py`
- Modify: `scripts/diagnose_robinhood.py`
- Modify: `README.md`
- Modify: `tests/test_service_schedule.py`
- Modify: `tests/test_installed_isolation.py`
- Modify: `tests/test_daily_cycle.py`
- Modify: `tests/test_market_reader.py`

**Interfaces:**
- Produces a `robinhoodproxy`-owned LaunchAgent label `com.openai.robinhood-read-proxy`, `KeepAlive=true`, proxy-only config arguments, and proxy-private redacted logs; the three operator-user application jobs remain in the operator session.
- Consumes `BrokerProxyClient` from Tasks 2–3; no live-cycle module imports proxy OAuth/MCP modules.
- Produces diagnostic output with `proxy_reachable`, `proxy_identity_verified`, `effective_read_tool_count=11`, `effective_write_tool_count=0`, `account_bounds.status`, `tripwire.status`, and `authorization.status`, with no values/identifiers.

- [ ] **Step 1: Write failing installed-boundary tests**

```python
def test_launchd_defines_separate_proxy_with_proxy_only_config():
    services = service_definitions(ROOT)
    proxy = services["com.openai.robinhood-read-proxy"]
    assert "broker_proxy.server" in proxy["ProgramArguments"]
    assert proxy["UserContext"] == "robinhoodproxy"
    assert "broker-proxy.local.yaml" in " ".join(proxy["ProgramArguments"])
    assert "broker-proxy.local.yaml" not in " ".join(services["com.openai.robinhood-daily"]["ProgramArguments"])

def test_proxy_unavailable_records_hold_operational_without_model_call(tmp_path, monkeypatch):
    model_calls = []
    monkeypatch.setattr(CodexBridge, "run", lambda *a, **k: model_calls.append((a, k)))
    result = run_live_cycle_with_socket(tmp_path / "missing.sock")
    assert result["status"] == "HOLD_OPERATIONAL"
    assert result["reason"] == "BROKER_READ_PROXY_UNAVAILABLE"
    assert model_calls == []
```

Define `run_live_cycle_with_socket` as a test-only harness around the real scheduled live-cycle entry point with the clock/lifecycle fixed to an eligible claim. Add an isolated-subprocess test that installs a fail-on-use Keychain backend, imports and runs `agents.daily_cycle` through a temporary real proxy, and exits `0`; the subprocess then asserts `broker_proxy.oauth`, `broker_proxy.mcp_client`, and `keyring` are absent from `sys.modules`. Add filesystem/identity tests proving the operator UID cannot read the proxy user's Keychain fixture or private files, the proxy socket is reachable only through the shared group, and an unrelated peer UID is rejected before dispatch. Add a diagnostic fixture containing `512.34`, `17.25`, `instrument-secret`, `order-secret`, and `account-secret`, and assert none appear in stdout or diagnostic JSON.

- [ ] **Step 2: Run service/integration tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_service_schedule.py tests/test_installed_isolation.py tests/test_daily_cycle.py tests/test_market_reader.py`

Expected: service set lacks the proxy and installed isolation is not yet proven.

- [ ] **Step 3: Complete service migration**

Add the proxy LaunchAgent under the already-created non-admin `robinhoodproxy` account and make installation require the safety pause. Setup preflight verifies user/group membership, proxy home/Keychain ownership, `0770` runtime directory, `0660` socket, registered operator UID, and the dedicated user's GUI session. It never creates a user, changes group membership, unlocks a Keychain, or widens permissions without an explicit operator-run administrative step. The daily worker connects only to the socket. Startup ordering is fail-closed: proxy absence or greeting mismatch records an operational hold and pages once; it never falls back to direct OAuth, Codex, fixture data, or a model. Update the dashboard operations view and README with the four service labels, dedicated-user session requirement, and revocation/runbook link.

- [ ] **Step 4: Run service/integration tests and verify GREEN**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_service_schedule.py tests/test_installed_isolation.py tests/test_daily_cycle.py tests/test_market_reader.py`

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/install_shadow_services.py scripts/check_broker_proxy_identity.py docs/operations/broker-proxy-user-setup.md agents/daily_cycle.py agents/market_reader.py scripts/diagnose_robinhood.py README.md tests/test_service_schedule.py tests/test_installed_isolation.py tests/test_daily_cycle.py tests/test_market_reader.py
git commit -m "feat: run live reads through installed proxy"
```

### Task 8: Verify the entire Phase 0 boundary and perform live proofs

**Files:**
- Modify: `agents/readiness.py`
- Modify: `scripts/verify_operations.py`
- Create/update generated evidence: `outputs/phase0-v1.4.1/`
- Test: full `tests/` suite

**Interfaces:**
- Consumes all prior task evidence.
- Produces a redacted readiness assessment with independent gates for OS-user/Keychain isolation, exact-eleven inventory, peer-UID enforcement, bounded cash, classified tripwire, authorization-expiry monitor, revoke/reauthorize drill, installed services, current-code tests, and the scheduled full cycle.
- Produces no Phase 1 code or v1.5.0 runtime behavior.

- [ ] **Step 1: Write failing final-gate tests**

Add readiness fixtures proving that each missing item independently keeps `phase0_gate_passed=false`, and one complete redacted fixture produces `true`. Assert that amounts/account identifiers in an input fixture never appear in JSON or Markdown output.

- [ ] **Step 2: Run final-gate tests and verify RED**

Run: `PYTHONPATH=. .venv/bin/pytest -q tests/test_operational_readiness.py`

Expected: readiness currently lacks the v1.4.1 proxy/tripwire/revocation gates.

- [ ] **Step 3: Implement final evidence gates**

Require current canonical source/config/preregistration hashes, a fresh test report with zero failures and every named regression present, a completed revoke drill, installed dedicated proxy identity, private proxy Keychain/files, operator-only peer acceptance, proxy-owned auth and expiry evidence, bounded-cash/classified-tripwire success, source hashes, no broker writes, and an installed scheduled cycle receipt. Keep each gate separate in JSON/Markdown.

- [ ] **Step 4: Run all automated verification**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.install_shadow_services
PYTHONPATH=. .venv/bin/python -m scripts.verify_operations \
  --run-tests \
  --test-report outputs/phase0-v1.4.1/test-results.xml \
  --test-manifest outputs/phase0-v1.4.1/test-run.json \
  --output-dir outputs/phase0-v1.4.1/readiness
```

Expected before live proofs: test suite passes; service definitions validate; readiness remains false only for live drill/scheduled evidence.

- [ ] **Step 5: Install while paused and run the operator-assisted revocation drill**

Keep `STOP_TRADING` engaged. The operator performs the documented administrative setup for the non-admin `robinhoodproxy` user and `robinhoodreaders` group, logs into that account once to unlock its Keychain, and confirms the identity preflight. Install the proxy LaunchAgent in that user session and the three application LaunchAgents in the operator session. Run `robinhood_revocation_drill begin`; the operator disconnects the Agentic Trading connection in Robinhood. Run `verify-revoked`, then `remove-local-credentials`. The operator runs the authorization flow personally. Run `verify-reauthorized` and the redacted read-only diagnostic. If any step is not positively proven, stop with the exact blocker and keep the kill switch engaged.

- [ ] **Step 6: Prove one installed scheduled market-day cycle**

Only after the drill and diagnostic pass, use the dashboard-owned pause control to permit the next eligible 10:00–10:20 AM ET window. Verify the proxy and daily jobs are launchd-owned, capture the terminal receipt, confirm zero broker writes, and re-engage the dashboard pause after completion. Do not substitute a manual run.

- [ ] **Step 7: Rerun the authoritative verifier**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m scripts.verify_operations \
  --test-report outputs/phase0-v1.4.1/test-results.xml \
  --test-manifest outputs/phase0-v1.4.1/test-run.json \
  --output-dir outputs/phase0-v1.4.1/readiness
```

Expected: exit `0`, `phase0_gate_passed=true`, `research_implementation_allowed=false`, and `phase1_blocked_pending_v1_5_approval=true`.

- [ ] **Step 8: Commit final automated gate code and redacted operator runbook evidence**

```bash
git add agents/readiness.py scripts/verify_operations.py tests/test_operational_readiness.py outputs/phase0-v1.4.1
git commit -m "test: prove bounded cash Phase zero gate"
```

Before staging, inspect every generated evidence file for secrets, balances, quantities, cost basis, and account identifiers. Never commit SQLite databases, Keychain data, local proxy configuration, raw MCP payloads, or log files.

## Final review and stop condition

After Task 8, generate the whole-branch review package and perform the required fresh-context review. Any Critical or Important finding gets one TDD fix pass plus the full suite. Phase 0 is complete only if the final verifier exits `0`; otherwise report the independent failing gates and stop with paper activity paused. Even on success, do not begin Phase 1. Prepare v1.5.0—baseline gross edge, measured token caps with `OUTPUT_TRUNCATED_AT_TOKEN_CAP`, and the funded Portfolio/Critic rebuttal envelopes—for separate operator review first.
