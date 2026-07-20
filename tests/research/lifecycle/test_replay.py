from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from msa.domain import PriceRange
from msa.research.lifecycle import (
    LifecycleEngineError, LifecycleEventType, LifecycleHistory,
    LifecycleInputError, replay_history,
)
from tests.research.lifecycle.fixtures import (
    START, T1, T2, T3, T4, T5, bar, config, engine, lifecycle_input,
    subject, upper_break_bars,
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


def test_history_rejects_snapshot_config_change() -> None:
    history = engine().build_batch(lifecycle_input(upper_break_bars()))
    changed = replace(
        history.snapshots[-1],
        config_snapshot=config(break_buffer=Decimal("2")),
    )
    with pytest.raises(LifecycleEngineError, match="configurations"):
        LifecycleHistory(
            events=changed.events,
            snapshots=history.snapshots[:-1] + (changed,),
            final_snapshot=changed,
        )


def test_history_rejects_subject_disappearance() -> None:
    first = engine().build_as_of(
        lifecycle_input((bar(0),), (subject("early"),)), T1
    )
    later = engine().build_as_of(
        lifecycle_input(
            (bar(0), bar(1)),
            (subject("late", confirm_time=T2),),
        ),
        T2,
    )
    with pytest.raises(LifecycleEngineError, match="cannot disappear"):
        LifecycleHistory(later.events, (first, later), later)


def test_history_rejects_subject_ref_replacement_for_same_id() -> None:
    original = subject("stable")
    changed_ref = replace(
        original,
        price_range=PriceRange(Decimal("110"), Decimal("111")),
    )
    first = engine().build_as_of(
        lifecycle_input((bar(0),), (original,)), T1
    )
    later = engine().build_as_of(
        lifecycle_input((bar(0), bar(1)), (changed_ref,)), T2
    )
    with pytest.raises(LifecycleEngineError, match="subject_ref facts are immutable"):
        LifecycleHistory(later.events, (first, later), later)


def test_history_rejects_nonprefix_state_event_ids() -> None:
    tested = engine().build_as_of(lifecycle_input((
        bar(0), bar(1, open="100", high="101", low="99", close="100"),
    )), T2)
    alternative = engine().build_as_of(lifecycle_input((
        bar(0), bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="103", high="104", low="103", close="103"),
    )), T3)
    with pytest.raises(LifecycleEngineError, match="extend the earlier event prefix"):
        LifecycleHistory(alternative.events, (tested, alternative), alternative)


def test_history_rejects_state_fact_change_without_new_event() -> None:
    data = lifecycle_input((
        bar(0),
        bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="103", high="104", low="103", close="103"),
    ))
    first = engine().build_as_of(data, T2)
    later = engine().build_as_of(data, T3)
    assert first.states[0].event_ids == later.states[0].event_ids
    changed_state = replace(later.states[0], break_threshold=Decimal("999"))
    changed = replace(later, states=(changed_state,))
    with pytest.raises(LifecycleEngineError, match="without a new event"):
        LifecycleHistory(changed.events, (first, changed), changed)


def test_history_accepts_subject_activated_in_later_snapshot() -> None:
    history = engine().build_batch(lifecycle_input(
        (bar(0), bar(1)),
        (subject("early"), subject("late", confirm_time=T2)),
    ))
    assert [len(snapshot.states) for snapshot in history.snapshots] == [1, 2]
    assert history.final_snapshot.states[1].subject_ref.object_id == "late"


def test_history_accepts_delayed_prefix_same_confirm_time_event_chain() -> None:
    bars = (
        replace(bar(0), available_time=T4),
        bar(1, open="100", high="101", low="99", close="100", available_time=T2),
        bar(2, open="100", high="101", low="99", close="100", available_time=T3),
        bar(3, open="100", high="101", low="99", close="100", available_time=T4),
    )
    history = engine().build_batch(lifecycle_input(bars))
    same_time = tuple(
        event for event in history.events if event.event_confirm_time == T4
    )
    assert tuple(event.event_type for event in same_time) == (
        LifecycleEventType.TEST,
        LifecycleEventType.WEAKENED,
        LifecycleEventType.TEST,
    )


def test_history_accepts_flip_touch_and_horizon_retirement_on_same_bar() -> None:
    bars = (
        bar(0),
        bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="103", high="104", low="103", close="103"),
        bar(3, open="103", high="104", low="103", close="103"),
        bar(4, open="101", high="102", low="100", close="101"),
    )
    history = engine().build_batch(lifecycle_input(bars))
    assert tuple(event.event_type for event in history.events[-2:]) == (
        LifecycleEventType.FLIP_TOUCH,
        LifecycleEventType.RETIRED,
    )
    assert history.events[-2].event_confirm_time == T5
    assert history.events[-1].event_confirm_time == T5


def test_history_accepts_complete_flipped_ledger() -> None:
    history = engine().build_batch(lifecycle_input(upper_break_bars()))
    assert history.events[-1].event_type is LifecycleEventType.FLIPPED
    assert history.final_snapshot == history.snapshots[-1]
