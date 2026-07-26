from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.active_box import ActiveBoxEventReason, ActiveBoxEventType
from msa.research.msa_core import replay_msa_core_run
from msa.research.resonance import ResonanceClass, ResonanceScorer
from msa.validation import MetricObservationStatus, evaluate_structural_metrics
from tests.research.active_box_engine.fixtures import selector
from tests.research.msa_core.fixtures import pipeline, source_input
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    T2,
    bar,
    custom_bundle,
    load_result,
    subject,
)
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import metric_config
from .test_resonance_lift import reaction, touch_event


def test_one_hundred_plus_asof_and_reference_bar_smoke_is_stable() -> None:
    source = source_input()
    bars = tuple(
        bar(
            index,
            high=str(105 + index % 3),
            low=str(95 - index % 3),
            close=str(100 + index % 2),
            source="reference-fixture",
        )
        for index in range(-1, 104)
    )
    extended = replace(
        source,
        reference_price_data=load_result(
            bars, config=source.reference_price_data.source_config
        ),
    )
    value = pipeline()
    baseline = value.run(extended)
    start = baseline.processing_times[0]
    schedule = tuple(
        sorted(
            {
                *baseline.processing_times,
                *(start + timedelta(minutes=index) for index in range(100)),
            }
        )
    )
    run = replay_msa_core_run(value, extended, schedule)
    first = evaluate_structural_metrics(run, metric_config()).to_dict()
    second = evaluate_structural_metrics(run, metric_config()).to_dict()
    assert len(run.processing_times) >= 100
    assert len(run.source_input.reference_price_data.bars) >= 100
    assert len(first["aggregates"]) == 10
    assert first == second


def test_scale_scenario_covers_reappearance_and_twenty_outcomes() -> None:
    subjects = (
        subject("old-upper", BoundarySide.UPPER, "110", "111"),
        subject("old-lower", BoundarySide.LOWER, "90", "91"),
        subject(
            "new-upper",
            BoundarySide.UPPER,
            "108",
            "109",
            confirm_time=T2 + timedelta(minutes=30),
        ),
        subject(
            "new-lower",
            BoundarySide.LOWER,
            "92",
            "93",
            confirm_time=T2 + timedelta(minutes=30),
        ),
    )
    frame_engine, data = custom_bundle(
        subjects, (bar(-1), bar(0), bar(1), bar(2)), (H4_PRIMARY,)
    )
    scored = ResonanceScorer(
        scoring_config(contexts=(H4_PRIMARY,))
    ).build_batch(frame_engine.build_batch(data))
    history = selector(
        minimum_quality_score=Decimal("0.28")
    ).build_batch(scored)
    reasons = tuple(item.event_reason for item in history.events)
    assert ActiveBoxEventReason.PAIR_UNAVAILABLE in reasons
    unavailable_index = next(
        index
        for index, event in enumerate(history.events)
        if event.event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    assert history.events[unavailable_index].event_type is (
        ActiveBoxEventType.FROZEN
    )
    assert history.events[unavailable_index + 1].event_type is (
        ActiveBoxEventType.CREATED
    )
    touches = tuple(
        touch_event(
            f"scale-{index}",
            ResonanceClass.SINGLE,
            str(index),
            index,
        )
        for index in range(20)
    )
    outcomes = tuple(reaction(item, str(index)) for index, item in enumerate(touches))
    assert len(outcomes) == 20
    assert all(
        item.status is MetricObservationStatus.MATURED
        for item in outcomes
    )
