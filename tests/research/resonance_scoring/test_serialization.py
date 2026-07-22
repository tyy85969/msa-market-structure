from dataclasses import replace
from decimal import Decimal

import pytest

from msa.research.resonance import (
    ResonanceClassRationale,
    ResonanceContextWeight,
    ResonanceDependencyComponent,
    ResonanceEvidenceContribution,
    ResonanceScoreFrame,
    ResonanceScoreHistory,
    ResonanceScoreReport,
    ResonanceScoringEngineError,
    ResonanceScoringSerializationError,
    ResonanceZone,
    ResonanceZoneExplanation,
)
from msa.research.resonance.scoring_identity import (
    _score_frame_id,
    _zone_snapshot_id,
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


def _assert_zone_rejected(
    frame: ResonanceScoreFrame,
    zone_index: int,
    zone: ResonanceZone,
    *,
    match: str,
) -> None:
    zones = list(frame.zones)
    zones[zone_index] = zone
    with pytest.raises(ResonanceScoringEngineError, match=match):
        replace(frame, zones=tuple(zones))
    payload = frame.to_dict()
    payload["zones"][zone_index] = zone.to_dict()
    with pytest.raises(ResonanceScoringSerializationError, match=match):
        ResonanceScoreFrame.from_dict(payload)


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


def test_zone_source_frame_id_is_bound_to_authoritative_frame_with_old_ids() -> None:
    frame = score_frame()
    zone = replace(frame.zones[0], source_frame_id="forged-source-frame")
    _assert_zone_rejected(frame, 0, zone, match="source_frame_id")


def test_fully_recomputed_forged_zone_lineage_is_rejected() -> None:
    frame = score_frame()
    original = frame.zones[0]
    forged_source = "forged-source-frame"
    scores = {
        "dependency_adjusted_base_score": str(original.dependency_adjusted_base_score),
        "source_diversity_bonus": str(original.source_diversity_bonus),
        "context_diversity_bonus": str(original.context_diversity_bonus),
        "quality_score": str(original.quality_score),
        "reference_price": str(original.reference_price),
        "distance_factor": str(original.distance_factor),
        "placement_factor": str(original.placement_factor),
        "selection_score": str(original.selection_score),
    }
    forged_snapshot = _zone_snapshot_id(
        source_frame_id=forged_source,
        config=frame.config_snapshot.to_dict(),
        zone_key_id=original.zone_key_id,
        member_evidence_ids=original.member_evidence_ids,
        contribution_ids=tuple(item.contribution_id for item in original.contributions),
        dependency_component_ids=tuple(
            item.component_id for item in original.dependency_components
        ),
        scores=scores,
        price_relation=original.price_relation.value,
        distance=str(original.distance),
        resonance_class=original.resonance_class.value,
        schema_version=original.schema_version,
    )
    forged_explanation = replace(
        original.explanation,
        side_rank_key=replace(
            original.explanation.side_rank_key,
            zone_snapshot_id=forged_snapshot,
        ),
    )
    forged_zone_parents = tuple(
        sorted(
            {
                forged_source,
                *original.member_evidence_ids,
                *(item.contribution_id for item in original.contributions),
                *(item.component_id for item in original.dependency_components),
            }
        )
    )
    forged_zone = replace(
        original,
        source_frame_id=forged_source,
        zone_snapshot_id=forged_snapshot,
        explanation=forged_explanation,
        provenance=replace(
            original.provenance,
            source_object_id=forged_snapshot,
            parent_object_ids=forged_zone_parents,
        ),
    )
    zones = (forged_zone, *frame.zones[1:])
    forged_score_frame_id = _score_frame_id(
        source_frame_id=frame.source_frame_id,
        as_of_time=frame.as_of_time.isoformat(),
        config=frame.config_snapshot.to_dict(),
        zone_snapshot_ids=tuple(item.zone_snapshot_id for item in zones),
        report=frame.report.to_dict(),
        schema_version=frame.schema_version,
    )
    forged_score_provenance = replace(
        frame.provenance,
        source_object_id=forged_score_frame_id,
        parent_object_ids=tuple(
            sorted(
                {
                    frame.source_frame_id,
                    *(item.zone_snapshot_id for item in zones),
                }
            )
        ),
    )
    with pytest.raises(ResonanceScoringEngineError, match="source_frame_id"):
        replace(
            frame,
            score_frame_id=forged_score_frame_id,
            zones=zones,
            provenance=forged_score_provenance,
        )
    payload = frame.to_dict()
    payload["zones"] = [item.to_dict() for item in zones]
    payload["score_frame_id"] = forged_score_frame_id
    payload["provenance"] = forged_score_provenance.to_dict()
    with pytest.raises(ResonanceScoringSerializationError, match="source_frame_id"):
        ResonanceScoreFrame.from_dict(payload)


def test_explanation_context_weight_is_bound_to_config() -> None:
    frame = score_frame()
    zone = frame.zones[0]
    weight = zone.explanation.context_weights[0]
    explanation = replace(
        zone.explanation,
        context_weights=(replace(weight, weight=weight.weight + Decimal("1")),),
    )
    _assert_zone_rejected(
        frame,
        0,
        replace(zone, explanation=explanation),
        match="context weights",
    )


def test_explanation_member_contexts_are_bound_to_member_evidence() -> None:
    frame = score_frame()
    zone = frame.zones[0]
    alternate = next(
        item
        for item in frame.config_snapshot.context_weights
        if item.context not in zone.contexts
    )
    explanation = replace(
        zone.explanation,
        member_contexts=(alternate.context,),
        context_weights=(
            ResonanceContextWeight(alternate.context, alternate.weight),
        ),
    )
    _assert_zone_rejected(
        frame,
        0,
        replace(zone, explanation=explanation),
        match="contexts",
    )


def test_explanation_dependency_repeat_credit_is_bound_to_config() -> None:
    frame = score_frame()
    zone = frame.zones[0]
    explanation = replace(
        zone.explanation,
        dependency_repeat_credit=Decimal("0.5"),
    )
    _assert_zone_rejected(
        frame,
        0,
        replace(zone, explanation=explanation),
        match="repeat credit",
    )


def test_explanation_rationale_evidence_count_is_authoritative() -> None:
    frame = score_frame()
    zone = frame.zones[0]
    rationale = replace(
        zone.explanation.resonance_class_rationale,
        evidence_count=3,
    )
    explanation = replace(zone.explanation, resonance_class_rationale=rationale)
    _assert_zone_rejected(
        frame,
        0,
        replace(zone, explanation=explanation),
        match="rationale",
    )


def test_explanation_rationale_context_count_is_authoritative() -> None:
    frame = score_frame()
    zone = frame.zones[1]
    rationale = replace(
        zone.explanation.resonance_class_rationale,
        distinct_context_count=2,
    )
    explanation = replace(zone.explanation, resonance_class_rationale=rationale)
    _assert_zone_rejected(
        frame,
        1,
        replace(zone, explanation=explanation),
        match="rationale",
    )


def test_explanation_rationale_thresholds_are_bound_to_config() -> None:
    frame = score_frame()
    zone = frame.zones[0]
    rationale = ResonanceClassRationale(
        evidence_count=2,
        distinct_context_count=1,
        minimum_resonant_evidence_count=3,
        minimum_resonant_context_count=3,
        assigned_class=zone.resonance_class,
    )
    explanation = replace(zone.explanation, resonance_class_rationale=rationale)
    _assert_zone_rejected(
        frame,
        0,
        replace(zone, explanation=explanation),
        match="rationale",
    )


@pytest.mark.parametrize(
    ("index", "field_name"),
    [
        (0, "contribution_id"),
        (0, "dependency_component_id"),
        (1, "component_id"),
        (3, "zone_key_id"),
        (3, "zone_snapshot_id"),
        (5, "score_frame_id"),
    ],
)
@pytest.mark.parametrize("invalid", [1, [], None], ids=["int", "list", "none"])
def test_non_string_identities_fail_closed(
    index: int,
    field_name: str,
    invalid: object,
) -> None:
    value = public_values()[index]
    with pytest.raises(ResonanceScoringEngineError, match="canonical SHA-256"):
        replace(value, **{field_name: invalid})
    payload = value.to_dict()
    payload[field_name] = invalid
    with pytest.raises(ResonanceScoringSerializationError, match="canonical SHA-256"):
        type(value).from_dict(payload)
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
