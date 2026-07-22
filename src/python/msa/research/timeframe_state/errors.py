"""Errors raised by the causal C-006B per-timeframe state engine."""


class TimeframeStateConfigurationError(ValueError):
    """Raised when the explicit timeframe-state policy is invalid."""


class TimeframeStateInputError(ValueError):
    """Raised when lifecycle history or an as-of schedule is invalid."""


class TimeframeStateEngineError(RuntimeError):
    """Raised when deterministic state construction cannot complete."""


class TimeframeStateSerializationError(ValueError):
    """Raised when a serialized timeframe-state payload fails closed."""
