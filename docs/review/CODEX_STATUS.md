# Codex status and questions

Newest entry first. Claude owns CLAUDE_REVIEW.md; Codex owns this status file.
Times are America/New_York. Evidence paths below are local, not Git attachments.

## 2026-09-30 10:23 ET — Readiness false-positive closed; independent review complete

Follow-up to the investigation below. Independent review found no blockers in
the bounded quote/hold fix (published as `f345721`), but identified a pre-existing
readiness weakness: a no-model/$0 COMPLETED result passed the scheduled-cycle
gate even when its decision was HOLD_OPERATIONAL. The installed verifier result
below must therefore **not** be treated as sufficient trading readiness.

Fixed on development branch only: code-only readiness now requires an explicit
HOLD_CASH decision. Three regression cases (operational, missing, empty decision)
failed before the fix and pass after; receipt hashes are recomputed in the tests.
Added fresh-quote/missing-history coverage to the earlier diagnostic tests.

- Independent follow-up review: no blockers; **52 focused tests passed**.
- Final full development suite: **706 passed, 0 failed/skipped, 61 warnings,
  50.73s**, same exact pytest command as the 10:19 entry.
- Running the new verifier read-only against unchanged installed evidence rejects
  today's operational hold: scheduled_full_cycle=false, ready=false. It reports
  both missing drill evidence and missing qualifying scheduled-cycle proof.
  The job genuinely ran; this does not relabel it as a scheduler failure.
- Installed tests remain 665 passing; installed runtime/fingerprint unchanged.
  Dashboard GET returned HTTP 200; daily/maintenance last exit=0; no open safety
  incidents and no incidents recorded today. Cost attribution is SETTLED with
  all lane/arm costs and total unique cost $0, which does not prove paid-call
  allocation.
- Both fixes are source-only review candidates. No deployment, service restart,
  preregistration edit, official rerun, paper fill, or real broker write.
- Reviewer inspected code and synthetic tests only; live collection/isolation
  and installed evidence above were independently checked by Codex, not the
  reviewer. Full historical capsule replay and end-to-end issuance remain open.

## 2026-09-30 10:19 ET — Market-hours investigation: misleading hold repaired on branch, not deployed

Operator requested investigations, fixes and tests during market hours. Work
remains isolated on `codex/task2-handoff-replay`; no installed code/config/model/
budget/preregistration changes, no restart, no official rerun or result edit.

### Root cause and scope

- Scheduled 10:00:07–10:00:47 ET cycle completed, live read-only, accounting
  SETTLED, estimated model cost $0. Parent cycle:
  `37c7e7947a124a9c821570a55ecb00db`.
- The stored strategy trace says SOXX advanced with a **one-second-old** quote.
  The blanket “no fresh normalized evidence” message was false.
- Three option quotes had zero bids. Normalization mislabeled them
  CORPORATE_ACTION_UNRESOLVED; the exclusion recorder discarded their contract
  identity, and any exclusion made the no-AI result claim universe-wide failure.
- AI correctly skipped an ETF-only signal under active v1.4.2. Independently,
  this runtime has **no code-only entry issuer for that signal**. We do not
  force AI to analyze an ETF, issue an unreviewed baseline, or call this a
  successful investment HOLD_CASH.
- Changes: invalid/nonfinite/nonpositive/crossed prices stay excluded with
  INVALID_QUOTE_PRICE; contract identity survives; unrelated exclusions no
  longer poison fresh candidates; empty/stale candidate sets remain operational
  holds; fresh deterministic signals report
  DETERMINISTIC_ENTRY_PATH_NOT_IMPLEMENTED with signal IDs. Official no-AI
  results now include measured quote freshness and observation time.
- No historical decision or UI record was rewritten. Dashboard remains installed
  code; corrected wording is not yet deployed. Legacy field
  corporate_action_exclusions remains compatible but can contain quote-quality
  exclusions; consumers should display the reason code, not infer an action.

### Verification

- Baseline development full suite: **691 passed**, 61 warnings, 51.90s.
- Added 11 test cases, observed failing before fixes; targeted suite:
  **41 passed**, 4 warnings. Updated the legacy ETF fixture assertion because
  it contains a real deterministic signal: it must not label the absent issuer
  as investment discipline.
- Final development full suite: **702 passed**, 61 warnings, 49.71s.
  Command (development worktree):
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q --tb=short`.
- Replayed the **stored 10:00 option quote inputs only** through normalization:
  547 accepted, 3 INVALID_QUOTE_PRICE, no corporate-action errors. This is a
  bounded normalization replay, not a full decision-capsule replay.
- Two live read-only isolated rehearsals, $0/model calls=0, cards=0, fills=0,
  official business digest unchanged in both. First: 561 quotes, 544 fresh,
  17 stale/future, 39.65s. Patched second: 561 quotes, 548 fresh, 13 stale/future,
  36.64s; 14 volatility series; 60-second limit unchanged. Patched result
  explicitly reports SOXX / DETERMINISTIC_ENTRY_PATH_NOT_IMPLEMENTED, SETTLED.
- Local private evidence:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-diagnostics/2026-09-30-market-evidence-1/`
  and `2026-09-30-market-evidence-2/`. Not Git artifacts.
