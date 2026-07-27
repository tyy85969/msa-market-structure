from decimal import Decimal

from msa.validation import MetricObservationStatus, ValidationMetricName

from .fixtures import direction_report


def test_up_episode_has_known_capture_ratio() -> None:
    values = tuple(
        item
        for item in direction_report().observations
        if item.metric_name is ValidationMetricName.TREND_CAPTURE_RATIO
    )
    assert values[0].status is MetricObservationStatus.MATURED
    assert values[0].value == Decimal("1")
    assert Decimal("0") <= values[0].value <= Decimal("1")


def test_unfinished_down_episode_is_right_censored_not_zero() -> None:
    values = tuple(
        item
        for item in direction_report().observations
        if item.metric_name is ValidationMetricName.TREND_CAPTURE_RATIO
    )
    assert values[-1].status is MetricObservationStatus.CENSORED_RIGHT
    assert values[-1].value is None
