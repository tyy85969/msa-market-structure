from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from msa.validation import (
    METRIC_REPORT_ASSUMPTIONS,
    MetricEvaluationReport,
    MetricEventKind,
    MetricInputError,
    MetricObservationStatus,
    MetricReportError,
    StructuralMetricEvent,
    StructuralMetricObservation,
    StructuralMetricError,
    ValidationMetricName,
    iter_structural_metric_observations,
    validate_metric_evaluation_report,
)
from msa.validation.metrics.contracts import METRIC_REPORT_PROVENANCE_ENTRY
from msa.validation.metrics.identity import digest, semantic_id
from msa.validation.metrics.matching import match_resonance_outcomes
from msa.validation.metrics.observations import build_metric_aggregates

from .fixtures import (
    base_report,
    base_run,
    metric_config,
    touch_report,
    touch_run,
)
from .test_resonance_lift import reaction, touch_event
from msa.research.resonance import ResonanceClass


def _resign_event(
    event: StructuralMetricEvent, **changes: object
) -> StructuralMetricEvent:
    payload = event.to_dict()
    payload.update(changes)
    if (
        "source_object_ids" in changes
        or "event_confirm_time" in changes
    ):
        facts = dict(
            item.split("=", 1) for item in payload["facts"]  # type: ignore[index]
        )
        if "source_object_ids" in changes:
            facts["source_object_ids_digest"] = digest(
                payload["source_object_ids"]
            )
        if "event_confirm_time" in changes:
            facts["event_confirm_time"] = payload["event_confirm_time"]
        payload["facts"] = [
            f"{key}={facts[key]}" for key in sorted(facts)
        ]
    identity_payload = dict(payload)
    identity_payload.pop("metric_event_id")
    payload["metric_event_id"] = semantic_id(
        "structural-metric-event-v1-", identity_payload
    )
    return StructuralMetricEvent.from_dict(payload)


def _resign_report(
    report: MetricEvaluationReport,
    *,
    events: tuple[StructuralMetricEvent, ...],
    observations,
) -> MetricEvaluationReport:
    formulas = report.formula_registry
    event_key = lambda item: (
        item.event_confirm_time,
        item.kind.value,
        item.metric_event_id,
    )
    ordered_events = tuple(sorted(events, key=event_key))
    event_by_id = {
        item.metric_event_id: item for item in ordered_events
    }
    formula_index = {
        item.metric_formula_id: index
        for index, item in enumerate(formulas)
    }
    base_observations = tuple(
        item
        for item in observations
        if item.metric_name is not ValidationMetricName.RESONANCE_LIFT
    )
    resonance_formula = next(
        item
        for item in formulas
        if item.metric_name is ValidationMetricName.RESONANCE_LIFT
    )
    matches, pair_observations = match_resonance_outcomes(
        ordered_events,
        base_observations,
        resonance_formula,
        report.config_snapshot,
    )
    all_observations = (*base_observations, *pair_observations)
    ordered_observations = tuple(
        sorted(
            all_observations,
            key=lambda item: (
                formula_index[item.metric_formula_id],
                event_by_id[item.metric_event_id].event_confirm_time,
                item.metric_event_id,
                item.metric_observation_id,
            ),
        )
    )
    aggregates = build_metric_aggregates(
        formulas, ordered_observations, report.config_snapshot
    )
    matured = sum(
        item.status is MetricObservationStatus.MATURED
        for item in ordered_observations
    )
    censored = sum(
        item.status is MetricObservationStatus.CENSORED_RIGHT
        for item in ordered_observations
    )
    unavailable = sum(
        item.status is MetricObservationStatus.UNAVAILABLE_INPUT
        for item in ordered_observations
    )
    identity_payload = {
        "source_run_id": report.source_run_id,
        "evaluation_as_of_time": report.evaluation_as_of_time.isoformat(),
        "config_snapshot": report.config_snapshot.to_dict(),
        "formula_registry": [item.to_dict() for item in formulas],
        "events": [item.to_dict() for item in ordered_events],
        "observations": [
            item.to_dict() for item in ordered_observations
        ],
        "resonance_matches": [item.to_dict() for item in matches],
        "aggregates": [item.to_dict() for item in aggregates],
        "event_count": len(ordered_events),
        "matured_observation_count": matured,
        "censored_observation_count": censored,
        "unavailable_observation_count": unavailable,
        "assumptions": list(METRIC_REPORT_ASSUMPTIONS),
        "warnings": [],
        "provenance": list(report.provenance),
        "schema_version": 1,
    }
    return MetricEvaluationReport(
        metric_report_id=semantic_id(
            "metric-evaluation-report-v1-", identity_payload
        ),
        source_run_id=report.source_run_id,
        evaluation_as_of_time=report.evaluation_as_of_time,
        config_snapshot=report.config_snapshot,
        formula_registry=formulas,
        events=ordered_events,
        observations=ordered_observations,
        resonance_matches=matches,
        aggregates=aggregates,
        event_count=len(ordered_events),
        matured_observation_count=matured,
        censored_observation_count=censored,
        unavailable_observation_count=unavailable,
        assumptions=METRIC_REPORT_ASSUMPTIONS,
        warnings=(),
        provenance=report.provenance,
    )