- Installed full suite independently: **665 passed**, 61 warnings, 49.25s.
  Installed verifier exit **2**, scheduled receipt gate now true; sole listed
  blocker is missing/invalid completed sanitized revocation/reauthorization
  evidence. Test+verifier artifacts:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-diagnostics/2026-09-30-installed-verification/`.
  Command: `.venv/bin/python -m scripts.verify_operations --run-tests`
  with `--output-dir`, `--test-report` and `--test-manifest` pointed there.
- Installed fingerprint remains
  `72494d38475231b394a9e9b323659fed2ea421ab7d47e6630360d1e4dd233593`;
  active preregistration is v1.4.2. No services restarted.

### Remaining blockers / next permitted work

1. Complete the operator-assisted after-close revocation/reauthorization drill;
   do not revoke access during the trading day. Phase 0 is not signed off.
2. Reviewer checks this diagnosis/reporting fix before an approved after-close
   release. No automatic deployment follows GitHub push.
3. ETF deterministic issuance requires the approved code-entry/risk/ledger path;
   do not activate it ad hoc to manufacture a fill. It remains a release gate,
   not fixed by better wording. Task 2 capsule/packet and remaining approved
   deliverables are still incomplete.
4. News remains disabled; universe remains the reviewed 14-symbol scope.
   Broader discovery, baselines and remaining agent features are not activated.
5. Today's $0 code-only result does not prove paid shared-cost attribution,
   current model execution, risk-to-fill behavior or live profitability.

## 2026-09-29 17:01 ET — Decision capsule added to Task 2 as P0

Read Claude's 17:00 checkpoint and operator instruction to add its capsule.
Updated the reconciled Task 2 plan and release-train document: canonical,
content-addressed append-only capsule per official cycle; hash-linked completion
evidence; ordered quote/volatility/strategy snapshots, per-lane/track paper context,
exact sanitized requests and outputs by role/attempt, deterministic risk evidence,
registration/models/prompts/source provenance. No account IDs, last4, tokens or
broker order histories. No raw capsule data in Git.

Default replay is free with recorded model outputs; deterministic stages actually
recompute from frozen inputs. Changed packets are explicitly diffed and do not
make reused outputs a new AI judgment. Paid what-if is optional, separately
authorized, capped at $0.20 and blocked from official writes. Capture failures
preserve the completed decision, append unavailable evidence and queue a
deduplicated non-latching warning; they never masquerade as replayable success.

Acceptance includes fixture-cycle exact round trip, privacy canaries, refresh and
per-track context fidelity, attempt/retry provenance, tamper/no-clobber tests,
write-failure injection preserving decisions, and replay isolation/budget tests.
Full details: `docs/superpowers/plans/2026-09-29-agent-desk-reconciled.md`, Task 2.

Documentation-only addition this turn: capsule implementation/tests not yet built
or run. No new test-pass claim; previous code checkpoint remains a0925d0.
Wednesday after-drill release is the target subject to Phase 0 sign-off, review,
installed suite and batch release approval. Thursday is the first fully replayable
official-run target, not a promise. Today's audit remains REPLAY_INCOMPLETE.
No runtime/config/preregistration edits, service restart or paid model calls.

## 2026-09-29 16:56 ET — Task 2 started; release train registered; replay gap explicit

Operator authorized Task 2 development now and, after Phase 0 sign-off, reviewed
after-close release batches (maximum three per ET week), with isolated stored-real
snapshot replay per change and full installed suite per release. Recorded in
`docs/review/RELEASE_TRAIN.md` and AGENTS.md. No automatic deployment authorization.
Read Claude's 16:44 acceptance and 16:22 UI review; runtime and UI remain separate.

Development branch `codex/task2-handoff-replay`, base `73f37c8`, uses the existing
isolated worktree. First checkpoint is standalone foundations, NOT daily-cycle
integration or complete Task 2:
- `agents/decision_packet.py`: explicit blind allowlist excludes hidden reasoning,
  quantities from Portfolio, account identifiers and raw order history. Keeps
  public thesis, quoted evidence and explicit paper context; missing fields remain
  unknown. Enforces lane/contract identity and finite nonnegative numeric inputs.
  Missing fractional policy is unknown; preliminary sizing is NOT_COMPUTED and
  explicitly non-executable. No unapproved v1.5 policy inferred.
- `agents/stored_decision_replay.py`: read-only stored-output/packet-gap audit,
  not an AI rerun or backtest. Official connection uses mode=ro/query_only.
  Logs parent run and content hash; does not invent prices, balances or judgments.
- 21 new focused tests pass. Independent checkpoint review found malformed string
  veto, empty timestamp/source ID, invalid class/contract identity gaps. Each got
  a failing regression then a passing fix. No deferred reviewer findings.

Real stored-record audit executed against parent
`624a402038ff4a9ca922b609595a893a`, source record SHA-256
`e0be979b60ec171c6703f54e321e5fad635a5f0c90c5d98f1e8a6edf326c43db`.
SOXX: Lane A, CRITIC_VETO, sizing NOT_REACHED. Official business digest unchanged;
zero model calls, zero official writes. No raw record or private account data
added to Git. Result is deliberately **REPLAY_INCOMPLETE**, not replay-proven.

Missing retained historical inputs: bid/ask and quote time, associated source IDs,
explicit asset-class/fractional policy and point-in-time settled cash, held/pending
quantities. Final records have decisions/signals/source hashes, not the full input
dossier. Current holdings or a new quote cannot fill those historical gaps.

Next work: integrate the blind context/risk preview, enforce deterministic ETF
scope across all AI packets and correct option identity, separate veto/whitelist/
duplicate statuses, verify slippage-aware limits and market-close/GET expiry,
then run a complete isolated replay from a complete real input snapshot. Wednesday
evening remains the target, not a guaranteed proof date if required evidence is
unavailable. A recorded-output audit alone cannot satisfy the release-train gate.

No deployment or service restart. Installed fingerprint remains
`72494d38475231b394a9e9b323659fed2ea421ab7d47e6630360d1e4dd233593`;
v1.4.2 stays active. Only review/governance documents mirrored to primary.
Final development suite: **691 passed, 61 warnings, 49.26s** using
`/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q`
from the development worktree. Baseline before edits was 670 passed. These are
branch tests, not a new installed-runtime suite. Task 2 completion checklist
remains open; no release or replay-ready claim.

## 2026-09-29 16:40 ET — Task 1 installed; tests pass; scheduled/drill proof pending

Executed the operator-approved September 29 after-close release at 16:37–16:40
ET. Read Claude's new 16:22 UI review first: its UI fixes remain development-only;
none were included and 8765 was not restarted. Installed ONLY the 13 files in
`task1-release-manifest.json`, from pinned source commit `6e2c220`.

Preflight: original complete fingerprint matched, every candidate file matched
its pinned hash, zero STARTED cycles, zero unresolved incidents, no stop marker.
Daily/maintenance were unloaded before edits; verified backup before applying.
Rollback archive: `/Users/tanmaysinnarkar/LocalProjects/task1-rollback.ZKzThs/before.tar`.
Its directory is mode 0700, with manifest and sanitized service evidence; no DB,
credentials or private settings copied. Written rollback remains in
`docs/review/TASK1_RELEASE_2026-09-29.md`. No rollback was required.

Installed verification command, run from primary:
```
.venv/bin/python -m scripts.verify_operations --run-tests --output-dir outputs/task1-release-2026-09-29 --test-report outputs/task1-release-2026-09-29/tests.xml --test-manifest outputs/task1-release-2026-09-29/test-run.json
```
**665 passed, 0 failed, 0 skipped; 61 warnings; 54.67 seconds.** Fewer than the
branch's 670 because the five proxy-receipt tests/helper change were deliberately
excluded, not skipped. Warnings are existing SDK asyncio/runpy warnings.
Installed report/manifest and operational-readiness JSON/Markdown are local in
`outputs/task1-release-2026-09-29/`; none is pushed as a runtime artifact.

Verifier exit **2 / NOT READY**, with exactly the anticipated blockers:
1. No matching-new-source authenticated scheduled full-cycle receipt yet.
2. Sanitized completed revocation/reauthorization evidence missing or invalid.
All 17 regression-evidence gates passed, including shared costs, real-order
denial, budget/freshness, cash/holdings checks and lifecycle. Live authentication,
capability/bounds and data gates remain unproven for this source until its real
scheduled receipt exists. Old evidence was not relabeled or modified.

Fingerprint before:
`8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
Fingerprint after, unchanged by installed tests:
`72494d38475231b394a9e9b323659fed2ea421ab7d47e6630360d1e4dd233593`.
Root preregistration remains **v1.4.2**, hash
`39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
No config/model/cap changes, v1.5 activation, proxy changes, forced cycle or paid
inference. No historical paper rows were rewritten by deployment.

Reloaded only `com.openai.robinhood-daily` and `com.openai.robinhood-maintenance`.
Both completed their after-close invocation with exit 0 and remain loaded;
daily reports SKIPPED_SCHEDULE, not a new trading review. Dashboard PID **19580**
unchanged. No second runner introduced. The one-time release automation was
deleted after this attempt; it will not recur tomorrow.

Wednesday 10:00 acceptance: SETTLED, exact provider-estimate cost conservation,
unrepresented B cost zero, no incident. Code-only outcomes are valid but do not
prove live shared-AI attribution. Wednesday after 16:30 drill remains a separate
operator-assisted task; no proxy helper deployment authorized by tonight's work.
Settlement/programming-error incidents deliberately pause paper activity for
operator review; the auxiliary attribution fallback warning does not latch.
Task 1 implementation is released, but operational evidence closure/Phase 0
sign-off remains pending. Task 2, UI fixes and Phase 1 are not started here.

## 2026-09-29 15:46 ET — Conditional tonight release prepared; v1.4.2 compatible

Read Claude's 15:38 review. Operator authorized Task 1 release tonight after
16:30 ET, conditional on active-v1.4.2 compatibility, installed full suite,
verifier, pinned fingerprint and written rollback; daily/maintenance restarts
only, no proxy changes. It is still before that window: NOTHING DEPLOYED.

Compatibility confirmed against primary/branch file diffs and the active loader:
root v1.4.2 is byte-exact; runtime reads no v1.5 draft; models, prompts, ceilings,
token envelopes, selection/risk/fill behavior and private config remain unchanged.
The operator-approved auxiliary-only fallback is recorded as the specific
allocation amendment, not broad v1.5 activation. Arm report labels do not start
new trading arms. No Task 2 or Phase 1 behavior included.

Release is the 13-file allowlisted overlay pinned to source commit `6e2c220`,
not the whole branch. `broker_proxy/revocation.py` and its changed/new tests are
excluded along with every proxy/service/credential change. Instructions and
written source-only rollback: `docs/review/TASK1_RELEASE_2026-09-29.md`.
Per-file before/after hashes: `docs/review/task1-release-manifest.json`.
Expected installed fingerprint:
`72494d38475231b394a9e9b323659fed2ea421ab7d47e6630360d1e4dd233593`.
Previous installed fingerprint:
`8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.

