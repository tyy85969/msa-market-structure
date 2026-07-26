from decimal import getcontext

from msa.research.msa_core import replay_msa_core_run
from msa.validation import (
    MetricEventKind,
    MetricObservationStatus,
    evaluate_structural_metrics,
)
from tests.research.msa_core.fixtures import pipeline, source_input
from tests.validation.causal_audit.fixtures import valid_prefix_pair
from tests.validation.metrics.fixtures import (
    base_run,
    metric_config,
    simultaneous_freeze_run,
    touch_run,
)


def causal_payload(report) -> dict[str, object]:
    payload = report.to_dict()
    payload.pop("metric_report_id")
    payload.pop("source_run_id")
    payload["provenance"] = tuple(
        item
        for item in payload["provenance"]
        if not item.startswith("source_run_id=")
    )
    return payload


def test_batch_and_default_replay_reports_are_identical() -> None:
    batch = base_run()
    replay = replay_msa_core_run(pipeline(), source_input())
    assert evaluate_structural_metrics(
        batch, metric_config()
    ).to_dict() == evaluate_structural_metrics(
        replay, metric_config()
    ).to_dict()


def test_future_append_preserves_complete_causal_payload_at_cutoff() -> None:
    prefix, extended = valid_prefix_pair()
    cutoff = prefix.processing_times[-1]
    left = evaluate_structural_metrics(prefix, metric_config(), cutoff)
    right = evaluate_structural_metrics(extended, metric_config(), cutoff)
    assert causal_payload(left) == causal_payload(right)


def test_future_append_does_not_change_old_event_ids_or_atr() -> None:
    prefix, extended = valid_prefix_pair()
    cutoff = prefix.processing_times[-1]
    left = evaluate_structural_metrics(prefix, metric_config(), cutoff)
    right = evaluate_structural_metrics(extended, metric_config(), cutoff)
    assert tuple(
        (item.metric_event_id, item.causal_atr) for item in left.events
    ) == tuple(
        (item.metric_event_id, item.causal_atr) for item in right.events
    )


def test_cutoff_makes_incomplete_windows_explicitly_censored() -> None:
    run = touch_run()
    report = evaluate_structural_metrics(
        run, metric_config(), run.processing_times[-2]
    )
    touches = {
        item.metric_event_id
        for item in report.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    }
    selected = tuple(
        item
        for item in report.observations
        if item.metric_event_id in touches
    )
    assert selected
    assert all(
        item.status is MetricObservationStatus.CENSORED_RIGHT
        for item in selected
    )
    assert all(item.value is None for item in selected)


def test_expanded_cutoff_only_matures_existing_touch_observations() -> None:
    run = touch_run()
    early = evaluate_structural_metrics(
        run, metric_config(), run.processing_times[-2]
    )
    late = evaluate_structural_metrics(run, metric_config())
    old_event_ids = {item.metric_event_id for item in early.events}
    assert old_event_ids <= {item.metric_event_id for item in late.events}
    assert all(
        item.status is MetricObservationStatus.MATURED
        for item in late.observations
        if item.metric_event_id in old_event_ids
        and item.status is not MetricObservationStatus.UNAVAILABLE_INPUT
    )


def test_freeze_time_bar_never_creates_first_touch() -> None:
    report = evaluate_structural_metrics(
        simultaneous_freeze_run(), metric_config()
    )
    assert not any(
        item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
        for item in report.events
    )


def test_global_decimal_context_and_repeat_do_not_change_payload() -> None:
    run = touch_run()
    expected = evaluate_structural_metrics(run, metric_config()).to_dict()
    old_precision = getcontext().prec
    try:
        getcontext().prec = 5
        assert evaluate_structural_metrics(
            run, metric_config()
        ).to_dict() == expected
    finally:
        getcontext().prec = old_precision
    assert evaluate_structural_metrics(
        run, metric_config()
    ).to_dict() == expected


def test_aggregate_order_and_no_false_zero_are_causal() -> None:
    report = evaluate_structural_metrics(base_run(), metric_config())
    assert tuple(item.metric_name for item in report.aggregates) == tuple(
        item.metric_name for item in report.formula_registry
    )
    assert all(
        item.value is None
        for item in report.observations
        if item.status is not MetricObservationStatus.MATURED
    )
