"""Analyst desk: AI off the trading path.

Language models write commentary and news/sentiment notes; code computes a market regime (a
Gaussian hidden Markov model retrained after the close) and shadow Kelly sizes. Nothing here can
place, size, approve or block a trade: the official run and its rules are unchanged, and every
output is stored in its own database (robinhood-diagnostics/analyst/analyst.db).
"""
