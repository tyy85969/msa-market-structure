from dataclasses import replace
from datetime import timedelta

from msa.research.lifecycle import LifecycleEventType, replay_history
from tests.research.lifecycle.fixtures import (
    START, T1, T2, T3, T4, bar, engine, lifecycle_input, subject,
    upper_break_bars,
)


def test_early_origin_does_not_activate_before_subject_confirm_time() -> None:
    data = lifecycle_input((bar(0),), (subject(confirm_time=T2),))
    assert engine().build_as_of(data, T1).states == ()
    assert engine().build_as_of(data, T2).states[0].structural_origin_time < T1


def test_subject_confirmation_observation_bar_is_not_consumed() -> None:
    bars = (bar(0, open="100", high="104", low="99", close="102"),)
    snapshot = engine().build_as_of(lifecycle_input(bars), T1)
    assert [item.event_type for item in snapshot.events] == [LifecycleEventType.ACTIVATED]


def test_next_complete_bar_is_first_that_can_test_or_break() -> None:
    bars = (bar(0), bar(1, open="101", high="103", low="100", close="102"))
    before = engine().build_as_of(lifecycle_input(bars), T2 - timedelta(microseconds=1))
    at_time = engine().build_as_of(lifecycle_input(bars), T2)
    assert LifecycleEventType.BROKEN not in [item.event_type for item in before.events]
    assert LifecycleEventType.BROKEN in [item.event_type for item in at_time.events]


def test_delayed_earlier_bar_blocks_all_later_bars() -> None:
    bars = list(upper_break_bars())
    bars[0] = replace(bars[0], available_time=T4)
    snapshot = engine().build_as_of(lifecycle_input(tuple(bars)), T3)
    assert snapshot.report.processed_bar_count == 0
    assert [item.event_type for item in snapshot.events] == [LifecycleEventType.ACTIVATED]


def test_break_bar_is_absent_until_available() -> None:
    bars = (bar(0), bar(1, open="101", high="103", low="100", close="102", available_time=T3))
    before = engine().build_as_of(lifecycle_input(bars), T3 - timedelta(microseconds=1))
    assert LifecycleEventType.BROKEN not in [item.event_type for item in before.events]


def test_break_first_appears_at_prefix_maximum_availability() -> None:
    bars = (
        replace(bar(0), available_time=T3),
        bar(1, open="101", high="103", low="100", close="102", available_time=T2),
    )
    snapshot = engine().build_as_of(lifecycle_input(bars), T3)
    broken = next(item for item in snapshot.events if item.event_type is LifecycleEventType.BROKEN)
    assert broken.event_origin_time == T1
    assert broken.event_confirm_time == T3


def test_flip_touch_and_confirmation_are_distinct_bars() -> None:
    snapshot = engine().build_batch(lifecycle_input(upper_break_bars())).final_snapshot
    touch = next(item for item in snapshot.events if item.event_type is LifecycleEventType.FLIP_TOUCH)
    flipped = next(item for item in snapshot.events if item.event_type is LifecycleEventType.FLIPPED)
    assert touch.source_bar_key != flipped.source_bar_key
    assert touch.event_origin_time < flipped.event_origin_time


def test_future_confirmation_bar_cannot_flip_early() -> None:
    data = lifecycle_input(upper_break_bars())
    before = engine().build_as_of(data, T4 - timedelta(microseconds=1))
    at_time = engine().build_as_of(data, T4)
    assert LifecycleEventType.FLIPPED not in [item.event_type for item in before.events]
    assert LifecycleEventType.FLIPPED in [item.event_type for item in at_time.events]


def test_batch_and_replay_first_seen_payloads_are_identical() -> None:
    data = lifecycle_input(upper_break_bars())
    batch = engine().build_batch(data)
    replay = replay_history(engine(), data)
    assert [item.to_dict() for item in replay.events] == [item.to_dict() for item in batch.events]
    assert all(item.first_seen_time == item.event_confirm_time for item in replay.events)


def test_future_append_does_not_change_old_event_payload() -> None:
    prefix = upper_break_bars()[:3]
    future = prefix + (bar(3, open="102", high="104", low="102", close="103"),)
    old_events = engine().build_batch(lifecycle_input(prefix)).events
    new_events = engine().build_batch(lifecycle_input(future)).events
    assert [item.to_dict() for item in new_events[:len(old_events)]] == [item.to_dict() for item in old_events]