def _resign_observation(
    observation: StructuralMetricObservation, **changes: object
) -> StructuralMetricObservation:
    payload = observation.to_dict()
    payload.update(changes)
    if (
        "observation_start_time" in changes
        or "observation_end_time" in changes
        or "observed_bar_ids" in changes
    ):
        facts = dict(
            item.split("=", 1) for item in payload["facts"]  # type: ignore[index]
        )
        facts["observation_window"] = (
            f"{payload['observation_start_time']}|"
            f"{payload['observation_end_time']}"
        )
        if "observed_bar_ids" in changes:
            facts["observed_bar_ids_digest"] = digest(
                payload["observed_bar_ids"]
            )
        payload["facts"] = [
            f"{key}={facts[key]}" for key in sorted(facts)
        ]
    identity_payload = dict(payload)
    identity_payload.pop("metric_observation_id")
    payload["metric_observation_id"] = semantic_id(
        "structural-metric-observation-v1-", identity_payload
    )
    return StructuralMetricObservation.from_dict(payload)


def test_source_bound_report_verifier_accepts_exact_report() -> None:
    run = touch_run()
    report = touch_report()
    assert validate_metric_evaluation_report(run, report) is report
    assert (
        f"source_run_payload_digest={digest(run.to_dict())}"
        in report.provenance
    )


def test_fully_resigned_event_deletion_is_internally_valid_but_unbound() -> None:
    report = touch_report()
    removed = next(
        item
        for item in report.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )
    forged = _resign_report(
        report,
        events=tuple(
            item
            for item in report.events
            if item.metric_event_id != removed.metric_event_id
        ),
        observations=tuple(
            item
            for item in report.observations
            if item.metric_event_id != removed.metric_event_id
        ),
    )
    assert MetricEvaluationReport.from_dict(
        forged.to_dict()
    ).to_dict() == forged.to_dict()
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(touch_run(), forged)


def test_fully_resigned_fake_event_is_internally_valid_but_unbound() -> None:
    report = base_report()
    donor = touch_report()
    fake = next(
        item
        for item in donor.events
        if item.kind is MetricEventKind.BOUNDARY_FIRST_TOUCH
    )
    forged = _resign_report(
        report,
        events=(*report.events, fake),
        observations=(
            *report.observations,
            *(
                item
                for item in donor.observations
                if item.metric_event_id == fake.metric_event_id
                and item.metric_name
                is not ValidationMetricName.RESONANCE_LIFT
            ),
        ),
    )
    assert MetricEvaluationReport.from_dict(
        forged.to_dict()
    ).to_dict() == forged.to_dict()
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(base_run(), forged)


def test_run_a_report_b_and_same_id_different_payload_are_rejected() -> None:
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(base_run(), touch_report())
    different_payload = touch_run()
    object.__setattr__(different_payload, "run_id", base_run().run_id)
    with pytest.raises(StructuralMetricError):
        validate_metric_evaluation_report(
            different_payload, base_report()
        )