Fresh branch compatibility group: **46 passed, 27 warnings**. Exact command is
in the release runbook. This is NOT the installed post-release full-suite result.
The installed suite/verifier will run after copying inside the window. Expected
missing new-source scheduled proof and revocation-drill evidence stay NOT PROVEN;
unexpected gate failures cause rollback/review, not relaxed acceptance.

Created thread follow-up `task-1-after-close-release` for 16:35 local/ET today.
It must delete itself after one attempt; if it misses September 29 it must skip
release, not install tomorrow. Mac/app availability is required; scheduling is
not completion evidence. No manual wait loop or second trading runner created.

Explicit operator effect: COST_SETTLEMENT_FAILED and INFERENCE_FAILED latch
the safety stop: **paper activity paused for your review**, until operator rearm.
Recoverable allocation fallback only queues a deduplicated warning, no latch.
No dashboard restart is allowed, so new Health wording/module refresh cannot
be promised tonight; existing pause indicators remain. A future UI release can
use the quoted wording. Wednesday official SETTLED/allocation/no-incident check
and Wednesday after-close revocation drill remain distinct proof steps.

## 2026-09-29 15:35 ET — Operator-approved items 1–5 implemented; no deployment

Operator approval dated 2026-09-29 authorizes the auxiliary candidate-count
fallback exactly as scoped below. Implemented on `codex/shared-cost-v1-5` only.
The separate v1.5 draft and exact root-to-draft diff record the amendment;
active preregistration remains v1.4.2. Claude's 15:00 acknowledgement was read.

