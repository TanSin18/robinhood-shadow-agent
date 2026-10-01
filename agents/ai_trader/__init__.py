"""AI trader forward book (ai_trader_fwd_v1): a paper trading firm scored only going forward.

Seats: Scout, PM, Critic (models); Risk and Clerk (code); the operator on book B.
Three paper books: A (AI alone), B (AI + operator yes/no), C (matched random control).
Own database, never the Official one; never a second trading runner (it is invoked from the
existing scheduled service once wired); real orders impossible (no broker writes anywhere).
"""
