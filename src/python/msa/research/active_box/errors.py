"""Errors for the C-007C Active Box contract layer."""


class ActiveBoxContractError(ValueError):
    """Raised when an immutable Active Box fact violates its contract."""


class ActiveBoxConfigurationError(ActiveBoxContractError):
    """Raised when selection policy configuration is invalid."""


class ActiveBoxInputError(ActiveBoxContractError):
    """Raised when authoritative C-007B input is inconsistent."""


class ActiveBoxSerializationError(ActiveBoxContractError):
    """Raised when a serialized payload is invalid or unsupported."""


class ActiveBoxProjectionError(ActiveBoxContractError):
    """Raised when a Zone cannot be projected to a formal boundary."""


class ActiveBoxEngineError(ActiveBoxContractError):
    """Raised when the causal selector receives invalid input or state."""


class ActiveBoxReplayError(ActiveBoxEngineError):
    """Raised when an Active Box replay schedule is invalid."""
