from decimal import Decimal
from dataclasses import replace
from itertools import permutations

import pytest

from msa.data import Timeframe
from msa.domain import BoundarySide, LifecycleState, MarketRole, ScaleDescriptor
from msa.research.timeframe_state import (
    CROSSED_PAIR_OLDER_SIDE,
    TimeframeStateEngineError,
)
from tests.research.timeframe_state.fixtures import (
    PRIMARY,
    START,
    T1,
    T2,
    T3,
    bar,
    base_pair,
    subject,
    timeframe_engine,
    timeframe_input,
)


def test_fresh_is_candidate_but_not_confirmed() -> None:
    snapshot = timeframe_engine().build_as_of(
        timeframe_input(base_pair(), (bar(0),)), START
    )
    assert snapshot.state.candidate_upper_boundary is not None
    assert snapshot.state.candidate_lower_boundary is not None
    assert snapshot.state.confirmed_upper_boundary is None
    assert snapshot.state.confirmed_lower_boundary is None


@pytest.mark.parametrize("bar_count", [1, 2])
def test_tested_and_weakened_enter_candidate_and_confirmed(bar_count: int) -> None:
    bars = tuple(bar(index) for index in range(bar_count))
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), bars)
    ).final_snapshot
    expected = LifecycleState.TESTED if bar_count == 1 else LifecycleState.WEAKENED
    assert snapshot.state.candidate_upper_boundary.lifecycle_state is expected
    assert snapshot.state.confirmed_upper_boundary.lifecycle_state is expected


def test_broken_is_excluded_from_both_groups() -> None:
    upper, lower = base_pair()
    data = timeframe_input(
        (upper, lower),
        (
            bar(0),
            bar(1, high="113", low="100", close="112"),
        ),
    )
    snapshot = timeframe_engine().build_as_of(data, T2)
    assert snapshot.state.candidate_upper_boundary is None
    assert snapshot.state.confirmed_upper_boundary is None
    assert snapshot.explanation.excluded_broken_ids == ("upper-old",)


def test_retired_is_excluded_from_both_groups() -> None:
    upper = subject("upper", BoundarySide.UPPER, "110", "111")
    data = timeframe_input(
        (upper,),
        (
            bar(0, high="113", low="110", close="112"),
            bar(1, high="110", low="108", close="109"),
        ),
    )
    snapshot = timeframe_engine().build_as_of(data, T2)
    assert snapshot.state.candidate_upper_boundary is None
    assert snapshot.explanation.excluded_retired_ids == ("upper",)


def test_flipped_uses_effective_lower_support_mapping_from_to_boundary_ref() -> None:
    upper = subject("flip-upper", BoundarySide.UPPER, "110", "111")
    data = timeframe_input(
        (upper,),
        (
            bar(0, high="113", low="110", close="112"),
            bar(1, high="111", low="110", close="110"),
            bar(2, high="113", low="112", close="112"),
        ),
    )
    snapshot = timeframe_engine().build_as_of(data, T3)
    boundary = snapshot.state.confirmed_lower_boundary
    assert boundary is not None
    assert boundary.boundary_side is BoundarySide.LOWER
    assert boundary.market_role is MarketRole.SUPPORT
    assert boundary.lifecycle_state is LifecycleState.FLIPPED
    assert boundary.confirm_time == T3


