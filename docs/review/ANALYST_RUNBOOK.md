# Analyst desk runbook (release G)

Decided 2026-10-01 by the operator after mentor review ("keep agents off the trading hot path;
use LLMs for commentary, auction analysis and news/sentiment; retrain an HMM and compute Kelly
post-market"):

- **Official 10:00 run: unchanged.** No amendment. The AI may still propose a stock as before.
- **AI trader: retired before it started** (`python -m agents.ai_trader.cli retire ...`). Trial-log
  row 18 (`ai_trader_fwd_v1`) is withdrawn, never run in paper. Its code stays for the record.
- **Analyst desk (new, `agents/analyst/`)**: its own DB `robinhood-diagnostics/analyst/analyst.db`,
  runs inside the existing daily service tick (no second runner), never trades or sizes.
  - Morning 10:05–12:00 ET, after the Official run COMPLETED: news (Google News RSS; SEC EDGAR if
    `robinhood-diagnostics/analyst/contact.txt` holds "Name email"), then commentary on the official
    decision with news/sentiment notes. No broker reads.
  - After the close 16:15–18:00 ET: read-only daily bars for the 23 names (same gateway bounds),
    3-state Gaussian HMM on VTI daily log returns (long history from the research backfill +
    gateway bars), shadow Kelly per ticker (raw / half / disciplined: 0 unless t ≥ 2, cap 25%),
    daily auction read (gap, range vs ATR20, close location, relative volume, day type), news,
    close commentary.
  - Model `gpt-5.4-mini-2026-03-17`, $1.00/day cap with worst-case reservation, strict JSON,
    no tools. Code checks every cited number, flags uncited numbers, hype and order-like language.
  - Headlines are untrusted: stored with links, passed only inside a labelled data block.
  - Max 2 attempts per job per day; every failure journaled; never an Official failure.
- **Research freeze exception** (operator, 2026-10-01): HMM + Kelly built now as shadow-only.
  Backtests remain frozen until 2026-10-31.

Operator commands (main user, after release G is INSTALLED):

    P=/Users/tanmaysinnarkar/LocalProjects/robinhood-shadow-agent
    $P/.venv/bin/python -m agents.ai_trader.cli retire --official-database $P/data/agent.db
    $P/.venv/bin/python -m agents.analyst.cli init --official-database $P/data/agent.db
    $P/.venv/bin/python -m agents.analyst.cli status --official-database $P/data/agent.db

Known limits: daily bars only (the gateway forbids intraday), so the auction read is not a true
market profile; regime-conditional Kelly uses in-sample HMM labels (look-ahead); nightly refits can
relabel history (recorded as `stability_vs_last_fit`).
