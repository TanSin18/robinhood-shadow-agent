# Release candidate — 2026-09-30 after close (DRAFT, not approved)

Status: CANDIDATE. Nothing is installed until the operator gives a fresh, explicit go that names the
executor, after (1) the completed revocation/reauthorization drill receipt, (2) the installed full
suite passing on the Mac, and (3) this manifest/rollback being reviewed. Hard finish: verified
before 2026-10-01 09:30 ET. Otherwise the installed version stays.

## What ships (core runtime, from `claude/continuation-2026-09-30`)

| Area | Behaviour on Thursday if v1.5 amendment is SIGNED and pinned | If NOT signed |
|---|---|---|
| Readiness | HOLD_CAPABILITY_GAP counts only with all operational gates | same |
| Quote/hold diagnostics (Codex f345721/81fb01d) | honest reasons, zero-bid options excluded by reason | same |
| Persisted results | no account digits | same |
| Decision capsule | one per official cycle, hash in result | same |
| Spread recording | first observation per symbol per session | same |
| Desk ETF policy | agent_alone + deterministic_no_ai paper fills at 10:00; "Desk rule (no AI)" card; YES fills at fresh quote ≤ limit before 15:30 | inert |
| Critic packet / ETF out of AI / lane guide | active | legacy v1.4.2 packets |
| Third paper track | `deterministic_no_ai` rows created ($500 per lane) | rows created, unused |

## Runtime files changed since installed Task 1 (`6e2c220`)

agents/daily_cycle.py, agents/decision_capsule.py (new), agents/decision_packet.py (new),
agents/etf_desk_policy.py (new), agents/etf_issuer.py (new), agents/inbox.py, agents/readiness.py,
agents/rehearsal.py, agents/stored_decision_replay.py (new), agents/v15_activation.py (new),
data/corporate_actions.py, risk/engine.py. `agents/desk_rehearsal.py` is an operator tool (not
imported by services). Root `preregistration.yaml` is **unchanged** (v1.4.2 SHA 3937…6075).
New root file only if signed: `preregistration-amendment-v1.5.0.yaml`.

The exact manifest with per-file SHA-256 is generated from the final signed commit
(`scripts` step below) — do not install from this draft table.

## Signing (operator) → pin (developer)

1. Operator reviews `docs/superpowers/plans/preregistration-amendment-v1.5.0.yaml` and says, in chat,
   "sign v1.5 amendment" (after the drill).
2. Developer sets `operator_signature: {status: SIGNED, signed_by: operator, signed_at_et: <time>}`,
   copies it to repo root, computes its SHA-256, sets `APPROVED_V15_SHA256` and
   `EFFECTIVE_FROM = 2026-10-01T09:30:00-04:00` in `agents/v15_activation.py`, commits, pushes.
3. Test proves `v15_active(root, 2026-10-01T10:00 ET)` is True with the signed file and False with
   any byte change.

## Install (only after explicit go; after close; mirrors Task 1)

1. Preflight: installed fingerprint matches 72494d38…3593; zero STARTED cycles; no unresolved
   incidents; no stop marker; drill receipt present and inside the drill window.
2. Unload `com.openai.robinhood-daily` and `com.openai.robinhood-maintenance` only.
3. Verified backup (tar of every file to be replaced + manifest), mode 0700, outside the primary.
4. Copy manifest files (hash-checked) + signed amendment into primary.
5. Installed suite: `.venv/bin/python -m scripts.verify_operations --run-tests --output-dir outputs/release-2026-09-30 ...`
   Must show 0 failures. Verifier exit 2 is acceptable only for drill/scheduled-proof gates.
6. Reload daily + maintenance; confirm exit 0 on first after-close invocation (SKIPPED_SCHEDULE).
7. Record fingerprints before/after in CODEX_STATUS / CLAUDE_RETURN.
8. UI (separate): new immutable Agent Desk release from `claude/ui-truthful-outcome`, then restart
   `com.openai.robinhood-inbox` only, with its own rollback to the current release directory.

## Rollback

Unload daily + maintenance; restore the backup tar over the primary; remove
`preregistration-amendment-v1.5.0.yaml`; reload; verify fingerprint returns to 72494d38…3593.
New tables (`liquidity_observations`, `decision_capsules`) and the extra `deterministic_no_ai`
paper rows are inert to the old code and may remain.

## Thursday acceptance (10:30 ET check)

Official cycle COMPLETED; capsule RECORDED; accounting SETTLED; no incident; if an ETF signal
qualifies: two paper fills + one PENDING desk card, quantity fractional ≤ 25% cap, limit =
reference × 1.005; if YES is given, fill only at a fresh quote ≤ limit before 15:30.
