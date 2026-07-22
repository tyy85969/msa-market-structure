"""Errors raised by the causal C-007A resonance-frame framework."""


class ResonanceFrameConfigurationError(ValueError):
    """Raised when resonance-frame configuration is invalid."""


class ResonanceFrameInputError(ValueError):
    """Raised when upstream histories or reference prices are ineligible."""


class ResonanceFrameEngineError(RuntimeError):
    """Raised when deterministic frame construction cannot complete."""


class ResonanceFrameSerializationError(ValueError):
    """Raised when a serialized resonance-frame payload fails closed."""
