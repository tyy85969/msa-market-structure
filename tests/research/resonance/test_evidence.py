from decimal import Decimal

from msa.domain import BoundarySide, LifecycleState, MarketRole
from msa.research.resonance import ResonanceEvidenceTier

from .fixtures import (
    H4_PRIMARY,
    START,
    T1,
    T2,
    T3,
    assembler,
    bar,
    custom_bundle,
    frame_input,
    subject,
)


def _by_subject(frame):
    return {item.subject_id: item for item in frame.evidence}


def test_fresh_maps_to_candidate_once() -> None:
    frame = assembler().build_as_of(frame_input(), START)
    assert frame.evidence
    assert all(item.lifecycle_state is LifecycleState.FRESH for item in frame.evidence)
    assert all(item.tier is ResonanceEvidenceTier.CANDIDATE for item in frame.evidence)
    assert len({item.subject_id for item in frame.evidence}) == len(frame.evidence)


def test_tested_maps_to_confirmed_once() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    evidence = _by_subject(frame)
    for subject_id in ("upper-a-old", "upper-z-new", "lower-main"):
        assert evidence[subject_id].lifecycle_state is LifecycleState.TESTED
        assert evidence[subject_id].tier is ResonanceEvidenceTier.CONFIRMED
        assert evidence[subject_id].touch_count == 1


def test_weakened_maps_to_confirmed_once() -> None:
    frame = assembler().build_as_of(frame_input(), T2)
    evidence = _by_subject(frame)
    for subject_id in ("upper-a-old", "upper-z-new", "lower-main"):
        assert evidence[subject_id].lifecycle_state is LifecycleState.WEAKENED
        assert evidence[subject_id].tier is ResonanceEvidenceTier.CONFIRMED
        assert evidence[subject_id].touch_count == 2


def test_flipped_maps_to_confirmed_effective_side_and_role() -> None:
    upper = subject("flip-upper", BoundarySide.UPPER, "110", "111")
    lifecycle_bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="111", low="110", close="110"),
        bar(2, high="113", low="112", close="112"),
    )
    engine, data = custom_bundle(
        (upper,), lifecycle_bars, (H4_PRIMARY,),
        break_buffer=Decimal("1"),
    )
    evidence = engine.build_as_of(data, T3).evidence[0]
    assert evidence.lifecycle_state is LifecycleState.FLIPPED
    assert evidence.tier is ResonanceEvidenceTier.CONFIRMED
    assert evidence.boundary.boundary_side is BoundarySide.LOWER
    assert evidence.boundary.market_role is MarketRole.SUPPORT


def test_broken_and_retired_are_reported_but_not_evidence() -> None:
    upper = subject("break-upper", BoundarySide.UPPER, "110", "111")
    bars = (
        bar(-1),
        bar(0, high="113", low="110", close="112"),
        bar(1, high="110", low="108", close="109"),
    )
    engine, data = custom_bundle(
        (upper,), bars, (H4_PRIMARY,), break_buffer=Decimal("1")
    )
    broken = engine.build_as_of(data, T1)
    retired = engine.build_as_of(data, T2)
    assert broken.evidence == ()
    assert broken.excluded_broken_subject_ids == ("break-upper",)
    assert broken.report.excluded_broken_count == 1
    assert retired.evidence == ()
    assert retired.excluded_retired_subject_ids == ("break-upper",)
    assert retired.report.excluded_retired_count == 1


def test_boundary_is_exactly_lifecycle_state_to_boundary_ref() -> None:
    value = frame_input()
    selected_snapshot = value.lifecycle_history.snapshots[1]
    frame = assembler().build_as_of(value, selected_snapshot.as_of_time)
    states = {item.subject_ref.object_id: item for item in selected_snapshot.states}
    for item in frame.evidence:
        assert item.boundary == states[item.subject_id].to_boundary_ref()
        assert item.lifecycle_event_id == states[item.subject_id].event_ids[-1]
        assert item.lifecycle_state_id == states[item.subject_id].state_id


def test_source_types_families_context_direction_and_touch_provenance_are_preserved() -> None:
    value = frame_input()
    frame = assembler().build_as_of(value, T1)
    directions = {item.context: item.direction for item in frame.context_states}
    states = {
        item.subject_ref.object_id: item
        for item in value.lifecycle_history.snapshots[1].states
    }
    for item in frame.evidence:
        assert item.source_types == item.boundary.source_types
        assert item.structure_families == item.boundary.structure_families
        assert item.context.timeframe is item.boundary.timeframe
        assert item.context.scale == item.boundary.scale
        assert item.direction is directions[item.context]
        assert item.touch_count == states[item.subject_id].test_count


def test_unselected_older_effective_subject_remains_in_complete_evidence_universe() -> None:
    value = frame_input()
    timeframe_snapshot = value.timeframe_state_histories[0].snapshots[1]
    slots = (
        timeframe_snapshot.state.candidate_upper_boundary,
        timeframe_snapshot.state.candidate_lower_boundary,
        timeframe_snapshot.state.confirmed_upper_boundary,
        timeframe_snapshot.state.confirmed_lower_boundary,
    )
    lifecycle_snapshot = value.lifecycle_history.snapshots[1]
    older_state = next(
        item for item in lifecycle_snapshot.states
        if item.subject_ref.object_id == "upper-a-old"
    )
    assert older_state.to_boundary_ref() not in slots
    frame = assembler().build_as_of(value, T1)
    assert {item.subject_id for item in frame.evidence} >= {
        "upper-a-old", "upper-z-new"
    }


def test_all_effective_states_are_partitioned_exactly_once() -> None:
    value = frame_input()
    lifecycle = value.lifecycle_history.snapshots[1]
    frame = assembler().build_as_of(value, T1)
    configured = set(assembler().config.contexts)
    expected = {
        item.subject_ref.object_id
        for item in lifecycle.states
        if item.lifecycle_state
        in {LifecycleState.FRESH, LifecycleState.TESTED, LifecycleState.WEAKENED, LifecycleState.FLIPPED}
        and item.subject_ref.symbol == "XAUUSD"
        and any(
            context.timeframe is item.subject_ref.timeframe
            and context.scale == item.subject_ref.scale
            for context in configured
        )
    }
    assert {item.subject_id for item in frame.evidence} == expected
    assert len(frame.evidence) == len(expected)


def test_evidence_order_and_identity_are_input_order_invariant() -> None:
    normal = assembler().build_as_of(frame_input(), T1)
    reversed_value = assembler().build_as_of(
        frame_input(reverse_histories=True), T1
    )
    assert reversed_value.evidence == normal.evidence
    assert reversed_value.frame_id == normal.frame_id