def test_latest_state_confirm_time_wins_per_side() -> None:
    subjects = (
        subject("older", BoundarySide.UPPER, "110", "111"),
        subject("newer", BoundarySide.UPPER, "120", "121", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (bar(0, high="111", low="100"), bar(1, high="121", low="100")),
    )
    snapshot = timeframe_engine().build_as_of(data, T2)
    assert snapshot.state.confirmed_upper_boundary is not None
    assert snapshot.explanation.raw_confirmed_upper_state_id is not None
    selected = snapshot.state.confirmed_upper_boundary
    assert selected.price_range.low == 120


def test_structural_confirm_time_breaks_equal_state_confirm_time() -> None:
    subjects = (
        subject("early", BoundarySide.UPPER, "110", "111"),
        subject("late", BoundarySide.UPPER, "120", "121", confirm_time=T1),
    )
    data = timeframe_input(
        subjects,
        (
            bar(0, high="100", low="100"),
            bar(1, high="121", low="100"),
        ),
    )
    snapshot = timeframe_engine().build_as_of(data, T2)
    assert snapshot.state.confirmed_upper_boundary.price_range.low == 120


def test_subject_id_breaks_equal_time_tie() -> None:
    subjects = (
        subject("a-upper", BoundarySide.UPPER, "110", "111"),
        subject("z-upper", BoundarySide.UPPER, "120", "121"),
    )
    data = timeframe_input(subjects, (bar(0, high="121", low="100"),))
    snapshot = timeframe_engine().build_as_of(data, T1)
    assert snapshot.state.confirmed_upper_boundary.price_range.low == 120


def test_state_id_is_the_final_public_key_tie_break() -> None:
    from msa.research.timeframe_state import BoundarySelectionKey

    left = BoundarySelectionKey(T1, START, "same", "a-state")
    right = BoundarySelectionKey(T1, START, "same", "z-state")
    assert right.comparison_tuple > left.comparison_tuple


def test_crossed_pair_keeps_newer_side_and_does_not_fallback() -> None:
    subjects = (
        subject("a-compatible-upper", BoundarySide.UPPER, "130", "131"),
        subject("y-raw-upper", BoundarySide.UPPER, "110", "111"),
        subject("z-raw-lower", BoundarySide.LOWER, "120", "121"),
    )
    data = timeframe_input(
        subjects,
        (bar(0, high="131", low="110", close="115"),),
        break_buffer=Decimal("100"),
    )
    snapshot = timeframe_engine().build_as_of(data, T1)
    assert snapshot.state.confirmed_upper_boundary is None
    assert snapshot.state.confirmed_lower_boundary is not None
    explanation = snapshot.explanation
    assert explanation.confirmed_crossing_conflict is True
    assert explanation.confirmed_dropped_reason == CROSSED_PAIR_OLDER_SIDE
    assert explanation.raw_confirmed_upper_boundary_id is not None
    assert explanation.confirmed_dropped_boundary_id == explanation.raw_confirmed_upper_boundary_id


def test_candidate_and_confirmed_crossing_are_resolved_independently() -> None:
    fresh_upper = subject(
        "zz-fresh-upper",
        BoundarySide.UPPER,
        "100",
        "101",
        confirm_time=T1,
    )
    tested_lower = subject("aa-tested-lower", BoundarySide.LOWER, "105", "106")
    data = timeframe_input(
        (fresh_upper, tested_lower),
        (bar(0, high="106", low="105", close="105"),),
    )
    snapshot = timeframe_engine().build_as_of(data, T1)
    assert snapshot.report.candidate_pair_crossing_conflict is True
    assert snapshot.report.confirmed_pair_crossing_conflict is False
    assert snapshot.state.confirmed_lower_boundary is not None


def test_other_timeframe_and_scale_are_ignored_without_error() -> None:
    target = base_pair()
    other = (
        subject(
            "other-timeframe",
            BoundarySide.UPPER,
            "200",
            "201",
            timeframe=Timeframe.H2,
        ),
        subject(
            "other-scale",
            BoundarySide.LOWER,
            "1",
            "2",
            scale=ScaleDescriptor("secondary", 2),
        ),
    )
    base = timeframe_engine().build_batch(
        timeframe_input(target, (bar(0),))
    ).to_dict()
    mixed = timeframe_engine().build_batch(
        timeframe_input(target + other, (bar(0),))
    ).to_dict()
    assert mixed != base
    assert mixed["final_snapshot"]["state"]["state_id"] == base["final_snapshot"]["state"]["state_id"]
    assert mixed["final_snapshot"]["state"]["direction"] == base["final_snapshot"]["state"]["direction"]
    assert len(mixed["events"]) == len(base["events"])


def test_subject_input_permutations_do_not_change_output() -> None:
    subjects = base_pair() + (
        subject("upper-alt", BoundarySide.UPPER, "120", "121"),
    )
    baseline = timeframe_engine().build_batch(
        timeframe_input(subjects, (bar(0, high="121", low="90"),))
    ).to_dict()
    for order in permutations(subjects):
        assert timeframe_engine().build_batch(
            timeframe_input(tuple(order), (bar(0, high="121", low="90"),))
        ).to_dict() == baseline


def test_incomplete_confirmed_pair_rejects_nonempty_current_pair_identity() -> None:
    upper = subject("upper", BoundarySide.UPPER, "110", "111")
    snapshot = timeframe_engine().build_batch(
        timeframe_input((upper,), (bar(0, high="110", low="100"),))
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        current_complete_pair_subject_ids=("upper", "missing-lower"),
        current_complete_pair_state_ids=("state-upper", "state-lower"),
        current_complete_pair_boundary_ids=("boundary-upper", "boundary-lower"),
        current_pair_midpoints=(Decimal("110.5"), Decimal("90.5")),
    )
    with pytest.raises(TimeframeStateEngineError, match="incomplete current"):
        replace(snapshot, explanation=forged)


def test_current_pair_subject_must_match_stable_key_subject() -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        current_complete_pair_subject_ids=("wrong-upper", "lower-old"),
    )
    with pytest.raises(TimeframeStateEngineError, match="subject IDs"):
        replace(snapshot, explanation=forged)


