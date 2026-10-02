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


class IsolationError(FirmLabError):
    """The Firm Lab database must never be the Official database or live beside it."""


class TrialActivationNotAvailable(FirmLabError):
    """Starting a registered trial is a separate operator decision and is not built at this checkpoint."""
