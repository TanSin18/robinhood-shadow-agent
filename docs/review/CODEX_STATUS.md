# Codex status and questions

## 2026-10-03 16:07 ET — Checkpoint 5 takeover; first storage slice tested

Claude stopped at raw macro sample capture (`3fdf450`), not live macro validation.
Work continues on `codex/checkpoint5-macro`, separate from installed Control A.

Added strict factual macro observation/event storage and 40 passing tests.
Fresh full suite: **939 passed, 1 failed**, 27 warnings. Existing failure:
`tests/test_installed_isolation.py::test_installed_child_filters_tools_and_denies_unexpected_server`
rejects Codex `configWarning`. Keep the prepared compatibility patch separate;
it remains `PREPARED_AND_PROVEN_NOT_INSTALLED`.

Control A release N fingerprint remains
`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`.
Daily last exit 0; no stop file; installed Lane B new-buy pause confirmed.
No service restart, deployment, official DB writes, model calls, paid feed or
strategy activation. No live research migration or macro capability promotion.

Checkpoint 5 is **not complete**. Next: source parsers with authoritative
publication evidence, real validation/ingestion, provider comparison, then the
read-only macro UI. Date-only vintage samples must not silently become exact
publication timestamps. No user action or credential entry is required for this
storage slice.

Full implementation boundary, commands, review finding/fix, results and remaining
work: [Checkpoint 5 handoff](../firm_lab/CODEX_CHECKPOINT5_HANDOFF.md).
