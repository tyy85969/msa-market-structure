from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from decimal import Decimal

import pytest

from msa.data import Timeframe
from msa.domain import (
    BoundarySide, LifecycleState, MarketRole, StructureObjectKind,
)
from msa.research.lifecycle import (
    LifecycleConfig, LifecycleConfigurationError, LifecycleInput,
    LifecycleEngineError, LifecycleEventType, LifecycleInputError,
    LifecycleSerializationError, RetirementReason,
)
from tests.research.lifecycle.fixtures import (
    T1, T2, T3, T4, T5, bar, config, engine, lifecycle_input, load_result,
    subject, upper_break_bars,
)


def test_config_round_trip_and_frozen() -> None:
    value = config()
    assert LifecycleConfig.from_dict(value.to_dict()) == value
    with pytest.raises(FrozenInstanceError):
        value.strict = False  # type: ignore[misc]


@pytest.mark.parametrize("field", [
    "test_tolerance", "break_buffer", "flip_tolerance",
    "flip_confirmation_distance", "failed_break_retirement_buffer",
])
def test_config_rejects_float_decimal(field: str) -> None:
    with pytest.raises(LifecycleConfigurationError, match="Decimal"):
        config(**{field: 1.0})


@pytest.mark.parametrize("field", [
    "test_tolerance", "break_buffer", "flip_tolerance",
    "flip_confirmation_distance", "failed_break_retirement_buffer",
])
def test_config_rejects_negative_or_nonfinite_decimal(field: str) -> None:
    with pytest.raises(LifecycleConfigurationError):
        config(**{field: Decimal("-0.1")})
    with pytest.raises(LifecycleConfigurationError):
        config(**{field: Decimal("NaN")})


@pytest.mark.parametrize(("field", "value"), [
    ("weakening_test_count", 1), ("minimum_test_separation_bars", 0),
    ("flip_horizon_bars", 0),
])
def test_config_rejects_invalid_integer_limits(field: str, value: int) -> None:
    with pytest.raises(LifecycleConfigurationError, match=field):
        config(**{field: value})


def test_strict_false_and_implicit_timeframe_are_rejected() -> None:
    with pytest.raises(LifecycleConfigurationError, match="strict must be True"):
        config(strict=False)
    with pytest.raises(LifecycleConfigurationError, match="observation_timeframe"):
        config(observation_timeframe="H1")


def test_config_unknown_schema_field_and_numeric_decimal_fail_closed() -> None:
    payload = config().to_dict()
    payload["future"] = True
    with pytest.raises(LifecycleSerializationError, match="unknown fields"):
        LifecycleConfig.from_dict(payload)
    del payload["future"]
    payload["schema_version"] = 2
    with pytest.raises(LifecycleSerializationError, match="schema_version"):
        LifecycleConfig.from_dict(payload)
    payload = config().to_dict()
    payload["test_tolerance"] = 1
    with pytest.raises(LifecycleSerializationError, match="Decimal string"):
        LifecycleConfig.from_dict(payload)


def test_candidate_and_cluster_refs_are_valid_inputs() -> None:
    value = lifecycle_input((bar(0),), (
        subject("candidate", kind=StructureObjectKind.LEVEL_CANDIDATE),
        subject("cluster", kind=StructureObjectKind.STRUCTURE_CLUSTER),
    ))
    assert len(value.subjects) == 2


def test_input_round_trip_is_exact_and_ordered() -> None:
    value = lifecycle_input((bar(0), bar(1)))
    assert LifecycleInput.from_dict(value.to_dict()) == value
    payload = value.to_dict()
    payload["subjects"] = tuple(payload["subjects"])
    with pytest.raises(LifecycleSerializationError, match="ordered list"):
        LifecycleInput.from_dict(payload)


def test_input_rejects_empty_duplicate_mixed_or_post_lifecycle_subjects() -> None:
    with pytest.raises(LifecycleInputError, match="non-empty"):
        LifecycleInput(load_result((bar(0),)), ())
    with pytest.raises(LifecycleInputError, match="unique"):
        LifecycleInput(load_result((bar(0),)), (subject("same"), subject("same")))
    with pytest.raises(LifecycleInputError, match="exactly CONFIRMED"):
        lifecycle_input((bar(0),), (subject(lifecycle_state=LifecycleState.FRESH),))


