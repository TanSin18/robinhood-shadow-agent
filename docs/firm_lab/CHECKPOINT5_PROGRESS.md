# Checkpoint 5 continuation ledger

Accepted base: `5d4b4feb6aa28ef799263ab39f769cca20dd4c33`.
Branch: `codex/checkpoint5-macro`. No Checkpoint 6 work.

- Accepted storage foundation retained. Only additive series identities and an
  optional shared transaction were needed: a reproduced partial-release defect
  required atomic observation/event ingestion.
- Official Fed / BEA parsers validated against three captured releases each.
  BLS parsers have synthetic fixtures only: two CPI and two labor requests
  returned HTTP 403. Never label them live-validated.
- Treasury CSV identities can be decoded, but exact publication evidence is
  absent. Candidates are rejected, not inserted. FRED/ALFRED date-only vintage
  evidence remains inadmissible. No timestamp defaults.
- Manual collector and cached replay implemented; receipts distinguish actual
  requests from processed documents. No scheduler, brokerage or official writes.
- PCE prior-month republications preserve real July revisions at capture time.
  PCE scope is monthly percentage change, not price-index levels. CPI scope is
  unadjusted index levels; no conversion to seasonally adjusted levels.
- Read-only UI added on branch; not deployed. Source/time/revision disclosures;
  explicit missing states, model NOT_STARTED, NO TRADES.
- Final verification: 69 focused / 250 Firm Lab passed; full native 968 passed,
  1 pre-existing installed Codex failure. Real-vintage as-of assertions passed.
  Provider decision and full report written; cloud evidence missing, no deploy.
- Final review: five findings fixed via red/green regressions. PCE selected-table
  units and publisher-linked conventions; CPI date columns; durable family
  validation state; invalid clocks; malformed Treasury numeric receipts.
  No deferred minor findings. Source sync follows staged sanitation check.
- Ruling: no date-only substitutes for blocked BLS/Treasury. Cost: unavailable
  coverage until authoritative timing/source evidence is reachable.
- Ruling: no live deployment with incomplete validation/cloud evidence. Cost:
  macro page remains branch-only.
- Ruling: provider NONE until licensed-use/retention rights confirmed. Cost:
  intraday activation remains deferred.
- No maintenance install, service restart, paid feed, model, strategy or trial.
