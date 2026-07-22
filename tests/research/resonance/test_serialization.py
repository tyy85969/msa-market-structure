from dataclasses import replace

import pytest

from msa.research.resonance import (
    ReferencePriceSnapshot,
    ResonanceContext,
    ResonanceContextState,
    ResonanceEvidence,
    ResonanceFrame,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceFrameReport,
    ResonanceFrameSerializationError,
)

from .fixtures import H4_PRIMARY, T1, assembler, frame_input


def public_objects():
    value = frame_input()
    history = assembler().build_batch(value)
    frame = assembler().build_as_of(value, T1)
    return (
        H4_PRIMARY,
        frame.reference_price,
        frame.context_states[0],
        frame.evidence[0],
        frame.report,
        frame,
        history,
        value,
    )


@pytest.mark.parametrize(
    ("object_type", "index"),
    [
        (ResonanceContext, 0),
        (ReferencePriceSnapshot, 1),
        (ResonanceContextState, 2),
        (ResonanceEvidence, 3),
        (ResonanceFrameReport, 4),
        (ResonanceFrame, 5),
        (ResonanceFrameHistory, 6),
        (ResonanceFrameInput, 7),
    ],
)
def test_public_objects_round_trip_exactly(object_type, index: int) -> None:
    value = public_objects()[index]
    payload = value.to_dict()
    restored = object_type.from_dict(payload)
    assert restored == value
    assert restored.to_dict() == payload


def test_unknown_nested_field_fails_closed() -> None:
    payload = assembler().build_batch(frame_input()).to_dict()
    payload["final_frame"]["evidence"][0]["boundary"]["future"] = True
    with pytest.raises(ResonanceFrameSerializationError):
        ResonanceFrameHistory.from_dict(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("reference_price", "price"), 101.0),
        (("report", "reference_price_age_seconds"), 0),
    ],
)
def test_decimal_serialization_requires_strings(path, value) -> None:
    payload = assembler().build_as_of(frame_input(), T1).to_dict()
    payload[path[0]][path[1]] = value
    with pytest.raises(ResonanceFrameSerializationError, match="Decimal string"):
        ResonanceFrame.from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    ["context_states", "evidence", "excluded_broken_subject_ids"],
)
def test_frame_tuple_fields_require_ordered_lists(field_name: str) -> None:
    payload = assembler().build_as_of(frame_input(), T1).to_dict()
    payload[field_name] = tuple(payload[field_name])
    with pytest.raises(ResonanceFrameSerializationError, match="ordered list"):
        ResonanceFrame.from_dict(payload)


def test_tampered_evidence_id_fails_closed() -> None:
    payload = assembler().build_as_of(frame_input(), T1).evidence[0].to_dict()
    payload["evidence_id"] = "resonance-evidence-v1-" + "b" * 64
    payload["provenance"]["source_object_id"] = payload["evidence_id"]
    with pytest.raises(ResonanceFrameSerializationError, match="evidence_id"):
        ResonanceEvidence.from_dict(payload)


def test_tampered_frame_id_report_and_provenance_fail_closed() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    payload = frame.to_dict()
    payload["frame_id"] = "resonance-frame-v1-" + "c" * 64
    payload["provenance"]["source_object_id"] = payload["frame_id"]
    with pytest.raises(ResonanceFrameSerializationError, match="frame_id"):
        ResonanceFrame.from_dict(payload)
    payload = frame.to_dict()
    payload["report"]["candidate_evidence_count"] += 1
    with pytest.raises(ResonanceFrameSerializationError, match="report"):
        ResonanceFrame.from_dict(payload)
    payload = frame.to_dict()
    payload["provenance"]["parent_object_ids"].append("extra")
    with pytest.raises(ResonanceFrameSerializationError, match="provenance"):
        ResonanceFrame.from_dict(payload)


def test_tier_and_lifecycle_conflict_fails_closed() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    payload = next(
        item for item in frame.evidence if item.subject_id == "upper-a-old"
    ).to_dict()
    payload["tier"] = "CANDIDATE"
    with pytest.raises(ResonanceFrameSerializationError, match="tier"):
        ResonanceEvidence.from_dict(payload)


def test_direct_frame_rejects_context_coverage_change() -> None:
    frame = assembler().build_as_of(frame_input(), T1)
    with pytest.raises(Exception, match="context_states"):
        replace(frame, context_states=frame.context_states[:1])


def test_repeated_round_trip_serialization_is_stable() -> None:
    payload = assembler().build_batch(frame_input()).to_dict()
    restored = ResonanceFrameHistory.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.to_dict() == restored.to_dict()
