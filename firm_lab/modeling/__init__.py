"""Checkpoint 7: modeling laboratory and validation tournament. Research only.

MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE. Nothing in this package can place, size or schedule a trade, and
nothing in the trading runtime imports it. A model here has a research status and nothing else: there is no
production or live status, no promotion, and no output that says what to do with a security.

Time rule (operator decision, 2026-10-03): SESSION_TIME_RETROSPECTIVE. Firm Lab captured its inputs on 2026-10-01 to
2026-10-03, so under the strict known-at rule no historical session has a single usable feature. For modeling
research only, a stored close is treated as known at the close of its own exchange session, and every other input is
treated as known at its publisher's own time (SEC acceptance, macro publication). Nothing is treated as known earlier
than that. Every dataset, model and report built this way is labelled retrospective: it is not evidence that the
system held the data at the time.
"""
WARNING = 'MODEL RESEARCH ONLY — NO TRADING STRATEGY IS ACTIVE'
TIME_POLICY = 'SESSION_TIME_RETROSPECTIVE'
DATABASE_ROLE = 'CHECKPOINT7_MODELING_RESEARCH'
BENCHMARK = 'VTI'
# The only statuses a research model may have. There is deliberately no production or live status.
STATUSES = ('EXPERIMENTAL', 'CHALLENGER', 'REJECTED', 'ELIGIBLE_FOR_FUTURE_REVIEW')
INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
EXPERIMENTAL_INSUFFICIENT_DATA = 'EXPERIMENTAL_INSUFFICIENT_DATA'
