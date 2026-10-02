# CONTROL A — the frozen baseline

Declared 2026-10-01 by operator order. Control A is the existing registered paper system. It keeps running so
that a later Firm trial can be compared with a clean baseline. It is not the future product.

## What Control A consists of

- the current registered universe (the existing 23 names);
- the 126-session momentum rule with the 200-session moving-average condition;
- the existing top-one behaviour;
- the current deterministic desk policy;
- the existing paper arms (Automatic arm, Approval arm, Rules only) in Lane A and Lane B;
- the existing registered exits (v1.5.1 ETF exit, v1.5.2 stock backstop, v1.6.0 15:50 protective check);
- the existing risk engine;
- the current Official database (`robinhood-shadow-agent/data/agent.db`), the experiment's source of truth;
- the current scheduling (`com.openai.robinhood-daily`, the only trading-capable service, and its maintenance job);
- the current recorded experiment and its result so far: NOT PROVEN versus VTI;
- the Official Lane B pause (no new option buys).

Installed identity at the freeze: release N, source `claude/ai-trader` @ `2d8ebc3`, fingerprint
`901f76060e481f50ea5a8ad4df84e16d5a90c013b552e0b8e9474cd045f5c876`, registration layers v1.4.2 + v1.5.0, v1.5.1,
v1.5.2, v1.6.0.

## What must not be added to Control A

More symbols, earnings, news, sector rotation, fundamentals, revision signals, new ML models, intraday signals,
new option strategies, new rankers, a new portfolio optimizer, different momentum windows. None of these, and no
other change made to improve its performance.

## What may still change

- Safety fixes and fixes to wrong labels, each under its own explicit, dated operator authorisation and release.
- Dashboard wording, delivered through the dashboard-only overlay. The overlay never contains a trading module.

## Known properties of Control A that are deliberately left alone

- Daily closes are labelled with the New York date of the bar's 00:00 UTC start (session minus one day).
- The drawdown latch has no reset; paper fills carry spread cost but no extra slippage.
- The draft v1.7 amendment that would have changed some of these was withdrawn and never installed
  (`claude/withdrawn-v1.7-draft`).