def test_modified_observation_window_and_box_churn_universe_are_rejected() -> None:
    report = touch_report()
    original = next(
        item
        for item in report.observations
        if item.metric_name is ValidationMetricName.MFE
        and item.status is MetricObservationStatus.MATURED
    )
    changed = _resign_observation(
        original,
        observation_end_time=original.observation_start_time.isoformat(),
    )
    forged_window = _resign_report(
        report,
        events=report.events,
        observations=tuple(
            changed
            if item.metric_observation_id
            == original.metric_observation_id
            else item
            for item in report.observations
        ),
    )
    assert MetricEvaluationReport.from_dict(
        forged_window.to_dict()
    ).to_dict() == forged_window.to_dict()
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(touch_run(), forged_window)

    base = base_report()
    removed_box = next(
        item
        for item in base.events
        if item.kind is MetricEventKind.BOX_EPISODE_CREATED
    )
    forged_box_universe = _resign_report(
        base,
        events=tuple(
            item
            for item in base.events
            if item.metric_event_id != removed_box.metric_event_id
        ),
        observations=tuple(
            item
            for item in base.observations
            if item.metric_event_id != removed_box.metric_event_id
        ),
    )
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(base_run(), forged_box_universe)


def test_modified_resonance_treatment_control_universe_is_rejected() -> None:
    report = base_report()
    treatment = touch_event(
        "forged-treatment",
        ResonanceClass.MULTI_CONTEXT_RESONANCE,
        "1",
        0,
    )
    control = touch_event(
        "forged-control", ResonanceClass.SINGLE, "1.1", 1
    )
    forged = _resign_report(
        report,
        events=(*report.events, treatment, control),
        observations=(
            *report.observations,
            reaction(treatment, "2"),
            reaction(control, "1"),
        ),
    )
    assert forged.resonance_matches
    assert MetricEvaluationReport.from_dict(
        forged.to_dict()
    ).to_dict() == forged.to_dict()
    with pytest.raises(MetricReportError):
        validate_metric_evaluation_report(base_run(), forged)


def test_report_public_boundary_never_leaks_builtin_errors() -> None:
    with pytest.raises(StructuralMetricError) as caught:
        validate_metric_evaluation_report(object(), object())
    assert not isinstance(
        caught.value, (AttributeError, KeyError, TypeError, AssertionError)
    )


def test_caller_supplied_exact_events_are_accepted() -> None:
    run = touch_run()
    report = touch_report()
    assert tuple(
        iter_structural_metric_observations(
            run,
            events=report.events,
            config=metric_config(),
        )
    )


@pytest.mark.parametrize(
    "attack",
    (
        "future",
        "other_run",
        "delete",
        "add",
        "reorder",
        "symbol",
        "timeframe",
        "source_ids",
        "causal_atr",
        "anchor",
    ),
)
def test_caller_event_injection_attacks_fail_closed(attack: str) -> None:
    run = touch_run()
    report = touch_report()
    events = report.events
    target = events[-1]
    if attack == "future":
        cutoff = run.processing_times[-2]
    else:
        cutoff = None
    if attack == "future":
        future_time = run.processing_times[-1].isoformat()
        supplied = (
            *events[:-1],
            _resign_event(
                target,
                event_confirm_time=future_time,
                first_observed_as_of_time=future_time,
            ),
        )
    elif attack == "other_run":
        supplied = base_report().events
    elif attack == "delete":
        supplied = events[:-1]
    elif attack == "add":
        supplied = (*events, events[-1])
    elif attack == "reorder":
        supplied = tuple(reversed(events))
    elif attack == "symbol":
        supplied = (*events[:-1], _resign_event(target, symbol="EURUSD"))
    elif attack == "timeframe":
        supplied = (
            *events[:-1],
            _resign_event(target, reference_timeframe="M1"),
        )
    elif attack == "source_ids":
        supplied = (
            *events[:-1],
            _resign_event(target, source_object_ids=["forged-source"]),
        )
    elif attack == "causal_atr":
        supplied = (
            *events[:-1],
            _resign_event(target, causal_atr="999"),
        )
    elif attack == "anchor":
        supplied = (
            *events[:-1],
            _resign_event(target, anchor_price="999"),
        )
    else:
        supplied = events
    with pytest.raises(MetricInputError):
        tuple(
            iter_structural_metric_observations(
                run,
                events=supplied,
                config=metric_config(),
                evaluation_as_of_time=cutoff,
            )
        )
