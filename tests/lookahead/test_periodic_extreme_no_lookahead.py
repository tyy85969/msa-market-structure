from dataclasses import replace
from datetime import timedelta
from random import Random

from msa.research.levels import replay_events
from tests.research.levels.fixtures import (
    START,
    bar,
    periodic_generator,
    periodic_input,
)


def test_periodic_extreme_is_invisible_before_bar_availability() -> None:
    source_bar = bar(0, available_time=START + timedelta(hours=3))
    data = periodic_input((source_bar,))
    generator = periodic_generator()
    assert generator.generate_as_of(
        data, source_bar.available_time - timedelta(microseconds=1)
    ).candidates == ()
    assert len(generator.generate_as_of(data, source_bar.available_time).candidates) == 2


def test_incomplete_period_never_exposes_final_looking_extremes() -> None:
    incomplete = bar(
        0,
        high="999",
        low="1",
        open="100",
        close="500",
        is_complete=False,
    )
    assert periodic_generator().generate_batch(
        periodic_input((incomplete,))
    ).candidates == ()


def test_future_append_does_not_change_periodic_history() -> None:
    original = periodic_generator().generate_batch(periodic_input((bar(0),))).candidates
    extended = periodic_generator().generate_batch(
        periodic_input((bar(0), bar(1, high="999", low="1", open="100", close="500")))
    ).candidates
    assert all(item in extended for item in original)


def test_future_price_mutation_does_not_change_old_periodic_candidate() -> None:
    bars = (bar(0), bar(1))
    original = periodic_generator().generate_batch(periodic_input(bars)).candidates[:2]
    changed_future = replace(
        bars[1],
        open=bars[1].open,
        high=bars[1].high + 100,
        low=bars[1].low - 50,
        close=bars[1].close,
    )
    changed = periodic_generator().generate_batch(
        periodic_input((bars[0], changed_future))
    ).candidates
    assert all(item in changed for item in original)


def test_fixed_seed_random_delays_preserve_exact_batch_replay_events() -> None:
    random = Random(20260719)
    bars = tuple(
        bar(
            index,
            available_time=START
            + timedelta(hours=index + 1, minutes=random.randrange(0, 180)),
        )
        for index in range(12)
    )
    data = periodic_input(bars)
    generator = periodic_generator()
    assert [event.to_dict() for event in replay_events(generator, data)] == [
        event.to_dict() for event in generator.iter_events(data)
    ]
