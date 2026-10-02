"""Firm Lab errors. Each one means "stop"; none is caught and worked around inside the package."""


class FirmLabError(RuntimeError):
    pass


class NoFillInBuildObserve(FirmLabError):
    """Raised for every order or fill attempt while the mode is BUILD_OBSERVE."""


class NoExecutionEngine(FirmLabError):
    """Raised for every order or fill attempt in any other mode: no fill engine exists yet."""


class RealExecutionDisabled(FirmLabError):
    """Raised for every real-order attempt, in every mode."""


class OfficialWriteRefused(FirmLabError):
    """Raised when anything tries to write to the registered (Official) database through Firm Lab."""


class CapabilityUnavailable(FirmLabError):
    """Raised instead of returning a value when a capability has no real data source."""


class ProviderUnavailable(FirmLabError):
    """A connected provider could not answer (not configured, refused, rate limited, unreachable). Carries a short
    connection state; never a credential."""

    def __init__(self, reason, state='ERROR'):
        super().__init__(reason)
        self.reason, self.state = str(reason), state


class ProviderRejected(FirmLabError):
    """A provider answered, but the answer cannot be trusted as it stands (wrong identity, conflicting times, ...).
    ``issues`` is a list of (code, detail) pairs. Nothing from the response is kept."""

    def __init__(self, issues, provenance=None):
        self.issues = [(str(c), str(d)) for c, d in issues]
        self.provenance = provenance
        super().__init__('; '.join(c for c, _ in self.issues))


class IsolationError(FirmLabError):
    """The Firm Lab database must never be the Official database or live beside it."""


class TrialActivationNotAvailable(FirmLabError):
    """Starting a registered trial is a separate operator decision and is not built at this checkpoint."""