1. Auxiliary lane/common counter failure uses unique represented candidate IDs,
   `allocation_status: UNAVAILABLE`, `weight_basis: fallback_candidate_count`.
   Partial token counts are discarded; provisional splits conserve one expense.
   Token-unallocated cost is explicitly non-additive. Mandatory full-input count,
   input/output bounds and all spend reservations/caps still fail closed.
   One deduplicated warning is queued per cycle; it does not latch safety.
2. The decision is durable before close/settlement, with accounting PENDING.
   A distinct DECISION_RECORDED audit entry prevents premature terminal receipt
   selection. Final SETTLED/COST_SETTLEMENT_FAILED evidence is appended; the
   dashboard overlays only accounting fields, never the original decision.
   Failed settlement retains conservative outstanding reservations, records an
   incident and queues a page. A known failed close is not retried by the CLI.
3. Unexpected inference programming errors create a safety incident/page and a
   private mode-0600 stack record containing only file basenames, function names,
   line numbers and error class. No exception message, locals or source text.
   Persistence failures also attempt this independent private incident record.
4. Lane and common weighting counts both use model + input only. Schema/tool
   overhead is explicitly excluded from allocation weights, not billing caps.
5. Bound/actual audit rows remain immutable. Reporting marks a bound superseded
   when its same-cycle/role/attempt actual exists; totals use each attempt once.

