"""Errors raised by the research-only C-004 level-generator framework."""


class LevelConfigurationError(ValueError):
    """Raised when generator configuration is invalid or unsupported."""


class LevelInputError(ValueError):
    """Raised when canonical bars or seed candidates are ineligible."""


class LevelGenerationError(RuntimeError):
    """Raised when deterministic generation or replay cannot complete."""
