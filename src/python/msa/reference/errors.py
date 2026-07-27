"""Errors raised by the formal MSA reference-profile boundary."""


class MSAReferenceError(ValueError):
    """Base error for immutable MSA reference profiles."""


class ReferenceConfigurationError(MSAReferenceError):
    """Raised when a reference contract is not formally valid."""


class ReferenceInputError(MSAReferenceError):
    """Raised when a public reference entrypoint receives an invalid type."""


class ReferenceSerializationError(MSAReferenceError):
    """Raised when serialized reference data fails closed."""


class ReferenceAuthorityError(MSAReferenceError):
    """Raised when content differs from the explicitly authorized profile."""
