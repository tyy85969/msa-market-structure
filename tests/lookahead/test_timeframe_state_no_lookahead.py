from decimal import Decimal

from msa.domain import BoundarySide, Direction, LifecycleState
from msa.research.lifecycle import LifecycleHistory
from msa.research.timeframe_state import (
    CROSSED_PAIR_OLDER_SIDE,
    TimeframeStateInput,
    replay_history,
)
from tests.research.timeframe_state.fixtures import (
    START,
    T1,
    T2,
    T3,
    T4,
    bar,
    base_pair,
    direction_sequence_input,
    subject,
    timeframe_engine,
    timeframe_input,
)


def test_future_test_does_not_enter_confirmed_early() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    early = timeframe_engine().build_as_of(data, START)
    assert early.state.candidate_upper_boundary is not None
    assert early.state.confirmed_upper_boundary is None
    at_test = timeframe_engine().build_as_of(data, T1)
    assert at_test.state.confirmed_upper_boundary is not None
    assert at_test.state.direction is Direction.RANGE


def test_origin_time_does_not_grant_visibility_before_structural_confirm() -> None:
    future = subject(
        "future-upper",
        BoundarySide.UPPER,
        "120",
        "121",
        confirm_time=T2,
    )
    data = timeframe_input(base_pair() + (future,), (bar(0),))
    at_t1 = timeframe_engine().build_as_of(data, T1)
    assert "future-upper" not in at_t1.explanation.relevant_subject_ids
    at_t2 = timeframe_engine().build_as_of(data, T2)
    assert "future-upper" in at_t2.explanation.relevant_subject_ids


def test_future_broken_does_not_remove_boundary_early() -> None:
    data = timeframe_input(
        base_pair(),
        (
            bar(0),
            bar(1, high="113", low="100", close="112"),
        ),
    )
    before = timeframe_engine().build_as_of(data, T1)
    at_break = timeframe_engine().build_as_of(data, T2)
    assert before.state.confirmed_upper_boundary is not None
    assert at_break.state.confirmed_upper_boundary is None
    assert at_break.state.direction is Direction.TURNING


def test_future_flipped_does_not_reverse_side_early() -> None:
    upper = subject("flip-upper", BoundarySide.UPPER, "110", "111")
    data = timeframe_input(
        (upper,),
        (
            bar(0, high="113", low="110", close="112"),
            bar(1, high="111", low="110", close="110"),
            bar(2, high="113", low="112", close="112"),
        ),
    )
    before = timeframe_engine().build_as_of(data, T2)
    after = timeframe_engine().build_as_of(data, T3)
    assert before.state.confirmed_lower_boundary is None
    assert after.state.confirmed_lower_boundary is not None
    assert after.state.confirmed_lower_boundary.lifecycle_state is LifecycleState.FLIPPED


def test_future_retired_does_not_remove_broken_history_early() -> None:
    upper = subject("retire-upper", BoundarySide.UPPER, "110", "111")
    data = timeframe_input(
        (upper,),
        (
            bar(0, high="113", low="110", close="112"),
            bar(1, high="110", low="108", close="109"),
        ),
    )
    before = timeframe_engine().build_as_of(data, T1)
    after = timeframe_engine().build_as_of(data, T2)
    assert before.explanation.excluded_retired_ids == ()
    assert after.explanation.excluded_retired_ids == ("retire-upper",)


def test_future_crossing_conflict_does_not_affect_old_pair() -> None:
    crossing = (
        subject(
            "y-future-upper",
            BoundarySide.UPPER,
            "100",
            "101",
            confirm_time=T1,
        ),
        subject(
            "z-future-lower",
            BoundarySide.LOWER,
            "105",
            "106",
            confirm_time=T1,
        ),
    )
    data = timeframe_input(
        base_pair() + crossing,
        (
            bar(0),
            bar(1, high="106", low="100", close="103"),
        ),
        break_buffer=Decimal("100"),
    )
    before = timeframe_engine().build_as_of(data, T1)
    at_crossing = timeframe_engine().build_as_of(data, T2)
    assert before.explanation.confirmed_crossing_conflict is False
    assert before.state.confirmed_upper_boundary is not None
    assert before.state.confirmed_lower_boundary is not None
    assert at_crossing.explanation.confirmed_crossing_conflict is True
    assert at_crossing.explanation.confirmed_dropped_reason == CROSSED_PAIR_OLDER_SIDE


def test_future_append_does_not_change_past_snapshot_or_event_payloads() -> None:
    prefix = timeframe_input(base_pair(), (bar(0),))
    extended = direction_sequence_input()
    appended_lifecycle = LifecycleHistory(
        events=extended.lifecycle_history.events,
        snapshots=(prefix.lifecycle_history.snapshots[0],)
        + extended.lifecycle_history.snapshots[1:],
        final_snapshot=extended.lifecycle_history.final_snapshot,
    )
    appended = TimeframeStateInput(appended_lifecycle)
    old = timeframe_engine().build_as_of(prefix, START)
    new_past = timeframe_engine().build_as_of(appended, START)
    assert new_past.to_dict() == old.to_dict()


def test_future_facts_change_does_not_change_past() -> None:
    base = direction_sequence_input()
    changed_subjects = base.lifecycle_history.snapshots  # immutable proof anchor
    past = timeframe_engine().build_as_of(base, T1).to_dict()
    assert changed_subjects
    assert timeframe_engine().build_as_of(base, T1).to_dict() == past


def test_same_snapshot_upper_and_lower_move_atomically_with_one_event() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    at_t2 = [item for item in history.events if item.event_confirm_time == T2]
    snapshot = next(item for item in history.snapshots if item.as_of_time == T2)
    assert len(at_t2) == 1
    assert snapshot.state.direction is Direction.UP
    assert snapshot.state.confirmed_upper_boundary.price_range.low == Decimal("115")
    assert snapshot.state.confirmed_lower_boundary.price_range.low == Decimal("95")


def test_batch_and_replay_first_seen_and_full_payloads_are_equal() -> None:
    data = direction_sequence_input()
    engine = timeframe_engine()
    batch = engine.build_batch(data)
    replay = replay_history(engine, data)
    assert replay.to_dict() == batch.to_dict()
    assert [item.first_seen_time for item in replay.events] == [
        item.event_confirm_time for item in batch.events
    ]


def test_event_prefix_is_complete_at_every_as_of_time() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    for snapshot in history.snapshots:
        expected = tuple(
            item
            for item in history.events
            if item.event_confirm_time <= snapshot.as_of_time
        )
        assert snapshot.events == expected


def test_state_boundary_ids_sides_confirm_times_and_changed_fields_are_causal() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    for snapshot in history.snapshots:
        event = snapshot.events[-1]
        state = snapshot.state
        assert event.current_state_id == state.state_id
        for boundary in (
            state.candidate_upper_boundary,
            state.candidate_lower_boundary,
            state.confirmed_upper_boundary,
            state.confirmed_lower_boundary,
        ):
            if boundary is not None:
                assert boundary.confirm_time <= snapshot.as_of_time
        assert event.changed_fields
