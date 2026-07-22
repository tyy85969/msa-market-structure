from decimal import Decimal

import pytest

from msa.domain import BoundarySide, Direction
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
from msa.research.timeframe_state.contracts import _direction_transition


def directions(data) -> list[Direction]:
    return [item.state.direction for item in timeframe_engine().build_batch(data).snapshots]


def test_no_complete_pair_is_unknown_and_first_pair_is_range() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    assert directions(data) == [Direction.UNKNOWN, Direction.RANGE]


def test_both_midpoints_rise_to_up_then_reverse_to_turning_then_resolve_down() -> None:
    result = directions(direction_sequence_input())
    assert result == [
        Direction.UNKNOWN,
        Direction.RANGE,
        Direction.UP,
        Direction.TURNING,
        Direction.DOWN,
    ]


def test_both_midpoints_fall_to_down() -> None:
    subjects = base_pair() + (
        subject("upper-new", BoundarySide.UPPER, "105", "106", confirm_time=T1),
        subject("lower-new", BoundarySide.LOWER, "85", "86", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="111", low="90", close="100"),
            bar(1, high="106", low="85", close="95"),
        ),
    )
    assert directions(data)[-1] is Direction.DOWN


def test_one_side_rises_and_one_falls_is_range() -> None:
    subjects = base_pair() + (
        subject("upper-new", BoundarySide.UPPER, "115", "116", confirm_time=T1),
        subject("lower-new", BoundarySide.LOWER, "85", "86", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="111", low="90", close="100"),
            bar(1, high="116", low="85", close="100"),
        ),
    )
    assert directions(data)[-1] is Direction.RANGE


def test_one_side_changes_and_one_is_equal_is_range() -> None:
    subjects = base_pair() + (
        subject("upper-new", BoundarySide.UPPER, "115", "116", confirm_time=T1),
        subject("lower-new", BoundarySide.LOWER, "90", "91", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="111", low="90", close="100"),
            bar(1, high="116", low="90", close="100"),
        ),
    )
    assert directions(data)[-1] is Direction.RANGE


def test_new_subjects_at_equal_midpoints_are_range() -> None:
    subjects = base_pair() + (
        subject("upper-replacement", BoundarySide.UPPER, "110", "111", confirm_time=T1),
        subject("lower-replacement", BoundarySide.LOWER, "90", "91", confirm_time=T1),
    )
    data = timeframe_input(subjects, (bar(0), bar(1)))
    final = timeframe_engine().build_batch(data).final_snapshot
    assert final.state.direction is Direction.RANGE
    assert final.explanation.pair_position_changed is True


def test_tested_to_weakened_same_subjects_and_midpoints_preserves_direction() -> None:
    data = timeframe_input(base_pair(), (bar(0), bar(1)))
    history = timeframe_engine().build_batch(data)
    assert history.snapshots[-2].state.direction is Direction.RANGE
    assert history.snapshots[-1].state.direction is Direction.RANGE
    assert history.snapshots[-1].explanation.pair_position_changed is False


def test_pair_loss_after_complete_pair_is_turning() -> None:
    data = timeframe_input(
        base_pair(),
        (
            bar(0),
            bar(1, high="113", low="100", close="112"),
        ),
    )
    history = timeframe_engine().build_batch(data)
    assert history.snapshots[-2].state.direction is Direction.RANGE
    assert history.final_snapshot.state.direction is Direction.TURNING
    assert history.final_snapshot.state.confirmed_upper_boundary is None
    assert history.final_snapshot.explanation.pair_position_changed is True


def test_persistent_missing_pair_keeps_turning_without_repeated_change() -> None:
    data = timeframe_input(
        base_pair(),
        (
            bar(0),
            bar(1, high="113", low="100", close="112"),
            bar(2, high="112", low="100", close="110"),
        ),
    )
    history = timeframe_engine().build_batch(data)
    first_loss, persistent = history.snapshots[-2:]
    assert first_loss.state.direction is Direction.TURNING
    assert first_loss.explanation.pair_position_changed is True
    assert persistent.state.direction is Direction.TURNING
    assert persistent.explanation.pair_position_changed is False


