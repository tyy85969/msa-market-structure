from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from msa.research.swing import replay_events
from tests.research.swing.c003b_fixtures import (
    atr_detector,
    atr_turn_bars,
    ohlc_bar,
)
from tests.research.swing.fixtures import load_result


def test_threshold_bar_must_be_available_before_confirmation() -> None:
    bars = list(atr_turn_bars()[:3])
    bars[-1] = replace(
        bars[-1], available_time=bars[-1].available_time + timedelta(minutes=29)
    )
    source = load_result(tuple(bars))
    before = bars[-1].available_time - timedelta(microseconds=1)
    assert atr_detector().detect_as_of(source, before).candidates == ()
    assert atr_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates


def test_delayed_early_bar_blocks_later_arrivals() -> None:
    bars = list(atr_turn_bars())
    bars[1] = replace(
        bars[1], available_time=bars[-1].available_time + timedelta(hours=2)
    )
    source = load_result(tuple(bars))
    assert atr_detector().detect_as_of(
        source, bars[-1].available_time
    ).candidates == ()


def test_origin_time_never_grants_visibility() -> None:
    bars = atr_turn_bars()[:3]
    source = load_result(bars)
    batch = atr_detector().detect_batch(source).candidates[0]
    assert batch.origin_time < batch.confirm_time
    assert atr_detector().detect_as_of(
        source, batch.confirm_time - timedelta(microseconds=1)
    ).candidates == ()


def test_future_append_does_not_change_old_event() -> None:
    prefix = atr_turn_bars()[:3]
    event = tuple(atr_detector().iter_events(load_result(prefix)))[0]
    extended = prefix + (
        ohlc_bar(3, open="30", high="35", low="25", close="32"),
    )
    matching = tuple(
        item
        for item in atr_detector().iter_events(load_result(extended))
        if item.candidate.candidate_id == event.candidate.candidate_id
    )
    assert matching == (event,)


def test_future_price_change_does_not_change_old_event() -> None:
    bars = atr_turn_bars()
    original = tuple(atr_detector().iter_events(load_result(bars)))[0]
    changed = list(bars)
    changed[-1] = replace(
        changed[-1],
        open=Decimal("40"),
        high=Decimal("50"),
        low=Decimal("30"),
        close=Decimal("45"),
    )
    after = tuple(
        event
        for event in atr_detector().iter_events(load_result(tuple(changed)))
        if event.candidate.candidate_id == original.candidate.candidate_id
    )
    assert after == (original,)


def test_batch_events_equal_replay_first_events() -> None:
    source = load_result(atr_turn_bars())
    detector = atr_detector()
    assert replay_events(detector, source) == tuple(detector.iter_events(source))
