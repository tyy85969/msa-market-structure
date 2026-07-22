from msa.data import Timeframe
from msa.domain import BoundarySide, Direction
from dataclasses import replace

import pytest

from msa.research.timeframe_state import (
    TimeframeStateEngineError,
    TimeframeStateEvent,
    TimeframeStateEventType,
)
from tests.research.timeframe_state.fixtures import (
    T1,
    T2,
    bar,
    base_pair,
    direction_sequence_input,
    subject,
    timeframe_engine,
    timeframe_input,
)


def test_initialized_occurs_exactly_once_even_for_empty_target_context() -> None:
    other = subject(
        "other",
        BoundarySide.UPPER,
        "110",
        "111",
        timeframe=Timeframe.H2,
    )
    history = timeframe_engine().build_batch(timeframe_input((other,), (bar(0),)))
    assert len(history.events) == 1
    event = history.events[0]
    assert event.event_type is TimeframeStateEventType.INITIALIZED
    assert event.previous_state_id is None
    assert event.previous_direction is None
    assert event.source_lifecycle_event_ids == ()
    assert history.snapshots[0].state.direction is Direction.UNKNOWN


def test_candidate_only_change_is_selection_changed() -> None:
    subjects = base_pair() + (
        subject("fresh-upper", BoundarySide.UPPER, "120", "121", confirm_time=T2),
    )
    history = timeframe_engine().build_batch(timeframe_input(subjects, (bar(0),)))
    event = history.events[-1]
    assert event.event_type is TimeframeStateEventType.SELECTION_CHANGED
    assert "candidate_upper_boundary" in event.changed_fields
    assert "direction" not in event.changed_fields


def test_boundary_and_direction_change_is_state_changed() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    assert all(
        item.event_type is TimeframeStateEventType.STATE_CHANGED
        for item in history.events[1:]
    )


def test_same_lifecycle_snapshot_multiple_subject_changes_emit_one_event() -> None:
    history = timeframe_engine().build_batch(timeframe_input(base_pair(), (bar(0),)))
    at_t1 = [item for item in history.events if item.event_confirm_time == T1]
    assert len(at_t1) == 1
    assert len(at_t1[0].source_lifecycle_event_ids) == 2


def test_event_first_seen_confirm_time_and_chains_are_exact() -> None:
    events = timeframe_engine().build_batch(direction_sequence_input()).events
    for index, event in enumerate(events):
        assert event.first_seen_time == event.event_confirm_time
        if index == 0:
            assert event.prior_event_id is None
            continue
        assert event.prior_event_id == events[index - 1].event_id
        assert event.previous_state_id == events[index - 1].current_state_id
        assert event.previous_direction is events[index - 1].current_direction


def test_changed_fields_are_canonical_and_exact() -> None:
    history = timeframe_engine().build_batch(timeframe_input(base_pair(), (bar(0),)))
    initialized, tested = history.events
    assert initialized.changed_fields == (
        "direction",
        "candidate_upper_boundary",
        "candidate_lower_boundary",
        "confirmed_upper_boundary",
        "confirmed_lower_boundary",
        "forming_candidate_ids",
    )
    assert tested.changed_fields == (
        "direction",
        "candidate_upper_boundary",
        "candidate_lower_boundary",
        "confirmed_upper_boundary",
        "confirmed_lower_boundary",
    )


def test_as_of_advance_without_new_lifecycle_snapshot_creates_no_event() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    at_t1 = timeframe_engine().build_as_of(data, T1)
    later = timeframe_engine().build_as_of(data, T1.replace(minute=30))
    assert later.events == at_t1.events
    assert later.state.state_id == at_t1.state.state_id
    assert later.state.origin_time == at_t1.state.origin_time
    assert later.state.confirm_time == at_t1.state.confirm_time
    assert later.state.provenance == at_t1.state.provenance
    assert later.state.as_of_time > at_t1.state.as_of_time


def test_event_provenance_is_bounded_and_self_identifying() -> None:
    events = timeframe_engine().build_batch(direction_sequence_input()).events
    assert all(item.provenance.source_object_id == item.event_id for item in events)
    assert all(len(item.provenance.parent_object_ids) <= 8 for item in events)


def test_event_type_must_match_changed_fields_and_directions() -> None:
    event = timeframe_engine().build_batch(direction_sequence_input()).events[-1]
    with pytest.raises(TimeframeStateEngineError, match="event_type"):
        replace(event, event_type=TimeframeStateEventType.SELECTION_CHANGED)


def test_event_direction_field_must_match_direction_change() -> None:
    event = timeframe_engine().build_batch(direction_sequence_input()).events[-1]
    payload = event.to_dict()
    payload["changed_fields"] = [
        item for item in payload["changed_fields"] if item != "direction"
    ]
    with pytest.raises(Exception, match="direction"):
        TimeframeStateEvent.from_dict(payload)


def test_initialized_event_requires_every_semantic_field() -> None:
    event = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).events[0]
    with pytest.raises(TimeframeStateEngineError, match="INITIALIZED"):
        replace(event, changed_fields=event.changed_fields[:-1])
