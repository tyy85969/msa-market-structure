"""Errors raised by the causal C-007A resonance-frame framework."""


class ResonanceFrameConfigurationError(ValueError):
    """Raised when resonance-frame configuration is invalid."""


class ResonanceFrameInputError(ValueError):
    """Raised when upstream histories or reference prices are ineligible."""


class ResonanceFrameEngineError(RuntimeError):
    """Raised when deterministic frame construction cannot complete."""


class ResonanceFrameSerializationError(ValueError):
    """Raised when a serialized resonance-frame payload fails closed."""


class ResonanceScoringConfigurationError(ValueError):
    """Raised when C-007B scoring configuration is invalid."""


class ResonanceScoringInputError(ValueError):
    """Raised when a C-007B authoritative Frame input is invalid."""


class ResonanceScoringEngineError(RuntimeError):
    """Raised when deterministic C-007B scoring cannot complete."""


class ResonanceScoringSerializationError(ValueError):
    """Raised when a serialized C-007B payload fails closed."""
