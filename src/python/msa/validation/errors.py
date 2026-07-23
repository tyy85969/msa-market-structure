"""Error boundary for the independent C-008 validation framework."""


class MSAValidationError(ValueError):
    """Base class for formal validation failures."""


class ValidationConfigurationError(MSAValidationError):
    """Raised when a validation configuration is not formal."""


class ValidationInputError(MSAValidationError):
    """Raised when an audit entrypoint receives an unsupported input."""


class CausalAuditError(MSAValidationError):
    """Raised when an audit cannot safely inspect its subject."""


class ValidationComparisonError(MSAValidationError):
    """Raised when two subjects do not form the requested relationship."""


class ValidationSerializationError(MSAValidationError):
    """Raised when a validation contract cannot be deserialized strictly."""
