from copy import deepcopy
from decimal import getcontext

import pytest

from msa.domain import BoundarySide
from msa.research.active_box import ActiveBoxEventType
from msa.research.msa_core import replay_msa_core_run
from msa.research.resonance import ResonanceClass
from msa.validation import (
    MetricInputError,
    MetricEventKind,
    MetricObservationStatus,
    ValidationMetricName,
    evaluate_structural_metrics,
    iter_structural_metric_observations,
)
from msa.validation.metrics.matching import match_resonance_outcomes
from tests.research.msa_core.fixtures import pipeline, source_input
from tests.validation.causal_audit.fixtures import valid_prefix_pair
from tests.validation.metrics.fixtures import (
    base_run,
    base_report,
    direction_run,
    metric_config,
    simultaneous_freeze_run,
    touch_report,
    touch_run,
)
from tests.validation.metrics.test_resonance_lift import (
    reaction,
    touch_event,
)
from tests.validation.metrics.fixtures import formula
from tests.validation.metrics.test_scale import _scale_runs
from tests.validation.metrics.test_report_binding import _resign_event


def component_payload(report, name: str) -> tuple[dict[str, object], ...]:
    return tuple(
        item.to_dict() for item in getattr(report, name)
    )


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
    for component in (
        "events",
        "observations",
        "resonance_matches",
        "aggregates",
    ):
        assert component_payload(left, component) == component_payload(
            right, component
        )
    assert left.source_run_id != right.source_run_id
    assert left.metric_report_id != right.metric_report_id
    assert left.provenance != right.provenance


def test_lifecycle_and_timeframe_state_future_append_are_inert_at_cutoff() -> None:
    prefix, extended = valid_prefix_pair()
    cutoff = prefix.processing_times[-1]
    assert len(prefix.source_input.lifecycle_history.events) < len(
        extended.source_input.lifecycle_history.events
    )
    assert all(
        len(left.snapshots) < len(right.snapshots)
        for left, right in zip(
            prefix.source_input.timeframe_state_histories,
            extended.source_input.timeframe_state_histories,
        )
    )
    left = evaluate_structural_metrics(prefix, metric_config(), cutoff)
    right = evaluate_structural_metrics(extended, metric_config(), cutoff)
    assert component_payload(left, "events") == component_payload(
        right, "events"
    )


def test_future_evidence_and_reference_bars_are_inert_at_old_cutoff() -> None:
    prefix, extended = valid_prefix_pair()
    cutoff = prefix.processing_times[-1]
    assert len(prefix.source_input.reference_price_data.bars) < len(
        extended.source_input.reference_price_data.bars
    )
    assert len(prefix.resonance_history.frames) < len(
        extended.resonance_history.frames
    )
    left = evaluate_structural_metrics(prefix, metric_config(), cutoff)
    right = evaluate_structural_metrics(extended, metric_config(), cutoff)
    assert component_payload(left, "observations") == component_payload(
        right, "observations"
    )
    assert component_payload(
        left, "resonance_matches"
    ) == component_payload(
        right, "resonance_matches"
    )


def test_origin_time_never_grants_visibility_before_confirm_time() -> None:
    report = evaluate_structural_metrics(base_run(), metric_config())
    structures = tuple(
        item
        for item in report.events
        if item.kind is MetricEventKind.STRUCTURE_CONFIRMATION
    )
    assert structures
    for event in structures:
        facts = dict(item.split("=", 1) for item in event.facts)
        assert facts["origin_time"] < event.event_confirm_time.isoformat()
        assert event.first_observed_as_of_time >= event.event_confirm_time


def test_turn_break_and_trend_windows_respect_exact_cutoffs() -> None:
    run = direction_run()
    at_turn = evaluate_structural_metrics(
        run, metric_config(), run.processing_times[-2]
    )
    after_turn = evaluate_structural_metrics(run, metric_config())
    turn = next(
        item
        for item in at_turn.observations
        if item.metric_name is ValidationMetricName.FALSE_TURN_RATE
    )
    assert turn.status is MetricObservationStatus.CENSORED_RIGHT
    matured_turn = next(
        item
        for item in after_turn.observations
        if item.metric_event_id == turn.metric_event_id
    )
    assert matured_turn.status is MetricObservationStatus.MATURED
    breaks = tuple(
        item
        for item in after_turn.observations
        if item.metric_name is ValidationMetricName.CONTINUED_BREAK_RATE
    )
    assert breaks and all(
        item.status is MetricObservationStatus.CENSORED_RIGHT
        for item in breaks
    )
    old_trends = {
        item.metric_event_id: item.to_dict()
        for item in at_turn.observations
        if item.metric_name is ValidationMetricName.TREND_CAPTURE_RATIO
    }
    assert old_trends
    assert all(
        item.to_dict() == old_trends[item.metric_event_id]
        for item in after_turn.observations
        if item.metric_event_id in old_trends
    )


