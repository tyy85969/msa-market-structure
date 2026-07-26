from decimal import Decimal

from msa.validation import MetricObservationStatus, ValidationMetricName

from .fixtures import base_report


def observations(report, name):
    return tuple(
        item for item in report.observations if item.metric_name is name
    )


def test_uncovered_origin_is_unavailable_not_silently_short_counted() -> None:
    values = observations(
        base_report(), ValidationMetricName.CONFIRMATION_DELAY_BARS
    )
    assert values
    assert all(
        item.status is MetricObservationStatus.UNAVAILABLE_INPUT
        for item in values
    )
    assert all(item.value is None for item in values)


def test_confirmation_displacement_uses_confirm_close_and_causal_atr() -> None:
    values = observations(
        base_report(), ValidationMetricName.CONFIRMATION_DELAY_ATR
    )
    assert values[0].status is MetricObservationStatus.MATURED
    assert values[0].value == Decimal("0.95")
    assert values[0].denominator == Decimal("10")
