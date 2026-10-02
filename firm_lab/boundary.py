"""The single Firm Lab execution boundary.

Any Firm Lab order or fill attempt, paper or real, must come through ``ExecutionBoundary``. At this checkpoint
it has exactly one behaviour: record the attempt and refuse. In BUILD_OBSERVE it raises NoFillInBuildObserve;
in any other mode it raises NoExecutionEngine, because no fill engine exists; a real order raises
RealExecutionDisabled in every mode. It holds no reference to a broker, a paper ledger or the Official
database, so there is nothing for it to mutate.
"""
from __future__ import annotations

from . import MODE_BUILD_OBSERVE
from .errors import NoExecutionEngine, NoFillInBuildObserve, RealExecutionDisabled


class ExecutionBoundary:
    def __init__(self, store):
        self._store = store

    def submit(self, *, instrument, asset_class, side, quantity, note=''):
        """A paper order of any kind (stock, ETF, option; buy or sell). Always refused at this checkpoint."""
        try:
            mode = self._store.mode()
        except Exception:
            mode = None                                   # an unreadable mode is not permission
        attempt = {'instrument': str(instrument), 'asset_class': str(asset_class), 'side': str(side), 'quantity': str(quantity),
                   'mode': mode, 'note': str(note)[:200]}
        try:
            self._store.event('FILL_REFUSED', attempt)
        except Exception:
            pass                                          # refusing never depends on being able to log
        if mode == MODE_BUILD_OBSERVE:
            raise NoFillInBuildObserve(f'Firm Lab is in BUILD_OBSERVE: no {side} of {instrument} can be created.')
        raise NoExecutionEngine('Firm Lab has no fill engine. A registered trial and an explicit operator start come first.')

    def real_order(self, *_, **__):
        try:
            self._store.event('REAL_ORDER_REFUSED', {})
        except Exception:
            pass
        raise RealExecutionDisabled('Real execution is disabled. Firm Lab has no path to a broker.')