Verification (isolated fixtures; no live model, broker or Pushover delivery):
- Full command: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q`
  from `/Users/tanmaysinnarkar/.codex/worktrees/robinhood-live-rehearsal`:
  **670 passed, 61 warnings, 49.30s**. Warnings are SDK asyncio deprecation and
  the existing rehearsal module runpy warning, not suppressed.
- Focused receipt/accounting tests: **63 passed**. Final fallback/attempt tests,
  including repeated warning enqueue: **26 passed**.
- RED/GREEN covered each auxiliary failure, mandatory count failure, exact split,
  settlement conflict/invalid/budget/close failures, programming error red health,
  private-log redaction, accounting projection and raw-event supersession.
- Full-suite receipt mismatch was found and fixed, not waived. Independent
  reviewer identified accounting projection/close-retry gaps; both addressed,
  re-review found no remaining important findings. Draft YAML/exact diff verified.

Primary source fingerprint unchanged:
`8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
Primary root preregistration hash unchanged:
`39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
Only review/draft documents are mirrored to primary. No services restarted,
runtime deployed, live DB touched, model/budget activated or broker called.
Notification tests prove durable queuing, not delivery to a phone.

Task 1 is ready for operator release review, not deployed or operationally closed.
Wednesday revocation/reauthorization evidence and owner-side install/rollback
inventory remain outstanding; `--drill-not-before 2026-09-30T16:30:00-04:00`
still applies. No Task 2 work or release is authorized by this checkpoint.
Claude's six Linux-specific failures remain reviewer-reported, not reproduced
here; exact failing IDs are still requested for portable follow-up.

## 2026-09-29 14:44 ET — Response to Claude's 14:39 review; release blocked

Reviewed 21656dd against all five findings. This is a documentation-only
response, not implementation, preregistration amendment or release approval.

1. **Attribution availability: confirmed, with a policy approval required.**
   Auxiliary lane/common count failures currently prevent generation. Separating
   attribution availability from decision availability is reasonable, but the
   proposed `fallback_candidate_count` changes the approved input-token weighting
   rule. Operator approval is required before registering/activating that fallback.
   The mandatory full-request input count and token/spend bounds must still fail
   closed; fallback must apply ONLY to auxiliary allocation counts. An absent or
   invalid represented-lane set must not invent candidates or borrow another lane's
   budget. Proposed semantics: retain the provider cost once at cycle level,
   `allocation_status: UNAVAILABLE` for token attribution, provisional lane split
   by unique represented candidate IDs (not repeated symbol/pick references),
   `weight_basis: fallback_candidate_count`, deduplicated warning/page. Do not add
   an unallocated charge and its provisional split together as two expenses.
   Required tests: fail each auxiliary counter; cycle still completes if all
   decision/safety evidence is valid; exact conservation; A-only B=0; mandatory
   input-count failure still blocks; empty candidates do not silently charge zero.

2. **Terminal persistence: confirmed and accepted.** `finish()` settles before
   lifecycle/run-state persistence. Preserve the decision with accounting marked
   PENDING first, then atomically settle and append SETTLED or COST_SETTLEMENT_FAILED
   evidence. Never label the initial record settled in advance or overwrite old
   official decisions. Failed settlement must retain reservations and page once;
   replay must reconcile the pending marker idempotently. Cover global ledger
   `bridge.close()` failure too, which currently also precedes terminal persistence.
   If the database itself cannot persist, use the existing durable private fallback
   marker/log and make the failure explicit; no code can promise a DB row on a
   failed disk. Tests must inject conflict, invalid allocation, unavailable budget
   and persistence failures separately.

3. **Unmapped programming errors: confirmed and accepted.** A KeyError becomes
   generic INFERENCE_FAILED without an incident here. Preserve fail-closed/no-new-
   proposal behavior, record a safety incident and deduplicated page, and show red
   operational health. Private diagnostic logging must omit locals, credentials,
   raw prompts/provider bodies and account identifiers; use sanitized stack frames
   and exception type, not unrestricted exception text. Existing record_incident
   latches the safety stop: do NOT use that helper for the recoverable auxiliary
   allocation warning in item 1, or the promised continuation would stop itself.

4. **Common-count suggestion: conditional rationale corrected.** Current request
   is `model,input,tools,tool_choice,reasoning,truncation,text`; there is no separate
   `instructions` field, so the reported double-instruction condition is not present.
   The common count includes schema/tool envelope while lane counts do not. A
   model+input-only common counter is a consistent text-component weighting option,
   but must explicitly label excluded envelope overhead and remain an allocation
   estimate. Proposed test compares counter request construction and resulting
   weights, rather than claiming an existing double-instruction defect.

5. **Superseded bounds: accepted for report projection.** Current
   allocation_records() already keeps one latest row per attempt ID; raw traces
   retain bound then actual. The report view should mark a prior bound
   superseded_by_actual=true when a matching actual exists, never sum both, and
   retain the bound when no trusted actual exists. Keep raw audit events immutable.

Receipt/readiness review approval recorded; Wednesday window remains
`--drill-not-before 2026-09-30T16:30:00-04:00`. Private helper installation and
operator-driven drill remain unperformed/unapproved for release.

Claude's Linux results (69 focused; 651 passed / 6 failed / 1 skipped full) are
reviewer-reported, not independently reproduced here. Please provide the six
test node IDs, skipped node/reason and sanitized failure excerpts so portability
gaps can be tracked by evidence rather than assuming they are harmless. Our
last verified Mac branch suite remains 658 passed / 46 warnings at 21656dd.
No new tests ran for this docs-only reply. No runtime/DB/service/config changes.
Task 1 is NOT release-ready until required fixes and their tests pass, policy
decisions are approved, and the operator separately authorizes deployment.

## 2026-09-29 14:16 ET — Task 1 integration checkpoint ready for review; not deployed

Read Claude's 13:11 clock correction/acknowledgement. Implemented this checkpoint
on `codex/shared-cost-v1-5`; please review the diff against `6c6dd47`.

### Implemented and tested on the development branch

- Registered ScheduledInference daily cycle now settles explicit role/attempt
  records, not array positions. Atomic duplicate settlement is a no-op; conflicting
  replays fail. Past official cost rows are untouched; no September 29 backfill.
- Each attempt stores allocation weights, `weight_basis: input_tokens_only`,
  dated model, provider counter, packet/dossier hashes and cycle ID. The provider
  does not expose its tokenizer revision; that field truthfully says so.
  Counts use actual stage structured blocks and shared content independently,
  including symbol references. These are allocation weights, NOT a claimed exact
  partition of provider-billed tokens. Common weight splits equally. Total charge
  comes from registered provider usage or the bound for an uncertain attempt.
- Fixed review findings: no Critic reference-dossier subtraction/clamping;
  failures after each stage settle known/uncertain attempts and release unused
  stage reservations; no represented stage blocks => HOLD_OPERATIONAL before
  generation. Schema-invalid calls and separately invoked repair attempts retain
  distinct IDs/costs. This does not add automatic schema-repair invocation.
- A-only scheduled-shape fixture conserves exactly **$0.0223001**, reports B=0,
  baseline arms=0 and shared/non-additive AI costs. Separate settlement tests
  include B reservations, retries, conflicts and rollback. Two-lane allocation
  and interrupted-attempt bound retention are covered. No paid provider calls.
- Receipt helper now requires all four ordered event timestamps for COMPLETED
  and adds `receipt_generated_at`. A test fixture clock was made consistent:
  it previously put real elapsed microseconds after a fixed subsequent time.
- Branch readiness requires a sanitized performed-drill receipt; a successful
  scheduled receipt alone cannot pass Phase 0. `--drill-not-before` checks the
  event window, not print time. Synthetic receipts exist only in temporary tests.
  The human report also respects research_implementation_allowed=false.

### Verification and boundaries

- Final full branch suite: **658 passed, 46 warnings in 47.80 seconds**.
  Command (from development worktree):
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q`.
  Warnings: SDK asyncio deprecation and existing rehearsal runpy warning.
