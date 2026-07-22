"""Pure C-007C eligibility, ordering, and hysteresis functions."""

from __future__ import annotations

from decimal import Decimal

from msa.domain import BoundarySide, ProvenanceRef
from msa.research.resonance import ResonancePriceRelation, ResonanceScoreFrame, ResonanceZone

from .contracts import (
    SCHEMA_VERSION,
    ActiveBoxSelectionConfig,
    ActiveBoxSelectionKey,
    ActiveBoxSideAction,
    ActiveBoxSideDecision,
    ZoneEligibility,
    ZoneEligibilityReason,
)
from .errors import ActiveBoxInputError
from .identity import semantic_id


_MODULE = "msa.research.active_box.policy"


def evaluate_zone(zone: ResonanceZone, config: ActiveBoxSelectionConfig) -> ZoneEligibility:
    if not isinstance(zone, ResonanceZone):
        raise ActiveBoxInputError("zone must be a ResonanceZone")
    if not isinstance(config, ActiveBoxSelectionConfig):
        raise ActiveBoxInputError("config must be an ActiveBoxSelectionConfig")
    reasons: list[ZoneEligibilityReason] = []
    if zone.price_relation is not ResonancePriceRelation.EXPECTED_SIDE:
        reasons.append(ZoneEligibilityReason.PRICE_RELATION_NOT_EXPECTED)
    if zone.resonance_class not in config.allowed_resonance_classes:
        reasons.append(ZoneEligibilityReason.RESONANCE_CLASS_NOT_ALLOWED)
    if zone.quality_score < config.minimum_quality_score:
        reasons.append(ZoneEligibilityReason.QUALITY_BELOW_MINIMUM)
    if zone.selection_score < config.minimum_selection_score:
        reasons.append(ZoneEligibilityReason.SELECTION_BELOW_MINIMUM)
    if zone.distance_factor <= 0:
        reasons.append(ZoneEligibilityReason.DISTANCE_FACTOR_NOT_POSITIVE)
    return ZoneEligibility(
        zone_key_id=zone.zone_key_id, zone_snapshot_id=zone.zone_snapshot_id,
        side=zone.side, resonance_class=zone.resonance_class,
        price_relation=zone.price_relation, quality_score=zone.quality_score,
        selection_score=zone.selection_score, distance=zone.distance,
        distance_factor=zone.distance_factor, side_rank=zone.side_rank,
        eligible=not reasons, reasons=tuple(reasons),
    )


def selection_key(zone: ResonanceZone) -> ActiveBoxSelectionKey:
    if not isinstance(zone, ResonanceZone):
        raise ActiveBoxInputError("zone must be a ResonanceZone")
    return ActiveBoxSelectionKey(
        distance=zone.distance, selection_score=zone.selection_score,
        quality_score=zone.quality_score,
        distinct_context_count=zone.distinct_context_count,
        distinct_source_type_count=zone.distinct_source_type_count,
        latest_evidence_confirm_time=zone.latest_evidence_confirm_time,
        zone_key_id=zone.zone_key_id, zone_snapshot_id=zone.zone_snapshot_id,
    )


def _side_zones(frame: ResonanceScoreFrame, side: BoundarySide) -> tuple[ResonanceZone, ...]:
    return frame.lower_zones if side is BoundarySide.LOWER else frame.upper_zones


