# Operator-approved release train

Approval: September 29, 2026, operator in chat. Effective only after recorded
Phase 0 sign-off. Until then, development and replay may proceed where explicitly
approved; tonight's Task 1 release does not itself establish Phase 0 sign-off.

- Batch reviewed changes into after-close releases: **at most three releases
  per America/New_York calendar week (Monday through Sunday)**, not a target
  of three deployments. Never deploy during an active cycle or market session.
- Preserve per-batch operator scope/approval, pinned manifest, exact source
  fingerprint, verified source rollback, service scope and read-only boundaries.
  A frequency allowance does not authorize unreviewed changes or new policy.
- Each behavior change must first pass an isolated replay using a stored real
  point-in-time snapshot. Pin parent official run, snapshot content hash, code,
  model/prompt/config versions and replay scope. No official DB writes, cards,
  fills, scoreboard or memory changes. Stored outcomes are not new AI judgments.
- Use local isolated replay storage or stdout only. No broker calls or current
  data substituted for historical missing inputs. Any paid model replay needs
  explicit authorization and must remain separately budgeted/attributed.
- Synthetic unit tests complement real-snapshot replay; they cannot substitute
  for it. Missing required snapshot evidence means REPLAY_INCOMPLETE and blocks
  that change from the release batch. Report exact missing fields, never infer.
- Run the full installed suite on every release, plus operational verifier and
  source fingerprint. Keep expected missing scheduled proof explicit, separate
  from passing software tests. Roll back unexpected failures using verified files;
  never restore over the experiment DB or erase history to make results pass.
- Record release date/ET week, changes, reviewed commit, replay evidence, installed
  suite, verifier outcome, fingerprints, rollback and services in CODEX_STATUS.
  Sync sanitized source/tests/docs to GitHub; no credentials, account identifiers,
  raw snapshots, runtime DB or logs. A rollback is part of the failed attempt,
  not permission to start another release beyond the weekly cap.

## Task 2 development started September 29

Branch: `codex/task2-handoff-replay`, based on `73f37c8`.
Wednesday evening is the target for replay evidence, not automatic deployment.
Order: blind Critic dossier → agent-scope/lane filtering → explicit veto/sizing
outcomes → fill and expiry regressions → isolated stored-real-snapshot replay
→ full suite and review → propose next after-close batch after Phase 0 sign-off.
The separate UI truthfulness changes remain on `ui/agent-desk`; do not fold a
dashboard restart into runtime deployment without explicit reviewed scope.

Current evidence gap: September 29 final cycle retains decisions, strategy signals,
source hashes and stage summaries, but not complete input quote/account snapshots.
An output-only veto audit is possible. It cannot prove how a revised Critic would
respond to a complete dossier. Do not manufacture missing quote times, balances,
contracts, fractional-policy evidence or a replacement model judgment.
