from dataclasses import replace

import pytest

from msa.research.resonance import (
    ResonanceDependencyComponent,
    ResonanceEvidenceContribution,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceScoreReport,
    ResonanceScoringSerializationError,
    ResonanceZone,
    ResonanceZoneExplanation,
)

from .fixtures import score_frame, scorer, source_history


def public_values():
    frame = score_frame()
    zone = frame.zones[0]
    return (
        zone.contributions[0],
        zone.dependency_components[0],
        zone.explanation,
        zone,
        frame.report,
        frame,
        scorer().build_batch(source_history()),
    )


@pytest.mark.parametrize(
    ("object_type", "index"),
    [
        (ResonanceEvidenceContribution, 0),
        (ResonanceDependencyComponent, 1),
        (ResonanceZoneExplanation, 2),
        (ResonanceZone, 3),
        (ResonanceScoreReport, 4),
        (ResonanceScoreFrame, 5),
        (ResonanceScoreHistory, 6),
    ],
)
def test_public_objects_round_trip_exactly(object_type, index: int) -> None:
    value = public_values()[index]
    payload = value.to_dict()
    restored = object_type.from_dict(payload)
    assert restored == value
    assert restored.to_dict() == payload


@pytest.mark.parametrize("index", range(7))
def test_unknown_fields_and_schema_fail_closed(index: int) -> None:
    value = public_values()[index]
    payload = value.to_dict()
    payload["future"] = True
    with pytest.raises(ResonanceScoringSerializationError):
        type(value).from_dict(payload)
    payload = value.to_dict()
    payload["schema_version"] = 2
    with pytest.raises(ResonanceScoringSerializationError):
        type(value).from_dict(payload)


def test_nested_unknown_field_and_tuple_contract_fail_closed() -> None:
    payload = score_frame().to_dict()
    payload["zones"][0]["contributions"][0]["future"] = True
    with pytest.raises(ResonanceScoringSerializationError):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["zones"] = tuple(payload["zones"])
    with pytest.raises(ResonanceScoringSerializationError, match="ordered list"):
        ResonanceScoreFrame.from_dict(payload)


def test_decimal_serialization_requires_strings() -> None:
    payload = score_frame().to_dict()
    payload["zones"][0]["quality_score"] = 1.0
    with pytest.raises(ResonanceScoringSerializationError, match="Decimal string"):
        ResonanceScoreFrame.from_dict(payload)


def test_contribution_component_and_explanation_tampering_are_rejected() -> None:
    payload = score_frame().to_dict()
    payload["zones"][0]["contributions"][0]["raw_contribution"] = "999"
    with pytest.raises(ResonanceScoringSerializationError, match="raw_contribution"):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["zones"][0]["dependency_components"][0]["adjusted_component_score"] = "999"
    with pytest.raises(ResonanceScoringSerializationError, match="component"):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["zones"][0]["explanation"]["quality_score"] = "999"
    with pytest.raises(ResonanceScoringSerializationError, match="explanation"):
        ResonanceScoreFrame.from_dict(payload)


def test_zone_and_score_frame_identity_tampering_are_rejected() -> None:
    payload = score_frame().to_dict()
    payload["zones"][0]["zone_key_id"] = "resonance-zone-key-v1-" + "a" * 64
    payload["zones"][0]["explanation"]["side_rank_key"]["zone_key_id"] = payload["zones"][0]["zone_key_id"]
    with pytest.raises(ResonanceScoringSerializationError, match="zone_key_id"):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["score_frame_id"] = "resonance-score-frame-v1-" + "b" * 64
    payload["provenance"]["source_object_id"] = payload["score_frame_id"]
    with pytest.raises(ResonanceScoringSerializationError, match="score_frame_id"):
        ResonanceScoreFrame.from_dict(payload)


def test_provenance_report_and_rank_conflicts_are_rejected() -> None:
    payload = score_frame().to_dict()
    payload["provenance"]["parent_object_ids"].append("extra")
    with pytest.raises(ResonanceScoringSerializationError, match="provenance"):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["report"]["zone_count"] += 1
    with pytest.raises(ResonanceScoringSerializationError, match="report"):
        ResonanceScoreFrame.from_dict(payload)
    payload = score_frame().to_dict()
    payload["zones"][0]["side_rank"] = 99
    with pytest.raises(ResonanceScoringSerializationError, match="side_rank"):
        ResonanceScoreFrame.from_dict(payload)


def test_repeated_serialization_is_stable() -> None:
    payload = scorer().build_batch(source_history()).to_dict()
    restored = ResonanceScoreHistory.from_dict(payload)
    assert restored.to_dict() == payload
    assert restored.to_dict() == restored.to_dict()
