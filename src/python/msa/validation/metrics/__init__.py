"""Public C-008B causal structural metric API."""

from .bars import (
    canonical_bar_id,
    causal_atr_at_or_before,
    causal_wilder_atr,
    true_ranges,
    validate_reference_bars,
    visible_reference_bars,
)
from .contracts import (
    FORMULA_STATUS_FROZEN,
    METRIC_REPORT_ASSUMPTIONS,
    SCHEMA_VERSION,
    BreakResolution,
    MetricAggregateStatus,
    MetricEvaluationReport,
    MetricEventKind,
    MetricFormulaDefinition,
    MetricObservationStatus,
    ResonanceMatchStatus,
    ResonanceOutcomeMatch,
    StructuralMetricAggregate,
    StructuralMetricConfig,
    StructuralMetricEvent,
    StructuralMetricObservation,
    TurnResolution,
)
from .engine import (
    StructuralMetricEvaluator,
    evaluate_structural_metrics,
)
from .errors import (
    MetricConfigurationError,
    MetricEventError,
    MetricInputError,
    MetricMatchingError,
    MetricObservationError,
    MetricSerializationError,
    StructuralMetricError,
)
from .events import extract_structural_metric_events
from .formula_registry import default_metric_formula_registry
from .matching import match_resonance_outcomes
from .observations import iter_structural_metric_observations

__all__ = [
    "FORMULA_STATUS_FROZEN",
    "METRIC_REPORT_ASSUMPTIONS",
    "SCHEMA_VERSION",
    "BreakResolution",
    "MetricAggregateStatus",
    "MetricConfigurationError",
    "MetricEvaluationReport",
    "MetricEventError",
    "MetricEventKind",
    "MetricFormulaDefinition",
    "MetricInputError",
    "MetricMatchingError",
    "MetricObservationError",
    "MetricObservationStatus",
    "MetricSerializationError",
    "ResonanceMatchStatus",
    "ResonanceOutcomeMatch",
    "StructuralMetricAggregate",
    "StructuralMetricConfig",
    "StructuralMetricError",
    "StructuralMetricEvaluator",
    "StructuralMetricEvent",
    "StructuralMetricObservation",
    "TurnResolution",
    "canonical_bar_id",
    "causal_atr_at_or_before",
    "causal_wilder_atr",
    "default_metric_formula_registry",
    "evaluate_structural_metrics",
    "extract_structural_metric_events",
    "iter_structural_metric_observations",
    "match_resonance_outcomes",
    "true_ranges",
    "validate_reference_bars",
    "visible_reference_bars",
]
