from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from msa.data import Timeframe, VolumeType
from msa.domain import Direction
from msa.research.resonance import (
    ReferencePriceSnapshot,
    ResonanceContextState,
    ResonanceEvidence,
    ResonanceFrame,
    ResonanceFrameEngineError,
    ResonanceFrameSerializationError,
)
from msa.research.resonance.identity import (
    _context_state_id,
    _evidence_id,
    _reference_id,
)

from .fixtures import T1, T2, assembler, frame_input


def _frame() -> ResonanceFrame:
    return assembler().build_as_of(frame_input(), T1)


def _reference_payload() -> dict[str, object]:
    return _frame().reference_price.to_dict()


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("close", "104"),
        ("open", "100.5"),
        ("high", "106.5"),
        ("low", "95.5"),
    ],
)
def test_reference_rejects_price_fact_tampering_with_retained_id(
    field_name: str, value: str
) -> None:
    payload = _reference_payload()
    payload["canonical_bar"][field_name] = value
    with pytest.raises(ResonanceFrameSerializationError, match="reference_id"):
        ReferencePriceSnapshot.from_dict(payload)


def test_reference_rejects_available_time_tampering_with_retained_id() -> None:
    payload = _reference_payload()
    payload["canonical_bar"]["available_time"] = (
        T1 + timedelta(microseconds=1)
    ).isoformat()
    with pytest.raises(ResonanceFrameSerializationError, match="reference_id"):
        ReferencePriceSnapshot.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source", "other-source"),
        ("session_id", "other-session"),
    ],
)
def test_reference_rejects_source_fact_tampering_with_retained_id(
    field_name: str, value: str
) -> None:
    payload = _reference_payload()
    payload["canonical_bar"][field_name] = value
    with pytest.raises(ResonanceFrameSerializationError, match="reference_id"):
        ReferencePriceSnapshot.from_dict(payload)


def test_reference_rejects_volume_tampering_with_retained_id() -> None:
    payload = _reference_payload()
    payload["canonical_bar"]["volume"] = "1.25"
    payload["canonical_bar"]["volume_type"] = VolumeType.TICK.value
    with pytest.raises(ResonanceFrameSerializationError, match="reference_id"):
        ReferencePriceSnapshot.from_dict(payload)


def test_reference_nested_payload_is_strict_and_normal_identity_is_unchanged() -> None:
    reference = _frame().reference_price
    assert reference.reference_id == _reference_id(
        reference.canonical_bar.to_dict(), schema_version=reference.schema_version
    )
    payload = reference.to_dict()
    payload["canonical_bar"]["future"] = True
    with pytest.raises(ResonanceFrameSerializationError, match="CanonicalBar fields"):
        ReferencePriceSnapshot.from_dict(payload)


def test_reference_requires_a_complete_bar() -> None:
    reference = _frame().reference_price
    incomplete = replace(reference.canonical_bar, is_complete=False)
    forged_id = _reference_id(
        incomplete.to_dict(), schema_version=reference.schema_version
    )
    with pytest.raises(ResonanceFrameEngineError, match="complete"):
        ReferencePriceSnapshot(forged_id, incomplete)


def test_frame_rejects_reference_symbol_and_future_availability() -> None:
    frame = _frame()
    other_symbol_bar = replace(frame.reference_price.canonical_bar, symbol="OTHER")
    other_symbol = ReferencePriceSnapshot(
        _reference_id(other_symbol_bar.to_dict(), schema_version=1),
        other_symbol_bar,
    )
    with pytest.raises(ResonanceFrameEngineError, match="reference price"):
        replace(frame, reference_price=other_symbol)

    other_timeframe_bar = replace(
        frame.reference_price.canonical_bar,
        timeframe=Timeframe.M30,
        end_time=frame.reference_price.bar_timestamp + timedelta(minutes=30),
    )
    other_timeframe = ReferencePriceSnapshot(
        _reference_id(other_timeframe_bar.to_dict(), schema_version=1),
        other_timeframe_bar,
    )
    with pytest.raises(ResonanceFrameEngineError, match="reference price"):
        replace(frame, reference_price=other_timeframe)

    future_bar = replace(
        frame.reference_price.canonical_bar,
        available_time=frame.as_of_time + timedelta(microseconds=1),
    )
    future_reference = ReferencePriceSnapshot(
        _reference_id(future_bar.to_dict(), schema_version=1), future_bar
    )
    with pytest.raises(ResonanceFrameEngineError, match="reference price"):
        replace(frame, reference_price=future_reference)


