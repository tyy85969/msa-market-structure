"""Errors raised by the research-only C-005 Level Pool framework."""


class LevelPoolConfigurationError(ValueError):
    """Raised when Level Pool configuration is invalid or unsupported."""


class LevelPoolInputError(ValueError):
    """Raised when candidate or dependency-family input is ineligible."""


class LevelPoolClusteringError(RuntimeError):
    """Raised when deterministic clustering or replay cannot complete."""


class LevelPoolSerializationError(ValueError):
    """Raised when a public serialized payload is invalid or unsupported."""
