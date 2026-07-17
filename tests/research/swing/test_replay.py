from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from msa.research.swing import (
    SwingDetectionError,
    SwingInputError,
    replay_events,
)
from tests.research.swing.fixtures import (
    START,
    bar,
    bars_from_extrema,
    detector,
    high_pivot_bars,
    load_result,
)


def delayed_high_pivot_bars() -> tuple[object, ...]:
    bars = list(high_pivot_bars())
    bars[3] = replace(
        bars[3], available_time=bars[3].end_time + timedelta(minutes=23)
    )
    return tuple(bars)


def test_as_of_consumes_only_bars_available_by_processing_time() -> None:
    bars = delayed_high_pivot_bars()
    processing_time = bars[3].available_time - timedelta(microseconds=1)
    result = detector().detect_as_of(load_result(bars), processing_time)
    assert result.candidates == ()
    assert result.report.input_bar_count == 3


def test_candidate_is_not_consumable_before_confirm_time() -> None:
    source = load_result(delayed_high_pivot_bars())
    candidate = detector().detect_batch(source).candidates[0]
    before = detector().detect_as_of(
        source, candidate.confirm_time - timedelta(microseconds=1)
    )
    assert before.candidates == ()


def test_candidate_first_becomes_consumable_at_confirm_time() -> None:
    source = load_result(delayed_high_pivot_bars())
    batch_candidate = detector().detect_batch(source).candidates[0]
    at_time = detector().detect_as_of(source, batch_candidate.confirm_time)
    assert at_time.candidates == (batch_candidate,)


def test_delayed_early_window_member_pushes_confirm_time() -> None:
    bars = list(high_pivot_bars())
    bars[1] = replace(
        bars[1], available_time=bars[1].end_time + timedelta(hours=8)
    )
    source = load_result(tuple(bars))
    candidate = detector().detect_batch(source).candidates[0]
    assert candidate.confirm_time == bars[1].available_time
    assert detector().detect_as_of(
        source, candidate.confirm_time - timedelta(microseconds=1)
    ).candidates == ()
    assert detector().detect_as_of(source, candidate.confirm_time).candidates == (
        candidate,
    )


def test_nonmonotonic_arrival_does_not_compress_fixed_window_membership() -> None:
    bars = list(high_pivot_bars())
    bars[1] = replace(
        bars[1], available_time=bars[4].available_time + timedelta(hours=2)
    )
    source = load_result(tuple(bars))
    before_delayed_left = detector().detect_as_of(
        source, bars[4].available_time
    )
    assert before_delayed_left.candidates == ()


def test_batch_and_replay_candidate_sets_are_equal() -> None:
    source = load_result(delayed_high_pivot_bars())
    pivot = detector()
    batch = pivot.detect_batch(source)
    replay = replay_events(pivot, source)
    assert {event.candidate for event in replay} == set(batch.candidates)


def test_batch_and_replay_first_appearance_times_are_equal() -> None:
    source = load_result(delayed_high_pivot_bars())
    pivot = detector()
    batch_events = tuple(pivot.iter_events(source))
    chronological = replay_events(pivot, source)
    assert [event.to_dict() for event in chronological] == [
        event.to_dict() for event in batch_events
    ]
    assert all(
        event.first_seen_time == event.candidate.confirm_time
        for event in chronological
    )


def test_appending_future_bars_does_not_change_old_candidate() -> None:
    prefix = high_pivot_bars()
    extended = prefix + (
        bar(5, high="18", low="11"),
        bar(6, high="19", low="12"),
    )
    original = detector().detect_batch(load_result(prefix)).candidates[0]
    later = detector().detect_batch(load_result(extended)).candidates
    assert original in later


def test_changing_prices_outside_confirmation_window_does_not_change_candidate() -> None:
    original_bars = high_pivot_bars()
    changed = list(original_bars)
    changed[4] = replace(
        changed[4],
        open=Decimal("90"),
        high=Decimal("100"),
        low=Decimal("80"),
        close=Decimal("90"),
    )
    original = detector().detect_batch(load_result(original_bars)).candidates[0]
    after = detector().detect_batch(load_result(tuple(changed))).candidates[0]
    assert after == original


def test_changing_right_window_price_can_change_forming_outcome() -> None:
    ordinary = list(high_pivot_bars())
    changed = list(ordinary)
    changed[3] = replace(
        changed[3],
        open=Decimal("30"),
        high=Decimal("31"),
        low=Decimal("11"),
        close=Decimal("20"),
        available_time=changed[3].end_time + timedelta(minutes=10),
    )
    ordinary[3] = replace(
        ordinary[3],
        available_time=ordinary[3].end_time + timedelta(minutes=10),
    )
    ordinary_source = load_result(tuple(ordinary))
    changed_source = load_result(tuple(changed))
    before = ordinary[3].available_time - timedelta(microseconds=1)
    assert detector().detect_as_of(ordinary_source, before).candidates == ()
    assert detector().detect_as_of(changed_source, before).candidates == ()
    assert len(
        detector().detect_as_of(
            ordinary_source, ordinary[3].available_time
        ).candidates
    ) == 1
    assert detector().detect_as_of(
        changed_source, changed[3].available_time
    ).candidates == ()


def test_emitted_candidate_object_is_not_rewritten_by_later_history() -> None:
    source = load_result(high_pivot_bars())
    emitted = replay_events(detector(), source)[0].candidate
    extended = high_pivot_bars() + (
        bar(5, high="100", low="50"),
        bar(6, high="90", low="40"),
    )
    historical = tuple(
        item
        for item in detector().detect_batch(load_result(extended)).candidates
        if item.candidate_id == emitted.candidate_id
    )
    assert historical == (emitted,)


def test_naive_processing_time_is_rejected() -> None:
    with pytest.raises(SwingInputError, match="timezone-aware"):
        detector().detect_as_of(
            load_result(high_pivot_bars()), datetime(2026, 7, 1, 1, 0)
        )


def test_replay_rejects_naive_schedule_time() -> None:
    with pytest.raises(SwingInputError, match="timezone-aware"):
        replay_events(
            detector(),
            load_result(high_pivot_bars()),
            (datetime(2026, 7, 1, 1, 0),),
        )


def test_replay_rejects_unsorted_or_duplicate_schedule() -> None:
    source = load_result(high_pivot_bars())
    first = source.bars[0].available_time
    with pytest.raises(SwingInputError, match="strictly ascending"):
        replay_events(detector(), source, (first, first))


def test_sparse_replay_schedule_cannot_claim_late_first_appearance() -> None:
    source = load_result(high_pivot_bars())
    after_confirm = source.bars[-1].available_time + timedelta(hours=1)
    with pytest.raises(SwingDetectionError, match="first appearance"):
        replay_events(detector(), source, (after_confirm,))


def test_replay_events_are_sorted_by_confirm_time_and_candidate_id() -> None:
    bars = bars_from_extrema(
        ("20", "40", "21", "50", "22"),
        ("10", "11", "9", "12", "8"),
    )
    events = replay_events(detector(), load_result(bars))
    signatures = [
        (event.first_seen_time, event.candidate.candidate_id) for event in events
    ]
    assert signatures == sorted(signatures)
