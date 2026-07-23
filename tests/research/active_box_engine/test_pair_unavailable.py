from msa.research.active_box import (
    ActiveBoxEventReason,
    ActiveBoxEventType,
)
from datetime import timedelta
from decimal import Decimal

from msa.domain import BoundarySide
from msa.research.resonance import ResonanceScorer
from tests.research.resonance.fixtures import (
    H4_PRIMARY,
    T2,
    bar,
    custom_bundle,
    subject,
)
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import PAIR_UNAVAILABLE_THRESHOLD, score_history, selector


def test_pair_unavailable_freezes_once_and_drops_current_box() -> None:
    value = selector(minimum_quality_score=PAIR_UNAVAILABLE_THRESHOLD)
    frames = score_history().frames
    previous = value.select_frame(frames[0]).active_box_snapshot
    unavailable = value.select_frame(frames[2], previous)
    assert unavailable.active_box_snapshot is None
    assert len(unavailable.emitted_events) == 1
    event = unavailable.emitted_events[0]
    assert event.event_type is ActiveBoxEventType.FROZEN
    assert event.event_reason is ActiveBoxEventReason.PAIR_UNAVAILABLE
    assert event.previous_box_snapshot == previous
    assert event.resulting_box_snapshot.active_box.selection_price == (
        previous.active_box.selection_price
    )


def test_absent_pair_after_freeze_does_not_repeat_freeze() -> None:
    value = selector(minimum_quality_score=PAIR_UNAVAILABLE_THRESHOLD)
    frames = score_history().frames
    first = value.select_frame(frames[0])
    frozen = value.select_frame(frames[2], first.active_box_snapshot)
    later = value.select_frame(frames[3], frozen.active_box_snapshot)
    assert frozen.active_box_snapshot is None
    assert later.active_box_snapshot is None
    assert later.emitted_events == ()


def test_pair_reappearance_creates_a_new_initial_episode() -> None:
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
    engine, data = custom_bundle(
        subjects, (bar(-1), bar(0), bar(1), bar(2)), (H4_PRIMARY,)
    )
    scoring = ResonanceScorer(scoring_config(contexts=(H4_PRIMARY,)))
    source = scoring.build_batch(engine.build_batch(data))
    history = selector(
        minimum_quality_score=Decimal("0.28")
    ).build_batch(source)
    unavailable_index = next(
        index
        for index, frame in enumerate(history.frames)
        if frame.emitted_events
        and frame.emitted_events[0].event_reason
        is ActiveBoxEventReason.PAIR_UNAVAILABLE
    )
    frozen_key = history.frames[
        unavailable_index
    ].emitted_events[0].box_key_id
    recreated = history.frames[unavailable_index + 1]
    assert (
        recreated.emitted_events[0].event_type
        is ActiveBoxEventType.CREATED
    )
    assert (
        recreated.emitted_events[0].event_reason
        is ActiveBoxEventReason.INITIAL_PAIR
    )
    assert recreated.active_box_snapshot.box_key_id != frozen_key