def test_box_created_events_are_independent_of_future_touch_prices() -> None:
    baseline = evaluate_structural_metrics(base_run(), metric_config())
    touched = evaluate_structural_metrics(touch_run(), metric_config())
    baseline_boxes = tuple(
        item.to_dict()
        for item in baseline.events
        if item.kind is MetricEventKind.BOX_EPISODE_CREATED
    )
    touched_boxes = tuple(
        item.to_dict()
        for item in touched.events
        if item.kind is MetricEventKind.BOX_EPISODE_CREATED
    )
    assert baseline_boxes == touched_boxes


def test_event_order_subset_superset_and_forged_event_are_rejected() -> None:
    run = touch_run()
    events = touch_report().events
    future_time = run.processing_times[-1].isoformat()
    future = _resign_event(
        events[-1],
        event_confirm_time=future_time,
        first_observed_as_of_time=future_time,
    )
    forged = _resign_event(events[-1], anchor_price="999")
    object.__setattr__(forged, "anchor_price", forged.anchor_price + 1)
    for supplied, cutoff in (
        (tuple(reversed(events)), None),
        (events[:-1], None),
        ((*events, events[-2]), None),
        ((*events[:-1], forged), None),
        ((*events[:-1], future), run.processing_times[-2]),
        (base_report().events, None),
    ):
        with pytest.raises(MetricInputError):
            tuple(
                iter_structural_metric_observations(
                    run,
                    events=supplied,
                    config=metric_config(),
                    evaluation_as_of_time=cutoff,
                )
            )


def test_future_pair_changed_and_frozen_events_do_not_rewrite_prefix() -> None:
    prefix, extended = _scale_runs()
    cutoff = prefix.source_input.reference_price_data.bars[-1].available_time
    future_events = tuple(
        item
        for item in extended.active_box_history.events
        if item.event_confirm_time > cutoff
    )
    assert any(
        item.event_reason.value == "PAIR_CHANGED"
        for item in future_events
    )
    assert any(
        item.event_type is ActiveBoxEventType.FROZEN
        for item in future_events
    )
    left = evaluate_structural_metrics(prefix, metric_config(), cutoff)
    right = evaluate_structural_metrics(extended, metric_config(), cutoff)
    for component in (
        "events",
        "observations",
        "resonance_matches",
        "aggregates",
    ):
        assert component_payload(left, component) == component_payload(
            right, component
        )


def test_matching_is_outcome_free_same_side_and_without_reuse() -> None:
    treatment_a = touch_event(
        "treatment-a",
        ResonanceClass.MULTI_CONTEXT_RESONANCE,
        "1",
        0,
    )
    treatment_b = touch_event(
        "treatment-b",
        ResonanceClass.MULTI_CONTEXT_RESONANCE,
        "1.01",
        1,
    )
    same_side = touch_event(
        "same-side", ResonanceClass.SINGLE, "1.02", 2
    )
    opposite = touch_event(
        "opposite",
        ResonanceClass.SINGLE,
        "1",
        3,
        side=BoundarySide.UPPER,
    )
    events = (treatment_a, treatment_b, same_side, opposite)
    first_observations = (
        reaction(treatment_a, "100"),
        reaction(treatment_b, "-100"),
        reaction(same_side, "1"),
        reaction(opposite, "1000"),
    )
    second_observations = (
        reaction(treatment_a, "-100"),
        reaction(treatment_b, "100"),
        reaction(same_side, "999"),
        reaction(opposite, "-1000"),
    )
    first, _ = match_resonance_outcomes(
        events,
        first_observations,
        formula(ValidationMetricName.RESONANCE_LIFT),
        metric_config(),
    )
    second, _ = match_resonance_outcomes(
        events,
        second_observations,
        formula(ValidationMetricName.RESONANCE_LIFT),
        metric_config(),
    )
    assert tuple(item.control_event_id for item in first) == tuple(
        item.control_event_id for item in second
    )
    matched = tuple(item for item in first if item.control_event_id)
    assert len(matched) == 1
    assert matched[0].control_event_id == same_side.metric_event_id