def test_selected_lifecycle_sets_must_be_exact_not_supersets() -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        selected_lifecycle_state_ids=(
            *snapshot.explanation.selected_lifecycle_state_ids,
            "extra-state",
        ),
    )
    with pytest.raises(TimeframeStateEngineError, match="exact selected-boundary"):
        replace(snapshot, explanation=forged)


def test_non_crossing_selected_ids_must_equal_raw_ids() -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        raw_confirmed_upper_boundary_id="different-raw-upper",
    )
    with pytest.raises(TimeframeStateEngineError, match="selected IDs must equal raw"):
        replace(snapshot, explanation=forged)


def test_raw_boundary_and_lifecycle_state_ids_must_correspond() -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        raw_confirmed_upper_state_id=(
            snapshot.explanation.raw_confirmed_lower_state_id
        ),
    )
    with pytest.raises(TimeframeStateEngineError, match="boundary ID contradicts"):
        replace(snapshot, explanation=forged)


def test_crossing_retained_and_dropped_ids_must_match_raw_pair() -> None:
    subjects = (
        subject("raw-upper", BoundarySide.UPPER, "110", "111"),
        subject("raw-lower", BoundarySide.LOWER, "120", "121"),
    )
    snapshot = timeframe_engine().build_batch(
        timeframe_input(
            subjects,
            (bar(0, high="121", low="110", close="115"),),
            break_buffer=Decimal("100"),
        )
    ).final_snapshot
    forged = replace(
        snapshot.explanation,
        confirmed_retained_boundary_id="not-selected",
    )
    with pytest.raises(TimeframeStateEngineError, match="crossing resolution"):
        replace(snapshot, explanation=forged)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("relevant_subject_ids", ("not-in-stable-keys",)),
        ("candidate_eligible_subject_ids", ("not-relevant",)),
        ("confirmed_eligible_subject_ids", ("not-candidate",)),
        ("excluded_broken_ids", ("upper-old",)),
    ],
)
def test_explanation_subject_sets_fail_closed_when_contradictory(
    field: str, value: tuple[str, ...]
) -> None:
    snapshot = timeframe_engine().build_batch(
        timeframe_input(base_pair(), (bar(0),))
    ).final_snapshot
    forged = replace(snapshot.explanation, **{field: value})
    with pytest.raises(TimeframeStateEngineError):
        replace(snapshot, explanation=forged)
