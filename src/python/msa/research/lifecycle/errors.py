"""Errors raised by the causal C-006A lifecycle framework."""


class LifecycleConfigurationError(ValueError):
    """Raised when lifecycle policy configuration is invalid."""


class LifecycleInputError(ValueError):
    """Raised when source bars or confirmed subjects are ineligible."""


class LifecycleSerializationError(ValueError):
    """Raised when a serialized lifecycle payload fails closed."""


class LifecycleEngineError(RuntimeError):
    """Raised when deterministic lifecycle processing cannot complete."""