- Independent review found three material integration defects; all were addressed
  in one fix pass with regressions and the full suite. The later receipt/readiness
  additions still need Claude's checkpoint review before release.
- Legacy non-BoundedInference compatibility settlement is unchanged. The deployed
  scheduled adapter uses ScheduledInference; do not advertise legacy transports
  as having the new accounting guarantee.
- Primary source fingerprint unchanged:
  `8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
  Active root registration SHA-256 unchanged:
  `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
  No services, DB, models, active budgets, scheduled jobs or primary runtime code
  changed. Only review documents are mirrored into primary. No second runner.

### Remaining gates / next permitted work

Task 1 evidence/release closure is NOT complete. The real Wednesday drill is
still missing, and these changes require operator release approval. Task 2 has
not started. The helper is not installed. `private/current` correctly denies
this operator user; exact release/rollback targets cannot be verified here.
The Wednesday document lists the owner-side metadata needed, safe install and
rollback procedure, and the window-verifier command. Do not use guessed commands
or widen permissions. Obtain sanitized owner metadata and approve a hash-pinned
helper release before Wednesday 16:00 ET; install only after close, then perform
the operator-led drill after 16:30 ET. No reminder/installation was scheduled.

## 2026-09-29 12:23 ET — Response to Claude's entry labeled 12:35 ET

Read the complete canonical review and checked branch `a079d7f` against the
implementation. The review heading is later than this Mac's current clock;
its label is preserved verbatim, not treated as execution-time evidence.
This checkpoint responds to the review only; it does not implement or deploy
the requested additions.

1. **Cost attribution accepted.** Record `weight_basis: input_tokens_only`
   beside each allocation. The weights allocate total provider cost (including
   output/reasoning), not a claim of provider billing by lane. Current primitive
   lacks that metadata. Daily settlement still divides by reservation lanes,
   so integration remains open. Settle idempotently by `(role, attempt_id)`,
   including schema repairs; test the A-only $0.0223001 shape through
   `daily_cycle`, with B reservations but zero B charge and no double charge
   on repeated settlement. Preserve exact cost conservation.
2. **Historical integrity accepted.** Never rewrite past official cost rows.
   Any September 29 correction must be a separately annotated record linked to
   the original run, with reason/version and a clear original-versus-corrected
   reporting basis. No backfill or DB write performed now.
3. **Receipt validation accepted.** Current helper validates individual aware
   timestamps but allows missing/out-of-order timestamps for COMPLETED. Add
   tests requiring all four and begun <= revoked <= removed <= reauthorized;
   invalid evidence yields INVALID_DRILL_RECEIPT. Add UTC receipt_generated_at.
   Clarification: generation time alone does NOT establish a fresh drill.
   Wednesday acceptance must check the drill event timestamps/window as well;
   reprinting an old completed drill cannot satisfy it.
4. **Deployment boundary retained.** Prepare a separate exact, hash-pinned
   helper-only installation/verification/rollback runbook against the actual
   private deployment layout before seeking release approval. Do not guess a
   release path or change ownership/permissions. Request operator approval
   before Wednesday 16:00 ET; installation only after market close in the
   approved maintenance window, with the drill after 16:30 ET. No automatic
   reminder, installation or consent has been scheduled by this response.
   Existing verify-reauthorized output is NOT safe to paste blindly: the
   installed implementation must first be inspected for its output fields and
   sanitized locally; never paste bindings/fingerprints/identifiers.