@pytest.mark.parametrize(
    ("current_midpoints", "expected"),
    [
        ((Decimal("100"), Decimal("80")), Direction.RANGE),
        ((Decimal("101"), Decimal("81")), Direction.UP),
        ((Decimal("99"), Decimal("79")), Direction.DOWN),
        ((Decimal("101"), Decimal("79")), Direction.RANGE),
    ],
)
def test_rebuild_compares_with_last_complete_even_after_missing_pair(
    current_midpoints: tuple[Decimal, Decimal], expected: Direction
) -> None:
    result = _direction_transition(
        Direction.TURNING,
        ("upper-old", "lower-old"),
        (Decimal("100"), Decimal("80")),
        (),
        (),
        ("upper-old", "lower-old"),
        current_midpoints,
    )
    assert result[0] is expected
    assert result[1] is expected
    assert result[2] is True


def test_crossing_loss_then_old_compatible_pair_rebuilds_as_range() -> None:
    subjects = (
        subject("old-upper", BoundarySide.UPPER, "130", "131"),
        subject("old-lower", BoundarySide.LOWER, "90", "91"),
        subject(
            "new-crossing-lower",
            BoundarySide.LOWER,
            "140",
            "141",
            confirm_time=T1,
        ),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="131", low="90", close="100"),
            bar(1, high="141", low="90", close="140"),
            bar(2, high="131", low="100", close="100"),
        ),
        break_buffer=Decimal("30"),
    )
    history = timeframe_engine().build_batch(data)
    loss, rebuilt = history.snapshots[-2:]
    assert loss.explanation.confirmed_crossing_conflict is True
    assert loss.state.direction is Direction.TURNING
    assert rebuilt.state.direction is Direction.RANGE
    assert rebuilt.explanation.current_complete_pair_subject_ids == (
        "old-upper",
        "old-lower",
    )
    assert rebuilt.explanation.pair_position_changed is True


def test_pair_incomplete_before_any_complete_pair_remains_unknown() -> None:
    upper = subject("upper", BoundarySide.UPPER, "110", "111")
    data = timeframe_input((upper,), (bar(0, high="100", low="90"),))
    assert all(item.state.direction is Direction.UNKNOWN for item in timeframe_engine().build_batch(data).snapshots)


def test_candidate_only_change_does_not_change_direction() -> None:
    subjects = base_pair() + (
        subject("fresh-upper", BoundarySide.UPPER, "120", "121", confirm_time=T2),
    )
    data = timeframe_input(subjects, (bar(0),))
    history = timeframe_engine().build_batch(data)
    assert history.snapshots[-2].state.direction is Direction.RANGE
    assert history.final_snapshot.state.direction is Direction.RANGE
    assert history.final_snapshot.state.candidate_upper_boundary.price_range.low == Decimal("120")
    assert history.final_snapshot.state.confirmed_upper_boundary.price_range.low == Decimal("110")


def test_direction_midpoint_uses_exact_decimal_without_rounding() -> None:
    subjects = (
        subject("upper-a", BoundarySide.UPPER, "110.1", "110.3"),
        subject("lower-a", BoundarySide.LOWER, "90.1", "90.3"),
        subject("upper-b", BoundarySide.UPPER, "110.1000000000000000001", "110.3000000000000000001", confirm_time=T1),
        subject("lower-b", BoundarySide.LOWER, "90.1000000000000000001", "90.3000000000000000001", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="110.3", low="90.1", close="100"),
            bar(1, high="110.3000000000000000001", low="90.1000000000000000001", close="100"),
        ),
        break_buffer=Decimal("100"),
    )
    final = timeframe_engine().build_batch(data).final_snapshot
    assert final.state.direction is Direction.UP
    assert final.explanation.current_pair_midpoints[0] == Decimal("110.2000000000000000001")


def test_forming_candidate_ids_are_always_empty() -> None:
    history = timeframe_engine().build_batch(direction_sequence_input())
    assert all(item.state.forming_candidate_ids == () for item in history.snapshots)