def build_side_decision(
    source_score_frame: ResonanceScoreFrame,
    config: ActiveBoxSelectionConfig,
    side: BoundarySide,
    current_zone_key_id: str | None = None,
) -> ActiveBoxSideDecision:
    if not isinstance(source_score_frame, ResonanceScoreFrame):
        raise ActiveBoxInputError("source_score_frame must be a ResonanceScoreFrame")
    if not isinstance(config, ActiveBoxSelectionConfig) or not isinstance(side, BoundarySide):
        raise ActiveBoxInputError("config/side type is invalid")
    if config.symbol != source_score_frame.source_frame.config_snapshot.symbol:
        raise ActiveBoxInputError("config symbol conflicts with source ScoreFrame")
    if current_zone_key_id is not None and (not isinstance(current_zone_key_id, str) or not current_zone_key_id.strip()):
        raise ActiveBoxInputError("current_zone_key_id must be None or non-empty text")
    zones = _side_zones(source_score_frame, side)
    evaluations_by_key = {zone.zone_key_id: evaluate_zone(zone, config) for zone in zones}
    if len(evaluations_by_key) != len(zones):
        raise ActiveBoxInputError("side zones must have unique stable zone_key IDs")
    zones_by_key = {zone.zone_key_id: zone for zone in zones}
    evaluations = tuple(evaluations_by_key[key] for key in sorted(evaluations_by_key))
    eligible_zones = tuple(sorted(
        (zone for zone in zones if evaluations_by_key[zone.zone_key_id].eligible),
        key=lambda zone: selection_key(zone).sort_key,
    ))
    eligible_ids = tuple(zone.zone_key_id for zone in eligible_zones)
    current = zones_by_key.get(current_zone_key_id) if current_zone_key_id is not None else None
    current_eligible = current is not None and evaluations_by_key[current.zone_key_id].eligible
    challenger = next((zone for zone in eligible_zones if zone.zone_key_id != current_zone_key_id), None)
    margin = config.effective_distance_margin(source_score_frame.source_frame.reference_price.price)
    action: ActiveBoxSideAction
    selected: ResonanceZone | None
    distance_gain: Decimal | None = None
    selection_gain: Decimal | None = None
    if current_zone_key_id is None:
        action = ActiveBoxSideAction.SELECT if eligible_zones else ActiveBoxSideAction.NONE
        selected = eligible_zones[0] if eligible_zones else None
    elif not current_eligible:
        action = ActiveBoxSideAction.REPLACE if eligible_zones else ActiveBoxSideAction.CLEAR
        selected = eligible_zones[0] if eligible_zones else None
    elif challenger is None or eligible_zones[0].zone_key_id == current_zone_key_id:
        action, selected = ActiveBoxSideAction.RETAIN, current
    else:
        distance_gain = current.distance - challenger.distance
        selection_gain = challenger.selection_score - current.selection_score
        replace = distance_gain > margin or (
            distance_gain >= 0
            and selection_gain > config.minimum_replacement_selection_score_improvement
        )
        action = ActiveBoxSideAction.REPLACE if replace else ActiveBoxSideAction.RETAIN
        selected = challenger if replace else current
    current_snapshot_id = None if current is None else current.zone_snapshot_id
    selected_snapshot_id = None if selected is None else selected.zone_snapshot_id
    payload = {
        "source_score_frame_id": source_score_frame.score_frame_id,
        "as_of_time": source_score_frame.as_of_time.isoformat(), "side": side.value,
        "action": action.value, "current_zone_key_id": current_zone_key_id,
        "current_zone_snapshot_id": current_snapshot_id,
        "selected_zone_key_id": None if selected is None else selected.zone_key_id,
        "selected_zone_snapshot_id": selected_snapshot_id,
        "zone_evaluations": [item.to_dict() for item in evaluations],
        "eligible_zone_key_ids_in_order": list(eligible_ids),
        "challenger_zone_key_id": None if challenger is None else challenger.zone_key_id,
        "effective_distance_margin": str(margin),
        "required_selection_score_improvement": str(config.minimum_replacement_selection_score_improvement),
        "distance_gain": None if distance_gain is None else str(distance_gain),
        "selection_gain": None if selection_gain is None else str(selection_gain),
        "schema_version": SCHEMA_VERSION,
    }
    decision_id = semantic_id("active-box-decision-v1-", payload)
    provenance = ProvenanceRef(
        source_module=_MODULE, source_version=config.engine_version,
        source_object_id=decision_id, policy_id=config.policy_id,
        parent_object_ids=(source_score_frame.score_frame_id,),
        notes=(f"engine_id={config.engine_id}",),
    )
    return ActiveBoxSideDecision(
        decision_id=decision_id, source_score_frame_id=source_score_frame.score_frame_id,
        as_of_time=source_score_frame.as_of_time, side=side, action=action,
        current_zone_key_id=current_zone_key_id, current_zone_snapshot_id=current_snapshot_id,
        selected_zone_key_id=None if selected is None else selected.zone_key_id,
        selected_zone_snapshot_id=selected_snapshot_id, zone_evaluations=evaluations,
        eligible_zone_key_ids_in_order=eligible_ids,
        challenger_zone_key_id=None if challenger is None else challenger.zone_key_id,
        effective_distance_margin=margin,
        required_selection_score_improvement=config.minimum_replacement_selection_score_improvement,
        distance_gain=distance_gain, selection_gain=selection_gain, provenance=provenance,
    )


def validate_side_decision(
    source_score_frame: ResonanceScoreFrame,
    config: ActiveBoxSelectionConfig,
    decision: ActiveBoxSideDecision,
) -> None:
    if not isinstance(source_score_frame, ResonanceScoreFrame):
        raise ActiveBoxInputError("source_score_frame must be a ResonanceScoreFrame")
    if not isinstance(config, ActiveBoxSelectionConfig):
        raise ActiveBoxInputError("config must be an ActiveBoxSelectionConfig")
    if not isinstance(decision, ActiveBoxSideDecision):
        raise ActiveBoxInputError("decision must be an ActiveBoxSideDecision")
    expected = build_side_decision(
        source_score_frame, config, decision.side, decision.current_zone_key_id
    )
    if decision != expected:
        raise ActiveBoxInputError("SideDecision is not the exact recomputable policy result")