def test_unfinished_reference_bar_is_rejected_not_observed() -> None:
    run = deepcopy(base_run())
    object.__setattr__(
        run.source_input.reference_price_data.bars[-1],
        "is_complete",
        False,
    )
    with pytest.raises(MetricInputError):
        evaluate_structural_metrics(run, metric_config())


def test_context_permutation_preserves_metric_component_payloads() -> None:
    normal = pipeline().run(source_input())
    permuted = pipeline().run(source_input(reverse_histories=True))
    left = evaluate_structural_metrics(normal, metric_config())
    right = evaluate_structural_metrics(permuted, metric_config())
    for component in (
        "events",
        "observations",
        "resonance_matches",
        "aggregates",
    ):
        assert component_payload(left, component) == component_payload(
            right, component
        )


NO_LOOKAHEAD_FACT_COVERAGE = {
    "01_batch_replay_complete_report": "test_batch_and_default_replay_reports_are_identical",
    "02_same_run_same_cutoff_complete_report": "test_batch_and_default_replay_reports_are_identical",
    "03_different_run_provenance_expected": "test_future_append_preserves_complete_causal_payload_at_cutoff",
    "04_lifecycle_append": "test_lifecycle_and_timeframe_state_future_append_are_inert_at_cutoff",
    "05_timeframe_state_append": "test_lifecycle_and_timeframe_state_future_append_are_inert_at_cutoff",
    "06_future_evidence": "test_future_evidence_and_reference_bars_are_inert_at_old_cutoff",
    "07_future_reference_bars": "test_future_evidence_and_reference_bars_are_inert_at_old_cutoff",
    "08_origin_confirm_separation": "test_origin_time_never_grants_visibility_before_confirm_time",
    "09_event_time_atr": "test_future_append_does_not_change_old_event_ids_or_atr",
    "10_turn_window_end": "test_turn_break_and_trend_windows_respect_exact_cutoffs",
    "11_break_window_end": "test_turn_break_and_trend_windows_respect_exact_cutoffs",
    "12_trend_capture_cutoff": "test_turn_break_and_trend_windows_respect_exact_cutoffs",
    "13_box_created_independence": "test_box_created_events_are_independent_of_future_touch_prices",
    "14_active_interval_touch": "test_cutoff_makes_incomplete_windows_explicitly_censored",
    "15_freeze_bar_exclusion": "test_freeze_time_bar_never_creates_first_touch",
    "16_future_pair_changed": "test_future_pair_changed_and_frozen_events_do_not_rewrite_prefix",
    "17_future_frozen": "test_future_pair_changed_and_frozen_events_do_not_rewrite_prefix",
    "18_right_censor_maturation": "test_expanded_cutoff_only_matures_existing_touch_observations",
    "19_outcome_free_control_matching": "test_matching_is_outcome_free_same_side_and_without_reuse",
    "20_same_side_control": "test_matching_is_outcome_free_same_side_and_without_reuse",
    "21_no_control_reuse": "test_matching_is_outcome_free_same_side_and_without_reuse",
    "22_unfinished_reference_bar": "test_unfinished_reference_bar_is_rejected_not_observed",
    "23_context_permutation": "test_context_permutation_preserves_metric_component_payloads",
    "24_event_order": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "25_forged_event": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "26_event_subset": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "27_event_superset": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "28_future_event": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "29_other_run_event": "test_event_order_subset_superset_and_forged_event_are_rejected",
    "30_aggregate_order_no_false_zero": "test_aggregate_order_and_no_false_zero_are_causal",
}


def test_thirty_no_lookahead_facts_are_explicitly_mapped_to_tests() -> None:
    assert len(NO_LOOKAHEAD_FACT_COVERAGE) == 30
    assert all(
        test_name in globals()
        for test_name in NO_LOOKAHEAD_FACT_COVERAGE.values()
    )


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
