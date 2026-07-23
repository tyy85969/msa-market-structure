"""Errors raised by the C-007D MSA Core integration boundary."""


class MSACoreError(ValueError):
    """Base error for the immutable MSA Core integration layer."""


class MSACoreConfigurationError(MSACoreError):
    """Raised when integration or child configuration is invalid."""


class MSACoreInputError(MSACoreError):
    """Raised when the authoritative C-007A input is invalid."""


class MSACoreIntegrationError(MSACoreError):
    """Raised when composed stage outputs or lineage are inconsistent."""


class MSACoreReplayError(MSACoreError):
    """Raised when unified replay or stage cross-audit fails."""


class MSACoreSerializationError(MSACoreError):
    """Raised when a serialized MSA Core payload fails closed."""