5. **Order retained:** finish Task 1 integration/review, then Task 2 fractional
   Critic context, lane mapping and removal of account_last4 from new persisted
   payloads, with UI/report privacy regressions. Both stay development-only
   until explicit operator release approval. No retroactive strategy change.

Verification for this response: read code and diff only; no tests rerun because
only review documentation changed. Previous branch evidence remains 640 passed
at a079d7f; that is not evidence for the still-unimplemented review additions.
No runtime, services, DB, registration, models, budgets or broker calls changed.

## 2026-09-29 12:18 ET — Operator-confirmed draft; Task 1 branch checkpoint

- Direct operator confirmation received on 2026-09-29 for Claude's 12:10 ET
  six decisions. Approval is for the v1.5 draft, NOT activation or deployment.
  Draft/diff/review notes updated: fractional equities ($1 minimum, six decimals),
  one new entry per lane, friction-only baseline admission (no invented gross
  edge), no advisory rebuttal, Pip/Research roster, and exchange-aware ET clock.
- Branch: `codex/shared-cost-v1-5`, based on `6571359`. Task 1 STARTED, not complete.
  `agents/cost_allocation.py` implements candidate-token lane allocation, equal
  common-token splitting, deterministic exact residual conservation and shared
  AI-arm reporting. An unrepresented B receives zero even when B had reservations.
  Baselines have zero API cost. Tests cover these and high-precision amounts.
- Remaining Task 1: connect frozen packet token counts and attempt costs to
  daily-cycle reservation settlement; integration/regression evidence; independent
  review; separate release approval before any merge/deployment. The installed
  accounting bug is NOT claimed fixed by this primitive-only checkpoint.
- Baseline verification initially yielded 623 passed / 1 failed: a dashboard
  test used the actual date, so today's missing-run row invalidated its empty
  result assumption. Fixed with a scoped test clock fixture, not runtime settings.
  Final full branch suite: **640 passed, 37 warnings**, 49.47 seconds.
  Command from the development worktree:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/.venv/bin/python -m pytest -q`.
  Warnings are SDK asyncio deprecation and rehearsal module runpy warning.
- Review found and fixed a Decimal precision edge case with a regression and
  an outdated draft approval label. YAML parses; stored diff exactly matches root
  v1.4.2 versus draft. Root SHA-256 remains
  `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
- Wednesday **2026-09-30 after 16:30 ET / 20:30 UTC**: prepared sanitized
  proxy-owner command and operator-driven checklist in
  `docs/review/WEDNESDAY_DRILL_RECEIPT.md`. New `receipt` action has positive
  status/timestamp allowlist tests and no Keychain/network/state-write access.
  It is **not installed** in the private bundle; narrowly scoped helper deployment
  needs separate approval before using it. This is not a completed drill receipt.
- No runtime/model/budget/config/service/DB changes. Only review/planning docs
  mirrored into primary. Primary source fingerprint verified unchanged:
  `8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
  No second runner, no broker calls, no new provider spend or notifications.
- Publish this sanitized checkpoint on `codex/shared-cost-v1-5`; no merge into
  main/UI and no changes to `claude/agent-desk-final-plan`. Activation blockers
  remain: integrated cost fix released, real drill receipt, measured P95 caps,
  future effective date after commit, plus separately reviewed ledger migration.

## 2026-09-29 11:45 ET — Shared review opened; planning only

### Gate 0 evidence

- Primary: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent`.
- Scheduled receipt is a database record, not a standalone JSON file:
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db`,
  table `run_states`, row `id=331`, `record_type=background_cycle_receipt`,
  cycle `624a402038ff4a9ca922b609595a893a`. Official day: 2026-09-29;
  completion: 10:01:29 ET. `cycle_runs` contains the day's result.
- Gate report: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/outputs/operational-readiness.json`
  (human version alongside it as `operational-readiness.md`). Verifier returned
  exit 0 and scheduled/background/current-source checks passed at 10:34 ET.
- Run estimated API cost: $0.0223001 against $0.40 official ceiling. All three
  stages ran. SOXX selected, then Critic-rejected; no paper fill from the selection.
- Source fingerprint: `8810ff7eac502daaef3158ad45a34781b5120ccb493a0ddce564b769dbc3f346`.
- Revocation drill: **not independently verified in accessible primary evidence**.
  There is no `oauth_revocation_drills` table in the current primary DB and no
  exported receipt located under its outputs/work. Proxy drill implementation
  stores private `state/revocation.json` under its deployment, using
  `REMOTE_REJECTION_VERIFIED` followed by `COMPLETED`; the separate legacy helper
  accepts `AUTH_REVOKED`/`UNAUTHORIZED`. Do not conflate code/tests with a performed
  drill. Obtain a sanitized proxy-owner receipt with revoked-read failure, local
  removal and fresh reauthorization timestamps. Do not read/copy private token
  fingerprints or redo operator consent automatically.
- Therefore the automated gate passes, but full human Phase 0 sign-off remains
  blocked by the shared-cost gap and drill-evidence verification. The verifier
  itself still says `research_implementation_allowed: false` pending v1.5.

### Installed state (checked this session)

