"""Firm Lab: the next research architecture, built beside the registered system (Control A).

Rules this package holds itself to:

* Isolation. Firm Lab has its own database. It may read the registered ("Official") database only through
  ``firm_lab.official`` (SQLite read-only, query-only, write statements denied). It never writes there.
* BUILD_OBSERVE. The persisted mode starts, and at this checkpoint stays, BUILD_OBSERVE: data, features,
  research records and counterfactual decisions are allowed; orders, fills and portfolio state are not.
  ``firm_lab.boundary.ExecutionBoundary`` is the single place any order or fill attempt must pass, and it
  fails closed. There is no fill engine and no order, fill, position or cash table in the Firm Lab schema.
* No second trader. Nothing in this package imports the trading modules (paper broker, inbox execution,
  risk issuance, broker clients). A test scans the source to keep it that way, so a research-only worker
  built from this package is structurally unable to trade.
* No fabrication. A capability without a real data source is UNAVAILABLE and returns no value.
* Standard library only, so the research worker and the read-only dashboard page need nothing else.
"""

MODE_BUILD_OBSERVE = 'BUILD_OBSERVE'
MODE_REGISTERED_PAPER_TRIAL = 'REGISTERED_PAPER_TRIAL'      # not reachable at this checkpoint
DEVELOPMENT_ONLY = 'DEVELOPMENT_ONLY'
SCHEMA_VERSION = 1
