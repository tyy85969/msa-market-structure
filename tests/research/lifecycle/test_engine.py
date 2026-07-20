from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from itertools import permutations

import pytest

from msa.domain import BoundarySide, LifecycleState, MarketRole
from msa.research.lifecycle import LifecycleEventType, RetirementReason
from tests.research.lifecycle.fixtures import (
    START, T1, T2, T3, T4, T5, bar, engine, lifecycle_input, subject,
    upper_break_bars,
)


def event_types(snapshot) -> list[LifecycleEventType]:
    return [item.event_type for item in snapshot.events]


def test_confirm_time_not_origin_activates_subject_and_is_atomic() -> None:
    refs = (subject("b"), subject("a"))
    data = lifecycle_input((bar(0),), refs)
    before = engine().build_as_of(data, T1 - timedelta(microseconds=1))
    at_time = engine().build_as_of(data, T1)
    assert before.states == () and before.events == ()
    assert [item.subject_ref.object_id for item in at_time.states] == ["a", "b"]
    assert all(item.lifecycle_state is LifecycleState.FRESH for item in at_time.states)
    assert all(item.event_type is LifecycleEventType.ACTIVATED for item in at_time.events)
    assert all(item.first_seen_time == T1 for item in at_time.events)


def test_confirmation_bar_is_not_monitored_but_next_bar_can_test() -> None:
    bars = (
        bar(0, open="100", high="104", low="99", close="102"),
        bar(1, open="100", high="101", low="99", close="100"),
    )
    snapshot = engine().build_as_of(lifecycle_input(bars), T2)
    assert event_types(snapshot) == [LifecycleEventType.ACTIVATED, LifecycleEventType.TEST]
    assert snapshot.states[0].test_count == 1
    assert snapshot.events[-1].event_origin_time == T1


def test_first_touch_tested_separation_and_weakening() -> None:
    bars = (
        bar(0),
        bar(1, open="100", high="101", low="99", close="100"),
        bar(2, open="100", high="101", low="99", close="100"),
        bar(3, open="100", high="101", low="99", close="100"),
    )
    separated = engine(minimum_test_separation_bars=2).build_batch(lifecycle_input(bars)).final_snapshot
    assert event_types(separated) == [LifecycleEventType.ACTIVATED, LifecycleEventType.TEST, LifecycleEventType.WEAKENED]
    assert separated.states[0].test_count == 2
    assert separated.states[0].lifecycle_state is LifecycleState.WEAKENED
    continued = engine().build_batch(lifecycle_input(bars)).final_snapshot
    assert event_types(continued)[-1] is LifecycleEventType.TEST
    assert continued.states[0].test_count == 3
    assert continued.states[0].lifecycle_state is LifecycleState.WEAKENED


def test_test_confirm_time_uses_prefix_maximum() -> None:
    bars = (
        replace(bar(0), available_time=T3),
        bar(1, open="100", high="101", low="99", close="100", available_time=T2),
    )
    snapshot = engine().build_as_of(lifecycle_input(bars), T3)
    test_event = snapshot.events[-1]
    assert test_event.event_origin_time == T1
    assert test_event.event_confirm_time == T3


def test_delayed_prefix_keeps_multiple_same_confirm_events_in_causal_order() -> None:
    bars = (
        replace(bar(0), available_time=T4),
        bar(1, open="100", high="101", low="99", close="100", available_time=T2),
        bar(2, open="100", high="101", low="99", close="100", available_time=T3),
        bar(3, open="100", high="101", low="99", close="100", available_time=T4),
    )
    snapshot = engine().build_as_of(lifecycle_input(bars), T4)
    same_time = [item for item in snapshot.events if item.event_confirm_time == T4]
    assert [item.event_type for item in same_time] == [
        LifecycleEventType.TEST,
        LifecycleEventType.WEAKENED,
        LifecycleEventType.TEST,
    ]
    assert snapshot.states[0].event_ids == tuple(
        item.event_id for item in snapshot.events
    )


def test_break_precedes_same_bar_test_and_does_not_increment_count() -> None:
    bars = (bar(0), bar(1, open="100", high="104", low="99", close="102"))
    snapshot = engine().build_batch(lifecycle_input(bars)).final_snapshot
    assert event_types(snapshot) == [LifecycleEventType.ACTIVATED, LifecycleEventType.BROKEN]
    state = snapshot.states[0]
    assert state.test_count == 0 and state.lifecycle_state is LifecycleState.BROKEN
    assert state.break_close == Decimal("102")
    assert state.break_threshold == Decimal("102")


@pytest.mark.parametrize("prior_tests", [0, 1, 2])
def test_upper_break_from_fresh_tested_or_weakened(prior_tests: int) -> None:
    bars = [bar(0)]
    for index in range(1, prior_tests + 1):
        bars.append(bar(index, open="100", high="101", low="99", close="100"))
    index = prior_tests + 1
    bars.append(bar(index, open="101", high="104", low="100", close="102"))
    snapshot = engine().build_batch(lifecycle_input(tuple(bars))).final_snapshot
    assert snapshot.states[0].lifecycle_state is LifecycleState.BROKEN
    assert snapshot.states[0].test_count == prior_tests