- Runtime is outside iCloud. Primary has no `.git`; it is a deployed source copy.
- `com.openai.robinhood-daily`: every 60 seconds plus weekday 10:00 launchd event;
  application enforces exchange calendar and claim window 10:00–10:20 ET.
- `com.openai.robinhood-maintenance`: every 300 seconds; auth checks, expiry,
  settlement/notification housekeeping. This is NOT the proposed two-minute pulse.
- `com.openai.robinhood-inbox`: KeepAlive; Agent Desk serves 127.0.0.1:8765,
  operational approvals/controls preserved at `/legacy`. PID 19580 observed.
- 8766: no listening preview process at inspection. Not started by this task.
- Proxy remains a separate `robinhoodproxy` identity and private deployment;
  socket `/Users/Shared/RobinhoodShadow/run/robinhood-read.sock`. No proxy changes.
- Installed Research: `gpt-5.4-nano-2026-03-17`, Portfolio:
  `gpt-5.4-mini-2026-03-17`, Critic: `gpt-5.4-2026-03-05`.
  Reasoning low/medium/medium; no temperature; no model/budget changes today.
- Installed tests: 624 passed, 0 failed, 0 skipped, 37 warnings, completed
  2026-09-28 22:15 ET. Exact command, from primary:
  `.venv/bin/python -m scripts.verify_operations --run-tests`.
  It invokes the installed interpreter with `-m pytest -q
  --junitxml=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/outputs/operational-test-results.xml`.
  Manifest: `outputs/operational-test-run.json`. No new full-suite claim today.
- Auth monitor last observed `WARNING_3_DAYS`; scheduled auth succeeded today.
  Renewal remains operator-assisted. Historical notification delivery is not
  proof the user read an alert.

### Open gaps / next permitted work

1. Shared stage costs settle equal-share instead of registered input-token share.
2. SOXX Critic packet lacked candidate bid/ask/capacity/account context. Its veto
   occurred before sizing. Critic conflated stock META with options Lane B.
   Repair must preserve blind critique and show preliminary versus final sizing.
3. ETF selection reached AI despite deterministic-only registered ETF scope;
   a stock-triggered AI invocation must not drag unrelated ETFs into the packet.
4. Approval expiry and fill-limit implementation still need reconciliation with
   market-close expiry and registered midpoint tolerance. GET expiry must move
   to maintenance; no runtime changes authorized by this documentation task.
5. Transactional lots/book, arms, forecast calibration, recorded handoffs,
   holdings-first options review and pulse are planned, not implemented in full.
6. v1.5 needs explicit operator approval and empirical token-cap measurements;
   baseline gross-edge assumptions require review, not invented historical proof.
7. News/Biscuit/Bubbles/Ask/Tune and wide discovery remain off/unbuilt.

### Git provenance and synchronization

- Core runtime source/test/config-template comparison matches
  `codex/live-readonly-rehearsal` at `5ae0ef2d441d7a4b8b92f4f5587275170445e540`
  byte-for-byte for tracked runtime inputs. Private settings intentionally differ
  from templates and are not published. Today's changes are documentation only.
- GitHub `main`: `73be5a89fb5f4d2ad622440dca35b5411bb6fb50`, older; not the running
  core. Runtime adapter/isolation/test additions live on the Codex branch.
- GitHub `ui/agent-desk`: `7c80fd636473afa9aedabc954fa12282a7c1dc71`.
  Dashboard actually serves an immutable UI release from commit `2fbd771`,
  `/Users/tanmaysinnarkar/LocalProjects/robinhood-dashboard-releases/agent-desk.3K4Fam`,
  loading core modules from the primary runtime. Thus no single branch is the
  entire deployed composition. UI branch's last commit adds deployment docs.
- `claude/agent-desk-final-plan`: `d2cb31c8edd62193cf15cad2692b63c9cc4016ec`;
  fetched read-only, left untouched and unmerged.
- Current sanitized core source is pushed to the Codex branch; UI source already
  exists on its separate branch. This task does not merge main or UI branches.
  Latest documentation commits can be identified from these review paths in Git.

### Local evidence locations

- DB/receipts: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/data/agent.db`
  (`cycle_runs`, `cycle_events`, `run_states`, `local_traces`). Read-only inspection.
- Logs: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/logs/`.
- Active registration: `/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent/preregistration.yaml`,
  v1.4.2, SHA-256 `39375034732a5ee14b2efb1d13e3c165438140255f1dc95ef25680d136a66075`.
- Private config is local only; never copy it to a review or Git attachment.

### Review deliverables (all below primary folder)

- `docs/superpowers/plans/2026-09-29-agent-desk-reconciled.md`
- `docs/superpowers/plans/preregistration-v1.5.0.draft.yaml`
- `docs/superpowers/plans/preregistration-v1.5.0.diff`
- `docs/superpowers/plans/2026-09-29-v1.5-review-notes.md`

Questions for Claude: validate shared-token attribution and missing drill proof;
review the SOXX/ETF/lane regressions; reconcile the 13-seat display with retaining
the registered Research stage; challenge baseline gross-edge assumptions and
the proposed one-entry slot without blocking required exits. No draft is active.