@pytest.mark.parametrize(
    ("field_name", "value_factory"),
    [
        (
            "origin_time",
            lambda state: (state.origin_time - timedelta(microseconds=1)).isoformat(),
        ),
        (
            "confirm_time",
            lambda state: (state.confirm_time - timedelta(microseconds=1)).isoformat(),
        ),
        (
            "direction",
            lambda state: (
                Direction.DOWN if state.direction is not Direction.DOWN else Direction.UP
            ).value,
        ),
        ("state_id", lambda state: f"{state.state_id}-tampered"),
    ],
)
def test_context_state_rejects_nested_state_tampering_with_retained_identity(
    field_name: str, value_factory
) -> None:
    context_state = _frame().context_states[0]
    payload = context_state.to_dict()
    payload["state"][field_name] = value_factory(context_state.state)
    with pytest.raises(ResonanceFrameSerializationError):
        ResonanceContextState.from_dict(payload)


@pytest.mark.parametrize("conflict", ["timeframe", "scale", "symbol"])
def test_context_state_context_or_symbol_conflicts_fail_closed(conflict: str) -> None:
    frame = _frame()
    payload = frame.to_dict()
    context_state = payload["context_states"][0]
    if conflict == "timeframe":
        context_state["context"]["timeframe"] = (
            "H4"
            if context_state["context"]["timeframe"] != "H4"
            else "H12"
        )
    elif conflict == "scale":
        context_state["context"]["scale"]["name"] = "other"
    else:
        context_state["state"]["symbol"] = "OTHER"
    with pytest.raises(ResonanceFrameSerializationError):
        ResonanceFrame.from_dict(payload)


def test_context_state_serialization_requires_complete_nested_state() -> None:
    payload = _frame().context_states[0].to_dict()
    payload["state"].pop("direction")
    with pytest.raises(ResonanceFrameSerializationError):
        ResonanceContextState.from_dict(payload)


def test_context_state_properties_are_authoritative_timeframe_state_views() -> None:
    context_state = _frame().context_states[0]
    assert context_state.timeframe_state_id == context_state.state.state_id
    assert context_state.direction is context_state.state.direction
    assert context_state.state_confirm_time == context_state.state.confirm_time
    assert context_state.state_origin_time == context_state.state.origin_time
    assert (
        context_state.state.as_of_time
        == context_state.timeframe_snapshot_as_of_time
    )


def test_frame_rejects_other_symbol_context_state_with_valid_context_identity() -> None:
    frame = _frame()
    context_state = frame.context_states[0]

    def other_symbol(boundary):
        return None if boundary is None else replace(boundary, symbol="OTHER")

    state = replace(
        context_state.state,
        symbol="OTHER",
        candidate_upper_boundary=other_symbol(
            context_state.state.candidate_upper_boundary
        ),
        candidate_lower_boundary=other_symbol(
            context_state.state.candidate_lower_boundary
        ),
        confirmed_upper_boundary=other_symbol(
            context_state.state.confirmed_upper_boundary
        ),
        confirmed_lower_boundary=other_symbol(
            context_state.state.confirmed_lower_boundary
        ),
    )
    context_state_id = _context_state_id(
        context=context_state.context.to_dict(),
        timeframe_snapshot_id=context_state.timeframe_snapshot_id,
        timeframe_snapshot_as_of_time=(
            context_state.timeframe_snapshot_as_of_time.isoformat()
        ),
        state=state.to_dict(),
        source_lifecycle_snapshot_id=context_state.source_lifecycle_snapshot_id,
        schema_version=context_state.schema_version,
    )
    changed = replace(
        context_state, context_state_id=context_state_id, state=state
    )
    with pytest.raises(ResonanceFrameEngineError, match="context state alignment"):
        replace(frame, context_states=(changed,) + frame.context_states[1:])


def test_frame_identity_binds_complete_context_state_identity() -> None:
    frame = _frame()
    context_state = frame.context_states[0]
    state = replace(
        context_state.state,
        forming_candidate_ids=context_state.state.forming_candidate_ids
        + ("identity-extension",),
    )
    context_state_id = _context_state_id(
        context=context_state.context.to_dict(),
        timeframe_snapshot_id=context_state.timeframe_snapshot_id,
        timeframe_snapshot_as_of_time=(
            context_state.timeframe_snapshot_as_of_time.isoformat()
        ),
        state=state.to_dict(),
        source_lifecycle_snapshot_id=context_state.source_lifecycle_snapshot_id,
        schema_version=context_state.schema_version,
    )
    changed = replace(
        context_state, context_state_id=context_state_id, state=state
    )
    states = (changed,) + frame.context_states[1:]
    with pytest.raises(ResonanceFrameEngineError, match="frame_id"):
        replace(frame, context_states=states)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("boundary", "object_id"), "not-a-lifecycle-boundary"),
        (("boundary", "provenance", "source_object_id"), "wrong-state"),
        (("boundary", "provenance", "parent_object_ids"), ["wrong-parent"]),
    ],
)
def test_evidence_rejects_non_authoritative_lifecycle_boundary(
    path: tuple[str, ...], value: object
) -> None:
    payload = _frame().evidence[0].to_dict()
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ResonanceFrameSerializationError, match="lifecycle mapping"):
        ResonanceEvidence.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_module", "other.module"),
        ("source_version", "other-version"),
        ("policy_id", "other-policy"),
        ("notes", ["engine_id=other-engine"]),
    ],
)
def test_evidence_provenance_must_match_frame_config(
    field_name: str, value: object
) -> None:
    payload = _frame().to_dict()
    payload["evidence"][0]["provenance"][field_name] = value
    with pytest.raises(ResonanceFrameSerializationError, match="provenance"):
        ResonanceFrame.from_dict(payload)


