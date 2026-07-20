from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from msa.research.lifecycle import LifecycleInputError, replay_history
from tests.research.lifecycle.fixtures import (
    START, T1, T2, T3, T4, bar, engine, lifecycle_input, upper_break_bars,
)


def test_batch_and_default_replay_are_fully_equal() -> None:
    data = lifecycle_input(upper_break_bars())
    assert replay_history(engine(), data).to_dict() == engine().build_batch(data).to_dict()


def test_explicit_complete_schedule_matches_events_and_final_snapshot() -> None:
    data = lifecycle_input(upper_break_bars())
    replay = replay_history(engine(), data, (T1, T2, T3, T4))
    batch = engine().build_batch(data)
    assert replay.events == batch.events
    assert replay.final_snapshot == batch.final_snapshot


def test_sparse_schedule_cannot_claim_late_discovery() -> None:
    data = lifecycle_input(upper_break_bars())
    with pytest.raises(LifecycleInputError, match="every true Event"):
        replay_history(engine(), data, (T4,))


@pytest.mark.parametrize("schedule", [
    (datetime(2026, 7, 1, 1),), (T1, T1), (T2, T1),
])
def test_invalid_schedule_is_rejected(schedule) -> None:
    with pytest.raises(LifecycleInputError):
        replay_history(engine(), lifecycle_input(upper_break_bars()), schedule)


def test_future_append_does_not_change_old_event_payloads() -> None:
    prefix = upper_break_bars()[:3]
    extended = upper_break_bars()
    old = engine().build_batch(lifecycle_input(prefix)).events
    new = engine().build_batch(lifecycle_input(extended)).events[:len(old)]
    assert new == old


def test_future_price_change_does_not_change_past_events() -> None:
    bars = upper_break_bars()
    changed = bars[:3] + (replace(bars[3], open=bars[3].open + 100,
                                  high=bars[3].high + 100,
                                  low=bars[3].low + 100,
                                  close=bars[3].close + 100),)
    past = engine().build_as_of(lifecycle_input(bars), T3).events
    changed_past = engine().build_as_of(lifecycle_input(changed), T3).events
    assert changed_past == past


def test_delayed_early_bar_blocks_later_bars() -> None:
    bars = list(upper_break_bars())
    bars[0] = replace(bars[0], available_time=T4)
    snapshot = engine().build_as_of(lifecycle_input(tuple(bars)), T3)
    assert snapshot.report.processed_bar_count == 0
    assert snapshot.report.causal_prefix_truncated is True
    assert len(snapshot.events) == 1  # activation needs no price bar


def test_same_time_events_are_atomic_and_stably_sorted() -> None:
    data = lifecycle_input((bar(0),), subjects=None)
    first = engine().build_as_of(data, T1)
    second = engine().build_as_of(data, T1)
    assert first == second
    assert all(item.first_seen_time == item.event_confirm_time for item in first.events)


def test_origin_time_does_not_grant_replay_visibility() -> None:
    data = lifecycle_input((bar(0),))
    assert engine().build_as_of(data, START).states == ()
