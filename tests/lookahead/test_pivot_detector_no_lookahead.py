from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.research.swing import replay_events
from tests.research.swing.fixtures import (
    bar,
    bars_from_extrema,
    detector,
    load_result,
)


def right_two_source():
    bars = list(
        bars_from_extrema(
            ("10", "11", "30.500", "12", "13"),
            ("5", "6", "7", "8", "9"),
        )
    )
    bars[4] = replace(
        bars[4], available_time=bars[4].end_time + timedelta(minutes=37)
    )
    return tuple(bars)


def pivot():
    return detector(left_bars=2, right_bars=2)


def test_right_two_high_pivot_requires_complete_causal_window() -> None:
    source = load_result(right_two_source())
    batch = pivot().detect_batch(source)
    assert len(batch.candidates) == 1


def test_only_through_center_cannot_confirm() -> None:
    bars = right_two_source()
    source = load_result(bars)
    assert pivot().detect_as_of(source, bars[2].available_time).candidates == ()
    assert pivot().detect_batch(load_result(bars[:3])).candidates == ()


def test_first_right_bar_cannot_confirm() -> None:
    bars = right_two_source()
    assert pivot().detect_as_of(
        load_result(bars), bars[3].available_time
    ).candidates == ()


def test_existing_but_unavailable_second_right_bar_cannot_confirm() -> None:
    bars = right_two_source()
    before = bars[4].available_time - timedelta(microseconds=1)
    assert pivot().detect_as_of(load_result(bars), before).candidates == ()


def test_pivot_first_confirms_at_maximum_window_availability() -> None:
    bars = right_two_source()
    source = load_result(bars)
    candidate = pivot().detect_batch(source).candidates[0]
    at_time = pivot().detect_as_of(source, bars[4].available_time)
    assert at_time.candidates == (candidate,)
    assert candidate.confirm_time == max(bar.available_time for bar in bars)


def test_origin_time_remains_center_bar_time_after_confirmation() -> None:
    bars = right_two_source()
    candidate = pivot().detect_batch(load_result(bars)).candidates[0]
    assert candidate.origin_time == bars[2].timestamp
    assert candidate.origin_time < candidate.confirm_time


def test_candidate_confirm_time_equals_replay_first_seen_time() -> None:
    source = load_result(right_two_source())
    event = replay_events(pivot(), source)[0]
    assert event.first_seen_time == event.candidate.confirm_time


def test_bars_outside_confirming_window_cannot_change_confirmed_pivot() -> None:
    bars = right_two_source()
    extended = bars + (
        bar(5, high="200", low="100"),
        bar(6, high="180", low="90"),
    )
    changed = list(extended)
    changed[6] = replace(
        changed[6],
        open=Decimal("350"),
        high=Decimal("400"),
        low=Decimal("300"),
        close=Decimal("350"),
    )
    original = pivot().detect_batch(load_result(extended)).candidates
    mutated = pivot().detect_batch(load_result(tuple(changed))).candidates
    center_time = bars[2].timestamp
    assert tuple(item for item in original if item.origin_time == center_time) == tuple(
        item for item in mutated if item.origin_time == center_time
    )


def test_batch_and_event_replay_are_fully_equal() -> None:
    source = load_result(right_two_source())
    batch_events = tuple(pivot().iter_events(source))
    chronological = replay_events(pivot(), source)
    assert chronological == batch_events
    assert [event.first_seen_time for event in chronological] == [
        event.candidate.confirm_time for event in batch_events
    ]
