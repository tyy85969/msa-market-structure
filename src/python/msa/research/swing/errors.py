"""Errors raised by the research-only Swing detector framework."""


class SwingConfigurationError(ValueError):
    """Raised when a detector configuration is invalid or unsupported."""


class SwingInputError(ValueError):
    """Raised when canonical source input is not eligible for detection."""


class SwingDetectionError(RuntimeError):
    """Raised when deterministic detection or replay cannot be completed."""
