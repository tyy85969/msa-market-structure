from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.research.swing import replay_events
from tests.research.swing.c003b_fixtures import (
    pivot_upper_break_bars,
    structure_detector,
)
from tests.research.swing.fixtures import load_result


def test_seed_origin_time_is_not_seed_availability() -> None:
    bars = pivot_upper_break_bars()
    source = load_result(bars)
    assert structure_detector().detect_as_of(
        source, bars[3].available_time
    ).candidates == ()


def test_break_bar_must_be_available() -> None:
    bars = list(pivot_upper_break_bars())
    bars[-1] = replace(
        bars[-1], available_time=bars[-1].available_time + timedelta(minutes=41)
    )
    source = load_result(tuple(bars))
    before = bars[-1].available_time - timedelta(microseconds=1)
    assert structure_detector().detect_as_of(source, before).candidates == ()
    assert structure_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates


def test_delayed_early_bar_blocks_structure_state() -> None:
    bars = list(pivot_upper_break_bars())
    bars[0] = replace(
        bars[0], available_time=bars[-1].available_time + timedelta(hours=2)
    )
    source = load_result(tuple(bars))
    assert structure_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates == ()


def test_future_append_does_not_change_structure_event() -> None:
    bars = pivot_upper_break_bars()
    original = tuple(structure_detector().iter_events(load_result(bars)))[0]
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
        for event in structure_detector().iter_events(load_result(bars + (future,)))
        if event.candidate.candidate_id == original.candidate.candidate_id
    )
    assert matching == (original,)


def test_batch_events_equal_structure_replay_events() -> None:
    source = load_result(pivot_upper_break_bars())
    detector = structure_detector()
    assert replay_events(detector, source) == tuple(detector.iter_events(source))
