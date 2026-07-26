from msa.validation import (
    MetricEventKind,
    MetricObservationStatus,
    ValidationMetricName,
    evaluate_structural_metrics,
)

from .fixtures import (
    metric_config,
    simultaneous_freeze_run,
    touch_report,
    touch_run,
)


def test_support_and_resistance_first_touch_use_near_edges() -> None:
    events = tuple(
        item
        for item in touch_report().events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )
    by_side = {item.boundary_side.value: item for item in events}
    assert by_side["LOWER"].anchor_price.__str__() == "91"
    assert by_side["UPPER"].anchor_price.__str__() == "110"


def test_freeze_simultaneous_bar_is_not_a_touch() -> None:
    report = evaluate_structural_metrics(
        simultaneous_freeze_run(), metric_config()
    )
    assert not tuple(
        item
        for item in report.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )


def test_touch_window_is_right_censored_at_touch_cutoff() -> None:
    run = touch_run()
    touch_time = run.processing_times[-2]
    report = evaluate_structural_metrics(
        run, metric_config(), touch_time
    )
    touch_observations = tuple(
        item
        for item in report.observations
        if item.metric_name
        in {
            ValidationMetricName.MFE,
            ValidationMetricName.MAE,
            ValidationMetricName.FIRST_TOUCH_REACTION,
        }
    )
    assert touch_observations
    assert all(
        item.status is MetricObservationStatus.CENSORED_RIGHT
        for item in touch_observations
    )
    assert all(item.value is None for item in touch_observations)
