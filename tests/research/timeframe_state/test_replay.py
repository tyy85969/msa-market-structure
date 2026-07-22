from datetime import datetime, timedelta

import pytest

from msa.research.timeframe_state import (
    TimeframeStateInputError,
    build_history,
    iter_replay_events,
    replay_history,
)
from tests.research.timeframe_state.fixtures import (
    START,
    T1,
    base_pair,
    bar,
    direction_sequence_input,
    timeframe_engine,
    timeframe_input,
)


def test_batch_and_default_replay_are_fully_equal() -> None:
    data = direction_sequence_input()
    engine = timeframe_engine()
    assert replay_history(engine, data).to_dict() == engine.build_batch(data).to_dict()


def test_build_history_alias_matches_batch() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    engine = timeframe_engine()
    assert build_history(engine, data) == engine.build_batch(data)


def test_iter_replay_events_matches_batch_ledger() -> None:
    data = direction_sequence_input()
    engine = timeframe_engine()
    assert tuple(iter_replay_events(engine, data)) == engine.build_batch(data).events


def test_explicit_complete_schedule_with_extra_as_of_creates_no_event() -> None:
    data = timeframe_input(base_pair(), (bar(0),))
    engine = timeframe_engine()
    replay = replay_history(
        engine,
        data,
        (START, START + timedelta(minutes=30), T1),
    )
    batch = engine.build_batch(data)
    assert replay.events == batch.events
    assert replay.final_snapshot == batch.final_snapshot
    assert len(replay.snapshots) == len(batch.snapshots) + 1
    assert replay.snapshots[1].events == replay.snapshots[0].events


@pytest.mark.parametrize(
    "schedule",
    [
        (datetime(2026, 7, 10),),
        (START, START),
        (T1, START),
    ],
)
def test_invalid_schedule_is_rejected(schedule) -> None:
    with pytest.raises(TimeframeStateInputError):
        replay_history(
            timeframe_engine(),
            timeframe_input(base_pair(), (bar(0),)),
            schedule,
        )


def test_sparse_schedule_missing_true_event_time_is_rejected() -> None:
    with pytest.raises(TimeframeStateInputError, match="every true Event"):
        replay_history(
            timeframe_engine(),
            timeframe_input(base_pair(), (bar(0),)),
            (T1,),
        )


def test_schedule_must_reach_final_lifecycle_snapshot() -> None:
    data = direction_sequence_input()
    batch = timeframe_engine().build_batch(data)
    event_times = tuple(item.first_seen_time for item in batch.events[:-1])
    with pytest.raises(TimeframeStateInputError):
        replay_history(timeframe_engine(), data, event_times)