@pytest.mark.parametrize(("side", "role"), [
    (BoundarySide.UPPER, MarketRole.SUPPORT),
    (BoundarySide.LOWER, MarketRole.RESISTANCE),
])
def test_input_rejects_invalid_side_role(side: BoundarySide, role: MarketRole) -> None:
    with pytest.raises(LifecycleInputError, match="side/role"):
        lifecycle_input((bar(0),), (subject(side=side, role=role),))


def test_engine_rejects_mixed_symbol_timeframe_and_non_strict_source() -> None:
    from tests.research.lifecycle.fixtures import engine, source_config
    with pytest.raises(LifecycleInputError, match="symbol"):
        engine().build_batch(lifecycle_input((bar(0),), (subject(symbol="EURUSD"),)))
    wrong = LifecycleInput(load_result((bar(0),), config=source_config(timeframe=Timeframe.M30)), (subject(),))
    with pytest.raises(LifecycleInputError, match="timeframe"):
        engine().build_batch(wrong)
    report_only = LifecycleInput(load_result((bar(0),), config=source_config(strict=False)), (subject(),))
    with pytest.raises(LifecycleInputError, match="strict=True"):
        engine().build_batch(report_only)


def test_input_objects_are_not_modified() -> None:
    bars = (bar(0), bar(1))
    refs = (subject(),)
    before_bars = tuple(item.to_dict() for item in bars)
    before_refs = tuple(item.to_dict() for item in refs)
    from tests.research.lifecycle.fixtures import engine
    engine().build_batch(lifecycle_input(bars, refs))
    assert tuple(item.to_dict() for item in bars) == before_bars
    assert tuple(item.to_dict() for item in refs) == before_refs


def test_naive_subject_confirm_time_is_rejected_upstream() -> None:
    payload = subject().to_dict()
    payload["confirm_time"] = datetime(2026, 7, 1, 1).isoformat()
    from msa.domain import BoundaryRef, DomainSerializationError
    with pytest.raises(DomainSerializationError):
        BoundaryRef.from_dict(payload)


def _rebuild_snapshot(snapshot, *, states=None, events=None, as_of_time=None):
    rebuilt_states = snapshot.states if states is None else tuple(states)
    rebuilt_events = snapshot.events if events is None else tuple(events)
    target_time = snapshot.as_of_time if as_of_time is None else as_of_time
    if target_time != snapshot.as_of_time:
        rebuilt_states = tuple(
            replace(state, as_of_time=target_time) for state in rebuilt_states
        )
    report = replace(
        snapshot.report,
        visible_subject_count=len(rebuilt_states),
        fresh_count=sum(
            state.lifecycle_state is LifecycleState.FRESH for state in rebuilt_states
        ),
        tested_count=sum(
            state.lifecycle_state is LifecycleState.TESTED for state in rebuilt_states
        ),
        weakened_count=sum(
            state.lifecycle_state is LifecycleState.WEAKENED for state in rebuilt_states
        ),
        broken_count=sum(
            state.lifecycle_state is LifecycleState.BROKEN for state in rebuilt_states
        ),
        flipped_count=sum(
            state.lifecycle_state is LifecycleState.FLIPPED for state in rebuilt_states
        ),
        retired_count=sum(
            state.lifecycle_state is LifecycleState.RETIRED for state in rebuilt_states
        ),
        test_event_count=sum(
            event.event_type is LifecycleEventType.TEST for event in rebuilt_events
        ),
        break_event_count=sum(
            event.event_type is LifecycleEventType.BROKEN for event in rebuilt_events
        ),
        flip_touch_event_count=sum(
            event.event_type is LifecycleEventType.FLIP_TOUCH
            for event in rebuilt_events
        ),
        flip_event_count=sum(
            event.event_type is LifecycleEventType.FLIPPED for event in rebuilt_events
        ),
        retirement_event_count=sum(
            event.event_type is LifecycleEventType.RETIRED for event in rebuilt_events
        ),
        earliest_event_confirm_time=(
            min(event.event_confirm_time for event in rebuilt_events)
            if rebuilt_events else None
        ),
        latest_event_confirm_time=(
            max(event.event_confirm_time for event in rebuilt_events)
            if rebuilt_events else None
        ),
    )
    return replace(
        snapshot,
        as_of_time=target_time,
        states=rebuilt_states,
        events=rebuilt_events,
        report=report,
    )


def _state_with_event_ids(state, event_ids):
    provenance = replace(
        state.provenance,
        parent_object_ids=(state.subject_ref.object_id, event_ids[-1]),
    )
    return replace(state, event_ids=tuple(event_ids), provenance=provenance)


