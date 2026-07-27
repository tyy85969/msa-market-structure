"""Failure-closed error boundary for C-008B structural metrics."""


class StructuralMetricError(ValueError):
    """Base class for formal structural-metric failures."""


class MetricConfigurationError(StructuralMetricError):
    """Raised when metric configuration is invalid or mutated."""


class MetricInputError(StructuralMetricError):
    """Raised when a metric input or causal boundary is invalid."""


class MetricEventError(StructuralMetricError):
    """Raised when a structural metric event is invalid."""


class MetricObservationError(StructuralMetricError):
    """Raised when an observation is invalid or internally inconsistent."""


class MetricMatchingError(StructuralMetricError):
    """Raised when resonance matching is invalid."""


class MetricSerializationError(StructuralMetricError):
    """Raised when strict metric deserialization fails."""


class MetricReportError(StructuralMetricError):
    """Raised when a report is not bound to the supplied source Run."""
