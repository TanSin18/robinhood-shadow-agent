"""Firm Lab research collectors: the only code in the Firm Lab that talks to the network.

Research-only. A collector fetches raw data from a provider the operator chose, hands it to the ``firm_lab``
interfaces for validation, and stores what passes. It cannot trade: this package imports nothing from the trading
system (``agents``, ``broker``, ``risk``, ...), starts no process, and network access lives in ``transport`` alone.
A test enforces all three.

Nothing here runs on a schedule. Each collector is started by hand, by the operator, with the operator's own
configuration (a declared SEC User-Agent, vendor API keys) supplied through environment variables. No credential
is stored in the repository, printed, or written to the Firm Lab database.
"""