def test_snapshot_rejects_ghost_and_non_immediate_prior_event_ids() -> None:
    snapshot = engine().build_batch(lifecycle_input(upper_break_bars())).final_snapshot
    events = list(snapshot.events)
    for prior in (("ghost-event",), (events[0].event_id,)):
        changed = events[:-1] + [replace(events[-1], prior_event_ids=prior)]
        with pytest.raises(LifecycleEngineError, match="immediate predecessor"):
            _rebuild_snapshot(snapshot, events=changed)


def test_snapshot_rejects_from_state_disconnected_from_previous_event() -> None:
    snapshot = engine().build_batch(lifecycle_input((
        bar(0),
        bar(1, open="100", high="101", low="99", close="100"),
        bar(2, open="101", high="103", low="100", close="102"),
    ))).final_snapshot
    events = list(snapshot.events)
    events[-1] = replace(events[-1], from_state=LifecycleState.FRESH)
    with pytest.raises(LifecycleEngineError, match="previous event to_state"):
        _rebuild_snapshot(snapshot, events=events)


def test_snapshot_rejects_missing_or_duplicate_activation() -> None:
    flipped = engine().build_batch(lifecycle_input(upper_break_bars())).final_snapshot
    events = flipped.events[1:]
    state = _state_with_event_ids(flipped.states[0], tuple(
        event.event_id for event in events
    ))
    with pytest.raises(LifecycleEngineError, match="begin with its exact ACTIVATED"):
        _rebuild_snapshot(flipped, states=(state,), events=events)

    activated = engine().build_as_of(lifecycle_input((bar(0),)), T1)
    first = activated.events[0]
    duplicate = replace(
        first,
        event_id="zz-duplicate-activation",
        provenance=replace(
            first.provenance,
            source_object_id="zz-duplicate-activation",
        ),
    )
    duplicate_events = activated.events + (duplicate,)
    duplicate_state = _state_with_event_ids(
        activated.states[0], tuple(event.event_id for event in duplicate_events)
    )
    with pytest.raises(LifecycleEngineError, match="only one ACTIVATED"):
        _rebuild_snapshot(
            activated, states=(duplicate_state,), events=duplicate_events
        )


@pytest.mark.parametrize("terminal", ["FLIPPED", "RETIRED"])
def test_snapshot_rejects_events_after_terminal_state(terminal: str) -> None:
    if terminal == "FLIPPED":
        snapshot = engine().build_batch(
            lifecycle_input(upper_break_bars())
        ).final_snapshot
    else:
        snapshot = engine().build_batch(lifecycle_input((
            bar(0),
            bar(1, open="101", high="103", low="100", close="102"),
            bar(2, open="100", high="100", low="98", close="99"),
        ))).final_snapshot
    terminal_event = snapshot.events[-1]
    template = next(
        event
        for event in snapshot.events
        if event.event_type is LifecycleEventType.BROKEN
    )
    extra = replace(
        template,
        event_id=f"zz-after-{terminal.lower()}",
        event_type=LifecycleEventType.FLIP_TOUCH,
        from_state=LifecycleState.BROKEN,
        to_state=LifecycleState.BROKEN,
        event_origin_time=T4,
        event_confirm_time=T5,
        first_seen_time=T5,
        prior_event_ids=(terminal_event.event_id,),
        provenance=replace(
            template.provenance,
            source_object_id=f"zz-after-{terminal.lower()}",
            parent_object_ids=(template.subject_id, terminal_event.event_id),
        ),
    )
    events = snapshot.events + (extra,)
    state = _state_with_event_ids(
        replace(snapshot.states[0], as_of_time=T5),
        tuple(event.event_id for event in events),
    )
    with pytest.raises(LifecycleEngineError, match="terminal lifecycle"):
        _rebuild_snapshot(
            snapshot, states=(state,), events=events, as_of_time=T5
        )


def test_snapshot_rejects_test_count_jump_and_nonincrementing_test() -> None:
    one_test = engine().build_as_of(lifecycle_input((
        bar(0), bar(1, open="100", high="101", low="99", close="100"),
    )), T2)
    jumped_event = replace(one_test.events[-1], test_count=3)
    jumped_state = replace(one_test.states[0], test_count=3)
    with pytest.raises(LifecycleEngineError, match="test_count progression"):
        _rebuild_snapshot(
            one_test,
            states=(jumped_state,),
            events=one_test.events[:-1] + (jumped_event,),
        )

    two_tests = engine(weakening_test_count=3).build_as_of(lifecycle_input((
        bar(0),
        bar(1, open="100", high="101", low="99", close="100"),
        bar(2, open="100", high="101", low="99", close="100"),
    )), T3)
    events = list(two_tests.events)
    events[-1] = replace(events[-1], test_count=1)
    state = replace(two_tests.states[0], test_count=1)
    with pytest.raises(LifecycleEngineError, match="test_count progression"):
        _rebuild_snapshot(two_tests, states=(state,), events=events)


