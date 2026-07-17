"""Domain-specific errors for immutable market-structure contracts."""


class DomainValidationError(ValueError):
    """Raised when a public domain object violates an invariant."""


class DomainSerializationError(DomainValidationError):
    """Raised when a serialized domain payload is invalid or unsupported."""


class DomainAvailabilityError(DomainValidationError):
    """Raised when an object is consumed before its causal availability time."""
