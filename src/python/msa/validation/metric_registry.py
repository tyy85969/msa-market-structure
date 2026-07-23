"""Reserved C-008 metric names and units without C-008B formulas."""

from __future__ import annotations

from .contracts import (
    FORMULA_STATUS_RESERVED,
    MetricDefinition,
    ValidationMetricInterpretation,
    ValidationMetricName,
    ValidationMetricUnit,
)
from .identity import semantic_id


def _definition(
    name: ValidationMetricName,
    unit: ValidationMetricUnit,
    description: str,
    interpretation: ValidationMetricInterpretation,
    required_inputs: tuple[str, ...],
) -> MetricDefinition:
    payload = {
        "name": name.value,
        "unit": unit.value,
        "description": description,
        "interpretation": interpretation.value,
        "required_inputs": list(required_inputs),
        "formula_status": FORMULA_STATUS_RESERVED,
        "schema_version": 1,
    }
    return MetricDefinition(
        metric_definition_id=semantic_id("validation-metric-v1-", payload),
        name=name,
        unit=unit,
        description=description,
        interpretation=interpretation,
        required_inputs=required_inputs,
    )


def default_metric_registry() -> tuple[MetricDefinition, ...]:
    """Return the fixed ten-name C-008 registry; no values are calculated."""

    lower = ValidationMetricInterpretation.LOWER_IS_BETTER
    higher = ValidationMetricInterpretation.HIGHER_IS_BETTER
    descriptive = ValidationMetricInterpretation.DESCRIPTIVE
    return (
        _definition(
            ValidationMetricName.CONFIRMATION_DELAY_BARS,
            ValidationMetricUnit.BARS,
            "Reserved bar-count distance from OriginTime to ConfirmTime.",
            lower,
            ("origin_time", "confirm_time", "bar_schedule"),
        ),
        _definition(
            ValidationMetricName.CONFIRMATION_DELAY_ATR,
            ValidationMetricUnit.ATR,
            "Reserved ATR-normalized confirmation displacement.",
            lower,
            ("origin_price", "confirm_price", "causal_atr"),
        ),
        _definition(
            ValidationMetricName.FALSE_TURN_RATE,
            ValidationMetricUnit.RATIO,
            "Reserved rate for confirmed turns that do not persist.",
            lower,
            ("confirmed_turn_events", "continuation_events"),
        ),
        _definition(
            ValidationMetricName.CONTINUED_BREAK_RATE,
            ValidationMetricUnit.RATIO,
            "Reserved rate for breaks that continue after confirmation.",
            higher,
            ("confirmed_break_events", "continuation_events"),
        ),
        _definition(
            ValidationMetricName.TREND_CAPTURE_RATIO,
            ValidationMetricUnit.RATIO,
            "Reserved descriptive coverage of an audited trend segment.",
            descriptive,
            ("confirmed_structure_events", "trend_segments"),
        ),
        _definition(
            ValidationMetricName.MFE,
            ValidationMetricUnit.PRICE,
            "Reserved maximum favorable excursion observation.",
            descriptive,
            ("causal_event", "future_observation_window"),
        ),
        _definition(
            ValidationMetricName.MAE,
            ValidationMetricUnit.PRICE,
            "Reserved maximum adverse excursion observation.",
            descriptive,
            ("causal_event", "future_observation_window"),
        ),
        _definition(
            ValidationMetricName.BOX_CHURN,
            ValidationMetricUnit.COUNT,
            "Reserved count of Active Box episode changes.",
            lower,
            ("active_box_events", "observation_window"),
        ),
        _definition(
            ValidationMetricName.FIRST_TOUCH_REACTION,
            ValidationMetricUnit.DIMENSIONLESS,
            "Reserved first-touch structural reaction descriptor.",
            descriptive,
            ("active_box_boundary", "first_touch_event"),
        ),
        _definition(
            ValidationMetricName.RESONANCE_LIFT,
            ValidationMetricUnit.DIMENSIONLESS,
            "Reserved comparison of resonance strata.",
            higher,
            ("resonance_strata", "matched_outcomes"),
        ),
    )