def test_snapshot_rejects_break_count_increase() -> None:
    snapshot = engine().build_batch(lifecycle_input((
        bar(0),
        bar(1, open="100", high="101", low="99", close="100"),
        bar(2, open="101", high="103", low="100", close="102"),
    ))).final_snapshot
    events = list(snapshot.events)
    events[-1] = replace(events[-1], test_count=2)
    state = replace(snapshot.states[0], test_count=2)
    with pytest.raises(LifecycleEngineError, match="test_count progression"):
        _rebuild_snapshot(snapshot, states=(state,), events=events)


def test_snapshot_enforces_weakening_threshold_progression() -> None:
    weakened = engine().build_batch(lifecycle_input((
        bar(0),
        bar(1, open="100", high="101", low="99", close="100"),
        bar(2, open="100", high="101", low="99", close="100"),
    ))).final_snapshot
    with pytest.raises(LifecycleEngineError, match="configured threshold"):
        replace(
            weakened,
            config_snapshot=config(weakening_test_count=3),
        )

    events = list(weakened.events)
    events[-1] = replace(
        events[-1],
        event_type=LifecycleEventType.TEST,
        to_state=LifecycleState.TESTED,
    )
    state = replace(weakened.states[0], lifecycle_state=LifecycleState.TESTED)
    with pytest.raises(LifecycleEngineError, match="cannot persist"):
        _rebuild_snapshot(weakened, states=(state,), events=events)


@pytest.mark.parametrize("event_kind", ["BROKEN", "FLIPPED"])
def test_snapshot_enforces_event_effective_side_and_role(event_kind: str) -> None:
    snapshot = engine().build_batch(
        lifecycle_input(upper_break_bars())
    ).final_snapshot
    events = list(snapshot.events)
    index = next(
        i for i, event in enumerate(events) if event.event_type.value == event_kind
    )
    event = events[index]
    if event_kind == "BROKEN":
        side, role = BoundarySide.LOWER, MarketRole.SUPPORT
    else:
        side, role = BoundarySide.UPPER, MarketRole.RESISTANCE
    events[index] = replace(
        event, effective_boundary_side=side, effective_market_role=role
    )
    with pytest.raises(LifecycleEngineError, match="contradicts subject_ref"):
        _rebuild_snapshot(snapshot, events=events)


def test_snapshot_rejects_final_state_event_mismatches() -> None:
    tested = engine().build_as_of(lifecycle_input((
        bar(0), bar(1, open="100", high="101", low="99", close="100"),
    )), T2)
    cases = (
        replace(tested.states[0], lifecycle_state=LifecycleState.WEAKENED),
        replace(
            tested.states[0],
            state_confirm_time=T3,
            last_test_confirm_time=T3,
            as_of_time=T3,
        ),
        replace(tested.states[0], test_count=2),
        replace(tested.states[0], last_test_bar_key="wrong-bar-key"),
    )
    matches = (
        "lifecycle_state", "state_confirm_time", "state test_count", "last-test facts",
    )
    for changed, match in zip(cases, matches):
        target_time = changed.as_of_time
        with pytest.raises(LifecycleEngineError, match=match):
            _rebuild_snapshot(tested, states=(changed,), as_of_time=target_time)


def test_snapshot_rejects_missing_or_mismatched_break_event_facts() -> None:
    broken = engine().build_as_of(lifecycle_input((
        bar(0), bar(1, open="101", high="103", low="100", close="102"),
    )), T2)
    activation_only = (broken.events[0],)
    state_without_event = _state_with_event_ids(
        broken.states[0], (broken.events[0].event_id,)
    )
    with pytest.raises(LifecycleEngineError):
        _rebuild_snapshot(
            broken, states=(state_without_event,), events=activation_only
        )
    changed = replace(broken.states[0], break_close=Decimal("999"))
    with pytest.raises(LifecycleEngineError, match="Break facts contradict"):
        _rebuild_snapshot(broken, states=(changed,))


