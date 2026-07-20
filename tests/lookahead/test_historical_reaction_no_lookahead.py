from dataclasses import replace
from datetime import timedelta

from msa.research.levels import replay_events
from tests.research.levels.fixtures import (
    START,
    bar,
    reaction_generator,
    reaction_input,
    seed,
    upper_success_bars,
)


def test_reaction_candidate_is_invisible_before_nth_confirmation() -> None:
    bars = upper_success_bars()
    data = reaction_input(bars)
    generator = reaction_generator()
    assert generator.generate_as_of(
        data, bars[4].available_time - timedelta(microseconds=1)
    ).candidates == ()
    assert len(generator.generate_as_of(data, bars[4].available_time).candidates) == 1


def test_delayed_prefix_member_delays_first_reaction_appearance() -> None:
    bars = list(upper_success_bars())
    bars[0] = replace(bars[0], available_time=START + timedelta(hours=12))
    data = reaction_input(tuple(bars))
    generator = reaction_generator()
    candidate = generator.generate_batch(data).candidates[0]
    assert candidate.confirm_time == START + timedelta(hours=12)
    assert generator.generate_as_of(
        data, START + timedelta(hours=11)
    ).candidates == ()
    assert generator.generate_as_of(
        data, START + timedelta(hours=12)
    ).candidates == (candidate,)


def test_future_append_and_extreme_prices_do_not_rewrite_reaction_candidate() -> None:
    original_bars = upper_success_bars()
    generator = reaction_generator()
    original = generator.generate_batch(reaction_input(original_bars)).candidates[0]
    future = (
        bar(5, high="500", low="10", open="100", close="300"),
        bar(6, high="600", low="1", open="100", close="50"),
    )
    assert generator.generate_batch(
        reaction_input(original_bars + future)
    ).candidates[0] == original


def test_touch_bar_close_away_does_not_backdate_confirmation() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="95", open="100", close="96"),
        bar(2, high="98", low="95", open="97", close="96"),
        bar(3, high="101", low="99", open="100", close="100"),
        bar(4, high="98", low="95", open="97", close="96"),
    )
    result = reaction_generator().generate_batch(reaction_input(bars))
    assert len(result.candidates) == 1
    assert result.candidates[0].confirm_time == bars[4].available_time
    assert result.candidates[0].confirm_time != bars[1].available_time


def test_batch_and_replay_preserve_exact_reaction_provenance_and_first_time() -> None:
    data = reaction_input(upper_success_bars())
    generator = reaction_generator()
    batch = tuple(generator.iter_events(data))
    replay = replay_events(generator, data)
    assert [event.to_dict() for event in replay] == [
        event.to_dict() for event in batch
    ]


def test_exact_horizon_candidate_first_appears_on_confirmation_bar() -> None:
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(1, high="101", low="99", open="100", close="100"),
        bar(2, high="101", low="98", open="100", close="100"),
        bar(3, high="98", low="95", open="97", close="96"),
        bar(4, high="101", low="99", open="100", close="100"),
        bar(5, high="101", low="98", open="100", close="100"),
        bar(6, high="98", low="95", open="97", close="96"),
    )
    data = reaction_input(bars)
    generator = reaction_generator(confirmation_horizon_bars=2)

    assert generator.generate_as_of(
        data,
        bars[6].available_time - timedelta(microseconds=1),
    ).candidates == ()
    candidate = generator.generate_as_of(
        data,
        bars[6].available_time,
    ).candidates[0]

    assert candidate.confirm_time == bars[6].available_time
    assert replay_events(generator, data)[0].first_seen_time == candidate.confirm_time


def test_ineligible_horizon_member_blocks_later_close_away() -> None:
    late_seed = seed(confirm_time=START + timedelta(hours=7))
    bars = (
        bar(0, high="90", low="88", open="89", close="89"),
        bar(
            1,
            high="101",
            low="99",
            open="100",
            close="100",
            available_time=START + timedelta(hours=8),
        ),
        bar(
            2,
            high="98",
            low="95",
            open="97",
            close="96",
            available_time=START + timedelta(hours=8),
        ),
        bar(
            3,
            high="90",
            low="88",
            open="89",
            close="89",
            available_time=START + timedelta(hours=8),
        ),
        bar(
            4,
            high="101",
            low="99",
            open="100",
            close="100",
            available_time=START + timedelta(hours=8),
        ),
        bar(
            5,
            high="101",
            low="98",
            open="100",
            close="100",
            available_time=START + timedelta(hours=8),
        ),
        bar(6, high="101", low="98", open="100", close="100"),
        bar(7, high="98", low="95", open="97", close="96"),
    )
    data = reaction_input(bars, (late_seed,))
    generator = reaction_generator(confirmation_horizon_bars=2)

    assert generator.generate_batch(data).candidates == ()
    assert generator.generate_as_of(
        data,
        bars[7].available_time,
    ).candidates == ()
    assert replay_events(generator, data) == ()