def test_wick_only_does_not_break_and_threshold_equality_does() -> None:
    wick = engine().build_batch(lifecycle_input((bar(0), bar(1, open="100", high="104", low="99", close="101")))).final_snapshot
    assert LifecycleEventType.BROKEN not in event_types(wick)
    equal = engine().build_batch(lifecycle_input((bar(0), bar(1, open="101", high="103", low="100", close="102")))).final_snapshot
    assert equal.states[0].lifecycle_state is LifecycleState.BROKEN


def test_lower_close_break_is_symmetric() -> None:
    bars = (bar(0, open="90", high="92", low="89", close="90"),
            bar(1, open="90", high="90", low="88", close="89"))
    snapshot = engine().build_batch(lifecycle_input(bars, (subject("lower", side=BoundarySide.LOWER),))).final_snapshot
    assert snapshot.states[0].break_threshold == Decimal("89")
    assert snapshot.states[0].lifecycle_state is LifecycleState.BROKEN


def test_break_bar_cannot_flip_touch_and_touch_cannot_confirm_same_bar() -> None:
    snapshot = engine().build_as_of(lifecycle_input(upper_break_bars()), T3)
    assert event_types(snapshot) == [LifecycleEventType.ACTIVATED, LifecycleEventType.BROKEN, LifecycleEventType.FLIP_TOUCH]
    assert snapshot.states[0].lifecycle_state is LifecycleState.BROKEN
    assert snapshot.states[0].flip_touch_time == T2


def test_upper_flip_reverses_effective_side_and_role() -> None:
    snapshot = engine().build_batch(lifecycle_input(upper_break_bars())).final_snapshot
    state = snapshot.states[0]
    assert state.lifecycle_state is LifecycleState.FLIPPED
    assert state.effective_boundary_side is BoundarySide.LOWER
    assert state.effective_market_role is MarketRole.SUPPORT
    boundary = state.to_boundary_ref()
    assert boundary.lifecycle_state is LifecycleState.FLIPPED
    assert boundary.confirm_time == state.state_confirm_time
    assert state.subject_ref.lifecycle_state is LifecycleState.CONFIRMED


def test_lower_flip_reverses_effective_mapping() -> None:
    bars = (
        bar(0, open="90", high="92", low="89", close="90"),
        bar(1, open="90", high="90", low="88", close="89"),
        bar(2, open="90", high="91", low="89", close="90"),
        bar(3, open="89", high="89", low="87", close="88"),
    )
    snapshot = engine().build_batch(lifecycle_input(bars, (subject("lower", side=BoundarySide.LOWER),))).final_snapshot
    state = snapshot.states[0]
    assert state.lifecycle_state is LifecycleState.FLIPPED
    assert (state.effective_boundary_side, state.effective_market_role) == (BoundarySide.UPPER, MarketRole.RESISTANCE)


def test_exact_horizon_can_flip() -> None:
    bars = (
        bar(0), bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="101", high="102", low="100", close="101"),
        bar(3, open="102", high="102", low="102", close="102"),
        bar(4, open="103", high="104", low="103", close="103"),
    )
    state = engine().build_batch(lifecycle_input(bars)).final_snapshot.states[0]
    assert state.lifecycle_state is LifecycleState.FLIPPED
    assert state.flipped_time == T4


def test_horizon_expiry_and_failed_break_retire_with_reasons() -> None:
    horizon = (
        bar(0), bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="103", high="104", low="103", close="103"),
        bar(3, open="103", high="104", low="103", close="103"),
        bar(4, open="103", high="104", low="103", close="103"),
    )
    hstate = engine().build_batch(lifecycle_input(horizon)).final_snapshot.states[0]
    assert hstate.lifecycle_state is LifecycleState.RETIRED
    assert hstate.retirement_reason is RetirementReason.FLIP_HORIZON_EXPIRED
    failed = (
        bar(0), bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="100", high="100", low="98", close="99"),
    )
    fstate = engine().build_batch(lifecycle_input(failed)).final_snapshot.states[0]
    assert fstate.retirement_reason is RetirementReason.FAILED_BREAK


def test_terminal_states_produce_no_later_events() -> None:
    base = upper_break_bars()
    future = base + (bar(4, open="100", high="101", low="80", close="85"),)
    old = engine().build_batch(lifecycle_input(base)).events
    new = engine().build_batch(lifecycle_input(future)).events
    assert new == old


def test_report_counts_and_provenance_are_bounded() -> None:
    snapshot = engine().build_batch(lifecycle_input(upper_break_bars())).final_snapshot
    report = snapshot.report
    assert report.flipped_count == 1 and report.break_event_count == 1
    assert report.flip_touch_event_count == 1 and report.flip_event_count == 1
    assert report.processed_bar_count == 4
    assert all(len(item.provenance.parent_object_ids) <= 2 for item in snapshot.events)
    assert len(snapshot.states[0].provenance.parent_object_ids) == 2


def test_input_permutation_does_not_change_payload() -> None:
    refs = (subject("a"), subject("b"), subject("c"))
    baseline = engine().build_batch(lifecycle_input((bar(0), bar(1)), refs)).to_dict()
    for order in permutations(refs):
        assert engine().build_batch(lifecycle_input((bar(0), bar(1)), tuple(order))).to_dict() == baseline