def test_frame_rejects_other_symbol_boundary_even_with_valid_evidence_identity() -> None:
    frame = _frame()
    evidence = frame.evidence[0]
    boundary = replace(evidence.boundary, symbol="OTHER")
    evidence_id = _evidence_id(
        subject_id=evidence.subject_id,
        lifecycle_state_id=evidence.lifecycle_state_id,
        lifecycle_event_id=evidence.lifecycle_event_id,
        boundary=boundary.to_dict(),
        tier=evidence.tier.value,
        context=evidence.context.to_dict(),
        direction=evidence.direction.value,
        lifecycle_state=evidence.lifecycle_state.value,
        structural_confirm_time=evidence.structural_confirm_time.isoformat(),
        state_confirm_time=evidence.state_confirm_time.isoformat(),
        touch_count=evidence.touch_count,
        source_types=tuple(item.value for item in evidence.source_types),
        structure_families=evidence.structure_families,
        schema_version=evidence.schema_version,
    )
    provenance = replace(evidence.provenance, source_object_id=evidence_id)
    forged = replace(
        evidence,
        evidence_id=evidence_id,
        boundary=boundary,
        provenance=provenance,
    )
    items = (forged,) + frame.evidence[1:]
    with pytest.raises(
        ResonanceFrameEngineError, match="context, direction, or causal time"
    ):
        replace(frame, evidence=items)


@pytest.mark.parametrize("exclusion", ["broken", "retired"])
def test_effective_evidence_cannot_overlap_exclusions(exclusion: str) -> None:
    frame = _frame()
    subject_id = frame.evidence[0].subject_id
    changes = (
        {"excluded_broken_subject_ids": (subject_id,)}
        if exclusion == "broken"
        else {"excluded_retired_subject_ids": (subject_id,)}
    )
    with pytest.raises(ResonanceFrameEngineError, match="disjoint"):
        replace(frame, **changes)


def test_broken_and_retired_exclusions_remain_disjoint() -> None:
    frame = _frame()
    with pytest.raises(ResonanceFrameEngineError, match="disjoint"):
        replace(
            frame,
            excluded_broken_subject_ids=("same-subject",),
            excluded_retired_subject_ids=("same-subject",),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("source_module", "other.module"),
        ("source_version", "other-version"),
        ("policy_id", "other-policy"),
        ("notes", ["engine_id=other-engine"]),
    ],
)
def test_frame_provenance_is_exact(field_name: str, value: object) -> None:
    payload = _frame().to_dict()
    payload["provenance"][field_name] = value
    with pytest.raises(ResonanceFrameSerializationError, match="provenance"):
        ResonanceFrame.from_dict(payload)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("assumptions", ["changed"]),
        ("warnings", ["changed"]),
        ("errors", ["changed"]),
    ],
)
def test_successful_frame_report_derived_fields_are_fixed(
    field_name: str, value: list[str]
) -> None:
    payload = _frame().to_dict()
    payload["report"][field_name] = value
    with pytest.raises(ResonanceFrameSerializationError, match="report"):
        ResonanceFrame.from_dict(payload)


def test_reference_age_is_exact_at_microsecond_precision() -> None:
    frame = assembler().build_as_of(frame_input(), T2 + timedelta(microseconds=123))
    assert frame.report.reference_price_age_seconds == Decimal("0.000123")


def test_reference_age_is_exact_across_long_time_spans() -> None:
    delta = timedelta(days=20_000, seconds=12_345, microseconds=678_901)
    frame = assembler().build_as_of(frame_input(), T2 + delta)
    actual_delta = frame.as_of_time - frame.reference_price.available_time
    expected_microseconds = (
        actual_delta.days * 86_400_000_000
        + actual_delta.seconds * 1_000_000
        + actual_delta.microseconds
    )
    assert frame.report.reference_price_age_seconds == (
        Decimal(expected_microseconds) / Decimal("1000000")
    )