def test_snapshot_rejects_missing_flip_touch_flip_and_retirement_events() -> None:
    touch_snapshot = engine().build_as_of(
        lifecycle_input(upper_break_bars()), T3
    )
    touch_events = tuple(
        event
        for event in touch_snapshot.events
        if event.event_type is not LifecycleEventType.FLIP_TOUCH
    )
    touch_state = replace(
        touch_snapshot.states[0],
        state_confirm_time=T2,
        flip_touch_confirm_time=T2,
        event_ids=tuple(event.event_id for event in touch_events),
        provenance=replace(
            touch_snapshot.states[0].provenance,
            parent_object_ids=(
                touch_snapshot.states[0].subject_ref.object_id,
                touch_events[-1].event_id,
            ),
        ),
    )
    with pytest.raises(LifecycleEngineError, match="flip-touch facts"):
        _rebuild_snapshot(
            touch_snapshot, states=(touch_state,), events=touch_events
        )

    flipped = engine().build_batch(
        lifecycle_input(upper_break_bars())
    ).final_snapshot
    without_flip = flipped.events[:-1]
    flipped_state = _state_with_event_ids(
        replace(
            flipped.states[0],
            state_confirm_time=T3,
            flipped_confirm_time=T3,
        ),
        tuple(event.event_id for event in without_flip),
    )
    with pytest.raises(LifecycleEngineError):
        _rebuild_snapshot(flipped, states=(flipped_state,), events=without_flip)

    retired = engine().build_batch(lifecycle_input((
        bar(0),
        bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="100", high="100", low="98", close="99"),
    ))).final_snapshot
    without_retired = retired.events[:-1]
    retired_state = _state_with_event_ids(
        replace(
            retired.states[0],
            state_confirm_time=T2,
            retired_time=T2,
            retired_confirm_time=T2,
        ),
        tuple(event.event_id for event in without_retired),
    )
    with pytest.raises(LifecycleEngineError):
        _rebuild_snapshot(
            retired, states=(retired_state,), events=without_retired
        )


def test_snapshot_rejects_retirement_reason_and_terminal_event_conflicts() -> None:
    retired = engine().build_batch(lifecycle_input((
        bar(0),
        bar(1, open="101", high="103", low="100", close="102"),
        bar(2, open="100", high="100", low="98", close="99"),
    ))).final_snapshot
    changed = replace(
        retired.states[0],
        retirement_reason=RetirementReason.FLIP_HORIZON_EXPIRED,
    )
    with pytest.raises(LifecycleEngineError, match="retirement facts contradict"):
        _rebuild_snapshot(retired, states=(changed,))

    flipped = engine().build_batch(
        lifecycle_input(upper_break_bars())
    ).final_snapshot
    template = retired.events[-1]
    extra = replace(
        template,
        event_id="zz-retired-after-flip",
        subject_id=flipped.states[0].subject_ref.object_id,
        event_origin_time=T5,
        event_confirm_time=T5,
        first_seen_time=T5,
        prior_event_ids=(flipped.events[-1].event_id,),
        provenance=replace(
            template.provenance,
            source_object_id="zz-retired-after-flip",
            parent_object_ids=(
                flipped.states[0].subject_ref.object_id,
                flipped.events[-1].event_id,
            ),
        ),
    )
    events = flipped.events + (extra,)
    state = _state_with_event_ids(
        replace(flipped.states[0], as_of_time=T5),
        tuple(event.event_id for event in events),
    )
    with pytest.raises(LifecycleEngineError, match="terminal lifecycle"):
        _rebuild_snapshot(
            flipped, states=(state,), events=events, as_of_time=T5
        )


@pytest.mark.parametrize(
    ("target", "field"),
    [
        ("event", "source_object_id"),
        ("event", "policy_id"),
        ("event", "source_version"),
        ("event", "parent_object_ids"),
        ("state", "source_object_id"),
        ("state", "policy_id"),
        ("state", "source_version"),
        ("state", "parent_object_ids"),
    ],
)
def test_snapshot_rejects_inconsistent_provenance(target: str, field: str) -> None:
    snapshot = engine().build_as_of(lifecycle_input((bar(0),)), T1)
    if target == "event":
        event = snapshot.events[0]
        value = () if field == "parent_object_ids" else "wrong"
        changed = replace(
            event, provenance=replace(event.provenance, **{field: value})
        )
        states = snapshot.states
        events = (changed,)
    else:
        state = snapshot.states[0]
        value = () if field == "parent_object_ids" else "wrong"
        changed = replace(
            state, provenance=replace(state.provenance, **{field: value})
        )
        states = (changed,)
        events = snapshot.events
    with pytest.raises(LifecycleEngineError, match="provenance"):
        _rebuild_snapshot(snapshot, states=states, events=events)
