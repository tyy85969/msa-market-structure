from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from msa.research.levels import (
    LevelGenerationError,
    LevelInputError,
    replay_events,
)
from tests.research.levels.fixtures import (
    START,
    bar,
    periodic_generator,
    periodic_input,
    reaction_generator,
    reaction_input,
    upper_success_bars,
)


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_batch_and_replay_events_are_exactly_equal(kind: str) -> None:
    if kind == "periodic":
        generator = periodic_generator()
        data = periodic_input((bar(0), bar(1)))
    else:
        generator = reaction_generator()
        data = reaction_input(upper_success_bars())
    batch_events = tuple(generator.iter_events(data))
    chronological = replay_events(generator, data)
    assert [item.to_dict() for item in chronological] == [
        item.to_dict() for item in batch_events
    ]


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_every_first_seen_time_equals_candidate_confirm_time(kind: str) -> None:
    if kind == "periodic":
        generator = periodic_generator()
        data = periodic_input((bar(0), bar(1)))
    else:
        generator = reaction_generator()
        data = reaction_input(upper_success_bars())
    assert all(
        event.first_seen_time == event.candidate.confirm_time
        for event in replay_events(generator, data)
    )


def test_periodic_replay_handles_nonmonotonic_arrival_without_timestamp_rewrite() -> None:
    earlier = bar(0, available_time=START + timedelta(hours=5))
    later = bar(1, available_time=START + timedelta(hours=2))
    events = replay_events(periodic_generator(), periodic_input((earlier, later)))
    assert [event.first_seen_time for event in events] == sorted(
        event.first_seen_time for event in events
    )
    assert {event.candidate.origin_time for event in events[:2]} == {later.timestamp}
    assert {event.candidate.origin_time for event in events[2:]} == {earlier.timestamp}


def test_reaction_replay_uses_bar_and_seed_schedule_union() -> None:
    bars = list(upper_success_bars())
    bars[0] = replace(bars[0], available_time=START + timedelta(hours=10))
    data = reaction_input(tuple(bars))
    events = replay_events(reaction_generator(), data)
    assert len(events) == 1
    assert events[0].first_seen_time == START + timedelta(hours=10)


def test_replay_rejects_naive_schedule_time() -> None:
    with pytest.raises(LevelInputError, match="timezone-aware"):
        replay_events(
            periodic_generator(),
            periodic_input((bar(0),)),
            (datetime(2026, 7, 1, 1),),
        )


def test_replay_rejects_duplicate_or_unsorted_schedule() -> None:
    moment = bar(0).available_time
    with pytest.raises(LevelInputError, match="strictly ascending"):
        replay_events(
            periodic_generator(), periodic_input((bar(0),)), (moment, moment)
        )


@pytest.mark.parametrize("kind", ["periodic", "reaction"])
def test_sparse_schedule_cannot_claim_late_first_appearance(kind: str) -> None:
    if kind == "periodic":
        generator = periodic_generator()
        data = periodic_input((bar(0),))
        late = bar(0).available_time + timedelta(hours=1)
    else:
        generator = reaction_generator()
        data = reaction_input(upper_success_bars())
        late = upper_success_bars()[-1].available_time + timedelta(hours=1)
    with pytest.raises(LevelGenerationError, match="first appearance"):
        replay_events(generator, data, (late,))


def test_replay_events_are_sorted_by_confirm_time_and_id() -> None:
    events = replay_events(
        periodic_generator(), periodic_input((bar(0), bar(1)))
    )
    signatures = [
        (event.first_seen_time, event.candidate.candidate_id) for event in events
    ]
    assert signatures == sorted(signatures)
