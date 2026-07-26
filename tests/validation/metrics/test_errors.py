from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from msa.validation import (
    MetricConfigurationError,
    MetricEvaluationReport,
    MetricInputError,
    MetricSerializationError,
    StructuralMetricConfig,
    StructuralMetricError,
    evaluate_structural_metrics,
    extract_structural_metric_events,
    iter_structural_metric_observations,
)

from .fixtures import base_run, touch_report


@pytest.mark.parametrize("value", (None, False, 0, "", object()))
def test_non_run_inputs_fail_with_domain_error(value: object) -> None:
    with pytest.raises(MetricInputError):
        evaluate_structural_metrics(value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("strict", False),
        ("atr_period", 0),
        ("atr_period", Decimal("1")),
        ("turn_resolution_bars", 1.5),
        ("break_continuation_atr", 1.0),
        ("resonance_match_max_distance_atr", Decimal("-1")),
    ),
)
def test_invalid_config_values_fail_closed(
    field: str, value: object
) -> None:
    with pytest.raises(MetricConfigurationError):
        StructuralMetricConfig(**{field: value})  # type: ignore[arg-type]


def test_tampered_config_is_revalidated_at_public_boundary() -> None:
    config = StructuralMetricConfig()
    object.__setattr__(config, "atr_period", 0)
    with pytest.raises(MetricConfigurationError):
        evaluate_structural_metrics(base_run(), config)


@pytest.mark.parametrize(
    "entry_point",
    (
        evaluate_structural_metrics,
        extract_structural_metric_events,
        lambda run: tuple(iter_structural_metric_observations(run)),
    ),
)
def test_public_entry_points_do_not_leak_builtin_errors(
    entry_point,
) -> None:
    with pytest.raises(StructuralMetricError) as caught:
        entry_point(object())
    assert not isinstance(
        caught.value, (AttributeError, KeyError, TypeError, AssertionError)
    )


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("source_run_id",), "forged"),
        (("evaluation_as_of_time",), datetime(2026, 1, 1).isoformat()),
        (("event_count",), 999),
        (("formula_registry",), []),
        (("events",), []),
        (("observations",), []),
        (("aggregates",), []),
        (("aggregates", 0, "matured_count"), 999),
        (("observations", -1, "value"), "0"),
    ),
)
def test_resigned_report_payload_attacks_fail_closed(
    path: tuple[object, ...], replacement: object
) -> None:
    payload = touch_report().to_dict()
    target = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index,assignment]
    target[path[-1]] = replacement  # type: ignore[index]
    payload["metric_report_id"] = (
        "metric-evaluation-report-v1-" + "0" * 64
    )
    with pytest.raises(MetricSerializationError):
        MetricEvaluationReport.from_dict(payload)


def test_direct_replacement_cannot_forge_observation_value() -> None:
    report = touch_report()
    matured = next(item for item in report.observations if item.value)
    with pytest.raises(StructuralMetricError):
        replace(matured, value=matured.value + Decimal("1"))
