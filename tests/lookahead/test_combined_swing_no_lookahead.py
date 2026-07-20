from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from random import Random

from msa.research.swing import replay_events
from tests.research.swing.c003b_fixtures import (
    atr_combination_bars,
    combined_detector,
)
from tests.research.swing.fixtures import load_result


def test_combination_not_visible_before_atr_seed_confirmation() -> None:
    bars = atr_combination_bars()
    source = load_result(bars)
    assert combined_detector().detect_as_of(
        source, bars[3].available_time
    ).candidates == ()


def test_combination_break_bar_must_be_available() -> None:
    bars = list(atr_combination_bars())
    bars[-1] = replace(
        bars[-1], available_time=bars[-1].available_time + timedelta(minutes=13)
    )
    source = load_result(tuple(bars))
    before = bars[-1].available_time - timedelta(microseconds=1)
    assert combined_detector().detect_as_of(source, before).candidates == ()
    assert combined_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates


def test_combination_honors_delayed_early_prefix_bar() -> None:
    bars = list(atr_combination_bars())
    bars[1] = replace(
        bars[1], available_time=bars[-1].available_time + timedelta(hours=1)
    )
    source = load_result(tuple(bars))
    assert combined_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates == ()


def test_future_price_change_after_confirmation_does_not_rewrite_event() -> None:
    bars = atr_combination_bars()
    original = tuple(combined_detector().iter_events(load_result(bars)))[0]
    future = replace(
        bars[-1],
        timestamp=bars[-1].timestamp + timedelta(hours=1),
        end_time=bars[-1].end_time + timedelta(hours=1),
        available_time=bars[-1].available_time + timedelta(hours=1),
        open=Decimal("30"),
        high=Decimal("35"),
        low=Decimal("25"),
        close=Decimal("32"),
    )
    matching = tuple(
        event
        for event in combined_detector().iter_events(load_result(bars + (future,)))
        if event.candidate.candidate_id == original.candidate.candidate_id
    )
    assert matching == (original,)


def test_combined_batch_events_equal_replay_first_events() -> None:
    source = load_result(atr_combination_bars())
    detector = combined_detector()
    assert replay_events(detector, source) == tuple(detector.iter_events(source))


def test_fixed_seed_arrival_delays_preserve_batch_replay_parity() -> None:
    random = Random(20260719)
    bars = tuple(
        replace(
            bar,
            available_time=bar.end_time + timedelta(minutes=random.randrange(0, 90)),
        )
        for bar in atr_combination_bars()
    )
    source = load_result(bars)
    detector = combined_detector()
    assert replay_events(detector, source) == tuple(detector.iter_events(source))
