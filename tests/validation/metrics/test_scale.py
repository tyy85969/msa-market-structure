from functools import lru_cache
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.active_box import ActiveBoxEventReason, ActiveBoxEventType
from msa.research.msa_core import MSACoreConfig, MSACorePipeline
from msa.validation import (
    MetricEventKind,
    MetricObservationStatus,
    evaluate_structural_metrics,
)
from tests.research.active_box_engine.fixtures import selector
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    START,
    bar,
    custom_bundle,
    subject,
)
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import metric_config


def _scale_subjects():
    values = []
    for index, hour in enumerate((0, 4, 8, 12, 16, 20, 24)):
        values.extend(
            (
                subject(
                    f"scale-lower-{index}",
                    BoundarySide.LOWER,
                    str(80 + index * 2),
                    str(81 + index * 2),
                    confirm_time=START + timedelta(hours=hour),
                ),
                subject(
                    f"scale-upper-{index}",
                    BoundarySide.UPPER,
                    str(119 - index * 2),
                    str(120 - index * 2),
                    confirm_time=START + timedelta(hours=hour),
                ),
            )
        )
    return tuple(values)


def _scale_bars(count: int):
    values = []
    for index in range(-1, count - 1):
        if index == 14:
            values.append(
                bar(
                    index,
                    high="131",
                    low="129",
                    close="130",
                    source="c008b-formal-scale",
                )
            )
        else:
            values.append(
                bar(
                    index,
                    high="121",
                    low="79",
                    close="100",
                    source="c008b-formal-scale",
                )
            )
    return tuple(values)


def _build_scale_run(bar_count: int):
    frame_engine, data = custom_bundle(
        _scale_subjects(),
        _scale_bars(bar_count),
        (H4_PRIMARY,),
        break_buffer=Decimal("1"),
        weakening_test_count=1000,
    )
    active_selector = selector(
        minimum_quality_score=Decimal("0"),
        minimum_selection_score=Decimal("0"),
        absolute_replacement_distance_margin=Decimal("0"),
        minimum_replacement_selection_score_improvement=Decimal("0"),
    )
    config = MSACoreConfig(
        engine_id="c008b-formal-scale-core",
        engine_version="1.0.0",
        policy_id="c008b-formal-scale-policy",
        frame_config=frame_engine.config,
        scoring_config=scoring_config(contexts=(H4_PRIMARY,)),
        active_box_config=active_selector.config,
        strict=True,
    )
    return MSACorePipeline(config).run(data)


@lru_cache(maxsize=1)
def _scale_runs():
    return _build_scale_run(11), _build_scale_run(106)


def _payload(report, name: str):
    return tuple(item.to_dict() for item in getattr(report, name))


def test_unified_formal_scale_scenario_is_end_to_end_and_stable() -> None:
    prefix, full = _scale_runs()
    report = evaluate_structural_metrics(full, metric_config())
    repeated = evaluate_structural_metrics(full, metric_config())

    assert len(full.processing_times) >= 100
    assert len(full.source_input.reference_price_data.bars) >= 100
    assert len(report.aggregates) == 10
    assert report.to_dict() == repeated.to_dict()

    active_events = full.active_box_history.events
    pair_changes = tuple(
        item
        for item in active_events
        if item.event_reason is ActiveBoxEventReason.PAIR_CHANGED
    )
    assert len(pair_changes) >= 4
    unavailable_index = next(
        index
        for index, event in enumerate(active_events)
        if event.event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    assert active_events[unavailable_index].event_type is (
        ActiveBoxEventType.FROZEN
    )
    assert active_events[unavailable_index + 1].event_type is (
        ActiveBoxEventType.CREATED
    )

    touch_event_ids = {
        item.metric_event_id
        for item in report.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    }
    matured_touches = tuple(
        item
        for item in report.observations
        if item.metric_event_id in touch_event_ids
        and item.status is MetricObservationStatus.MATURED
    )
    assert len(matured_touches) >= 20
    assert {
        item.metric_event_id for item in matured_touches
    } <= touch_event_ids
    aggregate_observation_ids = {
        observation_id
        for aggregate in report.aggregates
        for observation_id in aggregate.source_observation_ids
    }
    assert {
        item.metric_observation_id for item in matured_touches
    } <= aggregate_observation_ids

    cutoff = START + timedelta(hours=10)
    prefix_report = evaluate_structural_metrics(
        prefix, metric_config(), cutoff
    )
    appended_report = evaluate_structural_metrics(
        full, metric_config(), cutoff
    )
    for component in (
        "events",
        "observations",
        "resonance_matches",
        "aggregates",
    ):
        assert _payload(prefix_report, component) == _payload(
            appended_report, component
        )
    assert prefix_report.source_run_id != appended_report.source_run_id
    assert prefix_report.metric_report_id != appended_report.metric_report_id
